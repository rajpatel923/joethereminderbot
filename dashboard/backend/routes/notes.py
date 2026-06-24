from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dashboard.backend.database import get_db

router = APIRouter(prefix="/notes", tags=["notes"])


def _note_to_dict(n) -> dict:
    return {
        "id": n.id,
        "content": n.content,
        "created_at": n.created_at.isoformat(),
        "user_id": n.user_id,
    }


class CreateNoteRequest(BaseModel):
    content: str
    user_id: Optional[int] = None


@router.get("")
def list_notes(user_id: Optional[int] = Query(None)):
    db = get_db()
    notes = db.get_all_notes(user_id=user_id)
    return [_note_to_dict(n) for n in notes]


@router.post("", status_code=201)
def create_note(body: CreateNoteRequest):
    db = get_db()
    nid = db.save_note(body.content, user_id=body.user_id)
    return {"id": nid, "message": "Note saved"}


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, user_id: Optional[int] = Query(None)):
    db = get_db()
    deleted = db.delete_note(note_id, user_id=user_id)
    if not deleted:
        raise HTTPException(404, "Note not found")
