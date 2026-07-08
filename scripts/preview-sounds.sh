#!/usr/bin/env bash
# Browse and preview system sounds — pick paths for ~/.config/voicein/config.toml [cues]
set -euo pipefail

PLAYER=""
if command -v paplay >/dev/null 2>&1; then
  PLAYER=paplay
elif command -v aplay >/dev/null 2>&1; then
  PLAYER=aplay
else
  echo "Install paplay (pulseaudio-utils) or aplay (alsa-utils) to preview sounds."
  exit 1
fi

DIRS=(
  "/usr/share/sounds/freedesktop/stereo"
  "/usr/share/sounds/GNUstep"
  "/usr/share/sounds/sound-icons"
)

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: preview-sounds.sh [directory]

Interactive sound picker for VoiceIn [cues] config.

  preview-sounds.sh
      Start with freedesktop notification sounds (recommended).

  preview-sounds.sh /usr/share/sounds/GNUstep
      Preview sounds in one folder.

Commands inside the menu:
  <number>   play that sound
  p <path>   play a file by full path
  l          list again
  n          next sound folder
  q          quit

After you find sounds you like, add to ~/.config/voicein/config.toml:

  [cues]
  start = "/usr/share/sounds/freedesktop/stereo/bell.oga"
  stop = "/usr/share/sounds/freedesktop/stereo/complete.oga"
  paste = "/usr/share/sounds/freedesktop/stereo/message.oga"
EOF
  exit 0
fi

play_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "Missing: $f"
    return 1
  fi
  echo ">> $f"
  if [[ "$PLAYER" == paplay ]]; then
    paplay "$f" 2>/dev/null || true
  else
    aplay -q "$f" 2>/dev/null || true
  fi
}

dir_index=0
if [[ -n "${1:-}" ]]; then
  CURRENT="$1"
else
  CURRENT="${DIRS[0]}"
fi

while true; do
  if [[ ! -d "$CURRENT" ]]; then
    echo "Directory not found: $CURRENT"
    exit 1
  fi

  mapfile -t FILES < <(find "$CURRENT" -maxdepth 1 -type f \( -name '*.oga' -o -name '*.wav' \) | sort)
  echo
  echo "=== $CURRENT (${#FILES[@]} sounds) ==="
  echo "Folder ${dir_index}/${#DIRS[@]}: ${DIRS[dir_index]}"
  echo
  i=1
  for f in "${FILES[@]}"; do
    printf '%3d) %s\n' "$i" "$(basename "$f")"
    ((i++)) || true
  done
  echo
  echo "Enter number to play, 'p /path/to/file', 'n' next folder, 'l' relist, 'q' quit."

  read -r -p '> ' choice || exit 0
  case "$choice" in
    q|Q) exit 0 ;;
    l|L) continue ;;
    n|N)
      dir_index=$(( (dir_index + 1) % ${#DIRS[@]} ))
      CURRENT="${DIRS[$dir_index]}"
      ;;
    p|path)
      read -r -p 'Full path: ' manual || exit 0
      play_file "$manual"
      ;;
    p/*|/*)
      play_file "$choice"
      ;;
    ''|*[!0-9]*)
      if [[ "$choice" == p* && "$choice" != p ]]; then
        play_file "${choice#p }"
      else
        echo "Unknown input."
      fi
      ;;
    *)
      idx=$((choice - 1))
      if (( idx >= 0 && idx < ${#FILES[@]} )); then
        play_file "${FILES[$idx]}"
        echo
        echo "Config line example:"
        echo "  start = \"${FILES[$idx]}\""
      else
        echo "Out of range."
      fi
      ;;
  esac
done
