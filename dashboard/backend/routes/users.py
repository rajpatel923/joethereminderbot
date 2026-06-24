from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dashboard.backend.database import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users():
    db = get_db()
    users = db.get_all_allowed_users()
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "timezone": u.timezone,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


class UpdateTimezoneRequest(BaseModel):
    timezone: str


@router.patch("/{user_id}/timezone")
def update_timezone(user_id: int, body: UpdateTimezoneRequest):
    db = get_db()
    db.update_user_timezone(user_id, body.timezone)
    return {"message": "Timezone updated"}
