"""Shared application enumeration for UI + orchestrator."""

from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
