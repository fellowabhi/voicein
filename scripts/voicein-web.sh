#!/usr/bin/env bash
# VoiceIn phone web recorder (localhost). Paste uses DISPLAY from the GNOME session.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=voicein-session-env.sh
source "${REPO}/scripts/voicein-session-env.sh"
voicein_export_session_env

exec "${REPO}/.venv/bin/python" -m voicein web "$@"
