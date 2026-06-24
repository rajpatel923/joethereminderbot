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
/checkin — Get your morning summary right now
/help — Show this message"""


def _allowed(update: Update) -> bool:
    allowed_id = int(os.environ["TELEGRAM_CHAT_ID"])
    return update.effective_chat.id == allowed_id


class CommandHandler:
    def __init__(self, db: Database, ai: AIClient):
        self.db = db
        self.ai = ai
        self._tz = os.environ.get("TIMEZONE", "America/Toronto")

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
        note_id = self.db.save_note(text)
        await update.message.reply_text(f"Got it, I'll remember that (note #{note_id}).")
        logger.info("Saved note id=%d", note_id)

    async def notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        all_notes = self.db.get_all_notes()
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
        if self.db.delete_note(note_id):
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

        # Try progressively longer prefixes to find the time expression
        remind_at = None
        message_start = 1
        for i in range(1, len(context.args)):
            time_str = " ".join(context.args[:i])
            parsed = dateparser.parse(
                time_str,
                settings={"PREFER_DATES_FROM": "future", "TIMEZONE": self._tz},
            )
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo(self._tz))
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

        reminder_id = self.db.save_reminder(content, remind_at)
        time_str = remind_at.strftime("%b %d at %I:%M %p")
        await update.message.reply_text(
            f"Reminder set! I'll ping you on {time_str} about: {content} (#{reminder_id})"
        )
        logger.info("Saved reminder id=%d at=%s", reminder_id, remind_at)

    async def reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        pending = self.db.get_all_pending_reminders()
        if not pending:
            await update.message.reply_text("No pending reminders.")
            return
        lines = [
            f"#{r.id} — {r.remind_at.strftime('%b %d %I:%M %p')} — {r.content}"
            for r in pending
        ]
        await update.message.reply_text("Upcoming reminders:\n" + "\n".join(lines))

    async def checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _allowed(update):
            return
        await _send_checkin(self.db, self.ai, update.effective_chat.id, context.bot)


async def _send_checkin(db: Database, ai: AIClient, chat_id: int, bot):
    notes = db.get_all_notes()
    reminders = db.get_all_pending_reminders()

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
