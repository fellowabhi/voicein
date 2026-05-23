"""Continuous microphone recording into in-memory WAV buffer."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from io import BytesIO

import numpy as np
import sounddevice as sd
import wave

logger = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        input_device: str | int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.input_device = input_device
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._started_at: float | None = None

    def _resolve_device(self) -> int | str | None:
        if self.input_device is None:
            return None
        if isinstance(self.input_device, int):
            return self.input_device
        needle = str(self.input_device).lower()
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] <= 0:
                continue
            name = str(dev["name"]).lower()
            if needle in name:
                return i
        logger.warning(
            'No matching input device for pattern %r — using default',
            self.input_device,
        )
        return None

    def start(self, on_underflow: Callable[[], None] | None = None) -> None:
        if self._stream is not None:
            return

        device = self._resolve_device()

        def callback(indata, frames, t, status):  # type: ignore[no-untyped-def]
            del frames, t
            if status and getattr(status, "input_overflow", False):
                logger.debug("sounddevice overflow: %s", status)
            under = getattr(status, "input_underflow", False)
            if under and on_underflow:
                on_underflow()
            mono = np.mean(indata, axis=1) if indata.shape[1] > 1 else indata[:, 0]
            with self._lock:
                self._chunks.append(np.copy(mono.astype(np.float32)))

        self._chunks.clear()
        self._started_at = time.monotonic()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            device=device,
            callback=callback,
            blocksize=4096,
        )
        self._stream.start()

    def discard(self) -> None:
        """Abort capture silently (no WAV output)."""

        if self._stream is None:
            with self._lock:
                self._chunks.clear()
            self._started_at = None
            return

        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self._chunks.clear()
            self._started_at = None

    def stop_and_get_wav(self) -> bytes | None:
        """Stop stream and return WAV bytes (16-bit mono PCM); None when too weak/short."""

        if self._stream is None:
            return None

        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        recorded_start = self._started_at
        self._started_at = None

        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.array([], dtype=np.float32)

        self._chunks.clear()

        if audio.size == 0:
            return None

        peak = float(np.abs(audio).max())
        dur = audio.size / self.sample_rate

        if peak < 1e-4 or dur < 0.49:
            if recorded_start is not None:
                logger.debug("Discarded likely empty clip %.2fs peak=%s", dur, peak)
            return None

        int16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
        bio = BytesIO()
        with wave.open(bio, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(int16.tobytes())

        bytes_out = bio.getvalue()
        logger.debug(
            "Recorded WAV: %.2fs, %s bytes peak=%.6f",
            dur,
            len(bytes_out),
            peak,
        )
        return bytes_out

    def duration_seconds(self) -> float | None:
        if self._started_at is None:
            return None
        return max(0.0, time.monotonic() - self._started_at)
