"""Clipboard paste via ``xclip`` + ``xdotool`` on X11."""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def _clipboard_set_bytes(payload: bytes) -> None:
    subprocess.run(["xclip", "-selection", "clipboard"], input=payload, check=True)


def paste_text(text: str) -> None:
    """Copy result to clipboard, attempt Ctrl+V, leave text on clipboard.

    The transcription stays on the clipboard after paste so tools like CopyQ
    retain it and you can recover it if auto-paste missed the focused field.
    """

    encoded = text.encode("utf-8")
    _clipboard_set_bytes(encoded)
    time.sleep(0.07)

    try:
        subprocess.run(["xdotool", "key", "ctrl+v"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning(
            'Auto-paste failed — text is still on the clipboard (Ctrl+V to insert)',
        )

    logger.debug('Clipboard holds %s bytes after paste attempt', len(encoded))
