#!/usr/bin/env bash
# Register VoiceIn toggle in GNOME Settings → Keyboard → Custom Shortcuts.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOGGLE="${REPO}/scripts/voicein-toggle.sh"
BINDING="${VOICEIN_TOGGLE_BINDING:-<Control><Shift>Insert}"
SCHEMA="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voicein/"

chmod +x "${TOGGLE}"

if ! command -v gsettings >/dev/null 2>&1; then
  echo "gsettings not found — add manually in GNOME Settings → Keyboard:"
  echo "  Command: ${TOGGLE}"
  echo "  Shortcut: Ctrl+Shift+Insert"
  exit 1
fi

existing="$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)"
if [[ "${existing}" == "@as []" ]]; then
  gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['${SCHEMA}']"
elif [[ "${existing}" != *"voicein"* ]]; then
  trimmed="${existing%\]}"
  gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "${trimmed}, '${SCHEMA}']"
fi

gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${SCHEMA}" name 'VoiceIn toggle'
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${SCHEMA}" command "${TOGGLE}"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${SCHEMA}" binding "${BINDING}"

echo "VoiceIn toggle shortcut installed:"
echo "  ${BINDING}  →  ${TOGGLE}"
echo "Logs: ~/.local/state/voicein/toggle.log"
