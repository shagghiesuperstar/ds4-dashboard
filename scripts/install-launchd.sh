#!/bin/bash
# install-launchd.sh — Register DS4 as a launchd service
#
# Usage: bash install-launchd.sh [--uninstall]
#
# Installs com.ds4.engine as a LaunchAgent so DS4 auto-starts
# at login and stays alive. The dashboard's config_manager.py will
# detect launchd and use `launchctl kickstart` for restarts.

set -euo pipefail

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/ds4-launchd.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.ds4.engine.plist"
LABEL="com.ds4.engine"

if [[ "${1:-}" == "--uninstall" ]]; then
    echo "→ Unloading ${LABEL}..."
    launchctl bootout "gui/$(id -u)" "${PLIST_DST}" 2>/dev/null || true
    rm -f "${PLIST_DST}"
    echo "✓ Removed. DS4 will no longer auto-start at login."
    exit 0
fi

# Copy plist
echo "→ Installing plist to ${PLIST_DST}..."
cp -f "${PLIST_SRC}" "${PLIST_DST}"
chmod 644 "${PLIST_DST}"

# Load with launchctl
echo "→ Loading ${LABEL} via launchctl bootstrap..."
launchctl bootstrap "gui/$(id -u)" "${PLIST_DST}"

# Verify
echo "→ Verifying..."
sleep 1
if launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | grep -q "state = running"; then
    echo "✓ DS4 launchd service is running."
else
    echo "⚠ Service loaded but not yet running. Check /tmp/ds4-stdout.log."
fi

echo ""
echo "Commands for day-to-day use:"
echo "  Restart: launchctl kickstart gui/$(id -u)/${LABEL}"
echo "  Stop:    launchctl bootout gui/$(id -u)/${PLIST_DST}"
echo "  Logs:    tail -f /tmp/ds4-stdout.log"
echo "  Uninstall: bash ${0} --uninstall"
