#!/usr/bin/env bash
# Toggle on-demand dictation (no background pynput). Bind in GNOME Settings → Keyboard.
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

exec "${REPO}/.venv/bin/python" -m voicein toggle "$@"
