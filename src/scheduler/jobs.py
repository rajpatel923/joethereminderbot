import logging
import os

from src.memory.database import Database
from src.ai.client import AIClient
from src.bot.commands import _send_checkin

logger = logging.getLogger(__name__)


async def check_reminders(db: Database, ai: AIClient, bot):
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    due = db.get_pending_reminders()
    if not due:
        pending = db.get_all_pending_reminders()
        if pending:
            logger.debug(
                "No due reminders yet. Pending: %s",
                [(r.id, r.remind_at.isoformat(), r.content[:40]) for r in pending],
            )
        return

    logger.info("Firing %d due reminder(s)", len(due))
    for reminder in due:
        try:
            if reminder.reminder_type == "pre_check":
                text = f"Hey, you've got 3 hours to {reminder.content} — made any progress yet?"
            elif reminder.reminder_type == "warning":
                text = f"15 minutes left! Have you finished {reminder.content}?"
            elif reminder.reminder_type == "deadline":
                text = f"It's deadline time — did you get to {reminder.content}?"
            else:
                text = f"Hey! Reminder: {reminder.content}"

            await bot.send_message(chat_id=chat_id, text=text)
            db.mark_reminder_sent(reminder.id)

            if reminder.needs_followup:
                db.create_followup(reminder.content)
        except Exception:
            logger.exception("Failed to send reminder id=%d", reminder.id)


async def daily_checkin(db: Database, ai: AIClient, bot):
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    logger.info("Running daily check-in for chat_id=%d", chat_id)
    try:
        await _send_checkin(db, ai, chat_id, bot)
    except Exception:
        logger.exception("Daily check-in failed")
