from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dashboard.backend.database import get_db

router = APIRouter(prefix="/reminders", tags=["reminders"])

PRIORITY_MAP = {"low": 1, "medium": 2, "high": 3}
PRIORITY_LABEL = {1: "low", 2: "medium", 3: "high"}


def _reminder_to_dict(r) -> dict:
    return {
        "id": r.id,
        "content": r.content,
        "remind_at": r.remind_at.isoformat(),
        "sent": r.sent,
        "created_at": r.created_at.isoformat(),
        "reminder_type": r.reminder_type,
        "needs_followup": r.needs_followup,
        "user_id": r.user_id,
        "priority": PRIORITY_LABEL.get(r.priority, "medium"),
        "category": r.category,
        "recurrence_rule": r.recurrence_rule,
        "recurrence_end": r.recurrence_end.isoformat() if r.recurrence_end else None,
        "snoozed_until": r.snoozed_until.isoformat() if r.snoozed_until else None,
    }


class CreateReminderRequest(BaseModel):
    content: str
    remind_at: str
    priority: str = "medium"
    category: str = "general"
    user_id: Optional[int] = None
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[str] = None


class UpdateReminderRequest(BaseModel):
    content: Optional[str] = None
    remind_at: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None


class SnoozeRequest(BaseModel):
    minutes: int


@router.get("")
def list_reminders(
    user_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    db = get_db()
    reminders = db.get_all_pending_reminders(user_id=user_id)
    if category:
        reminders = [r for r in reminders if r.category == category]
    if priority:
        p = PRIORITY_MAP.get(priority.lower())
        if p:
            reminders = [r for r in reminders if r.priority == p]
    return [_reminder_to_dict(r) for r in reminders]


@router.post("", status_code=201)
def create_reminder(body: CreateReminderRequest):
    db = get_db()
    try:
        remind_at = datetime.fromisoformat(body.remind_at)
    except ValueError:
        raise HTTPException(400, "Invalid remind_at format (use ISO 8601)")
    p = PRIORITY_MAP.get(body.priority.lower(), 2)
    recurrence_end = None
    if body.recurrence_end:
        try:
            recurrence_end = datetime.fromisoformat(body.recurrence_end)
        except ValueError:
            raise HTTPException(400, "Invalid recurrence_end format")
    rid = db.save_reminder(
        body.content,
        remind_at,
        user_id=body.user_id,
        priority=p,
        category=body.category,
        recurrence_rule=body.recurrence_rule,
        recurrence_end=recurrence_end,
    )
    return {"id": rid, "message": "Reminder created"}


@router.patch("/{reminder_id}")
def update_reminder(reminder_id: int, body: UpdateReminderRequest, user_id: Optional[int] = Query(None)):
    db = get_db()
    kwargs = {}
    if body.content is not None:
        kwargs["content"] = body.content
    if body.remind_at is not None:
        try:
            kwargs["remind_at"] = datetime.fromisoformat(body.remind_at)
        except ValueError:
            raise HTTPException(400, "Invalid remind_at format")
    if body.priority is not None:
        p = PRIORITY_MAP.get(body.priority.lower())
        if p is None:
            raise HTTPException(400, "priority must be low, medium, or high")
        kwargs["priority"] = p
    if body.category is not None:
        kwargs["category"] = body.category
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    updated = db.update_reminder(reminder_id, user_id=user_id, **kwargs)
    if not updated:
        raise HTTPException(404, "Reminder not found")
    return {"message": "Updated"}


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int, user_id: Optional[int] = Query(None)):
    db = get_db()
    deleted = db.delete_reminder(reminder_id, user_id=user_id)
    if not deleted:
        raise HTTPException(404, "Reminder not found")


@router.post("/{reminder_id}/snooze")
def snooze_reminder(reminder_id: int, body: SnoozeRequest, user_id: Optional[int] = Query(None)):
    from datetime import timedelta
    db = get_db()
    until_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=body.minutes)
    snoozed = db.snooze_reminder(reminder_id, until_dt, user_id=user_id)
    if not snoozed:
        raise HTTPException(404, "Reminder not found")
    return {"message": f"Snoozed for {body.minutes} minutes"}
