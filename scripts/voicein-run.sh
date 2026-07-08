#!/usr/bin/env bash
# Launch VoiceIn with DISPLAY / XAUTHORITY from the active GNOME session.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UID_NUM="$(id -u)"
RUNTIME="/run/user/${UID_NUM}"

export DISPLAY="${DISPLAY:-:0}"

if [[ -z "${XAUTHORITY:-}" ]]; then
  for candidate in \
    "${RUNTIME}/gdm/Xauthority" \
    "${HOME}/.Xauthority"; do
    if [[ -f "${candidate}" ]]; then
      export XAUTHORITY="${candidate}"
      break
    fi
  done
  if [[ -z "${XAUTHORITY:-}" ]]; then
    shopt -s nullglob
    for candidate in "${RUNTIME}"/.mutter-XwaylandAuth.*; do
      export XAUTHORITY="${candidate}"
      break
    done
    shopt -u nullglob
  fi
fi

# Wait for the X session + systray to be ready (avoids pystray dock failures at boot).
for _ in $(seq 1 45); do
  if command -v xset >/dev/null 2>&1 && xset q >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

exec "${REPO}/.venv/bin/python" -m voicein run "$@"
