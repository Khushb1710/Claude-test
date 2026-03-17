"""
AI Meeting Note Taker — CLI entry point.

Usage:
  # Start the calendar-watching daemon
  python main.py daemon

  # Immediately join a specific meeting URL
  python main.py join <url> [--title "My Meeting"]

  # Transcribe + summarize an existing recording
  python main.py process <audio_file.wav> [--title "My Meeting"]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from config import settings


def _setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )


def cmd_daemon(_args) -> None:
    """Run the scheduler daemon."""
    from scheduler import main as run_scheduler
    run_scheduler()


def cmd_join(args) -> None:
    """Join a meeting by URL immediately."""
    from scheduler import join_from_url
    title = getattr(args, "title", "Ad-hoc Meeting") or "Ad-hoc Meeting"
    asyncio.run(join_from_url(args.url, title=title))


def cmd_process(args) -> None:
    """Process an existing audio recording."""
    from datetime import datetime, timezone, timedelta
    from models import Meeting, Platform
    from transcription import WhisperTranscriber
    from ai import MeetingSummarizer
    from output import save_to_google_docs, send_meeting_notes

    audio_path = Path(args.file)
    if not audio_path.exists():
        logger.error(f"File not found: {audio_path}")
        sys.exit(1)

    title = getattr(args, "title", None) or audio_path.stem.replace("_", " ")
    now = datetime.now(timezone.utc)

    # Synthetic meeting metadata
    meeting = Meeting(
        id=f"offline_{int(now.timestamp())}",
        title=title,
        start_time=now - timedelta(hours=1),
        end_time=now,
        platform=Platform.UNKNOWN,
        join_url="",
    )

    logger.info(f"Transcribing {audio_path}…")
    transcript = WhisperTranscriber().transcribe(audio_path, meeting)
    logger.info(f"Transcript: {len(transcript.full_text)} characters")

    logger.info("Summarizing…")
    notes = MeetingSummarizer().summarize(transcript)

    notes_path = audio_path.parent / "notes.md"
    notes_path.write_text(notes.as_markdown(), encoding="utf-8")
    logger.info(f"Notes saved → {notes_path}")

    doc_url = ""
    try:
        doc_url = save_to_google_docs(notes)
        logger.info(f"Google Doc → {doc_url}")
    except Exception as exc:
        logger.warning(f"Google Docs export failed: {exc}")

    try:
        send_meeting_notes(notes, doc_url=doc_url)
    except Exception as exc:
        logger.warning(f"Email delivery failed: {exc}")


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="meeting-notes",
        description="AI Meeting Note Taker",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # daemon
    subparsers.add_parser("daemon", help="Run the calendar-watching scheduler daemon")

    # join
    join_parser = subparsers.add_parser("join", help="Join a meeting by URL")
    join_parser.add_argument("url", help="Meeting join URL (Google Meet, Zoom, or Teams)")
    join_parser.add_argument("--title", default="Ad-hoc Meeting", help="Meeting title")

    # process
    proc_parser = subparsers.add_parser("process", help="Transcribe and summarize a recording")
    proc_parser.add_argument("file", help="Path to WAV audio file")
    proc_parser.add_argument("--title", default=None, help="Meeting title")

    args = parser.parse_args()

    dispatch = {
        "daemon": cmd_daemon,
        "join": cmd_join,
        "process": cmd_process,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
