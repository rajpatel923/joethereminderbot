import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.memory.database import Database
from src.memory.models import Reminder
from src.ai.client import AIClient
from src.bot.commands import _send_checkin

logger = logging.getLogger(__name__)


def _next_occurrence(reminder: Reminder) -> Optional[datetime]:
    """Compute next fire time for a recurring reminder."""
    rule = reminder.recurrence_rule
    if not rule:
        return None
    base = reminder.remind_at
    if rule == "daily":
        nxt = base + timedelta(days=1)
    elif rule == "weekly":
        nxt = base + timedelta(weeks=1)
    elif rule == "monthly":
        # Advance month by 1, clamp day if needed
        month = base.month + 1
        year = base.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(base.day, max_day)
        nxt = base.replace(year=year, month=month, day=day)
    else:
        return None

    if reminder.recurrence_end and nxt > reminder.recurrence_end:
        return None
    return nxt


async def _generate_followup_text(ai: AIClient, reminder: Reminder) -> str:
    """Generate an AI follow-up message for a reminder."""
    priority_label = {1: "low", 2: "medium", 3: "high"}.get(reminder.priority, "medium")
    prompt = (
        f"Generate a casual 1-line follow-up for someone who was reminded to "
        f"'{reminder.content}' (priority: {priority_label}, category: {reminder.category}). "
        f"Sound like a friend texting. No emojis unless natural. Keep it under 15 words."
    )
    messages = [
        {"role": "system", "content": "You text like a friend in your mid-twenties."},
        {"role": "user", "content": prompt},
    ]
    try:
        return await ai.chat(messages)
    except Exception:
        logger.exception("Failed to generate AI follow-up text")
        return f"hey did you get to {reminder.content}?"


def _build_reminder_text(reminder: Reminder) -> str:
    if reminder.reminder_type == "pre_check":
        return f"Hey, you've got 3 hours to {reminder.content} — made any progress yet?"
    elif reminder.reminder_type == "warning":
        return f"15 minutes left! Have you finished {reminder.content}?"
    elif reminder.reminder_type == "deadline":
        return f"It's deadline time — did you get to {reminder.content}?"
    else:
        return f"Hey! Reminder: {reminder.content}"


async def check_reminders(db: Database, ai: AIClient, bot):
    users = db.get_all_allowed_users()

    if not users:
        # Fallback: single-user mode via env var
        chat_id_str = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_ALLOWED_IDS", "").split(",")[0].strip()
        if not chat_id_str:
            return
        chat_id = int(chat_id_str)
        due = db.get_pending_reminders()
        if not due:
            _log_pending(db.get_all_pending_reminders())
            return
        logger.info("Firing %d due reminder(s) [single-user fallback]", len(due))
        for reminder in due:
            await _fire_reminder(reminder, chat_id, db, ai, bot, user_id=None)
        return

    for user in users:
        due = db.get_pending_reminders(user_id=user.id)
        if not due:
            pending = db.get_all_pending_reminders(user_id=user.id)
            if pending:
                _log_pending(pending, user.id)
            continue

        logger.info("Firing %d due reminder(s) for user_id=%d", len(due), user.id)
        for reminder in due:
            await _fire_reminder(reminder, user.telegram_id, db, ai, bot, user_id=user.id)


def _log_pending(pending, user_id=None):
    if pending:
        logger.debug(
            "No due reminders yet (user_id=%s). Pending: %s",
            user_id,
            [(r.id, r.remind_at.isoformat(), r.content[:40]) for r in pending],
        )


async def _fire_reminder(reminder: Reminder, chat_id: int, db: Database, ai: AIClient, bot, user_id=None):
    try:
        text = _build_reminder_text(reminder)
        await bot.send_message(chat_id=chat_id, text=text)
        db.mark_reminder_sent(reminder.id)

        # Handle recurring: schedule next occurrence
        if reminder.recurrence_rule:
            nxt = _next_occurrence(reminder)
            if nxt:
                db.save_reminder(
                    reminder.content,
                    nxt,
                    reminder_type=reminder.reminder_type,
                    needs_followup=reminder.needs_followup,
                    user_id=user_id,
                    priority=reminder.priority,
                    category=reminder.category,
                    recurrence_rule=reminder.recurrence_rule,
                    recurrence_end=reminder.recurrence_end,
                )
                logger.info(
                    "Scheduled next occurrence of recurring reminder id=%d at=%s",
                    reminder.id, nxt.isoformat(),
                )

        if reminder.needs_followup:
            followup_text = await _generate_followup_text(ai, reminder)
            db.create_followup(reminder.content, user_id=user_id)
            await bot.send_message(chat_id=chat_id, text=followup_text)

    except Exception:
        logger.exception("Failed to send reminder id=%d", reminder.id)


async def daily_checkin(db: Database, ai: AIClient, bot):
    users = db.get_all_allowed_users()

    if not users:
        # Fallback single-user
        chat_id_str = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_ALLOWED_IDS", "").split(",")[0].strip()
        if not chat_id_str:
            return
        chat_id = int(chat_id_str)
        logger.info("Running daily check-in (single-user fallback) chat_id=%d", chat_id)
        try:
            await _send_checkin(db, ai, chat_id, bot, user_id=None)
        except Exception:
            logger.exception("Daily check-in failed")
        return

    for user in users:
        logger.info("Running daily check-in for user_id=%d telegram_id=%d", user.id, user.telegram_id)
        try:
            await _send_checkin(db, ai, user.telegram_id, bot, user_id=user.id)
        except Exception:
            logger.exception("Daily check-in failed for user_id=%d", user.id)
