#!/usr/bin/env bash
# Build all images, push to Docker Hub, and push code to GitHub.
# Usage: ./scripts/deploy_mac.sh [optional commit message]
# Run from anywhere inside the project.

set -e

cd "$(dirname "$0")/.."

DOCKERHUB_USER="rajpatel293"
BOT_IMAGE="$DOCKERHUB_USER/reminder-agent:latest"
BACKEND_IMAGE="$DOCKERHUB_USER/reminder-agent-backend:latest"
FRONTEND_IMAGE="$DOCKERHUB_USER/reminder-agent-frontend:latest"

echo "=== Personal Reminder Agent — Mac Deploy ==="

# --- Git: commit & push ---
if ! git diff --quiet || ! git diff --cached --quiet; then
    MSG="${1:-update agent}"
    echo "-> Committing: \"$MSG\""
    git add -A
    git commit -m "$MSG"
else
    echo "-> Nothing to commit"
fi
echo "-> Pushing to GitHub..."
git push origin main

# --- Docker: build all images ---
echo ""
echo "-> Building images..."
docker build -t "$BOT_IMAGE" .
docker build -t "$BACKEND_IMAGE" ./dashboard/backend
docker build -t "$FRONTEND_IMAGE" ./dashboard/frontend

# --- Docker: push to Docker Hub ---
echo ""
echo "-> Pushing to Docker Hub..."
docker push "$BOT_IMAGE"
docker push "$BACKEND_IMAGE"
docker push "$FRONTEND_IMAGE"

echo ""
echo "Done! Images on Docker Hub:"
echo "  $BOT_IMAGE"
echo "  $BACKEND_IMAGE"
echo "  $FRONTEND_IMAGE"
echo ""
echo "On EC2, run:  ./deploy_ec2.sh"
