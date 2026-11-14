"""Keep recent dictation clips for A/B listening; rotate old files."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_SOURCE = re.compile(r"[^a-z0-9_-]+")

DEFAULT_KEEP = 40
DEFAULT_MAX_AGE_DAYS = 14
DEFAULT_MAX_MB = 400


def clips_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(state).expanduser() if state else Path.home() / ".local/state"
    return root / "voicein" / "clips"


def save_clip(
    *,
    data: bytes,
    filename: str,
    source: str,
    keep: int = DEFAULT_KEEP,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_mb: int = DEFAULT_MAX_MB,
) -> Path | None:
    if not data:
        return None

    folder = clips_dir()
    folder.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower() or ".bin"
    if ext not in {".wav", ".webm", ".mp3", ".mp4", ".m4a", ".ogg", ".opus"}:
        ext = ".webm" if "webm" in filename.lower() else ".wav"

    tag = _SAFE_SOURCE.sub("", source.strip().lower()) or "clip"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}-{tag}{ext}"
    if path.exists():
        path = folder / f"{stamp}-{tag}-{os.getpid()}{ext}"

    path.write_bytes(data)
    logger.info("Saved clip %s (%s bytes)", path, len(data))
    rotate_clips(keep=keep, max_age_days=max_age_days, max_mb=max_mb)
    return path


def rotate_clips(
    *,
    keep: int = DEFAULT_KEEP,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_mb: int = DEFAULT_MAX_MB,
) -> None:
    folder = clips_dir()
    if not folder.is_dir():
        return

    files = [p for p in folder.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    cutoff = time.time() - max(1, max_age_days) * 86400
    budget = max(1, max_mb) * 1024 * 1024
    kept: list[Path] = []
    total = 0

    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        too_old = st.st_mtime < cutoff
        too_many = len(kept) >= keep
        too_big = total + st.st_size > budget
        if too_old or too_many or too_big:
            try:
                path.unlink()
                logger.debug("Rotated clip %s", path)
            except OSError:
                logger.debug("Could not delete %s", path, exc_info=True)
            continue
        kept.append(path)
        total += st.st_size
