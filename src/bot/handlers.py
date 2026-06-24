import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from src.agent.graph import invoke_agent
from src.memory.database import Database

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db: Database, graph):
        self.db = db
        self.graph = graph
        self._allowed_chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
        self._window = int(os.environ.get("CONVERSATION_WINDOW", "20"))
        self._seen_updates: set[int] = set()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Deduplication guard
        if update.update_id in self._seen_updates:
            logger.debug("Skipping duplicate update_id=%d", update.update_id)
            return
        self._seen_updates.add(update.update_id)
        # Keep set from growing unboundedly
        if len(self._seen_updates) > 10_000:
            self._seen_updates.clear()

        # Security: only respond to the configured chat
        if update.effective_chat.id != self._allowed_chat_id:
            logger.warning("Ignored message from unknown chat_id=%d", update.effective_chat.id)
            return

        user_text = update.message.text
        logger.info("User message: %s", user_text[:80])

        # Persist user message
        self.db.save_message("user", user_text)

        notes = self.db.get_all_notes()
        history = self.db.get_recent_messages(self._window)
        pending_followup = self.db.get_pending_followup()

        reply = await invoke_agent(self.graph, user_text, history, notes, pending_followup)

        # Resolve followup now that user has responded
        if pending_followup:
            self.db.resolve_followup(pending_followup.id)

        # Persist AI reply
        self.db.save_message("assistant", reply)

        logger.info("Assistant reply: %s", reply[:200])
        await update.message.reply_text(reply)
