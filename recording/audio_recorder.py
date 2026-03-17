"""System audio recorder using PulseAudio (Linux) / sounddevice."""

import asyncio
import threading
import wave
from pathlib import Path
from datetime import datetime

import numpy as np
import sounddevice as sd
import soundfile as sf
from loguru import logger


class AudioRecorder:
    """
    Records system audio (loopback / monitor source) to a WAV file.

    On Linux with PulseAudio this captures the monitor of the default sink,
    which includes all desktop audio — including meeting audio played through
    the speakers.

    Usage:
        recorder = AudioRecorder(output_path)
        recorder.start()
        # ... meeting in progress ...
        recorder.stop()
        path = recorder.output_path  # Path to the saved WAV
    """

    SAMPLE_RATE = 16_000   # Whisper expects 16 kHz
    CHANNELS = 1           # Mono is fine for transcription
    CHUNK_SIZE = 1024
    DTYPE = "int16"

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._thread: threading.Thread | None = None
        self._stream: sd.InputStream | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin capturing audio in a background thread."""
        if self._recording:
            logger.warning("AudioRecorder already running")
            return

        device_index = self._find_monitor_device()
        self._frames = []
        self._recording = True

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype=self.DTYPE,
            blocksize=self.CHUNK_SIZE,
            device=device_index,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info(
            f"[AudioRecorder] Started recording → {self.output_path} "
            f"(device={device_index})"
        )

    def stop(self) -> Path:
        """Stop recording and flush audio to disk. Returns path to WAV file."""
        if not self._recording:
            logger.warning("AudioRecorder was not running")
            return self.output_path

        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()

        self._save_wav()
        logger.info(f"[AudioRecorder] Saved {len(self._frames)} chunks → {self.output_path}")
        return self.output_path

    # ── Internals ─────────────────────────────────────────────────────────────

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time,
        status,
    ) -> None:
        if status:
            logger.debug(f"[AudioRecorder] Stream status: {status}")
        if self._recording:
            self._frames.append(indata.copy())

    def _save_wav(self) -> None:
        if not self._frames:
            logger.warning("[AudioRecorder] No audio captured — empty recording")
            self.output_path.touch()
            return

        audio_data = np.concatenate(self._frames, axis=0)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(
            str(self.output_path),
            audio_data,
            samplerate=self.SAMPLE_RATE,
            subtype="PCM_16",
        )

    @staticmethod
    def _find_monitor_device() -> int | None:
        """
        Find the PulseAudio monitor (loopback) input device.
        Returns device index or None to use default input.
        """
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                name = dev.get("name", "").lower()
                if "monitor" in name and dev.get("max_input_channels", 0) > 0:
                    logger.info(f"[AudioRecorder] Using monitor device [{i}]: {dev['name']}")
                    return i
        except Exception as exc:
            logger.warning(f"[AudioRecorder] Device probe failed: {exc}")
        logger.info("[AudioRecorder] Falling back to default input device")
        return None
