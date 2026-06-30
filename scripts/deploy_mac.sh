#!/usr/bin/env bash
# Build all images, push to Docker Hub, and push code to GitHub.
# Usage: ./scripts/deploy_mac.sh [optional commit message]
# Run from anywhere inside the project.

set -e

cd "$(dirname "$0")/.."

DOCKERHUB_USER="patelraj293"
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

# --- Docker: build for linux/amd64 (EC2) and push ---
echo ""
echo "-> Building bot image for linux/amd64..."
docker buildx build \
    --platform linux/amd64 \
    -t "$BOT_IMAGE" \
    --push \
    .

echo ""
echo "Done! $BOT_IMAGE is live on Docker Hub."
echo "On EC2, run:  ./deploy_ec2.sh"
