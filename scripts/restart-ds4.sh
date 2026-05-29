#!/bin/bash
# DS4 Dwarfstar Dashboard — launchd restart wrapper
# Called by dashboard.py when a config change requires a DS4 restart.
# Uses launchctl to kickstart the DS4 service, which reloads the plist
# and re-execs ds4-server with updated flags.

set -euo pipefail

LABEL="com.ds4.server"

# 1) Gracefully stop the running service (if any)
echo "[restart-ds4] Stopping $LABEL..."
launchctl stop "$LABEL" 2>/dev/null || true

# 2) Small cooldown so the binary releases the port + Metal resources
sleep 1.5

# 3) Clear stale lockfile
rm -f /tmp/ds4.lock

# 4) Kickstart — launchd re-reads the plist and re-execs the launcher script
echo "[restart-ds4] Starting $LABEL..."
launchctl kickstart "$LABEL" 2>/dev/null || true

# 5) Wait for the port to become available
echo "[restart-ds4] Waiting for DS4 to listen on port 8001..."
for i in $(seq 1 30); do
  if lsof -i :8001 -P -n 2>/dev/null | grep -q LISTEN; then
    echo "[restart-ds4] DS4 ready after ${i}s."
    exit 0
  fi
  sleep 1
done

echo "[restart-ds4] TIMEOUT waiting for DS4 port 8001."
exit 1
