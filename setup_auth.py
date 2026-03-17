"""Two-step Google OAuth setup for remote environments.

Step 1: python setup_auth.py
Step 2: python setup_auth.py "http://localhost:8080/?code=..."
"""
import sys
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import InstalledAppFlow
from config import settings

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.send",
]

flow = InstalledAppFlow.from_client_secrets_file(
    str(settings.google_credentials_file), SCOPES
)

if len(sys.argv) == 1:
    # Step 1: print auth URL
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print("\nStep 1: Open this URL in your browser:\n")
    print(auth_url)
    print("\nStep 2: After granting permission, your browser will try to load")
    print("http://localhost:8080/?code=... and show a connection error.")
    print("Copy the FULL URL from the address bar, then run:")
    print('\n  python setup_auth.py "<paste-full-url-here>"\n')
else:
    # Step 2: exchange code for token
    redirect_url = sys.argv[1]
    parsed = urlparse(redirect_url)
    code = parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        print("ERROR: No 'code' found in the URL. Make sure you copied the full URL.")
        sys.exit(1)
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_path = settings.google_token_file
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"\nSuccess! Token saved to {token_path}")
