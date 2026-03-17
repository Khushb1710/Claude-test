"""Shared data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    TEAMS = "teams"
    UNKNOWN = "unknown"


@dataclass
class Meeting:
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    platform: Platform
    join_url: str
    organizer_email: str = ""
    attendee_emails: list[str] = field(default_factory=list)
    calendar_source: str = "google"  # "google" | "microsoft"

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class Transcript:
    meeting: Meeting
    segments: list[dict]          # [{start, end, text, speaker}]
    full_text: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def as_markdown(self) -> str:
        lines = [
            f"# Transcript: {self.meeting.title}",
            f"**Date:** {self.meeting.start_time.strftime('%B %d, %Y %H:%M')} UTC",
            f"**Duration:** {self.meeting.duration_minutes} minutes",
            f"**Platform:** {self.meeting.platform.value.replace('_', ' ').title()}",
            "",
            "---",
            "",
        ]
        for seg in self.segments:
            speaker = seg.get("speaker", "")
            prefix = f"**{speaker}:** " if speaker else ""
            ts = f"[{_fmt_ts(seg.get('start', 0))}] "
            lines.append(f"{ts}{prefix}{seg['text'].strip()}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class MeetingNotes:
    meeting: Meeting
    transcript: Transcript
    summary: str
    action_items: list[str]
    key_decisions: list[str]
    next_steps: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def as_markdown(self) -> str:
        lines = [
            f"# Meeting Notes: {self.meeting.title}",
            f"**Date:** {self.meeting.start_time.strftime('%B %d, %Y %H:%M')} UTC",
            f"**Duration:** {self.meeting.duration_minutes} minutes",
            f"**Platform:** {self.meeting.platform.value.replace('_', ' ').title()}",
            f"**Attendees:** {', '.join(self.meeting.attendee_emails) or 'N/A'}",
            "",
            "---",
            "",
            "## Summary",
            "",
            self.summary,
            "",
            "## Key Decisions",
            "",
        ]
        for d in self.key_decisions:
            lines.append(f"- {d}")
        lines += [
            "",
            "## Action Items",
            "",
        ]
        for item in self.action_items:
            lines.append(f"- [ ] {item}")
        lines += [
            "",
            "## Next Steps",
            "",
            self.next_steps,
            "",
            "---",
            "",
            "## Full Transcript",
            "",
            self.transcript.as_markdown(),
        ]
        return "\n".join(lines)


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
