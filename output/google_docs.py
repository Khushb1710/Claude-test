"""Save meeting notes to Google Docs."""

from loguru import logger
from calendars.google_calendar import get_google_credentials, build_google_service
from models import MeetingNotes


def save_to_google_docs(notes: MeetingNotes) -> str:
    """
    Create a new Google Doc with the full meeting notes.
    Returns the URL of the created document.
    """
    creds = get_google_credentials()
    docs_service = build_google_service("docs", "v1", creds)
    drive_service = build_google_service("drive", "v3", creds)

    title = f"Meeting Notes: {notes.meeting.title} — {notes.meeting.start_time.strftime('%Y-%m-%d')}"

    # Create the document
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    # Build the content as a series of insertions
    content = notes.as_markdown()
    _insert_text(docs_service, doc_id, content)

    logger.info(f"[GoogleDocs] Created document: {doc_url}")
    return doc_url


def _insert_text(docs_service, doc_id: str, text: str) -> None:
    """Insert text into a Google Doc and apply basic heading styles."""
    requests = []

    # Insert all text at once
    requests.append(
        {
            "insertText": {
                "location": {"index": 1},
                "text": text,
            }
        }
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()

    # Apply HEADING_1 style to lines starting with "# "
    _apply_heading_styles(docs_service, doc_id, text)


def _apply_heading_styles(docs_service, doc_id: str, text: str) -> None:
    """Apply heading paragraph styles to lines prefixed with # / ## / ###."""
    style_map = {
        "### ": "HEADING_3",
        "## ":  "HEADING_2",
        "# ":   "HEADING_1",
    }

    lines = text.split("\n")
    index = 1  # Docs API uses 1-based character indexes
    requests = []

    for line in lines:
        line_len = len(line) + 1  # +1 for \n
        for prefix, style in style_map.items():
            if line.startswith(prefix):
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": index, "endIndex": index + line_len},
                            "paragraphStyle": {"namedStyleType": style},
                            "fields": "namedStyleType",
                        }
                    }
                )
                break
        index += line_len

    if requests:
        try:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()
        except Exception as exc:
            logger.warning(f"[GoogleDocs] Heading styling failed (non-critical): {exc}")
