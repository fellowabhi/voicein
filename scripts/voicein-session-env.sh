# Shared GNOME session env for clipboard + paste (Wayland under systemd/autostart).
voicein_export_session_env() {
  local uid runtime candidate sock
  uid="$(id -u)"
  runtime="${XDG_RUNTIME_DIR:-/run/user/${uid}}"
  export XDG_RUNTIME_DIR="${runtime}"

  export DISPLAY="${DISPLAY:-:0}"

  if [[ -z "${WAYLAND_DISPLAY:-}" && -S "${runtime}/wayland-0" ]]; then
    export WAYLAND_DISPLAY=wayland-0
  fi
  if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    export XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-wayland}"
  fi

  if [[ -z "${XDG_CURRENT_DESKTOP:-}" || -z "${XDG_SESSION_DESKTOP:-}" ]] \
    && command -v loginctl >/dev/null 2>&1; then
    local session
    session="$(loginctl list-sessions --no-legend 2>/dev/null \
      | awk -v u="$(id -un)" '$3 == u && $4 == "" { print $1; exit }')"
  if [[ -z "${session}" ]]; then
    session="$(loginctl list-sessions --no-legend 2>/dev/null \
      | awk -v u="$(id -un)" '$3 == u { print $1; exit }')"
  fi
    if [[ -n "${session}" ]]; then
      if [[ -z "${XDG_SESSION_DESKTOP:-}" ]]; then
        local desk
        desk="$(loginctl show-session "${session}" -p Desktop --value 2>/dev/null || true)"
        [[ -n "${desk}" ]] && export XDG_SESSION_DESKTOP="${desk}"
      fi
      if [[ -z "${XDG_CURRENT_DESKTOP:-}" && -n "${XDG_SESSION_DESKTOP:-}" ]]; then
        export XDG_CURRENT_DESKTOP="${XDG_SESSION_DESKTOP}:GNOME"
      fi
    fi
  fi

  sock="${runtime}/.ydotool_socket"
  if [[ -e "${sock}" ]]; then
    export YDOTOOL_SOCKET="${sock}"
  fi

  if command -v ydotoold >/dev/null 2>&1 && ! pgrep -x ydotoold >/dev/null 2>&1; then
    /usr/bin/ydotoold --socket-path="${sock}" --socket-own="$(id -u):$(id -g)" >/dev/null 2>&1 || true
    sleep 0.2
  fi

  if [[ -z "${XAUTHORITY:-}" ]]; then
    for candidate in \
      "${runtime}/gdm/Xauthority" \
      "${HOME}/.Xauthority"; do
      if [[ -f "${candidate}" ]]; then
        export XAUTHORITY="${candidate}"
        break
      fi
    done
    if [[ -z "${XAUTHORITY:-}" ]]; then
      shopt -s nullglob
      for candidate in "${runtime}"/.mutter-XwaylandAuth.*; do
        export XAUTHORITY="${candidate}"
        break
      done
      shopt -u nullglob
    fi
  fi
}
