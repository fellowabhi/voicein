"""Optional global shortcut (toggle recording) via pynput — X11 typical."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


_SHORTCUT_KEYS: dict[str, keyboard.Key] = {
    "shift": keyboard.Key.shift,
    "shift_l": keyboard.Key.shift_l,
    "shift_r": keyboard.Key.shift_r,
    "ctrl": keyboard.Key.ctrl,
    "control": keyboard.Key.ctrl,
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "alt": keyboard.Key.alt,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
    "super": keyboard.Key.cmd,
    "win": keyboard.Key.cmd,
    "meta": keyboard.Key.cmd,
    "cmd": keyboard.Key.cmd,
    "windows": keyboard.Key.cmd,
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "ins": keyboard.Key.insert,
    "insert": keyboard.Key.insert,
}


def _normalize_key(
    key: keyboard.Key | keyboard.KeyCode | None,
) -> keyboard.Key | keyboard.KeyCode | None:
    """Collapse common left/right aliases so combos match typical Linux keyboards."""
    if key is None:
        return None
    lr_pairs = (
        (keyboard.Key.shift_l, keyboard.Key.shift),
        (keyboard.Key.shift_r, keyboard.Key.shift),
        (keyboard.Key.ctrl_l, keyboard.Key.ctrl),
        (keyboard.Key.ctrl_r, keyboard.Key.ctrl),
        (keyboard.Key.alt_l, keyboard.Key.alt),
        (keyboard.Key.alt_r, keyboard.Key.alt),
    )
    for lhs, merged in lr_pairs:
        if key == lhs:
            return merged
    return key


def _same_key(
    part: keyboard.Key | keyboard.KeyCode | None,
    pressed: keyboard.Key | keyboard.KeyCode | None,
) -> bool:
    """Loose equality for modifier keys pressed as left/right variants."""
    if part is None or pressed is None:
        return False
    if part == pressed:
        return True
    return _normalize_key(part) == _normalize_key(pressed)


def _parse_combo(spec: str) -> frozenset[keyboard.Key | keyboard.KeyCode]:
    parts = [
        p.strip().lower().replace("-", "_")
        for p in spec.split("+")
        if p.strip()
    ]
    combo: set[keyboard.Key | keyboard.KeyCode] = set()
    for raw in parts:
        if raw in _SHORTCUT_KEYS:
            combo.add(_SHORTCUT_KEYS[raw])
            continue
        if len(raw) == 1:
            combo.add(keyboard.KeyCode.from_char(raw))
            continue
        if raw.startswith("f") and raw[1:].isdigit():
            name = raw.lower().replace("+", "")
            fk = getattr(keyboard.Key, name, None)
            if fk is None:
                raise ValueError(f"Unknown function-key fragment: {raw!r}")
            combo.add(fk)
            continue
        raise ValueError(f"Unknown shortcut fragment: {raw!r}")

    return frozenset(combo)


class ShortcutListener:
    """Invoke ``on_toggle`` once each time combo keys transition to fully pressed."""

    def __init__(
        self,
        shortcut: str | None,
        *,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        stripped = shortcut.strip() if shortcut else ""
        try:
            self._combo = _parse_combo(stripped) if stripped else frozenset()
        except ValueError:
            logger.exception("Invalid shortcut %r — disabling hotkey listener", shortcut)
            self._combo = frozenset()

        self._on_toggle = on_toggle
        self._on_cancel = on_cancel

        self._listener: keyboard.Listener | None = None
        self._lock = threading.Lock()
        self._pressed: set[keyboard.Key | keyboard.KeyCode] = set()
        self._combo_holding = False

    def start(self) -> None:
        if not self._combo:
            return
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.start()
        logger.info("Shortcut listener attached (%d keys)", len(self._combo))

    def stop(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener.stop()
        finally:
            self._listener = None

    def _combo_satisfied_locked(self) -> bool:
        for part in self._combo:
            if not any(_same_key(part, p) for p in self._pressed):
                return False
        return bool(self._combo)

    def _press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:  # type: ignore[name-defined]
        if key is None:
            return

        if key == keyboard.Key.esc or _normalize_key(key) == keyboard.Key.esc:
            self._on_cancel()

        canon = _normalize_key(key)
        canon_key = canon if canon is not None else key

        with self._lock:
            self._pressed.add(key)
            self._pressed.add(canon_key)

            satisfied = self._combo_satisfied_locked()
            if satisfied and not self._combo_holding:
                self._combo_holding = True
                self._on_toggle()
            elif not satisfied:
                self._combo_holding = False

    def _release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:  # type: ignore[name-defined]
        if key is None:
            return

        canon = _normalize_key(key)
        canon_key = canon if canon is not None else key

        with self._lock:
            self._pressed.discard(key)
            self._pressed.discard(canon_key)

            self._combo_holding = self._combo_satisfied_locked()
