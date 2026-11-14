#!/usr/bin/env bash
# Toggle on-demand dictation (no background pynput). Bind in GNOME Settings → Keyboard.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=voicein-session-env.sh
source "${REPO}/scripts/voicein-session-env.sh"
voicein_export_session_env

exec "${REPO}/.venv/bin/python" -m voicein toggle "$@"
