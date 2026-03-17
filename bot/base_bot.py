"""Abstract base class for all meeting platform bots."""

import abc
from pathlib import Path

from models import Meeting


class BaseMeetingBot(abc.ABC):
    """Base class that all platform bots must implement."""

    def __init__(self, meeting: Meeting, audio_output_path: Path):
        self.meeting = meeting
        self.audio_output_path = audio_output_path
        self._joined = False

    @abc.abstractmethod
    async def join(self) -> None:
        """Navigate to the meeting URL and join the call."""

    @abc.abstractmethod
    async def leave(self) -> None:
        """Leave/hang up the meeting and clean up the browser session."""

    @abc.abstractmethod
    async def is_meeting_active(self) -> bool:
        """Return True while the meeting is still in progress."""

    async def __aenter__(self):
        await self.join()
        return self

    async def __aexit__(self, *_):
        await self.leave()
