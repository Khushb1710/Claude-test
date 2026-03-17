"""Meeting platform bots."""

from pathlib import Path

from models import Meeting, Platform
from .base_bot import BaseMeetingBot
from .google_meet_bot import GoogleMeetBot
from .zoom_bot import ZoomBot
from .teams_bot import TeamsBot


def get_bot(meeting: Meeting, audio_output_path: Path) -> BaseMeetingBot:
    """Factory — return the appropriate bot for the meeting's platform."""
    mapping = {
        Platform.GOOGLE_MEET: GoogleMeetBot,
        Platform.ZOOM: ZoomBot,
        Platform.TEAMS: TeamsBot,
    }
    bot_class = mapping.get(meeting.platform)
    if not bot_class:
        raise ValueError(f"No bot available for platform: {meeting.platform}")
    return bot_class(meeting, audio_output_path)
