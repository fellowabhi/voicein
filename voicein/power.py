"""Release global hotkey grab before system sleep (prevents X11 freezes)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


def install_sleep_watcher(
    *,
    on_sleep: Callable[[], None],
    on_wake: Callable[[], None],
) -> threading.Thread | None:
    """Watch logind PrepareForSleep via ``busctl`` (works inside venv)."""

    if not shutil.which('busctl'):
        logger.warning('busctl missing — cannot watch sleep/resume events')
        return None

    def _run() -> None:
        try:
            proc = subprocess.Popen(
                ['busctl', 'monitor', '--system', 'org.freedesktop.login1'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError:
            logger.exception('Unable to start busctl monitor')
            return

        assert proc.stdout is not None
        logger.info('Sleep/resume watcher active (busctl → logind)')

        for line in proc.stdout:
            lowered = line.lower()
            if 'prepareforsleep' not in lowered:
                continue
            if 'true' in lowered:
                on_sleep()
            elif 'false' in lowered:
                on_wake()

    thread = threading.Thread(target=_run, name='voicein-sleep-watch', daemon=True)
    thread.start()
    return thread
