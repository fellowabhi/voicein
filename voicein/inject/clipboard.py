"""Clipboard paste via ``xclip`` + ``xdotool`` on X11."""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def _clipboard_get_bytes() -> bytes | None:
    try:
        return subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        logger.debug('Clipboard snapshot failed (%s)', exc.returncode)
        return None
    except FileNotFoundError:
        logger.error("xclip not installed — clipboard paste unsupported")
        return None


def _clipboard_set_bytes(payload: bytes) -> None:
    subprocess.run(["xclip", "-selection", "clipboard"], input=payload, check=True)


def paste_text(text: str) -> None:
    snapshot = _clipboard_get_bytes()

    encoded = text.encode("utf-8")
    try:
        _clipboard_set_bytes(encoded)
        time.sleep(0.07)
        subprocess.run(["xdotool", "key", "ctrl+v"], check=True)
    finally:
        time.sleep(0.18)
        if snapshot is None:
            return
        try:
            _clipboard_set_bytes(snapshot)
        except subprocess.CalledProcessError:
            logger.warning(
                'Clipboard restoration failed — leaving pasted text in clipboard',
            )
