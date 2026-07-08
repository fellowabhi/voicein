"""Short audio cues for toggle recording (start / stop / paste)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, tuple[str, ...]] = {
    'start': (
        '/usr/share/sounds/freedesktop/stereo/bell.oga',
        '/usr/share/sounds/freedesktop/stereo/message-new-instant.oga',
    ),
    'stop': (
        '/usr/share/sounds/freedesktop/stereo/complete.oga',
        '/usr/share/sounds/freedesktop/stereo/dialog-information.oga',
    ),
    'paste': (
        '/usr/share/sounds/freedesktop/stereo/message.oga',
        '/usr/share/sounds/freedesktop/stereo/dialog-information.oga',
    ),
}

_CANBERRA: dict[str, tuple[str, ...]] = {
    'start': ('bell', 'message-new-instant'),
    'stop': ('complete', 'dialog-information'),
    'paste': ('message', 'complete'),
}


def play_recording_cue(phase: str, *, spec: str | None = None, block: bool = True) -> None:
    """Play a brief cue for ``start``, ``stop``, or ``paste``."""

    if phase not in _DEFAULTS:
        return

    if spec:
        if _play_spec(spec, block=block):
            return
        logger.warning('Configured cue %s=%r unavailable — using default', phase, spec)

    for raw in _DEFAULTS[phase]:
        path = Path(raw)
        if path.is_file() and _play_file(path, block=block):
            return

    for event in _CANBERRA[phase]:
        if _play_canberra(event, block=block):
            return

    logger.debug('No audio cue available for %s', phase)


def _play_spec(spec: str, *, block: bool) -> bool:
    text = spec.strip()
    if not text:
        return False
    if text.startswith('canberra:'):
        return _play_canberra(text.removeprefix('canberra:').strip(), block=block)
    path = Path(text).expanduser()
    if path.is_file():
        return _play_file(path, block=block)
    return _play_canberra(text, block=block)


def _play_file(path: Path, *, block: bool) -> bool:
    if shutil.which('paplay'):
        return _run(['paplay', str(path)], block=block)
    if shutil.which('aplay') and path.suffix.lower() == '.wav':
        return _run(['aplay', '-q', str(path)], block=block)
    return False


def _play_canberra(event: str, *, block: bool) -> bool:
    if not event or not shutil.which('canberra-gtk-play'):
        return False
    return _run(['canberra-gtk-play', '-i', event], block=block)


def _run(cmd: list[str], *, block: bool) -> bool:
    try:
        if block:
            subprocess.run(cmd, check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
