#!/usr/bin/env bash
# Run from project root on your MacBook to push latest changes to GitHub.
# Usage: ./scripts/deploy_mac.sh [optional commit message]

set -e

cd "$(dirname "$0")/.."

echo "=== Personal Reminder Agent — Mac Deploy ==="

# --- Stage & commit any local changes ---
if ! git diff --quiet || ! git diff --cached --quiet; then
    MSG="${1:-update agent}"
    echo "-> Staging and committing: \"$MSG\""
    git add -A
    git commit -m "$MSG"
else
    echo "-> Nothing to commit, working tree clean"
fi

# --- Push to GitHub ---
echo "-> Pushing to origin/main..."
git push origin main

echo ""
echo "Done! Code is on GitHub."
echo "Now SSH into EC2 and run:  ./scripts/deploy_ec2.sh"
