import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
from langchain_core.tools import tool as lc_tool

logger = logging.getLogger(__name__)

PRIORITY_MAP = {"low": 1, "medium": 2, "high": 3}
PRIORITY_LABEL = {1: "low", 2: "medium", 3: "high"}


def _parse_dt(s: str, tz: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        dt = dateparser.parse(s, settings={"TIMEZONE": tz, "PREFER_DATES_FROM": "future"})

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _find_reminders(db, keyword: str, user_id: Optional[int]):
    reminders = db.get_all_pending_reminders(user_id=user_id)
    return [r for r in reminders if keyword.lower() in r.content.lower()]


def make_tools(db, tz: str, user_id: Optional[int] = None) -> list:

    @lc_tool
    def save_reminder(
        content: str,
        remind_at_iso: str,
        priority: str = "medium",
        category: str = "general",
    ) -> str:
        """Save a single reminder at a specific point in time.
        content: what to remind about.
        remind_at_iso: ISO 8601 datetime or natural language like 'tomorrow at 9am'.
        priority: 'low', 'medium', or 'high' (default: medium).
        category: tag like 'work', 'health', 'personal', etc. (default: general)."""
        dt = _parse_dt(remind_at_iso, tz)
        if not dt:
            return f"Couldn't parse time: {remind_at_iso}"
        p = PRIORITY_MAP.get(priority.lower(), 2)
        rid = db.save_reminder(content, dt, user_id=user_id, priority=p, category=category)
        dt_local = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        logger.info("Saved reminder #%d: '%s' at %s", rid, content, dt_local.isoformat())
        return f"Reminder #{rid} saved for {dt_local.strftime('%b %d at %I:%M %p %Z')} [{priority}/{category}]"

    @lc_tool
    def save_deadline_reminders(content: str, deadline_iso: str) -> str:
        """Save staged reminders for a hard deadline: a check-in 3 hours before,
        a warning 15 minutes before, and a follow-up at the deadline itself.
        content: the task/goal.
        deadline_iso: ISO 8601 datetime string for the deadline."""
        deadline = _parse_dt(deadline_iso, tz)
        if not deadline:
            return f"Couldn't parse deadline: {deadline_iso}"
        db.save_deadline_reminders(content, deadline, user_id=user_id)
        pre = (deadline - timedelta(hours=3)).strftime("%I:%M %p")
        warn = (deadline - timedelta(minutes=15)).strftime("%I:%M %p")
        end = deadline.strftime("%I:%M %p")
        return f"Set 3 reminders for '{content}': check-in at {pre}, warning at {warn}, deadline follow-up at {end}."

    @lc_tool
    def save_recurring_reminder(
        content: str,
        start_iso: str,
        recurrence_rule: str,
        recurrence_end_iso: str = "",
    ) -> str:
        """Save a recurring reminder.
        content: what to remind about.
        start_iso: first occurrence datetime (ISO 8601 or natural language).
        recurrence_rule: 'daily', 'weekly', or 'monthly'.
        recurrence_end_iso: optional end date (ISO 8601); leave blank for forever."""
        dt = _parse_dt(start_iso, tz)
        if not dt:
            return f"Couldn't parse start time: {start_iso}"
        if recurrence_rule not in ("daily", "weekly", "monthly"):
            return "recurrence_rule must be 'daily', 'weekly', or 'monthly'."
        end_dt = _parse_dt(recurrence_end_iso, tz) if recurrence_end_iso.strip() else None
        rid = db.save_reminder(
            content, dt,
            user_id=user_id,
            recurrence_rule=recurrence_rule,
            recurrence_end=end_dt,
        )
        dt_local = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        end_str = f" until {end_dt.strftime('%b %d')}" if end_dt else " forever"
        return f"Recurring reminder #{rid} set: '{content}' starting {dt_local.strftime('%b %d at %I:%M %p %Z')}, repeating {recurrence_rule}{end_str}."

    @lc_tool
    def delete_reminder(keyword: str) -> str:
        """Delete pending reminders matching a keyword.
        keyword: a word or phrase from the reminder content to match."""
        matched = _find_reminders(db, keyword, user_id)
        if not matched:
            return f"No pending reminders matching '{keyword}'"
        for r in matched:
            db.delete_reminder(r.id, user_id=user_id)
        return f"Deleted {len(matched)} reminder(s) matching '{keyword}'"

    @lc_tool
    def edit_reminder(
        keyword: str,
        new_content: str = "",
        new_time_iso: str = "",
    ) -> str:
        """Edit an existing reminder's content and/or time.
        keyword: a word or phrase from the reminder content to match.
        new_content: replacement text (leave blank to keep current).
        new_time_iso: new time (ISO 8601 or natural language; leave blank to keep current)."""
        matched = _find_reminders(db, keyword, user_id)
        if not matched:
            return f"No pending reminders matching '{keyword}'"
        kwargs = {}
        if new_content.strip():
            kwargs["content"] = new_content.strip()
        if new_time_iso.strip():
            dt = _parse_dt(new_time_iso, tz)
            if not dt:
                return f"Couldn't parse new time: {new_time_iso}"
            kwargs["remind_at"] = dt
        if not kwargs:
            return "Nothing to update — provide new_content or new_time_iso."
        for r in matched:
            db.update_reminder(r.id, user_id=user_id, **kwargs)
        parts = []
        if "content" in kwargs:
            parts.append(f"content → '{kwargs['content']}'")
        if "remind_at" in kwargs:
            dt_local = kwargs["remind_at"].replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
            parts.append(f"time → {dt_local.strftime('%b %d at %I:%M %p %Z')}")
        return f"Updated {len(matched)} reminder(s): {', '.join(parts)}"

    @lc_tool
    def snooze_reminder(keyword: str, snooze_minutes: int) -> str:
        """Snooze a reminder by N minutes. It won't re-fire until the snooze expires.
        keyword: a word or phrase from the reminder content to match.
        snooze_minutes: how many minutes to snooze."""
        matched = _find_reminders(db, keyword, user_id)
        if not matched:
            return f"No pending reminders matching '{keyword}'"
        until_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=snooze_minutes)
        for r in matched:
            db.snooze_reminder(r.id, until_dt, user_id=user_id)
        return f"Snoozed {len(matched)} reminder(s) for {snooze_minutes} min"

    @lc_tool
    def set_priority(keyword: str, priority: str) -> str:
        """Set the priority on reminders matching a keyword.
        keyword: a word or phrase from the reminder content to match.
        priority: 'low', 'medium', or 'high'."""
        p = PRIORITY_MAP.get(priority.lower())
        if p is None:
            return "priority must be 'low', 'medium', or 'high'."
        matched = _find_reminders(db, keyword, user_id)
        if not matched:
            return f"No pending reminders matching '{keyword}'"
        for r in matched:
            db.update_reminder(r.id, user_id=user_id, priority=p)
        return f"Set priority={priority} on {len(matched)} reminder(s)"

    @lc_tool
    def set_category(keyword: str, category: str) -> str:
        """Tag reminders matching a keyword with a category.
        keyword: a word or phrase from the reminder content to match.
        category: any label, e.g. 'work', 'health', 'personal'."""
        matched = _find_reminders(db, keyword, user_id)
        if not matched:
            return f"No pending reminders matching '{keyword}'"
        for r in matched:
            db.update_reminder(r.id, user_id=user_id, category=category)
        return f"Set category='{category}' on {len(matched)} reminder(s)"

    @lc_tool
    def get_reminder_history(limit: int = 10) -> str:
        """Get the last N sent reminders (history).
        limit: how many to return (default 10)."""
        reminders = db.get_reminder_history(user_id=user_id, limit=limit)
        if not reminders:
            return "No reminder history yet."
        lines = [
            f"#{r.id} [{PRIORITY_LABEL.get(r.priority, 'med')}/{r.category}] "
            f"{r.remind_at.strftime('%b %d %I:%M %p')}: {r.content}"
            for r in reminders
        ]
        return "\n".join(lines)

    @lc_tool
    def save_note(content: str) -> str:
        """Save a long-term fact or note about the user (things to always remember).
        content: the fact to save."""
        nid = db.save_note(content, user_id=user_id)
        return f"Saved note #{nid}"

    @lc_tool
    def list_notes() -> str:
        """List all saved notes and facts about the user."""
        notes = db.get_all_notes(user_id=user_id)
        if not notes:
            return "No notes saved yet."
        return "\n".join(f"#{n.id}: {n.content}" for n in notes)

    @lc_tool
    def list_reminders() -> str:
        """List all pending (unsent) reminders."""
        all_reminders = db.get_all_pending_reminders(user_id=user_id)
        # Hide internal staging reminders (pre_check, warning) — show only user-visible ones
        reminders = [r for r in all_reminders if r.reminder_type not in ("pre_check", "warning")]
        if not reminders:
            return "No pending reminders."
        return "\n".join(
            f"#{r.id} [{PRIORITY_LABEL.get(r.priority, 'med')}/{r.category}] "
            f"{r.remind_at.strftime('%b %d %I:%M %p')}: {r.content}"
            for r in reminders
        )

    @lc_tool
    def delete_note(note_id: int) -> str:
        """Delete a saved note by its numeric ID.
        note_id: the integer ID of the note to delete."""
        if db.delete_note(note_id, user_id=user_id):
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
        reminders = db.get_all_pending_reminders(user_id=user_id)
        matched = [r for r in reminders if content_keyword.lower() in r.content.lower()]
        if not matched:
            return f"No pending reminders matching '{content_keyword}'"
        for r in matched:
            db.mark_reminder_sent(r.id)
        return f"Marked {len(matched)} reminder(s) as done"

    @lc_tool
    def create_calendar_event(title: str, start_iso: str, end_iso: str = "") -> str:
        """Create a Google Calendar event.
        title: event name.
        start_iso: start datetime (ISO 8601 or natural language).
        end_iso: end datetime (optional; defaults to 1 hour after start)."""
        if user_id is None:
            return "Calendar integration requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google Calendar not connected. Use /calendar to authenticate."
        try:
            from src.integrations.google_calendar import get_calendar_service, create_event
            start_dt = _parse_dt(start_iso, tz)
            if not start_dt:
                return f"Couldn't parse start time: {start_iso}"
            start_local = start_dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
            end_local = (
                _parse_dt(end_iso, tz).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
                if end_iso.strip()
                else start_local + timedelta(hours=1)
            )
            service = get_calendar_service(tokens, db, user_id)
            event_id = create_event(service, title, start_local, end_local)
            return f"Calendar event '{title}' created on {start_local.strftime('%b %d at %I:%M %p %Z')} (id: {event_id})"
        except Exception as e:
            logger.exception("Failed to create calendar event")
            return f"Couldn't create calendar event: {e}"

    @lc_tool
    def list_calendar_events(days_ahead: int = 7) -> str:
        """List upcoming Google Calendar events.
        days_ahead: how many days to look ahead (default 7)."""
        if user_id is None:
            return "Calendar integration requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google Calendar not connected. Use /calendar to authenticate."
        try:
            from src.integrations.google_calendar import get_calendar_service, list_events
            service = get_calendar_service(tokens, db, user_id)
            events = list_events(service, days_ahead=days_ahead)
            if not events:
                return f"No events in the next {days_ahead} days."
            lines = [
                f"• {e['start']} — {e['summary']}"
                for e in events
            ]
            return "\n".join(lines)
        except Exception as e:
            logger.exception("Failed to list calendar events")
            return f"Couldn't fetch calendar events: {e}"

    return [
        get_current_time,
        save_reminder,
        save_deadline_reminders,
        save_recurring_reminder,
        save_note,
        list_notes,
        list_reminders,
        delete_note,
        mark_done,
        delete_reminder,
        edit_reminder,
        snooze_reminder,
        set_priority,
        set_category,
        get_reminder_history,
        create_calendar_event,
        list_calendar_events,
    ]
