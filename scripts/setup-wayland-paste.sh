#!/usr/bin/env bash
# GNOME on Wayland: wtype does NOT work. Use ydotool + ydotoold.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v ydotool >/dev/null 2>&1 || ! command -v ydotoold >/dev/null 2>&1; then
  echo "Install: sudo apt install ydotool"
  exit 1
fi

chmod +x "${REPO}/scripts/ydotoold-user.sh"
mkdir -p "${HOME}/.config/systemd/user"
sed "s|@VOICEIN_REPO@|${REPO}|g" "${REPO}/systemd/ydotoold.service" \
  >"${HOME}/.config/systemd/user/ydotoold.service"
systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service

if ! groups | grep -q '\binput\b'; then
  echo "Add yourself to the input group (required once, then log out/in):"
  echo "  sudo usermod -aG input ${USER}"
fi

echo "ydotoold is running. VoiceIn config should use: wayland_paste = \"ydotool\""
