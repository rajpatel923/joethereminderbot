import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _get_oauth_config() -> tuple[str, str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "urn:ietf:wg:oauth:2.0:oob")
    if not client_id or not client_secret:
        raise ValueError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env for Calendar integration"
        )
    return client_id, client_secret, redirect_uri


def _build_client_config(client_id: str, client_secret: str, redirect_uri: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def create_oauth_flow():
    """Create and return a Flow object (must be reused for token exchange)."""
    from google_auth_oauthlib.flow import Flow

    client_id, client_secret, redirect_uri = _get_oauth_config()
    flow = Flow.from_client_config(
        _build_client_config(client_id, client_secret, redirect_uri),
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=redirect_uri,
    )
    return flow


def get_auth_url(flow) -> str:
    """Get the authorization URL from an existing Flow object."""
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_code_for_tokens(flow, code: str) -> dict:
    """Exchange an authorization code using the SAME Flow object that generated the auth URL.
    This preserves the PKCE code verifier required by Google."""
    import os as _os
    _os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def get_calendar_service(tokens, db=None, user_id: Optional[int] = None):
    """Build an authenticated Google Calendar service, refreshing token if needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id, client_secret, _ = _get_oauth_config()

    creds = Credentials(
        token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist updated token
        if db and user_id is not None:
            db.save_google_tokens(user_id, creds.token, creds.refresh_token, creds.expiry)
        logger.debug("Refreshed Google access token for user_id=%s", user_id)

    return build("calendar", "v3", credentials=creds)


def create_event(service, title: str, start_dt: datetime, end_dt: Optional[datetime] = None) -> str:
    """Create a Google Calendar event and return the event ID."""
    if end_dt is None:
        end_dt = start_dt + timedelta(hours=1)

    event = {
        "summary": title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": str(start_dt.tzinfo) if start_dt.tzinfo else "UTC",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": str(end_dt.tzinfo) if end_dt.tzinfo else "UTC",
        },
    }
    result = service.events().insert(calendarId="primary", body=event).execute()
    event_id = result.get("id", "")
    logger.info("Created calendar event '%s' id=%s", title, event_id)
    return event_id


def list_events(service, days_ahead: int = 7) -> list[dict]:
    """Return calendar events from start of today through days_ahead."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    now = today_start.isoformat()
    end = (today_start + timedelta(days=days_ahead)).isoformat()
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            timeMax=end,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for item in result.get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date", ""))
        events.append({"summary": item.get("summary", "(no title)"), "start": start})
    return events
