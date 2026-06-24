"""Thin wrapper that imports the shared Database from src/memory/database.py.
In Docker the src/ directory is mounted at /app/src via volume."""
import sys
import os
from pathlib import Path

# Allow importing src.memory.database when running inside Docker
_src_root = Path(__file__).parent.parent.parent
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

from src.memory.database import Database  # noqa: E402
from src.memory.models import Reminder, Note, User  # noqa: E402

DB_PATH = Path(os.environ.get("DB_PATH", "/app/data/memory.db"))

_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(db_path=DB_PATH)
        _db.connect()
    return _db
