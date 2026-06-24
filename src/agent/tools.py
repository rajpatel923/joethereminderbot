import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
from langchain_core.tools import tool as lc_tool

logger = logging.getLogger(__name__)


def _parse_dt(s: str, tz: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        dt = dateparser.parse(s, settings={"TIMEZONE": tz, "PREFER_DATES_FROM": "future"})

    if dt is None:
        return None

    # Normalize to UTC so DB comparisons are consistent
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def make_tools(db, tz: str) -> list:
    @lc_tool
    def save_reminder(content: str, remind_at_iso: str) -> str:
        """Save a single reminder at a specific point in time.
        content: what to remind about.
        remind_at_iso: ISO 8601 datetime string for when to fire the reminder."""
        dt = _parse_dt(remind_at_iso, tz)
        if not dt:
            return f"Couldn't parse time: {remind_at_iso}"
        rid = db.save_reminder(content, dt)
        return f"Reminder #{rid} saved for {dt.strftime('%b %d at %I:%M %p')}"

    @lc_tool
    def save_deadline_reminders(content: str, deadline_iso: str) -> str:
        """Save staged reminders for a hard deadline: a check-in 3 hours before,
        a warning 15 minutes before, and a follow-up at the deadline itself.
        content: the task/goal.
        deadline_iso: ISO 8601 datetime string for the deadline."""
        deadline = _parse_dt(deadline_iso, tz)
        if not deadline:
            return f"Couldn't parse deadline: {deadline_iso}"
        db.save_deadline_reminders(content, deadline)
        pre = (deadline - timedelta(hours=3)).strftime("%I:%M %p")
        warn = (deadline - timedelta(minutes=15)).strftime("%I:%M %p")
        end = deadline.strftime("%I:%M %p")
        return f"Set 3 reminders for '{content}': check-in at {pre}, warning at {warn}, deadline follow-up at {end}."

    @lc_tool
    def save_note(content: str) -> str:
        """Save a long-term fact or note about the user (things to always remember).
        content: the fact to save."""
        nid = db.save_note(content)
        return f"Saved note #{nid}"

    @lc_tool
    def list_notes() -> str:
        """List all saved notes and facts about the user."""
        notes = db.get_all_notes()
        if not notes:
            return "No notes saved yet."
        return "\n".join(f"#{n.id}: {n.content}" for n in notes)

    @lc_tool
    def list_reminders() -> str:
        """List all pending (unsent) reminders."""
        reminders = db.get_all_pending_reminders()
        if not reminders:
            return "No pending reminders."
        return "\n".join(
            f"#{r.id} [{r.reminder_type}] {r.remind_at.strftime('%b %d %I:%M %p')}: {r.content}"
            for r in reminders
        )

    @lc_tool
    def delete_note(note_id: int) -> str:
        """Delete a saved note by its numeric ID.
        note_id: the integer ID of the note to delete."""
        if db.delete_note(note_id):
            return f"Deleted note #{note_id}"
        return f"Note #{note_id} not found"

    @lc_tool
    def get_current_time(timezone: str = "") -> str:
        """Get the current date and time. Optionally in a specific IANA timezone (e.g. 'America/Chicago').
        If no timezone is given, uses the user's configured timezone."""
        target_tz = timezone.strip() or tz
        try:
            now = datetime.now(ZoneInfo(target_tz))
            return now.strftime(f"%A, %B %d %Y %I:%M %p (%Z, {target_tz})")
        except ZoneInfoNotFoundError:
            return f"Unknown timezone '{target_tz}'. Use an IANA name like 'America/Chicago'."

    @lc_tool
    def mark_done(content_keyword: str) -> str:
        """Mark unsent reminders matching a keyword as done/completed.
        Use when the user says they finished something or it no longer applies.
        content_keyword: a word or phrase from the reminder content to match."""
        reminders = db.get_all_pending_reminders()
        matched = [r for r in reminders if content_keyword.lower() in r.content.lower()]
        if not matched:
            return f"No pending reminders matching '{content_keyword}'"
        for r in matched:
            db.mark_reminder_sent(r.id)
        return f"Marked {len(matched)} reminder(s) as done"

    return [
        get_current_time,
        save_reminder,
        save_deadline_reminders,
        save_note,
        list_notes,
        list_reminders,
        delete_note,
        mark_done,
    ]
