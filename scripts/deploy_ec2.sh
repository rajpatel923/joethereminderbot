#!/usr/bin/env bash
# Pull latest bot image from Docker Hub and restart it.
# EC2 only needs this script + ~/reminder-agent/.env
# Usage: ./deploy_ec2.sh

set -e

DOCKERHUB_USER="patelraj293"
BOT_IMAGE="$DOCKERHUB_USER/reminder-agent:latest"
PROJECT_DIR="$HOME/reminder-agent"
DB_PATH="$PROJECT_DIR/data/reminders.db"

echo "=== Personal Reminder Agent — EC2 Deploy ==="

# --- Ensure sqlite3 is available ---
if ! command -v sqlite3 &>/dev/null; then
    echo "-> Installing sqlite3..."
    sudo yum install -y sqlite 2>/dev/null || sudo apt-get install -y sqlite3 2>/dev/null || true
fi

# --- Check .env exists ---
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo ""
    echo "ERROR: .env not found at $PROJECT_DIR/.env"
    echo "Create it first:  nano $PROJECT_DIR/.env"
    exit 1
fi

# --- Create data directory if needed ---
mkdir -p "$PROJECT_DIR/data"

# --- Pull latest image ---
echo "-> Pulling $BOT_IMAGE..."
docker pull "$BOT_IMAGE"

# --- Stop and remove old container if running ---
echo "-> Stopping old container..."
docker rm -f reminder-agent 2>/dev/null || true

# --- Start new container ---
echo "-> Starting new container..."
docker run -d \
    --name reminder-agent \
    --restart unless-stopped \
    --env-file "$PROJECT_DIR/.env" \
    -v "$PROJECT_DIR/data:/app/data" \
    "$BOT_IMAGE"

# --- Wait for it to be running ---
echo "-> Waiting for container..."
for i in $(seq 1 10); do
    STATUS=$(docker inspect -f '{{.State.Status}}' reminder-agent 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "running" ]; then
        echo "   Container is running."
        break
    fi
    echo "   ($i/10) status: $STATUS..."
    sleep 2
done

# --- Clean up duplicate reminders in database ---
echo "-> Cleaning up duplicate reminders..."
if [ -f "$DB_PATH" ]; then
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
    [ "$FIXED" -gt 0 ] && echo "   Demoted $FIXED duplicate(s) to checkin." || echo "   No duplicates found."
else
    echo "   No database yet — skipping."
fi

# --- Show current pending reminders ---
echo ""
echo "=== Pending reminders ==="
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" "
        SELECT '  #' || id || ' [' || reminder_type || '] ' || remind_at || ' — ' || SUBSTR(content,1,60)
        FROM reminders WHERE sent=FALSE ORDER BY remind_at ASC;
    " || echo "  (none)"
else
    echo "  (database not created yet)"
fi

echo ""
echo "Deploy complete! Logs: docker logs -f reminder-agent"
