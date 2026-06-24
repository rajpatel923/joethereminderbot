import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import dateparser
from telegram import Update
from telegram.ext import ContextTypes

from src.memory.database import Database
from src.ai.client import AIClient
from src.ai.prompts import CHECKIN_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

HELP_TEXT = """Here's what I can do:

/note <text> — Save a fact I should remember
/notes — List all saved notes
/forget <id> — Delete a note by its ID
/remind <time> <message> — Set a reminder (e.g. /remind in 2 hours drink water)
/reminders — List your pending reminders
/history — Show recently sent reminders
/checkin — Get your morning summary right now
/calendar — Connect Google Calendar
/calauth <code> — Complete Google Calendar setup
/help — Show this message"""


def _parse_allowed_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_IDS", "").strip()
    if raw:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    fallback = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if fallback:
        return {int(fallback)}
    return set()


_ALLOWED_IDS = _parse_allowed_ids()


def _allowed(update: Update) -> bool:
    if not _ALLOWED_IDS:
        return True
    return update.effective_chat.id in _ALLOWED_IDS


class CommandHandler:
    def __init__(self, db: Database, ai: AIClient):
        self.db = db
        self.ai = ai
        self._tz = os.environ.get("TIMEZONE", "America/Chicago")
        self._pending_oauth_flows: dict[int, object] = {}  # user_id -> Flow

    def _get_user(self, update: Update):
        return self.db.get_or_create_user(update.effective_chat.id, self._tz)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        await update.message.reply_text(
            "Hey! I'm your personal reminder assistant. "
            "Just talk to me normally, or use /help to see commands."
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        await update.message.reply_text(HELP_TEXT)

    async def note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        text = " ".join(context.args).strip()
        if not text:
            await update.message.reply_text("Usage: /note <something to remember>")
            return
        user = self._get_user(update)
        note_id = self.db.save_note(text, user_id=user.id)
        await update.message.reply_text(f"Got it, I'll remember that (note #{note_id}).")

    async def notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        user = self._get_user(update)
        all_notes = self.db.get_all_notes(user_id=user.id)
        if not all_notes:
            await update.message.reply_text("You haven't saved any notes yet.")
            return
        lines = [f"#{n.id} — {n.content}" for n in all_notes]
        await update.message.reply_text("Your notes:\n" + "\n".join(lines))

    async def forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /forget <note id>")
            return
        try:
            note_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please give me a numeric note ID.")
            return
        user = self._get_user(update)
        if self.db.delete_note(note_id, user_id=user.id):
            await update.message.reply_text(f"Done, note #{note_id} is gone.")
        else:
            await update.message.reply_text(f"Couldn't find note #{note_id}.")

    async def remind(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /remind <time> <message>\nExample: /remind in 2 hours drink water"
            )
            return

        tz = self._tz
        remind_at = None
        message_start = 1
        for i in range(1, len(context.args)):
            time_str = " ".join(context.args[:i])
            parsed = dateparser.parse(
                time_str,
                settings={"PREFER_DATES_FROM": "future", "TIMEZONE": tz},
            )
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo(tz))
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            if parsed and parsed > datetime.now(timezone.utc).replace(tzinfo=None):
                remind_at = parsed
                message_start = i
            else:
                break

        if not remind_at:
            await update.message.reply_text(
                "I couldn't figure out when that is. Try something like "
                "'in 2 hours', 'tomorrow at 9am', or 'next Monday'."
            )
            return

        content = " ".join(context.args[message_start:]).strip()
        if not content:
            await update.message.reply_text("What should I remind you about?")
            return

        user = self._get_user(update)
        reminder_id = self.db.save_reminder(content, remind_at, user_id=user.id)
        time_str = remind_at.strftime("%b %d at %I:%M %p")
        await update.message.reply_text(
            f"Reminder set! I'll ping you on {time_str} about: {content} (#{reminder_id})"
        )

    async def reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        user = self._get_user(update)
        all_pending = self.db.get_all_pending_reminders(user_id=user.id)
        pending = [r for r in all_pending if r.reminder_type not in ("pre_check", "warning")]
        if not pending:
            await update.message.reply_text("No pending reminders.")
            return
        lines = [
            f"#{r.id} — {r.remind_at.strftime('%b %d %I:%M %p')} [{r.category}] — {r.content}"
            for r in pending
        ]
        await update.message.reply_text("Upcoming reminders:\n" + "\n".join(lines))

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        user = self._get_user(update)
        sent = self.db.get_reminder_history(user_id=user.id, limit=15)
        if not sent:
            await update.message.reply_text("No reminder history yet.")
            return
        lines = [
            f"#{r.id} — {r.remind_at.strftime('%b %d %I:%M %p')} — {r.content}"
            for r in sent
        ]
        await update.message.reply_text("Recent reminders:\n" + "\n".join(lines))

    async def calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        user = self._get_user(update)
        try:
            from src.integrations.google_calendar import create_oauth_flow, get_auth_url
            flow = create_oauth_flow()
            auth_url = get_auth_url(flow)
            self._pending_oauth_flows[user.id] = flow
            await update.message.reply_text(
                f"Visit this URL to connect Google Calendar:\n{auth_url}\n\n"
                "Then send /calauth <code> with the authorization code you receive."
            )
        except Exception:
            logger.exception("Failed to start OAuth flow")
            await update.message.reply_text(
                "Couldn't start Google Calendar auth. Make sure GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI are set in .env"
            )

    async def calauth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /calauth <authorization code>")
            return
        code = context.args[0].strip()
        user = self._get_user(update)
        flow = self._pending_oauth_flows.pop(user.id, None)
        if not flow:
            await update.message.reply_text(
                "No pending auth session found. Run /calendar first to get an auth URL."
            )
            return
        try:
            from src.integrations.google_calendar import exchange_code_for_tokens
            token_data = exchange_code_for_tokens(flow, code)
            from datetime import datetime as dt
            expiry = None
            if token_data.get("expiry"):
                expiry = dt.fromisoformat(token_data["expiry"])
            self.db.save_google_tokens(
                user.id,
                token_data["access_token"],
                token_data.get("refresh_token", ""),
                expiry,
            )
            await update.message.reply_text(
                "Google Calendar connected! You can now ask me to create or list calendar events."
            )
        except Exception as e:
            logger.exception("Failed to exchange OAuth code")
            await update.message.reply_text(f"Auth failed: {e}")

    async def checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        user = self._get_user(update)
        await _send_checkin(self.db, self.ai, update.effective_chat.id, context.bot, user_id=user.id)


async def _send_checkin(db: Database, ai: AIClient, chat_id: int, bot, user_id=None):
    notes = db.get_all_notes(user_id=user_id)
    reminders = db.get_all_pending_reminders(user_id=user_id)

    notes_text = "\n".join(f"- {n.content}" for n in notes) or "None"
    reminders_text = (
        "\n".join(
            f"- {r.remind_at.strftime('%b %d %I:%M %p')}: {r.content}"
            for r in reminders
        )
        or "None"
    )

    prompt = CHECKIN_PROMPT_TEMPLATE.format(
        notes=notes_text, reminders=reminders_text
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Morning check-in please"},
    ]
    summary = await ai.chat(messages)
    logger.info("Sending daily check-in to chat_id=%d", chat_id)
    await bot.send_message(chat_id=chat_id, text=summary)
