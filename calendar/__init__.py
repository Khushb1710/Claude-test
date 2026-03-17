"""Calendar integrations."""

from models import Meeting
from .google_calendar import fetch_upcoming_meetings as _google_meetings
from .outlook_calendar import fetch_upcoming_meetings as _outlook_meetings


def fetch_all_upcoming_meetings(lookahead_minutes: int = 60) -> list[Meeting]:
    """Aggregate upcoming meetings from all configured calendars."""
    meetings: list[Meeting] = []
    meetings.extend(_google_meetings(lookahead_minutes))
    meetings.extend(_outlook_meetings(lookahead_minutes))

    # Deduplicate by join URL
    seen: set[str] = set()
    unique: list[Meeting] = []
    for m in sorted(meetings, key=lambda x: x.start_time):
        if m.join_url not in seen:
            seen.add(m.join_url)
            unique.append(m)

    return unique
