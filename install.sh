#!/usr/bin/env bash
# DS4 Dwarfstar Dashboard installer.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DS4_HOME="${DS4_HOME:-${HOME}/ds4}"
LAUNCHD_DIR="${HOME}/Library/LaunchAgents"
GUI_DOMAIN="gui/$(id -u)"

DASHBOARD_LABEL="com.dwarfstar.ds4-dashboard"
DS4_LABEL="com.dwarfstar.ds4"
DASHBOARD_PLIST_SRC="${ROOT_DIR}/scripts/ds4-dashboard-launchd.plist"
DS4_PLIST_SRC="${ROOT_DIR}/scripts/ds4-launchd.plist"
DASHBOARD_PLIST_DST="${LAUNCHD_DIR}/${DASHBOARD_LABEL}.plist"
DS4_PLIST_DST="${LAUNCHD_DIR}/${DS4_LABEL}.plist"

INSTALL_DEPS=1
INSTALL_DASHBOARD_LAUNCHD=0
INSTALL_DS4_LAUNCHD=0
UNINSTALL_LAUNCHD=0

usage() {
  cat <<USAGE
Usage: ./install.sh [options]

Options:
  --launchd-dashboard   Install and load the dashboard LaunchAgent.
  --launchd-ds4         Install and load the DS4 engine LaunchAgent.
  --launchd-all         Install and load both LaunchAgents.
  --uninstall-launchd   Unload and remove dashboard and DS4 LaunchAgents.
  --skip-deps           Do not create/update the Python virtualenv.
  --help                Show this help.

Environment:
  PYTHON_BIN            Python executable for venv creation. Default: python3
  VENV_DIR              Virtualenv path. Default: .venv in this repo
  DS4_HOME              DS4 engine home. Default: \$HOME/ds4
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --launchd-dashboard)
      INSTALL_DASHBOARD_LAUNCHD=1
      ;;
    --launchd-ds4)
      INSTALL_DS4_LAUNCHD=1
      ;;
    --launchd-all)
      INSTALL_DASHBOARD_LAUNCHD=1
      INSTALL_DS4_LAUNCHD=1
      ;;
    --uninstall-launchd)
      UNINSTALL_LAUNCHD=1
      ;;
    --skip-deps)
      INSTALL_DEPS=0
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

require_macos_launchd() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "launchd install is only supported on macOS." >&2
    exit 1
  fi
  if ! command -v launchctl >/dev/null 2>&1; then
    echo "launchctl was not found." >&2
    exit 1
  fi
}

unload_agent() {
  local label="$1"
  local plist="$2"
  launchctl bootout "${GUI_DOMAIN}" "${plist}" >/dev/null 2>&1 || true
  launchctl bootout "${GUI_DOMAIN}/${label}" >/dev/null 2>&1 || true
}

render_plist() {
  local src="$1"
  local dst="$2"
  mkdir -p "${LAUNCHD_DIR}"
  sed \
    -e "s#/Users/m4mbp/ds4-dashboard/.venv/bin/python#${VENV_DIR}/bin/python#g" \
    -e "s#/Users/m4mbp/ds4-dashboard#${ROOT_DIR}#g" \
    -e "s#<string>/Users/m4mbp/ds4/ds4-server</string>#<string>${DS4_HOME}/ds4-server</string>#g" \
    -e "s#<string>/Users/m4mbp/ds4</string>#<string>${DS4_HOME}</string>#g" \
    "${src}" > "${dst}"
  chmod 644 "${dst}"
}

load_agent() {
  local label="$1"
  local plist="$2"
  unload_agent "${label}" "${plist}"
  launchctl bootstrap "${GUI_DOMAIN}" "${plist}"
  launchctl kickstart -k "${GUI_DOMAIN}/${label}" >/dev/null 2>&1 || true
  launchctl print "${GUI_DOMAIN}/${label}" >/dev/null
}

if [[ "${UNINSTALL_LAUNCHD}" -eq 1 ]]; then
  require_macos_launchd
  unload_agent "${DASHBOARD_LABEL}" "${DASHBOARD_PLIST_DST}"
  unload_agent "${DS4_LABEL}" "${DS4_PLIST_DST}"
  rm -f "${DASHBOARD_PLIST_DST}" "${DS4_PLIST_DST}"
  echo "Removed Dwarfstar LaunchAgents."
  exit 0
fi

if [[ "${INSTALL_DEPS}" -eq 1 ]]; then
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  "${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"
fi

if [[ "${INSTALL_DASHBOARD_LAUNCHD}" -eq 1 || "${INSTALL_DS4_LAUNCHD}" -eq 1 ]]; then
  require_macos_launchd
fi

if [[ "${INSTALL_DASHBOARD_LAUNCHD}" -eq 1 ]]; then
  render_plist "${DASHBOARD_PLIST_SRC}" "${DASHBOARD_PLIST_DST}"
  load_agent "${DASHBOARD_LABEL}" "${DASHBOARD_PLIST_DST}"
  echo "Loaded ${DASHBOARD_LABEL}."
fi

if [[ "${INSTALL_DS4_LAUNCHD}" -eq 1 ]]; then
  render_plist "${DS4_PLIST_SRC}" "${DS4_PLIST_DST}"
  load_agent "${DS4_LABEL}" "${DS4_PLIST_DST}"
  echo "Loaded ${DS4_LABEL}."
fi

cat <<NEXT
Install complete.

Manual dashboard:
  ${VENV_DIR}/bin/python dashboard.py --host 127.0.0.1 --port 8765

Dashboard URL:
  http://127.0.0.1:8765

LaunchAgent logs:
  tail -f /tmp/ds4-dashboard-stdout.log
  tail -f /tmp/ds4-dashboard-stderr.log
NEXT
