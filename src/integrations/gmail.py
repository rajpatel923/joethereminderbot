import base64
import email as email_lib
import logging
import os
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

PROCESSED_LABEL = "ReminderAgent"


def get_gmail_service(tokens, db=None, user_id: Optional[int] = None):
    """Build an authenticated Gmail service, refreshing token if needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    creds = Credentials(
        token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.modify"],
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if db and user_id is not None:
            db.save_google_tokens(user_id, creds.token, creds.refresh_token, creds.expiry)
        logger.debug("Refreshed Google access token for Gmail, user_id=%s", user_id)

    return build("gmail", "v1", credentials=creds)


def get_unread_emails(service, max_results: int = 50) -> list[dict]:
    """Return unread inbox emails not yet labeled as processed."""
    result = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=f"is:unread in:inbox -label:{PROCESSED_LABEL}",
            maxResults=max_results,
        )
        .execute()
    )
    messages = result.get("messages", [])
    emails = []
    for msg in messages:
        msg_data = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="metadata",
                 metadataHeaders=["From", "Subject"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg["id"],
            "thread_id": msg_data.get("threadId", ""),
            "sender": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": msg_data.get("snippet", ""),
        })
    return emails


def get_email_body(service, message_id: str) -> str:
    """Fetch and return the plain-text body of an email."""
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    def _extract_parts(payload) -> str:
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            text = _extract_parts(part)
            if text:
                return text
        return ""

    body = _extract_parts(msg.get("payload", {}))
    return body or msg.get("snippet", "")


async def classify_email(ai, sender: str, subject: str, snippet: str) -> str:
    """Classify an email into SPAM, MARKETING, REAL_PERSON, or IMPORTANT."""
    prompt = (
        "Classify this email. Reply with exactly one word: SPAM, MARKETING, REAL_PERSON, or IMPORTANT.\n"
        "IMPORTANT = recruiter outreach, job offer, government/legal, bank/financial alert, medical.\n"
        "MARKETING = newsletters, promotions, sales, subscriptions.\n"
        "SPAM = phishing, suspicious, unsolicited bulk.\n"
        "REAL_PERSON = genuine personal or professional message from an individual.\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Preview: {snippet}"
    )
    messages = [
        {"role": "system", "content": "You are an email classifier. Reply with exactly one word."},
        {"role": "user", "content": prompt},
    ]
    reply = await ai.chat(messages)
    category = reply.strip().upper().split()[0] if reply.strip() else "REAL_PERSON"
    if category not in ("SPAM", "MARKETING", "REAL_PERSON", "IMPORTANT"):
        category = "REAL_PERSON"
    return category


def trash_email(service, message_id: str) -> None:
    """Move an email to Trash."""
    service.users().messages().trash(userId="me", id=message_id).execute()
    logger.debug("Trashed message id=%s", message_id)


def star_email(service, message_id: str) -> None:
    """Add the STARRED label to an email."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": ["STARRED"]},
    ).execute()
    logger.debug("Starred message id=%s", message_id)


async def create_draft_reply(service, ai, sender: str, subject: str, body: str) -> str:
    """Generate an AI reply and save it as a Gmail draft. Returns the draft ID."""
    prompt = (
        "Write a short professional reply to this email. 2-4 sentences max. Be direct and natural.\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Body: {body}"
    )
    messages = [
        {"role": "system", "content": "You write concise, professional email replies."},
        {"role": "user", "content": prompt},
    ]
    reply_text = await ai.chat(messages)

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    mime_msg = MIMEText(reply_text)
    mime_msg["To"] = sender
    mime_msg["Subject"] = reply_subject

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    draft_id = draft.get("id", "")
    logger.debug("Created draft id=%s for subject='%s'", draft_id, subject)
    return draft_id


def ensure_processed_label(service) -> str:
    """Get or create the ReminderAgent label, returning its ID."""
    labels_result = service.users().labels().list(userId="me").execute()
    for label in labels_result.get("labels", []):
        if label["name"] == PROCESSED_LABEL:
            return label["id"]

    new_label = (
        service.users()
        .labels()
        .create(userId="me", body={"name": PROCESSED_LABEL})
        .execute()
    )
    logger.info("Created Gmail label '%s' id=%s", PROCESSED_LABEL, new_label["id"])
    return new_label["id"]


def mark_processed(service, message_id: str, label_id: str) -> None:
    """Apply the ReminderAgent label to prevent reprocessing."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def search_gmail(service, query: str, max_results: int = 20) -> list[dict]:
    """Search Gmail with a raw query string. Returns list of {id, sender, subject, snippet, thread_id}."""
    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    messages = result.get("messages", [])
    emails = []
    for msg in messages:
        msg_data = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="metadata",
                 metadataHeaders=["From", "Subject"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg["id"],
            "thread_id": msg_data.get("threadId", ""),
            "sender": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": msg_data.get("snippet", ""),
        })
    return emails
