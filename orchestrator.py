"""
Meeting orchestrator — ties together the bot, recorder, transcriber, and output.

For a given Meeting it will:
  1. Join the meeting via the appropriate platform bot
  2. Record system audio for the duration
  3. Leave once the meeting ends (or the scheduled end time passes)
  4. Transcribe the recording with Whisper
  5. Summarize with Claude
  6. Save notes to Google Docs
  7. Email notes to attendees
  8. Persist raw files (audio, transcript, notes) to DATA_DIR
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger

from config import settings
from models import Meeting, Transcript, MeetingNotes
from bot import get_bot
from recording import AudioRecorder
from transcription import WhisperTranscriber
from ai import MeetingSummarizer
from output import save_to_google_docs, send_meeting_notes


# Singletons (shared across meetings)
_transcriber = WhisperTranscriber()
_summarizer = MeetingSummarizer()

# Poll interval while waiting for meeting to end
_POLL_SECONDS = 15
# Maximum time to wait past scheduled end before force-leaving
_MAX_OVERTIME_MINUTES = 30


async def run_meeting(meeting: Meeting) -> MeetingNotes | None:
    """
    Full pipeline for a single meeting.
    Returns the MeetingNotes or None if the meeting could not be processed.
    """
    logger.info(f"[Orchestrator] Starting pipeline for: {meeting.title}")

    # Prepare paths
    safe_title = _safe_filename(meeting.title)
    ts = meeting.start_time.strftime("%Y%m%d_%H%M")
    base_dir = settings.data_dir / f"{ts}_{safe_title}"
    base_dir.mkdir(parents=True, exist_ok=True)
    audio_path = base_dir / "recording.wav"
    transcript_path = base_dir / "transcript.json"
    notes_path = base_dir / "notes.md"

    # ── Step 1 & 2: Join + Record ─────────────────────────────────────────────
    recorder = AudioRecorder(audio_path)
    bot = get_bot(meeting, audio_path)

    try:
        async with bot:
            recorder.start()
            logger.info(f"[Orchestrator] In meeting — recording to {audio_path}")
            await _wait_for_end(bot, meeting)
    except Exception as exc:
        logger.error(f"[Orchestrator] Bot error during meeting: {exc}")
        # Still try to process whatever was recorded
    finally:
        recorder.stop()

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        logger.error("[Orchestrator] No audio captured — aborting pipeline")
        return None

    # ── Step 3: Transcribe ────────────────────────────────────────────────────
    try:
        transcript = _transcriber.transcribe(audio_path, meeting)
        transcript_path.write_text(
            json.dumps(
                {"segments": transcript.segments, "full_text": transcript.full_text},
                ensure_ascii=False,
                indent=2,
            )
        )
        logger.info(f"[Orchestrator] Transcript saved → {transcript_path}")
    except Exception as exc:
        logger.error(f"[Orchestrator] Transcription failed: {exc}")
        return None

    # ── Step 4: Summarize ─────────────────────────────────────────────────────
    try:
        notes = _summarizer.summarize(transcript)
        notes_path.write_text(notes.as_markdown(), encoding="utf-8")
        logger.info(f"[Orchestrator] Notes saved → {notes_path}")
    except Exception as exc:
        logger.error(f"[Orchestrator] Summarization failed: {exc}")
        return None

    # ── Step 5: Deliver outputs ───────────────────────────────────────────────
    doc_url = ""
    try:
        doc_url = save_to_google_docs(notes)
    except Exception as exc:
        logger.error(f"[Orchestrator] Google Docs export failed: {exc}")

    try:
        send_meeting_notes(notes, doc_url=doc_url)
    except Exception as exc:
        logger.error(f"[Orchestrator] Email delivery failed: {exc}")

    logger.info(f"[Orchestrator] Pipeline complete for: {meeting.title}")
    return notes


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _wait_for_end(bot, meeting: Meeting) -> None:
    """Poll until the meeting ends or the deadline passes."""
    deadline = meeting.end_time + timedelta(minutes=_MAX_OVERTIME_MINUTES)

    while True:
        now = datetime.now(timezone.utc)
        if now >= deadline:
            logger.info("[Orchestrator] Deadline reached — leaving meeting")
            break
        if not await bot.is_meeting_active():
            logger.info("[Orchestrator] Meeting ended (detected by bot)")
            break
        await asyncio.sleep(_POLL_SECONDS)


def _safe_filename(name: str) -> str:
    """Strip characters unsafe for file names."""
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name)[:60].strip()
