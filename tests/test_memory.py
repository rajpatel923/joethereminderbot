import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.memory.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(db_path=tmp_path / "test.db")
    d.connect()
    yield d
    d.close()


def test_save_and_retrieve_messages(db):
    db.save_message("user", "hello")
    db.save_message("assistant", "hi there")
    msgs = db.get_recent_messages(10)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"


def test_conversation_window(db):
    for i in range(25):
        db.save_message("user", f"msg {i}")
    msgs = db.get_recent_messages(10)
    assert len(msgs) == 10
    assert msgs[-1].content == "msg 24"


def test_save_and_list_notes(db):
    note_id = db.save_note("I take my medication at 8pm")
    notes = db.get_all_notes()
    assert len(notes) == 1
    assert notes[0].id == note_id
    assert "medication" in notes[0].content


def test_delete_note(db):
    note_id = db.save_note("temporary note")
    deleted = db.delete_note(note_id)
    assert deleted is True
    assert db.get_all_notes() == []


def test_delete_nonexistent_note(db):
    assert db.delete_note(9999) is False


def test_save_and_get_pending_reminders(db):
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    db.save_reminder("past reminder", past)
    db.save_reminder("future reminder", future)

    pending = db.get_pending_reminders()
    assert len(pending) == 1
    assert pending[0].content == "past reminder"


def test_mark_reminder_sent(db):
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    rid = db.save_reminder("test", past)
    db.mark_reminder_sent(rid)
    assert db.get_pending_reminders() == []


def test_get_all_pending_reminders(db):
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    db.save_reminder("future 1", future)
    db.save_reminder("future 2", future)
    all_pending = db.get_all_pending_reminders()
    assert len(all_pending) == 2
