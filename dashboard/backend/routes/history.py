from typing import Optional

from fastapi import APIRouter, Query

from dashboard.backend.database import get_db

router = APIRouter(prefix="/history", tags=["history"])

PRIORITY_LABEL = {1: "low", 2: "medium", 3: "high"}


@router.get("")
def get_history(user_id: Optional[int] = Query(None), limit: int = Query(20, ge=1, le=100)):
    db = get_db()
    reminders = db.get_reminder_history(user_id=user_id, limit=limit)
    return [
        {
            "id": r.id,
            "content": r.content,
            "remind_at": r.remind_at.isoformat(),
            "created_at": r.created_at.isoformat(),
            "reminder_type": r.reminder_type,
            "priority": PRIORITY_LABEL.get(r.priority, "medium"),
            "category": r.category,
            "user_id": r.user_id,
        }
        for r in reminders
    ]
