"""Microsoft Outlook / Teams calendar integration via Microsoft Graph API."""

import re
from datetime import datetime, timezone, timedelta

import msal
import requests
from loguru import logger

from config import settings
from models import Meeting, Platform

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["https://graph.microsoft.com/.default"]

_TEAMS_RE = re.compile(r"https://teams\.microsoft\.com/l/meetup-join/\S+", re.IGNORECASE)
_ZOOM_RE = re.compile(r"https://[a-z0-9.]*zoom\.us/j/\S+", re.IGNORECASE)
_MEET_RE = re.compile(r"https://meet\.google\.com/[a-z0-9\-]+", re.IGNORECASE)


def _get_access_token() -> str | None:
    """Acquire an access token via MSAL client credentials flow."""
    if not all([settings.microsoft_client_id, settings.microsoft_client_secret, settings.microsoft_tenant_id]):
        logger.warning("Microsoft credentials not configured — skipping Outlook calendar")
        return None

    authority = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}"
    app = msal.ConfidentialClientApplication(
        settings.microsoft_client_id,
        authority=authority,
        client_credential=settings.microsoft_client_secret,
    )
    result = app.acquire_token_for_client(scopes=SCOPES)
    if "access_token" not in result:
        logger.error(f"MSAL token error: {result.get('error_description')}")
        return None
    return result["access_token"]


def fetch_upcoming_meetings(lookahead_minutes: int = 60) -> list[Meeting]:
    """Return Teams/Outlook meetings starting within the next *lookahead_minutes*."""
    token = _get_access_token()
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(minutes=lookahead_minutes)

    meetings: list[Meeting] = []

    # Iterate over configured Microsoft accounts
    for account in settings.microsoft_accounts:
        try:
            events = _fetch_events(headers, account, now, time_max)
            for event in events:
                meeting = _parse_event(event, account)
                if meeting:
                    meetings.append(meeting)
        except Exception as exc:
            logger.error(f"Outlook calendar error for {account}: {exc}")

    logger.info(f"Outlook Calendar: found {len(meetings)} upcoming meeting(s)")
    return meetings


def _fetch_events(headers: dict, user: str, start: datetime, end: datetime) -> list[dict]:
    url = f"{GRAPH_BASE}/users/{user}/calendarView"
    params = {
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,location,bodyPreview,attendees,organizer,onlineMeeting",
        "$orderby": "start/dateTime",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("value", [])


def _parse_event(event: dict, calendar_owner: str) -> Meeting | None:
    start = _parse_dt(event.get("start", {}).get("dateTime"))
    end = _parse_dt(event.get("end", {}).get("dateTime"))
    if not start or not end:
        return None

    join_url, platform = _extract_join_url(event)
    if not join_url:
        return None

    organizer = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
    attendees = [
        a["emailAddress"]["address"]
        for a in event.get("attendees", [])
        if a.get("emailAddress", {}).get("address")
        and a["emailAddress"]["address"] != calendar_owner
    ]

    return Meeting(
        id=event["id"],
        title=event.get("subject", "Untitled Meeting"),
        start_time=start,
        end_time=end,
        platform=platform,
        join_url=join_url,
        organizer_email=organizer,
        attendee_emails=attendees,
        calendar_source="microsoft",
    )


def _extract_join_url(event: dict) -> tuple[str, Platform]:
    # 1. Native Teams online meeting
    online = event.get("onlineMeeting") or {}
    url = online.get("joinUrl", "")
    if url:
        return url, Platform.TEAMS

    # 2. Scan location + bodyPreview
    for text in [event.get("location", {}).get("displayName", ""), event.get("bodyPreview", "")]:
        for pattern, platform in [
            (_TEAMS_RE, Platform.TEAMS),
            (_ZOOM_RE, Platform.ZOOM),
            (_MEET_RE, Platform.GOOGLE_MEET),
        ]:
            match = pattern.search(text or "")
            if match:
                return match.group(0), platform

    return "", Platform.UNKNOWN


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
