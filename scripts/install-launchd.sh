#!/usr/bin/env bash
# install-launchd.sh — Register DS4 + DS4 Dashboard as launchd services
#
# Usage:
#   bash install-launchd.sh                       # install both (engine + dashboard)
#   bash install-launchd.sh --component engine    # install only the engine
#   bash install-launchd.sh --component dashboard # install only the dashboard
#   bash install-launchd.sh --uninstall           # remove both
#   bash install-launchd.sh --uninstall --component dashboard
#
# This script RENDERS the plist templates under scripts/ by substituting
# path placeholders with real values detected on this machine (overridable
# via env vars), then bootstraps them into the user's launchd domain.
#
# Placeholders handled:
#   PYTHON_PATH_PLACEHOLDER   -> venv python that has fastapi + uvicorn
#   PROJECT_PATH_PLACEHOLDER  -> repo root (dashboard.py's parent dir)
#   DS4_HOME_PLACEHOLDER      -> directory containing ds4-server
#   DS4_BINARY_PLACEHOLDER    -> absolute path to ds4-server
#
# Env var overrides (optional):
#   DS4_HOME          override DS4 home directory (default: ~/ds4)
#   DS4_DASHBOARD_DIR override dashboard repo path (default: script's parent)

set -euo pipefail

# --- locate script dir / repo root -------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- defaults overridable by env --------------------------------------------------
DS4_HOME="${DS4_HOME:-$HOME/ds4}"
DS4_DASHBOARD_DIR="${DS4_DASHBOARD_DIR:-$REPO_ROOT}"
PYTHON_PATH="${PYTHON_PATH:-${DS4_DASHBOARD_DIR}/.venv/bin/python}"

# --- arg parsing ------------------------------------------------------------------
COMPONENT="all"
UNINSTALL=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --component)
            COMPONENT="${2:-}"; shift 2 ;;
        --component=*)
            COMPONENT="${1#*=}"; shift ;;
        --uninstall)
            UNINSTALL=1; shift ;;
        -h|--help)
            sed -n '2,25p' "$0"; exit 0 ;;
        *)
            echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

case "$COMPONENT" in
    engine|dashboard|all) ;;
    *) echo "Invalid --component: $COMPONENT (must be engine|dashboard|all)" >&2; exit 2 ;;
esac

