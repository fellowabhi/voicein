"""Minimal system tray for on-demand toggle mode (recording / processing / done)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time

import pystray

from voicein.tray import (
    ICON_ERROR,
    ICON_IDLE,
    ICON_PROCESSING,
    ICON_PROCESSING_PULSE,
    ICON_RECORD,
    ICON_SUCCESS,
    _draw_icon,
)

from voicein.toggle_session import (
    PHASE_ERROR,
    PHASE_PROCESSING,
    PHASE_RECORDING,
    PHASE_SUCCESS,
    clear_session_state,
    pid_alive,
    read_session_state,
    runtime_dir,
    tray_pid_path,
)

logger = logging.getLogger(__name__)

ICON_RECORD_PULSE = _draw_icon((255, 118, 118))
POLL_SEC = 0.35
SUCCESS_SHOW_SEC = 2.75
ERROR_SHOW_SEC = 5.0


def _tray_title(text: str) -> str:
    """pystray on XWayland only accepts latin-1 tooltip strings."""
    return text.encode('ascii', 'replace').decode('ascii')


class ToggleStatusTray:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._rec_pulse = False
        self._proc_pulse = False
        self._last_phase = ''

        self.icon = pystray.Icon(
            name='voicein-toggle',
            icon=ICON_IDLE,
            title='VoiceIn - ready',
            menu=pystray.Menu(
                pystray.MenuItem('Toggle dictation', self._on_toggle, default=True),
                pystray.MenuItem('Quit tray icon', self._on_quit),
            ),
        )
        self.icon.default_action = self._on_toggle

    def _on_toggle(self, *_args: object) -> None:
        subprocess.Popen(  # noqa: S603
            [sys.executable, '-m', 'voicein', 'toggle'],
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _on_quit(self, *_args: object) -> None:
        self._stop.set()
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        try:
            self.icon.run()
        finally:
            self._stop.set()
            try:
                tray_pid_path().unlink(missing_ok=True)
            except OSError:
                pass

    def _poll_loop(self) -> None:
        while not self._stop.wait(POLL_SEC):
            try:
                self._apply_state(read_session_state())
            except Exception:  # noqa: BLE001
                logger.debug('tray poll failed', exc_info=True)

    def _apply_state(self, state: dict | None) -> None:
        now = time.time()
        if not state:
            self._last_phase = ''
            self.icon.icon = ICON_IDLE
            self.icon.title = 'VoiceIn - ready (shortcut to dictate)'
            return

        phase = str(state.get('phase', ''))
        detail = str(state.get('detail', '') or '').strip()
        started = float(state.get('started', now))
        pid = int(state.get('pid', 0))

        if phase == PHASE_RECORDING and pid and not pid_alive(pid):
            clear_session_state()
            return

        if phase == PHASE_SUCCESS:
            self.icon.icon = ICON_SUCCESS
            title = 'VoiceIn - pasted'
            if detail:
                short = detail if len(detail) <= 72 else detail[:69] + '...'
                title = f'VoiceIn - pasted: {short}'
            self.icon.title = _tray_title(title)
            if now - started >= SUCCESS_SHOW_SEC:
                clear_session_state()
            return

        if phase == PHASE_ERROR:
            self.icon.icon = ICON_ERROR
            title = detail[:80] if detail else 'VoiceIn - failed'
            self.icon.title = _tray_title(f'VoiceIn - {title}')
            if now - started >= ERROR_SHOW_SEC:
                clear_session_state()
            return

        if phase == PHASE_RECORDING:
            self._rec_pulse = not self._rec_pulse
            self.icon.icon = ICON_RECORD_PULSE if self._rec_pulse else ICON_RECORD
            elapsed = max(0, int(now - started))
            self.icon.title = f'VoiceIn - recording {elapsed // 60:02d}:{elapsed % 60:02d}'
            self._last_phase = phase
            return

        if phase == PHASE_PROCESSING:
            self._proc_pulse = not self._proc_pulse
            self.icon.icon = (
                ICON_PROCESSING_PULSE if self._proc_pulse else ICON_PROCESSING
            )
            self.icon.title = 'VoiceIn - transcribing...'
            self._last_phase = phase
            return

        self.icon.icon = ICON_IDLE
        self.icon.title = 'VoiceIn - ready'


def write_tray_pid() -> None:
    runtime_dir().mkdir(parents=True, exist_ok=True)
    tray_pid_path().write_text(str(os.getpid()), encoding='utf-8')


def run_toggle_tray() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    write_tray_pid()
    ToggleStatusTray().run()
    return 0
