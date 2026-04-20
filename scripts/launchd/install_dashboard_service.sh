#!/usr/bin/env bash
set -euo pipefail

PLIST_SRC="/Users/brock/Documents/GitHub/seldon/scripts/launchd/com.brock.seldon-observability-dashboard.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.brock.seldon-observability-dashboard.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.seldon-observability"

# Copy (not symlink — launchd does not follow symlinks reliably)
cp "$PLIST_SRC" "$PLIST_DEST"

# Unload if already loaded (idempotent)
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Load
launchctl load "$PLIST_DEST"

# Check status
sleep 2
if launchctl list | grep -q 'com.brock.seldon-observability-dashboard'; then
    echo "Loaded: com.brock.seldon-observability-dashboard"
    echo "Check http://127.0.0.1:8765 in a browser."
else
    echo "FAILED: service did not load. Check ~/.seldon-observability/dashboard.stderr.log"
    exit 1
fi
