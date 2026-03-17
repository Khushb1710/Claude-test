"""
Background scheduler — polls calendars and launches meeting pipelines.

Run this as the main process:
    python scheduler.py

It checks both Google Calendar and Outlook every minute, and joins any
meeting that starts within the next JOIN_BUFFER_MINUTES minutes.
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone

import schedule
from loguru import logger

from config import settings
from calendars import fetch_all_upcoming_meetings
from models import Meeting
from orchestrator import run_meeting


# Track meetings we've already dispatched (by meeting ID)
_dispatched: set[str] = set()
# Currently running meeting tasks
_active_tasks: set[asyncio.Task] = set()


# ── Scheduler logic ───────────────────────────────────────────────────────────

def check_calendar() -> None:
    """Synchronous wrapper called by the `schedule` library."""
    asyncio.get_event_loop().run_until_complete(_check_and_dispatch())


async def _check_and_dispatch() -> None:
    meetings = fetch_all_upcoming_meetings(lookahead_minutes=settings.join_buffer_minutes + 1)
    now = datetime.now(timezone.utc)

    for meeting in meetings:
        if meeting.id in _dispatched:
            continue
        # Only dispatch if meeting starts within the buffer window
        seconds_until_start = (meeting.start_time - now).total_seconds()
        if seconds_until_start <= settings.join_buffer_minutes * 60:
            logger.info(
                f"[Scheduler] Dispatching: {meeting.title} "
                f"(starts in {int(seconds_until_start)}s)"
            )
            _dispatched.add(meeting.id)
            task = asyncio.create_task(_run_and_track(meeting))
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)


async def _run_and_track(meeting: Meeting) -> None:
    try:
        await run_meeting(meeting)
    except Exception as exc:
        logger.error(f"[Scheduler] Unhandled error for {meeting.title}: {exc}")


# ── Manual meeting join ───────────────────────────────────────────────────────

async def join_from_url(url: str, title: str = "Ad-hoc Meeting") -> None:
    """Immediately join a meeting by URL without calendar lookup."""
    from models import Platform
    from calendars.google_calendar import _detect_platform

    platform = _detect_platform(url)
    now = datetime.now(timezone.utc)

    # Create a synthetic Meeting with a 2-hour window
    from datetime import timedelta
    from models import Meeting

    meeting = Meeting(
        id=f"manual_{int(now.timestamp())}",
        title=title,
        start_time=now,
        end_time=now + timedelta(hours=2),
        platform=platform,
        join_url=url,
    )
    logger.info(f"[Scheduler] Manually joining: {url}")
    await run_meeting(meeting)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
    logger.add(
        settings.data_dir / "app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("AI Meeting Note Taker starting up…")
    logger.info(f"  Calendar poll interval : 1 minute")
    logger.info(f"  Join buffer            : {settings.join_buffer_minutes} minutes before start")
    logger.info(f"  Transcription model    : {settings.whisper_model}")
    logger.info(f"  Data directory         : {settings.data_dir}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Check calendar every minute
    schedule.every(1).minutes.do(check_calendar)

    # Run an immediate check on startup
    loop.run_until_complete(_check_and_dispatch())

    def _shutdown(sig, frame):
        logger.info("Shutting down…")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        loop.run_until_complete(asyncio.sleep(5))


if __name__ == "__main__":
    main()