GUI="gui/$(id -u)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# --- helpers ----------------------------------------------------------------------
log()  { printf '\033[1;36m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

detect_dashboard_python() {
    # Use the explicit override if it exists.
    if [[ -x "$PYTHON_PATH" ]]; then
        echo "$PYTHON_PATH"; return
    fi
    # Fall back to repo's venv, then to whatever 'python3' resolves to.
    if [[ -x "${DS4_DASHBOARD_DIR}/.venv/bin/python" ]]; then
        echo "${DS4_DASHBOARD_DIR}/.venv/bin/python"
    else
        command -v python3
    fi
}

detect_ds4_binary() {
    local candidate="$DS4_HOME/ds4-server"
    if [[ -x "$candidate" ]]; then
        echo "$candidate"
    else
        command -v ds4-server 2>/dev/null || echo ""
    fi
}

verify_paths() {
    local need_python=0 need_binary=0
    [[ "$COMPONENT" == "dashboard" || "$COMPONENT" == "all" ]] && need_python=1
    [[ "$COMPONENT" == "engine"    || "$COMPONENT" == "all" ]] && need_binary=1

    if [[ $need_binary -eq 1 ]]; then
        DS4_BINARY="$(detect_ds4_binary)"
        if [[ -z "$DS4_BINARY" ]]; then
            err "ds4-server not found. Set DS4_HOME (currently: $DS4_HOME)"
            err "or pass DS4_BINARY=... to this script."
            return 1
        fi
    fi
    if [[ $need_python -eq 1 ]]; then
        PYTHON_PATH="$(detect_dashboard_python)"
        if [[ ! -x "$PYTHON_PATH" ]]; then
            err "Dashboard python not found. Tried: $PYTHON_PATH"
            err "Create a venv with: python3 -m venv ${DS4_DASHBOARD_DIR}/.venv && ${DS4_DASHBOARD_DIR}/.venv/bin/pip install -r ${DS4_DASHBOARD_DIR}/requirements.txt"
            return 1
        fi
    fi
    return 0
}

render_plist() {
    # render_plist <template> <output> <component>
    # Performs placeholder substitution. The python binary gets a sanity check
    # that it can import fastapi+uvicorn so we don't bootstrap a doomed service.
    local template="$1" output="$2" component="$3"
    local content
    content="$(cat "$template")"

    if [[ "$component" == "engine" ]]; then
        content="${content//DS4_BINARY_PLACEHOLDER/$DS4_BINARY}"
        content="${content//DS4_HOME_PLACEHOLDER/$DS4_HOME}"
    else
        content="${content//PYTHON_PATH_PLACEHOLDER/$PYTHON_PATH}"
        content="${content//PROJECT_PATH_PLACEHOLDER/$DS4_DASHBOARD_DIR}"
        content="${content//DS4_HOME_PLACEHOLDER/$DS4_HOME}"
    fi

    # Guard against accidental un-rendered placeholders.
    if grep -q 'PLACEHOLDER' <<<"$content"; then
        err "Rendered plist still contains PLACEHOLDER: $output"
        return 1
    fi

    printf '%s' "$content" > "$output"
    chmod 644 "$output"

    if ! plutil -lint "$output" >/dev/null 2>&1; then
        err "Plist syntax invalid: $output"
        plutil -lint "$output" || true
        return 1
    fi
    ok "Rendered $(basename "$output")"
}

bootout_if_loaded() {
    # bootout_if_loaded <label>
    local label="$1"
    if launchctl print "$GUI/$label" >/dev/null 2>&1; then
        launchctl bootout "$GUI/$label" 2>/dev/null || true
    fi
}

bootstrap() {
    # bootstrap <plist_path> <label> <wait_seconds>
    local plist="$1" label="$2" wait_s="${3:-5}"
    bootout_if_loaded "$label"
    if ! launchctl bootstrap "$GUI" "$plist" 2>/dev/null; then
        # Already bootstrapped is a benign race; ignore.
        launchctl print "$GUI/$label" >/dev/null 2>&1 || {
            err "Failed to bootstrap $label"
            return 1
        }
    fi
    ok "Bootstrapped $label"

    # Wait briefly for the service to settle.
    for ((i=1; i<=wait_s; i++)); do
        if launchctl print "$GUI/$label" 2>/dev/null | grep -q "state = running"; then
            ok "$label is running (after ${i}s)"
            return 0
        fi
        sleep 1
    done
    warn "$label loaded but not yet running. Check /tmp/ds4-stdout.log or /tmp/ds4-dashboard-stdout.log"
    return 0
}

# --- engine ------------------------------------------------------------------------
install_engine() {
    log "Installing engine service (com.ds4.engine)"
    render_plist "$SCRIPT_DIR/ds4-launchd.plist" "$LAUNCH_AGENTS_DIR/com.ds4.engine.plist" engine
    bootstrap "$LAUNCH_AGENTS_DIR/com.ds4.engine.plist" com.ds4.engine 5
}

uninstall_engine() {
    log "Removing engine service (com.ds4.engine)"
    launchctl bootout "$GUI/com.ds4.engine" 2>/dev/null || true
    rm -f "$LAUNCH_AGENTS_DIR/com.ds4.engine.plist"
    ok "Engine service removed."
}

# --- dashboard ---------------------------------------------------------------------
install_dashboard() {
    log "Installing dashboard service (com.ds4.dashboard)"
    # Verify the python can actually serve the app before we install it.
    if ! "$PYTHON_PATH" -c "import fastapi, uvicorn" 2>/dev/null; then
        err "Python at $PYTHON_PATH cannot import fastapi+uvicorn."
        err "Run: $PYTHON_PATH -m pip install -r ${DS4_DASHBOARD_DIR}/requirements.txt"
        return 1
    fi
    render_plist "$SCRIPT_DIR/ds4-dashboard-launchd.plist" "$LAUNCH_AGENTS_DIR/com.ds4.dashboard.plist" dashboard
    bootstrap "$LAUNCH_AGENTS_DIR/com.ds4.dashboard.plist" com.ds4.dashboard 8
}

uninstall_dashboard() {
    log "Removing dashboard service (com.ds4.dashboard)"
    launchctl bootout "$GUI/com.ds4.dashboard" 2>/dev/null || true
    rm -f "$LAUNCH_AGENTS_DIR/com.ds4.dashboard.plist"
    ok "Dashboard service removed."
}

# --- dispatch ----------------------------------------------------------------------
if [[ $UNINSTALL -eq 1 ]]; then
    case "$COMPONENT" in
        engine)    uninstall_engine ;;
        dashboard) uninstall_dashboard ;;
        all)
            uninstall_dashboard
            uninstall_engine
            ;;
    esac
    echo ""
    ok "Uninstall complete."
    exit 0
fi

# Install path: verify everything before touching launchd.
verify_paths || exit 1

# Final summary of what we're about to install.
echo ""
log "Install plan"
echo "  Component:           $COMPONENT"
if [[ "$COMPONENT" == "engine" || "$COMPONENT" == "all" ]]; then
    echo "  DS4 binary:          $DS4_BINARY"
    echo "  DS4 home:            $DS4_HOME"
    echo "  Engine plist:        $LAUNCH_AGENTS_DIR/com.ds4.engine.plist"
fi
if [[ "$COMPONENT" == "dashboard" || "$COMPONENT" == "all" ]]; then
    echo "  Dashboard python:    $PYTHON_PATH"
    echo "  Dashboard repo:      $DS4_DASHBOARD_DIR"
    echo "  Dashboard plist:     $LAUNCH_AGENTS_DIR/com.ds4.dashboard.plist"
fi
echo ""

case "$COMPONENT" in
    engine)    install_engine ;;
    dashboard) install_dashboard ;;
    all)
        install_dashboard
        install_engine
        ;;
esac

echo ""
ok "Install complete. Day-to-day commands:"
echo "  Restart dashboard: launchctl kickstart -k $GUI/com.ds4.dashboard"
echo "  Restart engine:    launchctl kickstart -k $GUI/com.ds4.engine"
echo "  Logs (dashboard):  tail -f /tmp/ds4-dashboard-stdout.log /tmp/ds4-dashboard-stderr.log"
echo "  Logs (engine):     tail -f /tmp/ds4-stdout.log /tmp/ds4-stderr.log"
echo "  Uninstall:         bash $0 --uninstall"
echo "  Open dashboard:    open http://127.0.0.1:8765"
