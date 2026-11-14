#!/usr/bin/env bash
# Isolate VoiceIn paste: clipboard + synthetic Ctrl+V (same env as voicein-web / toggle).
#
# Usage:
#   ./scripts/test-paste.sh              # default test string, 5s countdown
#   ./scripts/test-paste.sh "hello"      # custom text
#   ./scripts/test-paste.sh --no-paste   # clipboard only (manual Ctrl+V)
#   ./scripts/test-paste.sh --ctrl-v     # ydotool Ctrl+V (broken on GNOME/Mutter)
#   ./scripts/test-paste.sh --xdotool    # force xdotool (usually bad on Wayland)
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=voicein-session-env.sh
source "${REPO}/scripts/voicein-session-env.sh"
voicein_export_session_env

TEXT="VoiceIn paste test $(date +%H:%M:%S)"
DO_PASTE=1
PASTE_TOOL="auto"
COUNTDOWN=5

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-paste) DO_PASTE=0; shift ;;
    --xdotool) PASTE_TOOL=xdotool; shift ;;
    --ydotool|--type) PASTE_TOOL=ydotool-type; shift ;;
    --ctrl-v) PASTE_TOOL=ydotool-ctrl-v; shift ;;
    --help|-h)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    --) shift; break ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) TEXT=$1; shift ;;
  esac
done

is_wayland() {
  [[ "${XDG_SESSION_TYPE:-}" == wayland ]] || [[ -n "${WAYLAND_DISPLAY:-}" ]] \
    || [[ -S "${XDG_RUNTIME_DIR}/wayland-0" ]]
}

is_gnome() {
  [[ "${XDG_CURRENT_DESKTOP:-}" == *[Gg]nome* ]] || [[ "${XDG_CURRENT_DESKTOP:-}" == ubuntu* ]]
}

ok() { printf '  OK  %s\n' "$*"; }
fail() { printf ' FAIL %s\n' "$*" >&2; }
info() { printf '      %s\n' "$*"; }

echo "=== VoiceIn paste test ==="
echo

echo "[session]"
info "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-<unset>}"
info "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-<unset>}"
info "DISPLAY=${DISPLAY:-<unset>}"
info "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-<unset>}"
info "YDOTOOL_SOCKET=${YDOTOOL_SOCKET:-<unset>}"
if is_wayland; then ok "detected Wayland session"; else info "not detected as Wayland (will use X11 tools)"; fi
if is_gnome; then
  info "GNOME/Mutter: Ctrl+V via ydotool often fails silently; default paste uses ydotool type"
fi
echo

echo "[tools]"
for cmd in wl-copy wl-paste ydotool ydotoold xclip xdotool wtype; do
  if command -v "$cmd" >/dev/null 2>&1; then ok "$cmd → $(command -v "$cmd")"; else fail "$cmd not installed"; fi
done
if groups | grep -q '\binput\b'; then ok "user in group: input"; else fail "user NOT in group input (sudo usermod -aG input \$USER, re-login)"; fi
if pgrep -x ydotoold >/dev/null 2>&1; then ok "ydotoold running (pid $(pgrep -x ydotoold))"; else fail "ydotoold not running (run: systemctl --user start ydotoold)"; fi
sock="${XDG_RUNTIME_DIR}/.ydotool_socket"
if [[ -e "$sock" ]]; then ok "ydotool socket: $sock"; else fail "missing socket: $sock"; fi
echo

echo "[clipboard] text: ${TEXT@Q}"
if is_wayland && command -v wl-copy >/dev/null 2>&1; then
  if printf '%s' "$TEXT" | wl-copy; then ok "wl-copy"; else fail "wl-copy"; exit 1; fi
  if [[ "$(wl-paste)" == "$TEXT" ]]; then ok "wl-paste matches"; else fail "wl-paste mismatch: $(wl-paste@Q)"; exit 1; fi
else
  if printf '%s' "$TEXT" | xclip -selection clipboard; then ok "xclip"; else fail "xclip (need DISPLAY/XAUTHORITY?)"; exit 1; fi
fi
echo

if [[ "$DO_PASTE" -eq 0 ]]; then
  echo "[paste] skipped (--no-paste). Focus a text field and press Ctrl+V."
  exit 0
fi

echo "[paste] Focus a text field now (${COUNTDOWN}s)…"
for ((i = COUNTDOWN; i >= 1; i--)); do printf '\r      %s… ' "$i"; sleep 1; done
printf '\r      go!   \n'

paste_err=""
if [[ "$PASTE_TOOL" == auto ]]; then
  if is_wayland && is_gnome; then PASTE_TOOL=ydotool-type
  elif is_wayland; then PASTE_TOOL=ydotool-ctrl-v
  else PASTE_TOOL=xdotool; fi
fi

case "$PASTE_TOOL" in
  ydotool-type)
    if ydotool type --key-delay 0 --key-hold 0 -- "$TEXT" 2>"/tmp/voicein-test-paste.err"; then
      ok "ydotool type (GNOME-safe; types text at caret)"
    else
      paste_err=$(cat "/tmp/voicein-test-paste.err" 2>/dev/null || true)
      fail "ydotool type: ${paste_err:-unknown error}"
    fi
    ;;
  ydotool|ydotool-ctrl-v)
    if ydotool key ctrl+v 2>"/tmp/voicein-test-paste.err"; then
      ok "ydotool key ctrl+v (may succeed but paste nothing on GNOME)"
    else
      paste_err=$(cat "/tmp/voicein-test-paste.err" 2>/dev/null || true)
      fail "ydotool: ${paste_err:-unknown error}"
    fi
    ;;
  xdotool)
    if xdotool key ctrl+v 2>"/tmp/voicein-test-paste.err"; then
      ok "xdotool key ctrl+v"
    else
      paste_err=$(cat "/tmp/voicein-test-paste.err" 2>/dev/null || true)
      fail "xdotool: ${paste_err:-unknown error}"
    fi
    ;;
  *)
    fail "unknown paste tool: $PASTE_TOOL"
    exit 1
    ;;
esac

echo
if [[ -n "$paste_err" ]]; then
  echo "If clipboard works but paste failed: caret focus, ydotoold, or try --no-paste then Ctrl+V."
  exit 1
fi
echo "Done. You should see the test line in the focused field."
echo "If --ctrl-v shows OK but nothing appears, use default (ydotool type) — known GNOME/Mutter issue."
