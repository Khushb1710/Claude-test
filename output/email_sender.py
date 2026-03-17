"""Send meeting notes via email (SMTP)."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

from loguru import logger

from config import settings
from models import MeetingNotes


def send_meeting_notes(notes: MeetingNotes, doc_url: str = "", extra_recipients: list[str] | None = None) -> None:
    """
    Email the meeting summary + transcript to attendees.

    Recipients:
      1. Meeting attendees (from the calendar event)
      2. `extra_recipients` passed in
      3. `DEFAULT_EMAIL_RECIPIENTS` from settings (fallback)
    """
    recipients = _build_recipient_list(notes, extra_recipients)
    if not recipients:
        logger.warning("[Email] No recipients found — skipping email")
        return

    subject = f"Meeting Notes: {notes.meeting.title} ({notes.meeting.start_time.strftime('%B %d, %Y')})"
    html_body = _build_html_body(notes, doc_url)
    text_body = notes.as_markdown()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_username
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    _smtp_send(msg, recipients)


def _build_recipient_list(notes: MeetingNotes, extra: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for email in (
        notes.meeting.attendee_emails
        + (extra or [])
        + settings.default_email_recipients
    ):
        email = email.strip().lower()
        if email and email not in seen:
            seen.add(email)
            result.append(email)

    return result


def _build_html_body(notes: MeetingNotes, doc_url: str) -> str:
    action_items_html = "".join(f"<li>{item}</li>" for item in notes.action_items)
    decisions_html = "".join(f"<li>{d}</li>" for d in notes.key_decisions)
    doc_link = f'<p><a href="{doc_url}">📄 View full notes in Google Docs</a></p>' if doc_url else ""

    return f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; color: #333; max-width: 700px; margin: 0 auto; padding: 20px; }}
    h1 {{ color: #1a73e8; }}
    h2 {{ color: #444; border-bottom: 1px solid #eee; padding-bottom: 6px; }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 4px 0; }}
    .meta {{ color: #888; font-size: 0.9em; margin-bottom: 20px; }}
    .summary {{ background: #f8f9fa; padding: 16px; border-radius: 6px; margin: 16px 0; }}
    .footer {{ color: #999; font-size: 0.8em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; }}
  </style>
</head>
<body>
  <h1>Meeting Notes: {notes.meeting.title}</h1>
  <div class="meta">
    <strong>Date:</strong> {notes.meeting.start_time.strftime('%B %d, %Y %H:%M')} UTC &nbsp;|&nbsp;
    <strong>Duration:</strong> {notes.meeting.duration_minutes} min &nbsp;|&nbsp;
    <strong>Platform:</strong> {notes.meeting.platform.value.replace('_', ' ').title()}
  </div>

  {doc_link}

  <h2>Summary</h2>
  <div class="summary">{notes.summary}</div>

  <h2>Key Decisions</h2>
  <ul>{decisions_html if decisions_html else '<li>None recorded</li>'}</ul>

  <h2>Action Items</h2>
  <ul>{action_items_html if action_items_html else '<li>None recorded</li>'}</ul>

  <h2>Next Steps</h2>
  <p>{notes.next_steps or 'None specified.'}</p>

  <div class="footer">
    Generated automatically by AI Meeting Note Taker.
  </div>
</body>
</html>
"""


def _smtp_send(msg: MIMEMultipart, recipients: list[str]) -> None:
    if not settings.smtp_username or not settings.smtp_password:
        logger.error("[Email] SMTP credentials not configured")
        return

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(msg["From"], recipients, msg.as_string())
        logger.info(f"[Email] Sent meeting notes to: {', '.join(recipients)}")
    except Exception as exc:
        logger.error(f"[Email] Failed to send email: {exc}")
        raise
