#!/usr/bin/env bash
# Run on EC2 inside the project directory to pull latest code, rebuild containers,
# and fix any existing duplicate reminders in the database.
# Usage: ./scripts/deploy_ec2.sh

set -e

cd "$(dirname "$0")/.."

echo "=== Personal Reminder Agent — EC2 Deploy ==="

# --- Pull latest code ---
echo "-> Pulling latest code from GitHub..."
git pull origin main

# --- Rebuild and restart containers ---
echo "-> Rebuilding and restarting containers..."
docker compose up -d --build

# --- Wait for bot container to be healthy ---
echo "-> Waiting for containers to be healthy..."
for i in $(seq 1 15); do
    STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
data = sys.stdin.read().strip()
lines = [l for l in data.splitlines() if l.strip()]
states = [json.loads(l).get('State', '') for l in lines]
print('ok' if all(s in ('running', 'healthy') for s in states) else 'waiting')
" 2>/dev/null || echo "waiting")
    if [ "$STATUS" = "ok" ]; then
        echo "   Containers up."
        break
    fi
    echo "   ($i/15) waiting..."
    sleep 2
done

# --- Clean up duplicate reminders in the database ---
echo "-> Cleaning up duplicate reminders in database..."
DB_PATH="./data/reminders.db"

if [ ! -f "$DB_PATH" ]; then
    echo "   Database not found at $DB_PATH — skipping cleanup."
else
    BEFORE=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM reminders WHERE sent=FALSE AND reminder_type='single';")

    sqlite3 "$DB_PATH" "
        UPDATE reminders
        SET reminder_type = 'checkin'
        WHERE sent = FALSE
          AND reminder_type = 'single'
          AND id NOT IN (
              SELECT MAX(id)
              FROM reminders
              WHERE sent = FALSE AND reminder_type = 'single'
              GROUP BY content
          );
    "

    AFTER=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM reminders WHERE sent=FALSE AND reminder_type='single';")
    FIXED=$((BEFORE - AFTER))

    if [ "$FIXED" -gt 0 ]; then
        echo "   Demoted $FIXED duplicate reminder(s) to check-in (hidden from list)."
    else
        echo "   No duplicates found."
    fi
fi

# --- Show current pending reminders ---
echo ""
echo "=== Current pending reminders ==="
sqlite3 "$DB_PATH" "
    SELECT '  #' || id || ' [' || reminder_type || '] ' || remind_at || ' — ' || content
    FROM reminders
    WHERE sent = FALSE
    ORDER BY remind_at ASC;
" 2>/dev/null || echo "  (could not read database)"

echo ""
echo "Deploy complete!"
