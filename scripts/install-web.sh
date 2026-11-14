#!/usr/bin/env bash
# Install VoiceIn phone web listener (localhost) + login autostart.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOSTART_DST="${HOME}/.config/autostart/voicein-web.desktop"
UNIT_DST="${HOME}/.config/systemd/user/voicein-web.service"

chmod +x "${REPO}/scripts/voicein-web.sh" "${REPO}/scripts/setup-cloudflare-tunnel.sh"

"${REPO}/.venv/bin/python" -m voicein web-setup "$@"

mkdir -p "${HOME}/.config/autostart" "${HOME}/.config/systemd/user"
sed "s|@VOICEIN_REPO@|${REPO}|g" "${REPO}/autostart/voicein-web.desktop" >"${AUTOSTART_DST}"
sed "s|@VOICEIN_REPO@|${REPO}|g" "${REPO}/systemd/voicein-web.service" >"${UNIT_DST}"

systemctl --user daemon-reload
systemctl --user enable voicein-web.service 2>/dev/null || true
systemctl --user restart voicein-web.service 2>/dev/null || true

# Autostart is the reliable path on this machine (same as toggle mode).
if ! pgrep -f "voicein web" >/dev/null 2>&1; then
  nohup "${REPO}/scripts/voicein-web.sh" >/dev/null 2>&1 &
  sleep 0.4
fi

echo
echo "Laptop listener: http://127.0.0.1:8765 (not public yet)"
echo "Next: ${REPO}/scripts/setup-cloudflare-tunnel.sh"
echo "  → creates https://voice.rasdine.com without changing the main site"
echo
echo "Bookmark that URL on your phone. Sign in once; stays logged in 90 days."
