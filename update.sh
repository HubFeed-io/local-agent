#!/usr/bin/env bash
# Hubfeed Agent — Update Script (Linux / macOS)
# Run this on the HOST machine (not inside the container).
# It pulls the latest image and recreates the container.
# Persistent data in ./data and ./logs is preserved.

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SERVICE_NAME="${SERVICE_NAME:-hubfeed-agent}"

echo "=== Hubfeed Agent Updater ==="
echo ""

# Check docker compose is available
if command -v docker compose &>/dev/null; then
    DC="docker compose"
elif command -v docker-compose &>/dev/null; then
    DC="docker-compose"
else
    echo "ERROR: docker compose is not installed."
    exit 1
fi

# Show current version (if container is running)
CURRENT=$($DC -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" /py/bin/python -c \
    "from src.__version__ import __version__; print(__version__)" 2>/dev/null || echo "unknown")
echo "Current version: $CURRENT"
echo ""

echo "Pulling latest image..."
$DC -f "$COMPOSE_FILE" pull

echo ""
echo "Recreating container..."
$DC -f "$COMPOSE_FILE" up -d

echo ""
echo "Waiting for agent to start..."
sleep 5

# Show new version
NEW=$($DC -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" /py/bin/python -c \
    "from src.__version__ import __version__; print(__version__)" 2>/dev/null || echo "unknown")
echo "New version: $NEW"

if [ "$CURRENT" = "$NEW" ] && [ "$CURRENT" != "unknown" ]; then
    echo ""
    echo "Already on the latest version."
else
    echo ""
    echo "Update complete!"
fi
