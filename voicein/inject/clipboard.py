"""Clipboard paste: wl-copy/xclip + Wayland ydotool/dotool or X11 xdotool."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from collections.abc import Callable

from voicein.config import load_config

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return True
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime, "wayland-0").exists()


def _is_gnome() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop or desktop.startswith("ubuntu"):
        return True
    session = os.environ.get("XDG_SESSION_DESKTOP", "").lower()
    return session in {"ubuntu", "gnome", "gnome-wayland", "gnome-xorg"}


def _clipboard_set_bytes(payload: bytes) -> None:
    if _is_wayland() and shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=payload, check=True)
        return
    subprocess.run(["xclip", "-selection", "clipboard"], input=payload, check=True)


def _ydotool_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    sock = runtime / ".ydotool_socket"
    if sock.exists():
        env["YDOTOOL_SOCKET"] = str(sock)
    return env


def _paste_ydotool_key() -> None:
    subprocess.run(
        ["ydotool", "key", "ctrl+v"],
        env=_ydotool_env(),
        check=True,
        timeout=8,
    )


def _paste_ydotool_type(text: str) -> None:
    # GNOME/Mutter drops uinput modifier chords (Ctrl+V exits 0 but pastes nothing).
    subprocess.run(
        [
            "ydotool",
            "type",
            "--key-delay",
            "0",
            "--key-hold",
            "0",
            "--",
            text,
        ],
        env=_ydotool_env(),
        check=True,
        timeout=max(30, len(text) // 20 + 10),
    )


def _paste_dotool() -> None:
    subprocess.run(
        ["dotool"],
        input=b"key ctrl+v\n",
        check=True,
        timeout=8,
    )


def _paste_wtype() -> None:
    subprocess.run(["wtype", "-M", "ctrl", "-p", "v", "-m", "ctrl"], check=True, timeout=8)


def _paste_xdotool() -> None:
    subprocess.run(["xdotool", "key", "ctrl+v"], check=True, timeout=8)


def _paste_key(text: str) -> bool:
    """Inject text at focus. GNOME Wayland: ydotool type (Mutter drops Ctrl+V chords)."""

    cfg = load_config()
    if not cfg.inject_auto_paste:
        return False

    if _is_wayland():
        mode = (cfg.inject_wayland_paste or "ydotool").strip().lower()
        if mode == "none":
            return False

        # wtype fails on GNOME with "Compositor does not support the virtual keyboard protocol"
        attempts: list[tuple[str, Callable[[], None]]] = []
        if mode == "wtype":
            attempts = [("wtype", _paste_wtype)]
        elif mode == "dotool":
            attempts = [("dotool", _paste_dotool)]
        elif mode == "ydotool-key":
            attempts = [("ydotool-key", _paste_ydotool_key)]
        else:
            # Default ydotool on Wayland: type first (GNOME/Mutter drops Ctrl+V chords;
            # systemd web service often lacks XDG_CURRENT_DESKTOP — key still exits 0).
            attempts = [
                ("ydotool-type", lambda: _paste_ydotool_type(text)),
                ("ydotool-key", _paste_ydotool_key),
                ("dotool", _paste_dotool),
            ]

        for name, fn in attempts:
            if name == "wtype" and not shutil.which("wtype"):
                continue
            if name.startswith("ydotool") and not shutil.which("ydotool"):
                continue
            if name == "dotool" and not shutil.which("dotool"):
                continue
            try:
                fn()
                return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
                logger.warning("%s paste failed: %s", name, exc)

        logger.info(
            "Wayland auto-paste unavailable — text is on the clipboard (Ctrl+V). "
            "On GNOME run: ./scripts/setup-wayland-paste.sh (ydotool + ydotoold)",
        )
        return False

    _paste_xdotool()
    return True


def paste_text(text: str) -> None:
    """Copy result to clipboard, attempt auto-paste, leave text on clipboard."""

    encoded = text.encode("utf-8")
    _clipboard_set_bytes(encoded)
    time.sleep(0.07)

    try:
        _paste_key(text)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning(
            "Auto-paste failed — text is still on the clipboard (Ctrl+V to insert)",
        )

    logger.debug("Clipboard holds %s bytes after paste attempt", len(encoded))
