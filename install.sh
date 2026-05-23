#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/voicein"
VENVP="$REPO/.venv"

say() { printf '%s\n' "$*"; }

say "[voicein] repository: ${REPO}"

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
  sudo apt-get install -y python3-dev portaudio19-dev ffmpeg xclip xdotool
  sudo apt-get install -y gir1.2-ayatanaappindicator3-0.1 2>/dev/null || say "[voicein] (optional indicator gir package skipped)"

fi

mkdir -p "${CFG_DIR}"
if [[ ! -f "${CFG_DIR}/config.toml" ]]; then
  cp "${REPO}/config.example.toml" "${CFG_DIR}/config.toml"
  say "[voicein] seeded ${CFG_DIR}/config.toml"
fi
if [[ ! -f "${CFG_DIR}/.env" ]] && [[ -f "${REPO}/.env.example" ]]; then
  cp "${REPO}/.env.example" "${CFG_DIR}/.env"
  say "[voicein] seeded ${CFG_DIR}/.env (add OPENAI_API_KEY)"
fi

UNIT_DST="${HOME}/.config/systemd/user/voicein.service"
mkdir -p "${HOME}/.config/systemd/user"
sed \
  -e "s|@VOICEIN_VENV_PYTHON@|${VENVP}/bin/python|g" \
  -e "s|@VOICEIN_REPO@|${REPO}|g" \
  "${REPO}/systemd/voicein.service" >"${UNIT_DST}"

say "[voicein] wrote user unit: ${UNIT_DST}"
say "[voicein] next steps:"
say "    - Edit ${CFG_DIR}/.env with OPENAI_API_KEY="
say "    - systemctl --user daemon-reload"
say "    - systemctl --user enable --now voicein.service"
say "[voicein] foreground test:"
say "    ${VENVP}/bin/python -m voicein run"
