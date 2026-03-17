"""Meeting summarization using Claude (Anthropic)."""

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models import Transcript, MeetingNotes

_SYSTEM_PROMPT = """\
You are an expert meeting analyst. You will receive a full transcript of a meeting \
and produce concise, structured meeting notes.

Your output must be a JSON object with these exact keys:
- "summary": a 3–5 sentence executive summary of what was discussed
- "key_decisions": a list of strings, each being a clear decision made during the meeting
- "action_items": a list of strings in the format "Owner: task description" (use "TBD" if owner unknown)
- "next_steps": a short paragraph describing immediate next steps and any follow-up meetings

Be specific, professional, and focus on outcomes rather than discussion details.
If no decisions or action items are mentioned, return empty lists.
"""


class MeetingSummarizer:

    def __init__(self):
        self._client = None  # lazy-init

    # ── Public ────────────────────────────────────────────────────────────────

    def summarize(self, transcript: Transcript) -> MeetingNotes:
        """Generate structured meeting notes from a transcript."""
        logger.info(f"[Summarizer] Summarizing transcript ({len(transcript.full_text)} chars)")

        raw = self._call_claude(transcript.full_text, transcript.meeting.title)
        parsed = self._parse_response(raw)

        notes = MeetingNotes(
            meeting=transcript.meeting,
            transcript=transcript,
            summary=parsed.get("summary", "No summary available."),
            action_items=parsed.get("action_items", []),
            key_decisions=parsed.get("key_decisions", []),
            next_steps=parsed.get("next_steps", ""),
        )
        logger.info(
            f"[Summarizer] Done — {len(notes.action_items)} action items, "
            f"{len(notes.key_decisions)} decisions"
        )
        return notes

    # ── Internals ─────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_claude(self, transcript_text: str, meeting_title: str) -> str:
        client = self._get_client()

        # Truncate very long transcripts to stay within context limits
        max_chars = 180_000
        if len(transcript_text) > max_chars:
            logger.warning(f"[Summarizer] Transcript truncated from {len(transcript_text)} to {max_chars} chars")
            transcript_text = transcript_text[:max_chars] + "\n\n[Transcript truncated due to length]"

        user_message = (
            f"Meeting title: {meeting_title}\n\n"
            f"Full transcript:\n\n{transcript_text}"
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def _parse_response(self, raw: str) -> dict:
        import json
        import re

        # Extract JSON block — Claude may wrap it in ```json ... ```
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("[Summarizer] Could not parse JSON response — returning raw text as summary")
            return {
                "summary": raw,
                "key_decisions": [],
                "action_items": [],
                "next_steps": "",
            }

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client
