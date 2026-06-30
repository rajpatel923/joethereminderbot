#!/usr/bin/env bash
# Pull latest images from Docker Hub and restart the bot.
# EC2 only needs this script + a .env file. No git, no source code required.
# Usage: ./deploy_ec2.sh

set -e

DOCKERHUB_USER="patelraj293"
BOT_IMAGE="$DOCKERHUB_USER/reminder-agent:latest"
BACKEND_IMAGE="$DOCKERHUB_USER/reminder-agent-backend:latest"
FRONTEND_IMAGE="$DOCKERHUB_USER/reminder-agent-frontend:latest"
PROJECT_DIR="$HOME/reminder-agent"
DB_PATH="$PROJECT_DIR/data/reminders.db"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

echo "=== Personal Reminder Agent — EC2 Deploy ==="

# --- Pick docker compose command ---
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose &>/dev/null; then
    DC="docker-compose"
else
    echo "-> Installing docker-compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    DC="docker-compose"
fi
echo "-> Using: $DC"

# --- Ensure docker and sqlite3 are available ---
if ! command -v sqlite3 &>/dev/null; then
    echo "-> Installing sqlite3..."
    sudo yum install -y sqlite 2>/dev/null || sudo apt-get install -y sqlite3 2>/dev/null || true
fi

# --- Create project directory if needed ---
mkdir -p "$PROJECT_DIR/data"

# --- Write docker-compose.yml (no build, images only) ---
echo "-> Writing docker-compose.yml..."
cat > "$COMPOSE_FILE" <<EOF
services:
  reminder-agent:
    image: $BOT_IMAGE
    restart: unless-stopped
    env_file: $HOME/.env
    volumes:
      - $PROJECT_DIR/data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  dashboard-backend:
    image: $BACKEND_IMAGE
    restart: unless-stopped
    env_file: $HOME/.env
    ports:
      - "8000:8000"
    volumes:
      - $PROJECT_DIR/data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  dashboard-frontend:
    image: $FRONTEND_IMAGE
    restart: unless-stopped
    ports:
      - "3000:80"
    environment:
      - VITE_API_URL=http://localhost:8000
EOF

# --- Pull latest images from Docker Hub ---
echo "-> Pulling latest images from Docker Hub..."
docker pull "$BOT_IMAGE"
docker pull "$BACKEND_IMAGE"
docker pull "$FRONTEND_IMAGE"

# --- Restart containers ---
echo "-> Restarting containers..."
$DC -f "$COMPOSE_FILE" up -d

# --- Wait for containers to be running ---
echo "-> Waiting for containers..."
for i in $(seq 1 15); do
    RUNNING=$($DC -f "$COMPOSE_FILE" ps --status running --quiet 2>/dev/null | wc -l | tr -d ' ')
    if [ "$RUNNING" -ge 1 ]; then
        echo "   Containers up ($RUNNING running)."
        break
    fi
    echo "   ($i/15) waiting..."
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
echo "Deploy complete!"
