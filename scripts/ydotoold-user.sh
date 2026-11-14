#!/usr/bin/env bash
# Keep ydotoold running under systemd (ydotoold forks; Type=simple would restart-loop).
set -euo pipefail

runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
sock="${runtime}/.ydotool_socket"
own="$(id -u):$(id -g)"

if ! pgrep -x ydotoold >/dev/null 2>&1; then
  /usr/bin/ydotoold --socket-path="${sock}" --socket-own="${own}"
  sleep 0.3
fi

while pgrep -x ydotoold >/dev/null 2>&1; do
  sleep 5
done
