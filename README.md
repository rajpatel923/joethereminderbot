# Personal Reminder Agent

An AI-powered Telegram bot that acts as a personal reminder friend. Talk to it naturally, set reminders, save notes, and get a daily morning check-in — all running locally for free.

## Architecture

- **Telegram bot** — polling-based via `python-telegram-bot`
- **AI brain** — local vLLM model via OpenAI-compatible API
- **Memory** — SQLite with WAL mode, persisted via Docker volume
- **Scheduler** — APScheduler running in-process for reminders and daily check-ins
- **Isolation** — Docker container with non-root user, auto-restart on failure

## Setup

### 1. Create a Telegram bot

1. Open Telegram and message `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the API token you receive

### 2. Get your Telegram chat ID

1. Message `@userinfobot` on Telegram
2. It will reply with your user ID — copy it

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...     # from BotFather
TELEGRAM_CHAT_ID=987654321               # your Telegram user ID
VLLM_BASE_URL=http://host.docker.internal:8000/v1
VLLM_MODEL_NAME=meta-llama/Llama-3-8B-Instruct   # model name in your vLLM server
CONVERSATION_WINDOW=20
DAILY_CHECKIN_TIME=08:00
TIMEZONE=America/Toronto
```

### 4. Start your vLLM server

Make sure vLLM is running on the host at port 8000 before starting the bot.

### 5. Run

```bash
docker compose up -d
docker compose logs -f   # watch logs
```

To stop:
```bash
docker compose stop
```

## Commands

| Command | Description |
|---|---|
| `/note <text>` | Save a persistent fact |
| `/notes` | List all saved notes |
| `/forget <id>` | Delete a note by ID |
| `/remind <time> <message>` | Set a reminder — natural time parsing |
| `/reminders` | List pending reminders |
| `/checkin` | Get your morning summary now |
| `/help` | Show command list |

### Reminder time examples

```
/remind in 2 hours drink water
/remind tomorrow at 9am call the dentist
/remind next Monday review budget
/remind in 30 minutes check the oven
```

## Data persistence

Your notes and reminders survive container restarts because the SQLite database is stored in `./data/memory.db` (mounted as a Docker volume).

```bash
# Back up your data
cp data/memory.db data/memory.db.backup
```

## Running tests locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/ -v
```

## Security

The bot only responds to the single `TELEGRAM_CHAT_ID` configured in `.env`. All messages from any other account are silently ignored.
