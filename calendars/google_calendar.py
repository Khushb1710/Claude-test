"""Google Calendar integration — fetches upcoming meetings."""

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

from config import settings
from models import Meeting, Platform

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.send",
]

# Regex patterns to detect meeting links in event descriptions/locations
_MEET_RE = re.compile(r"https://meet\.google\.com/[a-z0-9\-]+", re.IGNORECASE)
_ZOOM_RE = re.compile(r"https://[a-z0-9.]*zoom\.us/j/\S+", re.IGNORECASE)
_TEAMS_RE = re.compile(r"https://teams\.microsoft\.com/l/meetup-join/\S+", re.IGNORECASE)


def get_google_credentials() -> Credentials:
    """Return valid Google OAuth2 credentials, refreshing or prompting as needed."""
    creds: Credentials | None = None
    token_path = settings.google_token_file

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(settings.google_credentials_file), SCOPES
            )
            creds = flow.run_local_server(port=8080, open_browser=False)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def fetch_upcoming_meetings(lookahead_minutes: int = 60) -> list[Meeting]:
    """Return meetings starting within the next *lookahead_minutes* minutes."""
    try:
        creds = get_google_credentials()
        service = build("calendar", "v3", credentials=creds)
    except Exception as exc:
        logger.error(f"Google Calendar auth failed: {exc}")
        return []

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(minutes=lookahead_minutes)

    try:
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as exc:
        logger.error(f"Google Calendar API error: {exc}")
        return []

    meetings = []
    for event in result.get("items", []):
        meeting = _parse_event(event)
        if meeting:
            meetings.append(meeting)

    logger.info(f"Google Calendar: found {len(meetings)} upcoming meeting(s)")
    return meetings


def _parse_event(event: dict) -> Meeting | None:
    """Convert a Google Calendar event dict into a Meeting, or None if no join URL."""
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})

    start = _parse_dt(start_raw.get("dateTime") or start_raw.get("date"))
    end = _parse_dt(end_raw.get("dateTime") or end_raw.get("date"))
    if not start or not end:
        return None

    # Try to find a meeting URL from conferenceData, location, or description
    join_url, platform = _extract_join_url(event)
    if not join_url:
        return None

    organizer = event.get("organizer", {}).get("email", "")
    attendees = [
        a["email"]
        for a in event.get("attendees", [])
        if a.get("email") and not a.get("self")
    ]

    return Meeting(
        id=event["id"],
        title=event.get("summary", "Untitled Meeting"),
        start_time=start,
        end_time=end,
        platform=platform,
        join_url=join_url,
        organizer_email=organizer,
        attendee_emails=attendees,
        calendar_source="google",
    )


def _extract_join_url(event: dict) -> tuple[str, Platform]:
    """Return (url, platform) from an event, checking multiple fields."""
    # 1. Google Meet via conferenceData
    conf = event.get("conferenceData", {})
    for ep in conf.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            url = ep.get("uri", "")
            if url:
                return url, _detect_platform(url)

    # 2. Scan location and description for any meeting link
    for field in ("location", "description"):
        text = event.get(field, "") or ""
        for pattern, platform in [
            (_MEET_RE, Platform.GOOGLE_MEET),
            (_ZOOM_RE, Platform.ZOOM),
            (_TEAMS_RE, Platform.TEAMS),
        ]:
            match = pattern.search(text)
            if match:
                return match.group(0), platform

    return "", Platform.UNKNOWN


def _detect_platform(url: str) -> Platform:
    if "meet.google.com" in url:
        return Platform.GOOGLE_MEET
    if "zoom.us" in url:
        return Platform.ZOOM
    if "teams.microsoft.com" in url:
        return Platform.TEAMS
    return Platform.UNKNOWN


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
