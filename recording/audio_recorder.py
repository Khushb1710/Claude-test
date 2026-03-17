"""
System audio recorder with multiple backend support.

Backend priority:
  1. sounddevice  — requires libportaudio2 (best quality, cross-platform)
  2. ffmpeg       — requires ffmpeg binary with PulseAudio support
  3. arecord      — ALSA-based (Linux only)

The first available backend is used automatically.
"""

import subprocess
import threading
from pathlib import Path

from loguru import logger

SAMPLE_RATE = 16_000
CHANNELS = 1


class AudioRecorder:
    """
    Records system audio to a WAV file.

    Usage:
        recorder = AudioRecorder(output_path)
        recorder.start()
        # ... meeting in progress ...
        recorder.stop()
    """

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self._backend: str | None = None
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._frames = []
        self._stream = None
        self._recording = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._backend = self._detect_backend()
        logger.info(f"[AudioRecorder] Using backend: {self._backend}")

        if self._backend == "sounddevice":
            self._start_sounddevice()
        elif self._backend == "ffmpeg":
            self._start_ffmpeg()
        elif self._backend == "arecord":
            self._start_arecord()
        else:
            logger.warning("[AudioRecorder] No audio backend available — recording skipped")

        self._recording = True

    def stop(self) -> Path:
        self._recording = False
        if self._backend == "sounddevice":
            self._stop_sounddevice()
        elif self._backend in ("ffmpeg", "arecord"):
            self._stop_subprocess()
        logger.info(f"[AudioRecorder] Recording saved → {self.output_path}")
        return self.output_path

    # ── Backend detection ─────────────────────────────────────────────────────

    @staticmethod
    def _detect_backend() -> str | None:
        # 1. sounddevice (needs libportaudio2 at runtime)
        try:
            import sounddevice as sd
            sd.query_devices()  # will throw if PortAudio not found
            return "sounddevice"
        except Exception:
            pass

        # 2. ffmpeg with PulseAudio
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return "ffmpeg"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 3. arecord (ALSA)
        try:
            result = subprocess.run(
                ["arecord", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return "arecord"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None

    # ── sounddevice backend ───────────────────────────────────────────────────

    def _start_sounddevice(self) -> None:
        import sounddevice as sd
        import numpy as np

        device_index = self._find_monitor_device()
        self._frames = []

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=1024,
            device=device_index,
            callback=self._sd_callback,
        )
        self._stream.start()

    def _sd_callback(self, indata, frames, time, status) -> None:
        if status:
            logger.debug(f"[AudioRecorder] {status}")
        if self._recording:
            self._frames.append(indata.copy())

    def _stop_sounddevice(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        if self._frames:
            import numpy as np
            import soundfile as sf
            audio = np.concatenate(self._frames, axis=0)
            sf.write(str(self.output_path), audio, samplerate=SAMPLE_RATE, subtype="PCM_16")
        else:
            logger.warning("[AudioRecorder] No audio frames captured")
            self.output_path.touch()

    @staticmethod
    def _find_monitor_device():
        try:
            import sounddevice as sd
            for i, dev in enumerate(sd.query_devices()):
                if "monitor" in dev.get("name", "").lower() and dev.get("max_input_channels", 0) > 0:
                    return i
        except Exception:
            pass
        return None

    # ── ffmpeg backend ────────────────────────────────────────────────────────

    def _start_ffmpeg(self) -> None:
        cmd = [
            "ffmpeg", "-y",
            "-f", "pulse",          # PulseAudio input
            "-i", "default.monitor",  # system audio monitor
            "-ar", str(SAMPLE_RATE),
            "-ac", str(CHANNELS),
            "-acodec", "pcm_s16le",
            str(self.output_path),
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug(f"[AudioRecorder] ffmpeg PID: {self._proc.pid}")

    def _stop_subprocess(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.write(b"q")
            self._proc.stdin.flush()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.terminate()

    # ── arecord backend ───────────────────────────────────────────────────────

    def _start_arecord(self) -> None:
        cmd = [
            "arecord",
            "-f", "S16_LE",
            "-r", str(SAMPLE_RATE),
            "-c", str(CHANNELS),
            "-D", "default",
            str(self.output_path),
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug(f"[AudioRecorder] arecord PID: {self._proc.pid}")
