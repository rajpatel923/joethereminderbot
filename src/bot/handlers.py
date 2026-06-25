import logging
import os

from langchain_openai import ChatOpenAI
from telegram import Update
from telegram.ext import ContextTypes

from src.agent.graph import build_graph, invoke_agent
from src.memory.database import Database

logger = logging.getLogger(__name__)


def _parse_allowed_ids() -> set[int]:
    """Parse TELEGRAM_ALLOWED_IDS (comma-separated) or fall back to TELEGRAM_CHAT_ID."""
    raw = os.environ.get("TELEGRAM_ALLOWED_IDS", "").strip()
    if raw:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    fallback = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if fallback:
        return {int(fallback)}
    return set()


class MessageHandler:
    def __init__(self, db: Database, llm: ChatOpenAI, tz: str, ai=None):
        self.db = db
        self.llm = llm
        self.tz = tz
        self.ai = ai
        self._allowed_ids = _parse_allowed_ids()
        self._window = int(os.environ.get("CONVERSATION_WINDOW", "20"))
        self._user_graphs: dict[int, object] = {}
        self._seen_updates: set[int] = set()

    def _get_graph(self, user_id: int):
        if user_id not in self._user_graphs:
            self._user_graphs[user_id] = build_graph(
                db=self.db, tz=self.tz, llm=self.llm, user_id=user_id, ai=self.ai
            )
        return self._user_graphs[user_id]

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Deduplication guard
        if update.update_id in self._seen_updates:
            logger.debug("Skipping duplicate update_id=%d", update.update_id)
            return
        self._seen_updates.add(update.update_id)
        if len(self._seen_updates) > 10_000:
            self._seen_updates.clear()

        chat_id = update.effective_chat.id
        if self._allowed_ids and chat_id not in self._allowed_ids:
            logger.warning("Ignored message from unknown chat_id=%d", chat_id)
            return

        # Get or create user record
        user = self.db.get_or_create_user(chat_id, self.tz)

        user_text = update.message.text
        logger.info("User message (uid=%d): %s", user.id, user_text[:80])

        self.db.save_message("user", user_text, user_id=user.id)

        notes = self.db.get_all_notes(user_id=user.id)
        history = self.db.get_recent_messages(self._window, user_id=user.id)
        pending_followup = self.db.get_pending_followup(user_id=user.id)

        graph = self._get_graph(user.id)
        reply = await invoke_agent(
            graph, user_text, history, notes, pending_followup, tz=user.timezone
        )

        if pending_followup:
            self.db.resolve_followup(pending_followup.id)

        self.db.save_message("assistant", reply, user_id=user.id)

        logger.info("Assistant reply (uid=%d): %s", user.id, reply[:200])
        await update.message.reply_text(reply)
