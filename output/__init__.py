"""Output delivery — Google Docs and email."""

from .google_docs import save_to_google_docs
from .email_sender import send_meeting_notes

__all__ = ["save_to_google_docs", "send_meeting_notes"]
