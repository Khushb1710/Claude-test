# AI Meeting Note Taker

Automatically joins your meetings (Google Meet, Zoom, Microsoft Teams), records the audio, transcribes it with OpenAI Whisper, and generates a structured summary using Claude. Notes are saved to Google Docs and emailed to attendees.

## Features

- **Calendar integration** — watches Google Calendar and Outlook for upcoming meetings
- **Auto-join** — headless browser bot joins meetings before they start
- **Audio recording** — captures system audio via PulseAudio monitor
- **Transcription** — OpenAI Whisper (local model or API)
- **AI summarization** — Claude produces summary, action items, key decisions, and next steps
- **Google Docs** — a new Doc is created for each meeting
- **Email delivery** — notes are emailed to all attendees

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys and credentials
```

### 3. Set up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **Google Calendar API**, **Google Docs API**, and **Gmail API**
3. Create OAuth 2.0 credentials (Desktop app) and download as `credentials/google_credentials.json`
4. On first run the app will open a browser for you to authorize

### 4. Set up Microsoft Azure (for Teams/Outlook)

1. Register an app in [Azure AD](https://portal.azure.com/)
2. Add permissions: `Calendars.Read`, `OnlineMeetings.Read`
3. Copy the Client ID, Secret, and Tenant ID to `.env`

### 5. Set up PulseAudio loopback (Linux)

```bash
# Load the loopback module so system audio is capturable
pactl load-module module-loopback
```

## Usage

### Run the daemon (watches calendar automatically)

```bash
python main.py daemon
```

### Join a meeting immediately by URL

```bash
python main.py join "https://meet.google.com/abc-defg-hij" --title "Team Standup"
python main.py join "https://zoom.us/j/1234567890?pwd=xxx"
python main.py join "https://teams.microsoft.com/l/meetup-join/..."
```

### Process an existing recording

```bash
python main.py process recording.wav --title "Q1 Planning"
```

## Project Structure

```
├── main.py                  # CLI entry point
├── scheduler.py             # Calendar polling & meeting dispatch
├── orchestrator.py          # Per-meeting pipeline (join → record → transcribe → summarize → deliver)
├── config.py                # Settings (loaded from .env)
├── models.py                # Data models (Meeting, Transcript, MeetingNotes)
├── calendar/
│   ├── google_calendar.py   # Google Calendar API
│   └── outlook_calendar.py  # Microsoft Graph API (Outlook/Teams)
├── bot/
│   ├── google_meet_bot.py   # Google Meet Playwright bot
│   ├── zoom_bot.py          # Zoom web client Playwright bot
│   └── teams_bot.py         # Teams web app Playwright bot
├── recording/
│   └── audio_recorder.py    # PulseAudio system audio capture
├── transcription/
│   └── whisper_transcriber.py  # OpenAI Whisper (local or API)
├── ai/
│   └── summarizer.py        # Claude meeting summarization
└── output/
    ├── google_docs.py       # Google Docs export
    └── email_sender.py      # SMTP email delivery
```

## Configuration Reference

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | For Whisper API (set `WHISPER_MODEL=api`) |
| `ANTHROPIC_API_KEY` | For Claude summarization |
| `GOOGLE_CREDENTIALS_FILE` | Path to Google OAuth JSON |
| `MICROSOFT_CLIENT_ID/SECRET/TENANT_ID` | Azure AD app credentials |
| `SMTP_HOST/PORT/USERNAME/PASSWORD` | SMTP settings for email |
| `BOT_GOOGLE_EMAIL/PASSWORD` | Google account for the bot |
| `BOT_ZOOM_EMAIL/PASSWORD` | Zoom credentials |
| `BOT_MICROSOFT_EMAIL/PASSWORD` | Microsoft account for Teams bot |
| `JOIN_BUFFER_MINUTES` | How many minutes before start to join (default: 2) |
| `WHISPER_MODEL` | `api`, `tiny`, `base`, `small`, `medium`, `large` |
| `DATA_DIR` | Where to store recordings and notes (default: `./data`) |

## Output Format

Each meeting produces:
- `data/<timestamp>_<title>/recording.wav` — raw audio
- `data/<timestamp>_<title>/transcript.json` — timestamped segments
- `data/<timestamp>_<title>/notes.md` — full markdown notes
- A Google Doc with formatted notes
- An email to all attendees

Meeting notes include:
- **Summary** (3–5 sentences)
- **Key Decisions**
- **Action Items** (with owners where mentioned)
- **Next Steps**
- **Full Transcript** (with timestamps)
