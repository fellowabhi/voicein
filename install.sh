#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/voicein"
VENVP="$REPO/.venv"
AUTOSTART_DST="${HOME}/.config/autostart/voicein.desktop"
UNIT_DST="${HOME}/.config/systemd/user/voicein.service"

say() { printf '%s\n' "$*"; }

say "[voicein] repository: ${REPO}"

chmod +x "${REPO}/scripts/voicein-run.sh"
chmod +x "${REPO}/scripts/voicein-toggle.sh"
chmod +x "${REPO}/scripts/install-toggle-shortcut.sh"

if [[ ! -x "${VENVP}/bin/python" ]]; then
  say "[voicein] creating virtualenv ..."
  python3 -m venv "${VENVP}"
fi

"${VENVP}/bin/python" -m pip install --upgrade pip >/dev/null
say "[voicein] installing package (editable) ..."
"${VENVP}/bin/pip" install -e "${REPO}"

if command -v apt-get >/dev/null 2>&1; then
  say "[voicein] apt-get installs (needs sudo)"
  sudo apt-get update
  sudo apt-get install -y \
    python3-dev portaudio19-dev ffmpeg xclip xdotool \
    python3-dbus python3-gi gir1.2-glib-2.0
  sudo apt-get install -y gir1.2-ayatanaappindicator3-0.1 2>/dev/null \
    || say "[voicein] (optional indicator gir package skipped)"
fi

mkdir -p "${CFG_DIR}"
if [[ ! -f "${CFG_DIR}/config.toml" ]]; then
  cp "${REPO}/config.example.toml" "${CFG_DIR}/config.toml"
  say "[voicein] seeded ${CFG_DIR}/config.toml"
fi
if [[ ! -f "${CFG_DIR}/.env" ]] && [[ -f "${REPO}/.env.example" ]]; then
  cp "${REPO}/.env.example" "${CFG_DIR}/.env"
  say "[voicein] seeded ${CFG_DIR}/.env (add API key)"
fi

mkdir -p "${HOME}/.config/autostart" "${HOME}/.config/systemd/user"

sed "s|@VOICEIN_REPO@|${REPO}|g" "${REPO}/autostart/voicein.desktop" >"${AUTOSTART_DST}"
sed "s|@VOICEIN_REPO@|${REPO}|g" "${REPO}/systemd/voicein.service" >"${UNIT_DST}"

say "[voicein] autostart: ${AUTOSTART_DST}"
say "[voicein] systemd unit: ${UNIT_DST} (optional backup)"

systemctl --user daemon-reload
systemctl --user disable voicein.service 2>/dev/null || true
systemctl --user stop voicein.service 2>/dev/null || true

say "[voicein] using GNOME autostart (reliable DISPLAY/XAUTHORITY at login)"
say "[voicein] next steps:"
say "    - Add API key to ${REPO}/.env or ${CFG_DIR}/.env"
say "    - Log out and back in, OR run: ${REPO}/scripts/voicein-run.sh"
say "[voicein] if GUI freezes after sleep, ensure python3-dbus is installed (see install above)"
