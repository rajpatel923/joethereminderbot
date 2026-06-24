import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .models import Message, Note, Reminder, PendingFollowup

logger = logging.getLogger(__name__)

DB_PATH = Path("/app/data/memory.db")


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL mode for safe concurrent reads
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        logger.info("Database connected: %s", self.db_path)

    def _migrate(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                remind_at DATETIME NOT NULL,
                sent BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_content TEXT NOT NULL,
                asked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE
            );
        """)

        # Safe additive migrations for new reminders columns
        existing_cols = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(reminders)").fetchall()
        }
        if "reminder_type" not in existing_cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN reminder_type TEXT DEFAULT 'single'"
            )
        if "needs_followup" not in existing_cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN needs_followup BOOLEAN DEFAULT FALSE"
            )

        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    # --- Messages ---

    def save_message(self, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content),
        )
        self.conn.commit()
        logger.debug("Saved message role=%s", role)

    def get_recent_messages(self, limit: int) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        messages = [
            Message(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in reversed(rows)
        ]
        return messages

    # --- Notes ---

    def save_note(self, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO notes (content) VALUES (?)",
            (content,),
        )
        self.conn.commit()
        logger.debug("Saved note id=%d", cur.lastrowid)
        return cur.lastrowid

    def get_all_notes(self) -> list[Note]:
        rows = self.conn.execute(
            "SELECT * FROM notes ORDER BY id ASC"
        ).fetchall()
        return [
            Note(
                id=r["id"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def delete_note(self, note_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.conn.commit()
        deleted = cur.rowcount > 0
        logger.debug("Deleted note id=%d success=%s", note_id, deleted)
        return deleted

    # --- Reminders ---

    def save_reminder(
        self,
        content: str,
        remind_at: datetime,
        reminder_type: str = "single",
        needs_followup: bool = False,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO reminders (content, remind_at, reminder_type, needs_followup) VALUES (?, ?, ?, ?)",
            (content, remind_at.isoformat(), reminder_type, needs_followup),
        )
        self.conn.commit()
        logger.debug("Saved reminder id=%d at=%s type=%s", cur.lastrowid, remind_at, reminder_type)
        return cur.lastrowid

    def save_deadline_reminders(self, content: str, deadline: datetime) -> None:
        self.save_reminder(content, deadline - timedelta(hours=3), reminder_type="pre_check")
        self.save_reminder(content, deadline - timedelta(minutes=15), reminder_type="warning")
        self.save_reminder(content, deadline, reminder_type="deadline", needs_followup=True)
        logger.debug("Saved 3 staged reminders for deadline=%s content=%s", deadline, content)

    def get_all_pending_reminders(self) -> list[Reminder]:
        rows = self.conn.execute(
            "SELECT * FROM reminders WHERE sent = FALSE ORDER BY remind_at ASC"
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def get_pending_reminders(self) -> list[Reminder]:
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM reminders WHERE sent = FALSE AND remind_at <= ? ORDER BY remind_at ASC",
            (now,),
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: int):
        self.conn.execute(
            "UPDATE reminders SET sent = TRUE WHERE id = ?",
            (reminder_id,),
        )
        self.conn.commit()
        logger.debug("Marked reminder sent id=%d", reminder_id)

    # --- Pending followups ---

    def get_pending_followup(self) -> PendingFollowup | None:
        row = self.conn.execute(
            "SELECT * FROM pending_followups WHERE resolved = FALSE ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return PendingFollowup(
            id=row["id"],
            reminder_content=row["reminder_content"],
            asked_at=datetime.fromisoformat(row["asked_at"]),
            resolved=bool(row["resolved"]),
        )

    def create_followup(self, reminder_content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO pending_followups (reminder_content) VALUES (?)",
            (reminder_content,),
        )
        self.conn.commit()
        logger.debug("Created followup id=%d for: %s", cur.lastrowid, reminder_content)
        return cur.lastrowid

    def resolve_followup(self, followup_id: int):
        self.conn.execute(
            "UPDATE pending_followups SET resolved = TRUE WHERE id = ?",
            (followup_id,),
        )
        self.conn.commit()
        logger.debug("Resolved followup id=%d", followup_id)

    def _row_to_reminder(self, r) -> Reminder:
        return Reminder(
            id=r["id"],
            content=r["content"],
            remind_at=datetime.fromisoformat(r["remind_at"]),
            sent=bool(r["sent"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            reminder_type=r["reminder_type"],
            needs_followup=bool(r["needs_followup"]),
        )
