"""
Transcription using OpenAI Whisper.

Supports two modes:
  - "api"   : sends the audio file to the OpenAI Whisper API (cloud, fast, no GPU needed)
  - anything else: loads the model locally via the `openai-whisper` package
                   (e.g. WHISPER_MODEL=base, small, medium, large)
"""

from pathlib import Path

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models import Meeting, Transcript


class WhisperTranscriber:

    def __init__(self):
        self._local_model = None  # lazy-loaded

    # ── Public ────────────────────────────────────────────────────────────────

    def transcribe(self, audio_path: Path, meeting: Meeting) -> Transcript:
        """Transcribe *audio_path* and return a Transcript object."""
        logger.info(f"[Whisper] Transcribing {audio_path} ({audio_path.stat().st_size // 1024} KB)")

        if settings.whisper_model.lower() == "api":
            segments = self._transcribe_via_api(audio_path)
        else:
            segments = self._transcribe_locally(audio_path)

        full_text = " ".join(s["text"].strip() for s in segments)
        logger.info(f"[Whisper] Done — {len(segments)} segments, {len(full_text)} chars")

        return Transcript(
            meeting=meeting,
            segments=segments,
            full_text=full_text,
        )

    # ── API mode ──────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _transcribe_via_api(self, audio_path: Path) -> list[dict]:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        for seg in (response.segments or []):
            segments.append(
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "speaker": "",  # Whisper API doesn't do diarization natively
                }
            )
        return segments

    # ── Local model mode ──────────────────────────────────────────────────────

    def _transcribe_locally(self, audio_path: Path) -> list[dict]:
        model = self._get_local_model()
        result = model.transcribe(str(audio_path), fp16=False, verbose=False)

        segments = []
        for seg in result.get("segments", []):
            segments.append(
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"],
                    "speaker": "",
                }
            )
        return segments

    def _get_local_model(self):
        if self._local_model is None:
            try:
                import whisper  # openai-whisper package
            except ImportError:
                raise ImportError(
                    "The 'openai-whisper' package is required for local transcription. "
                    "Install it with: pip install openai-whisper\n"
                    "Or set WHISPER_MODEL=api to use the OpenAI API instead."
                )
            logger.info(f"[Whisper] Loading local model: {settings.whisper_model}")
            self._local_model = whisper.load_model(settings.whisper_model)
        return self._local_model
