import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.memory.database import Database
from src.scheduler.jobs import check_reminders


@pytest.fixture
def db(tmp_path):
    d = Database(db_path=tmp_path / "test.db")
    d.connect()
    yield d
    d.close()


@pytest.mark.asyncio
async def test_check_reminders_fires_due(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    db.save_reminder("drink water", past)

    mock_bot = AsyncMock()
    mock_ai = MagicMock()

    await check_reminders(db=db, ai=mock_ai, bot=mock_bot)

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert "drink water" in call_kwargs["text"]
    assert db.get_pending_reminders() == []


@pytest.mark.asyncio
async def test_check_reminders_skips_future(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    db.save_reminder("future task", future)

    mock_bot = AsyncMock()
    await check_reminders(db=db, ai=MagicMock(), bot=mock_bot)

    mock_bot.send_message.assert_not_called()
    assert len(db.get_all_pending_reminders()) == 1
