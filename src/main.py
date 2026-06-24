import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _validate_env():
    required = [
        "TELEGRAM_BOT_TOKEN",
        "LLM_PROVIDER",
    ]
    # Accept either TELEGRAM_ALLOWED_IDS (multi-user) or TELEGRAM_CHAT_ID (legacy)
    if not os.environ.get("TELEGRAM_ALLOWED_IDS") and not os.environ.get("TELEGRAM_CHAT_ID"):
        required.append("TELEGRAM_CHAT_ID")  # trigger the missing-var message
    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


_validate_env()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler as TGMessageHandler,
    filters,
)

from src.ai.client import AIClient
from src.ai.provider import make_llm
from src.memory.database import Database
from src.bot.handlers import MessageHandler
from src.bot.commands import CommandHandler as BotCommandHandler
from src.scheduler.jobs import check_reminders, daily_checkin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_checkin_time() -> tuple[int, int]:
    raw = os.environ.get("DAILY_CHECKIN_TIME", "08:00")
    try:
        h, m = raw.split(":")
        return int(h), int(m)
    except Exception:
        logger.warning("Invalid DAILY_CHECKIN_TIME '%s', defaulting to 08:00", raw)
        return 8, 0


async def main():
    logger.info("Starting Personal Reminder Agent")

    db = Database()
    db.connect()

    tz = os.environ.get("TIMEZONE", "America/Chicago")
    provider = os.environ["LLM_PROVIDER"]
    ai = AIClient()
    llm = make_llm(provider)

    msg_handler = MessageHandler(db=db, llm=llm, tz=tz)
    cmd_handler = BotCommandHandler(db=db, ai=ai)

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_handler.start))
    app.add_handler(CommandHandler("help", cmd_handler.help_cmd))
    app.add_handler(CommandHandler("note", cmd_handler.note))
    app.add_handler(CommandHandler("notes", cmd_handler.notes))
    app.add_handler(CommandHandler("forget", cmd_handler.forget))
    app.add_handler(CommandHandler("remind", cmd_handler.remind))
    app.add_handler(CommandHandler("reminders", cmd_handler.reminders))
    app.add_handler(CommandHandler("history", cmd_handler.history))
    app.add_handler(CommandHandler("checkin", cmd_handler.checkin))
    app.add_handler(CommandHandler("calendar", cmd_handler.calendar))
    app.add_handler(CommandHandler("calauth", cmd_handler.calauth))

    app.add_handler(
        TGMessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler.handle_message)
    )

    scheduler = AsyncIOScheduler(timezone=tz)
    bot = app.bot

    scheduler.add_job(
        check_reminders,
        "interval",
        seconds=60,
        misfire_grace_time=60,
        kwargs={"db": db, "ai": ai, "bot": bot},
    )

    checkin_hour, checkin_minute = _parse_checkin_time()
    scheduler.add_job(
        daily_checkin,
        "cron",
        hour=checkin_hour,
        minute=checkin_minute,
        misfire_grace_time=60,
        kwargs={"db": db, "ai": ai, "bot": bot},
    )

    scheduler.start()
    logger.info(
        "Scheduler started. Check-in at %02d:%02d %s, reminder poll every 60s",
        checkin_hour, checkin_minute, tz,
    )

    stop_event = asyncio.Event()

    def _handle_sigterm(*_):
        logger.info("SIGTERM received, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot is polling for updates")

    await stop_event.wait()

    logger.info("Stopping...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    scheduler.shutdown(wait=False)
    db.close()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
