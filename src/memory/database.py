import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from .models import Message, Note, Reminder, PendingFollowup, User, GoogleTokens

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
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        logger.info("Database connected: %s", self.db_path)

    def _migrate(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                timezone TEXT DEFAULT 'America/Chicago',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS google_tokens (
                user_id INTEGER PRIMARY KEY,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

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

        # Additive migrations for reminders
        reminder_cols = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(reminders)").fetchall()
        }
        for col, defn in [
            ("reminder_type", "TEXT DEFAULT 'single'"),
            ("needs_followup", "BOOLEAN DEFAULT FALSE"),
            ("user_id", "INTEGER"),
            ("priority", "INTEGER DEFAULT 2"),
            ("category", "TEXT DEFAULT 'general'"),
            ("recurrence_rule", "TEXT"),
            ("recurrence_end", "DATETIME"),
            ("snoozed_until", "DATETIME"),
        ]:
            if col not in reminder_cols:
                self.conn.execute(f"ALTER TABLE reminders ADD COLUMN {col} {defn}")

        # Additive migrations for messages, notes, pending_followups
        for table in ("messages", "notes", "pending_followups"):
            cols = {
                row[1]
                for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "user_id" not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")

        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    # --- Users ---

    def get_or_create_user(self, telegram_id: int, timezone: str = "America/Chicago") -> User:
        row = self.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if row:
            return self._row_to_user(row)
        cur = self.conn.execute(
            "INSERT INTO users (telegram_id, timezone) VALUES (?, ?)",
            (telegram_id, timezone),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        logger.info("Created new user telegram_id=%d id=%d", telegram_id, cur.lastrowid)
        return self._row_to_user(row)

    def get_all_allowed_users(self) -> list[User]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
        return [self._row_to_user(r) for r in rows]

    def update_user_timezone(self, user_id: int, timezone: str):
        self.conn.execute(
            "UPDATE users SET timezone = ? WHERE id = ?", (timezone, user_id)
        )
        self.conn.commit()

    def _row_to_user(self, r) -> User:
        return User(
            id=r["id"],
            telegram_id=r["telegram_id"],
            timezone=r["timezone"],
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    # --- Google Tokens ---

    def save_google_tokens(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expiry: Optional[datetime],
    ):
        expiry_iso = expiry.isoformat() if expiry else None
        self.conn.execute(
            """INSERT INTO google_tokens (user_id, access_token, refresh_token, token_expiry)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 access_token=excluded.access_token,
                 refresh_token=excluded.refresh_token,
                 token_expiry=excluded.token_expiry""",
            (user_id, access_token, refresh_token, expiry_iso),
        )
        self.conn.commit()
        logger.debug("Saved google tokens for user_id=%d", user_id)

    def get_google_tokens(self, user_id: int) -> Optional[GoogleTokens]:
        row = self.conn.execute(
            "SELECT * FROM google_tokens WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        expiry = datetime.fromisoformat(row["token_expiry"]) if row["token_expiry"] else None
        return GoogleTokens(
            user_id=row["user_id"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expiry=expiry,
        )

    # --- Messages ---

    def save_message(self, role: str, content: str, user_id: Optional[int] = None):
        self.conn.execute(
            "INSERT INTO messages (role, content, user_id) VALUES (?, ?, ?)",
            (role, content, user_id),
        )
        self.conn.commit()
        logger.debug("Saved message role=%s user_id=%s", role, user_id)

    def get_recent_messages(self, limit: int, user_id: Optional[int] = None) -> list[Message]:
        if user_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE user_id = ? OR user_id IS NULL ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Message(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                user_id=r["user_id"],
            )
            for r in reversed(rows)
        ]

    # --- Notes ---

    def save_note(self, content: str, user_id: Optional[int] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO notes (content, user_id) VALUES (?, ?)",
            (content, user_id),
        )
        self.conn.commit()
        logger.debug("Saved note id=%d", cur.lastrowid)
        return cur.lastrowid

    def get_all_notes(self, user_id: Optional[int] = None) -> list[Note]:
        if user_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM notes WHERE user_id = ? OR user_id IS NULL ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM notes ORDER BY id ASC").fetchall()
        return [
            Note(
                id=r["id"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
                user_id=r["user_id"],
            )
            for r in rows
        ]

    def delete_note(self, note_id: int, user_id: Optional[int] = None) -> bool:
        if user_id is not None:
            cur = self.conn.execute(
                "DELETE FROM notes WHERE id = ? AND (user_id = ? OR user_id IS NULL)",
                (note_id, user_id),
            )
        else:
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
        user_id: Optional[int] = None,
        priority: int = 2,
        category: str = "general",
        recurrence_rule: Optional[str] = None,
        recurrence_end: Optional[datetime] = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO reminders
               (content, remind_at, reminder_type, needs_followup, user_id, priority, category, recurrence_rule, recurrence_end)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                content,
                remind_at.isoformat(),
                reminder_type,
                needs_followup,
                user_id,
                priority,
                category,
                recurrence_rule,
                recurrence_end.isoformat() if recurrence_end else None,
            ),
        )
        self.conn.commit()
        logger.debug(
            "Saved reminder id=%d at=%s type=%s user_id=%s",
            cur.lastrowid, remind_at, reminder_type, user_id,
        )
        return cur.lastrowid

    def save_deadline_reminders(
        self, content: str, deadline: datetime, user_id: Optional[int] = None
    ) -> None:
        self.save_reminder(
            content, deadline - timedelta(hours=3),
            reminder_type="pre_check", user_id=user_id,
        )
        self.save_reminder(
            content, deadline - timedelta(minutes=15),
            reminder_type="warning", user_id=user_id,
        )
        self.save_reminder(
            content, deadline,
            reminder_type="deadline", needs_followup=True, user_id=user_id,
        )
        logger.debug("Saved 3 staged reminders deadline=%s content=%s", deadline, content)

    def get_all_pending_reminders(self, user_id: Optional[int] = None) -> list[Reminder]:
        if user_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM reminders WHERE sent = FALSE AND (user_id = ? OR user_id IS NULL) ORDER BY remind_at ASC",
                (user_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM reminders WHERE sent = FALSE ORDER BY remind_at ASC"
            ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def get_pending_reminders(self, user_id: Optional[int] = None) -> list[Reminder]:
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if user_id is not None:
            rows = self.conn.execute(
                """SELECT * FROM reminders
                   WHERE sent = FALSE
                     AND remind_at <= ?
                     AND (snoozed_until IS NULL OR snoozed_until <= ?)
                     AND (user_id = ? OR user_id IS NULL)
                   ORDER BY remind_at ASC""",
                (now, now, user_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM reminders
                   WHERE sent = FALSE
                     AND remind_at <= ?
                     AND (snoozed_until IS NULL OR snoozed_until <= ?)
                   ORDER BY remind_at ASC""",
                (now, now),
            ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def get_reminder_history(self, user_id: Optional[int] = None, limit: int = 20) -> list[Reminder]:
        if user_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM reminders WHERE sent = TRUE AND (user_id = ? OR user_id IS NULL) ORDER BY remind_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM reminders WHERE sent = TRUE ORDER BY remind_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: int):
        self.conn.execute(
            "UPDATE reminders SET sent = TRUE WHERE id = ?", (reminder_id,)
        )
        self.conn.commit()
        logger.debug("Marked reminder sent id=%d", reminder_id)

    def delete_reminder(self, reminder_id: int, user_id: Optional[int] = None) -> bool:
        if user_id is not None:
            cur = self.conn.execute(
                "DELETE FROM reminders WHERE id = ? AND (user_id = ? OR user_id IS NULL)",
                (reminder_id, user_id),
            )
        else:
            cur = self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self.conn.commit()
        deleted = cur.rowcount > 0
        logger.debug("Deleted reminder id=%d success=%s", reminder_id, deleted)
        return deleted

    def update_reminder(
        self,
        reminder_id: int,
        user_id: Optional[int] = None,
        **kwargs,
    ) -> bool:
        allowed = {"content", "remind_at", "priority", "category", "recurrence_rule", "recurrence_end"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        # Serialize datetime values
        for k in ("remind_at", "recurrence_end"):
            if k in updates and isinstance(updates[k], datetime):
                updates[k] = updates[k].isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        if user_id is not None:
            values += [reminder_id, user_id]
            cur = self.conn.execute(
                f"UPDATE reminders SET {set_clause} WHERE id = ? AND (user_id = ? OR user_id IS NULL)",
                values,
            )
        else:
            values.append(reminder_id)
            cur = self.conn.execute(
                f"UPDATE reminders SET {set_clause} WHERE id = ?", values
            )
        self.conn.commit()
        updated = cur.rowcount > 0
        logger.debug("Updated reminder id=%d success=%s", reminder_id, updated)
        return updated

    def snooze_reminder(
        self, reminder_id: int, until_dt: datetime, user_id: Optional[int] = None
    ) -> bool:
        if user_id is not None:
            cur = self.conn.execute(
                "UPDATE reminders SET snoozed_until = ? WHERE id = ? AND (user_id = ? OR user_id IS NULL)",
                (until_dt.isoformat(), reminder_id, user_id),
            )
        else:
            cur = self.conn.execute(
                "UPDATE reminders SET snoozed_until = ? WHERE id = ?",
                (until_dt.isoformat(), reminder_id),
            )
        self.conn.commit()
        snoozed = cur.rowcount > 0
        logger.debug("Snoozed reminder id=%d until=%s success=%s", reminder_id, until_dt, snoozed)
        return snoozed

    # --- Pending followups ---

    def get_pending_followup(self, user_id: Optional[int] = None) -> Optional[PendingFollowup]:
        if user_id is not None:
            row = self.conn.execute(
                "SELECT * FROM pending_followups WHERE resolved = FALSE AND (user_id = ? OR user_id IS NULL) ORDER BY id ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        else:
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
            user_id=row["user_id"],
        )

    def create_followup(self, reminder_content: str, user_id: Optional[int] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO pending_followups (reminder_content, user_id) VALUES (?, ?)",
            (reminder_content, user_id),
        )
        self.conn.commit()
        logger.debug("Created followup id=%d for: %s", cur.lastrowid, reminder_content)
        return cur.lastrowid

    def resolve_followup(self, followup_id: int):
        self.conn.execute(
            "UPDATE pending_followups SET resolved = TRUE WHERE id = ?", (followup_id,)
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
            reminder_type=r["reminder_type"] or "single",
            needs_followup=bool(r["needs_followup"]),
            user_id=r["user_id"],
            priority=r["priority"] if r["priority"] is not None else 2,
            category=r["category"] or "general",
            recurrence_rule=r["recurrence_rule"],
            recurrence_end=datetime.fromisoformat(r["recurrence_end"]) if r["recurrence_end"] else None,
            snoozed_until=datetime.fromisoformat(r["snoozed_until"]) if r["snoozed_until"] else None,
        )
