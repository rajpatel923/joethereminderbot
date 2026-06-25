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


def make_tools(db, tz: str, user_id: Optional[int] = None, ai=None) -> list:

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

    INTERNAL_TYPES = ("pre_check", "warning")

    @lc_tool
    def list_reminders_filtered(category: str = "", priority: str = "", due_today: bool = False) -> str:
        """List pending reminders filtered by category, priority, or whether they're due today.
        category: filter by category tag (e.g. 'work', 'health'). Leave blank for all.
        priority: filter by priority 'low', 'medium', or 'high'. Leave blank for all.
        due_today: if True, only return reminders due today in the user's local timezone."""
        from zoneinfo import ZoneInfo
        reminders = db.get_all_pending_reminders(user_id=user_id)
        reminders = [r for r in reminders if r.reminder_type not in INTERNAL_TYPES]
        if category.strip():
            reminders = [r for r in reminders if r.category.lower() == category.strip().lower()]
        if priority.strip():
            p = PRIORITY_MAP.get(priority.strip().lower())
            if p is not None:
                reminders = [r for r in reminders if r.priority == p]
        if due_today:
            local_today = datetime.now(ZoneInfo(tz)).date()
            reminders = [
                r for r in reminders
                if r.remind_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date() == local_today
            ]
        if not reminders:
            filters = []
            if category.strip():
                filters.append(f"category='{category}'")
            if priority.strip():
                filters.append(f"priority='{priority}'")
            if due_today:
                filters.append("due today")
            desc = ", ".join(filters) if filters else "any filters"
            return f"No reminders matching {desc}"
        return "\n".join(
            f"#{r.id} [{PRIORITY_LABEL.get(r.priority, 'med')}/{r.category}] "
            f"{r.remind_at.strftime('%b %d %I:%M %p')}: {r.content}"
            for r in reminders
        )

    @lc_tool
    def bulk_delete_reminders(keyword: str = "", category: str = "") -> str:
        """Delete multiple pending reminders at once.
        keyword: only delete reminders whose content contains this word (optional).
        category: only delete reminders with this category tag (optional).
        If both are blank, deletes ALL pending reminders — confirm with the user first."""
        reminders = db.get_all_pending_reminders(user_id=user_id)
        reminders = [r for r in reminders if r.reminder_type not in INTERNAL_TYPES]
        if keyword.strip():
            reminders = [r for r in reminders if keyword.lower() in r.content.lower()]
        if category.strip():
            reminders = [r for r in reminders if r.category.lower() == category.strip().lower()]
        if not reminders:
            return "No matching reminders to delete."
        for r in reminders:
            db.delete_reminder(r.id, user_id=user_id)
        desc = []
        if keyword.strip():
            desc.append(f"keyword='{keyword}'")
        if category.strip():
            desc.append(f"category='{category}'")
        desc_str = ", ".join(desc) if desc else "all"
        return f"Deleted {len(reminders)} reminder(s) matching {desc_str}"

    @lc_tool
    async def trigger_gmail_scan() -> str:
        """Scan Gmail inbox right now: classify emails, trash spam/marketing, star important ones,
        and create reply drafts for real-person and important emails."""
        if ai is None:
            return "AI client not available — cannot run Gmail scan."
        if user_id is None:
            return "Gmail scan requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google not connected. Use /calendar to authenticate first."
        try:
            from src.integrations.gmail import (
                get_gmail_service, get_unread_emails, get_email_body,
                classify_email, trash_email, star_email, create_draft_reply,
                ensure_processed_label, mark_processed,
            )
            service = get_gmail_service(tokens, db, user_id)
            label_id = ensure_processed_label(service)
            emails = get_unread_emails(service)
        except Exception as e:
            logger.exception("Gmail scan setup failed")
            return f"Couldn't connect to Gmail: {e}"

        if not emails:
            return "Inbox is clear — no unread emails to process."

        counts = {"spam": 0, "marketing": 0, "real": 0, "important": []}
        for email in emails:
            try:
                category = await classify_email(ai, email["sender"], email["subject"], email["snippet"])
                if category == "SPAM":
                    trash_email(service, email["id"])
                    counts["spam"] += 1
                elif category == "MARKETING":
                    trash_email(service, email["id"])
                    counts["marketing"] += 1
                elif category == "REAL_PERSON":
                    body = get_email_body(service, email["id"])
                    await create_draft_reply(service, ai, email["sender"], email["subject"], body)
                    counts["real"] += 1
                elif category == "IMPORTANT":
                    body = get_email_body(service, email["id"])
                    star_email(service, email["id"])
                    await create_draft_reply(service, ai, email["sender"], email["subject"], body)
                    counts["important"].append(f'"{email["subject"]}" from {email["sender"]}')
                mark_processed(service, email["id"], label_id)
            except Exception:
                logger.exception("Failed to process email id=%s", email["id"])

        spam_total = counts["spam"] + counts["marketing"]
        draft_total = counts["real"] + len(counts["important"])
        total = spam_total + draft_total
        if total == 0:
            return "No emails needed processing."
        lines = [f"Inbox scan complete ({total} email{'s' if total != 1 else ''} processed):"]
        if spam_total:
            lines.append(f"- {spam_total} spam/marketing trashed")
        if draft_total:
            lines.append(f"- {draft_total} reply draft{'s' if draft_total != 1 else ''} created (check Gmail Drafts)")
        for item in counts["important"]:
            lines.append(f"- Important: {item}")
        return "\n".join(lines)

    @lc_tool
    def get_email_summary() -> str:
        """Get a read-only snapshot of Gmail inbox: unread count and sender/subject list.
        Does NOT process, trash, or modify any emails."""
        if user_id is None:
            return "Gmail requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google not connected. Use /calendar to authenticate first."
        try:
            from src.integrations.gmail import get_gmail_service, search_gmail
            service = get_gmail_service(tokens, db, user_id)
            emails = search_gmail(service, "is:unread in:inbox", max_results=20)
        except Exception as e:
            logger.exception("Failed to fetch email summary")
            return f"Couldn't fetch inbox: {e}"
        if not emails:
            return "No unread emails in inbox."
        lines = [f"You have {len(emails)} unread email{'s' if len(emails) != 1 else ''}:"]
        for e in emails:
            lines.append(f"- From {e['sender']}: {e['subject']}")
        return "\n".join(lines)

    @lc_tool
    def search_emails(query: str) -> str:
        """Search Gmail using a query string (Gmail syntax supported).
        query: Gmail search query, e.g. 'from:john@example.com', 'subject:invoice', 'recruiter'.
        The LLM should construct this from the user's natural language request."""
        if user_id is None:
            return "Gmail requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google not connected. Use /calendar to authenticate first."
        try:
            from src.integrations.gmail import get_gmail_service, search_gmail
            service = get_gmail_service(tokens, db, user_id)
            emails = search_gmail(service, query, max_results=10)
        except Exception as e:
            logger.exception("Failed to search Gmail")
            return f"Couldn't search Gmail: {e}"
        if not emails:
            return f"No emails found matching '{query}'"
        lines = [f"Found {len(emails)} email{'s' if len(emails) != 1 else ''} for '{query}':"]
        for e in emails:
            preview = e["snippet"][:80] + "…" if len(e["snippet"]) > 80 else e["snippet"]
            lines.append(f"- From {e['sender']}: {e['subject']}\n  {preview}")
        return "\n".join(lines)

    @lc_tool
    def delete_calendar_event(title_keyword: str) -> str:
        """Delete an upcoming Google Calendar event by searching its title.
        title_keyword: a word or phrase from the event title to search for."""
        if user_id is None:
            return "Calendar integration requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google Calendar not connected. Use /calendar to authenticate."
        try:
            from src.integrations.google_calendar import get_calendar_service, find_event_by_title, delete_event as _delete_event
            service = get_calendar_service(tokens, db, user_id)
            event = find_event_by_title(service, title_keyword)
            if not event:
                return f"No upcoming event found matching '{title_keyword}'"
            _delete_event(service, event["id"])
            # Format the start time nicely if possible
            try:
                start_dt = datetime.fromisoformat(event["start"]).astimezone(ZoneInfo(tz))
                start_str = start_dt.strftime("%b %d at %I:%M %p %Z")
            except Exception:
                start_str = event["start"]
            return f"Deleted '{event['summary']}' (was scheduled for {start_str})"
        except Exception as e:
            logger.exception("Failed to delete calendar event")
            return f"Couldn't delete event: {e}"

    @lc_tool
    def edit_calendar_event(title_keyword: str, new_time_iso: str = "", new_title: str = "") -> str:
        """Edit an upcoming calendar event's time and/or title.
        title_keyword: a word or phrase from the event title to search for.
        new_time_iso: new start time (ISO 8601 or natural language like '5pm tomorrow'). Leave blank to keep current.
        new_title: replacement event title. Leave blank to keep current.
        At least one of new_time_iso or new_title must be provided."""
        if not new_time_iso.strip() and not new_title.strip():
            return "Nothing to update — provide new_time_iso or new_title."
        if user_id is None:
            return "Calendar integration requires a logged-in user."
        tokens = db.get_google_tokens(user_id)
        if not tokens:
            return "Google Calendar not connected. Use /calendar to authenticate."
        try:
            from src.integrations.google_calendar import get_calendar_service, find_event_by_title, update_event as _update_event
            service = get_calendar_service(tokens, db, user_id)
            event = find_event_by_title(service, title_keyword)
            if not event:
                return f"No upcoming event found matching '{title_keyword}'"
            new_start_dt = None
            new_end_dt = None
            if new_time_iso.strip():
                new_start_dt = _parse_dt(new_time_iso, tz)
                if not new_start_dt:
                    return f"Couldn't parse new time: {new_time_iso}"
                new_start_local = new_start_dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
                new_end_local = new_start_local + timedelta(hours=1)
                new_end_dt = new_end_local
            _update_event(
                service, event["id"],
                new_title=new_title.strip(),
                new_start_dt=new_start_local if new_start_dt else None,
                new_end_dt=new_end_local if new_end_dt else None,
            )
            parts = []
            if new_title.strip():
                parts.append(f"title → '{new_title.strip()}'")
            if new_start_dt:
                parts.append(f"time → {new_start_local.strftime('%b %d at %I:%M %p %Z')}")
            return f"Updated '{event['summary']}': {', '.join(parts)}"
        except Exception as e:
            logger.exception("Failed to edit calendar event")
            return f"Couldn't update event: {e}"

    return [
        get_current_time,
        save_reminder,
        save_deadline_reminders,
        save_recurring_reminder,
        save_note,
        list_notes,
        list_reminders,
        list_reminders_filtered,
        bulk_delete_reminders,
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
        delete_calendar_event,
        edit_calendar_event,
        trigger_gmail_scan,
        get_email_summary,
        search_emails,
    ]
