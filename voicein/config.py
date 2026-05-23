"""Load optional user configuration from ``~/.config/voicein``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from dotenv import load_dotenv

# Project-specific name — wins over generic OPENAI_API_KEY when both are set.
VOICEIN_OPENAI_API_KEY = "VOICEIN_OPENAI_API_KEY"
FALLBACK_OPENAI_API_KEY = "OPENAI_API_KEY"


def config_dir() -> Path:
    override = os.environ.get("VOICEIN_CONFIG_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    default = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return default / "voicein"


def project_root() -> Path:
    """Repository root (parent of the ``voicein`` package)."""

    return Path(__file__).resolve().parent.parent


def project_env_path() -> Path:
    return project_root() / ".env"


def default_config_paths() -> tuple[Path, Path]:
    d = config_dir()
    return d / "config.toml", d / ".env"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


@dataclass
class VoicEinConfig:
    hotkey_shortcut: str | None = "Super+Shift+V"
    audio_sample_rate: int = 16000
    audio_input_device: str | int | None = None  # "" or None = default
    audio_max_duration_secs: int = 300

    stt_provider: str = "openai"
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_language: str = "en"

    llm_enabled: bool = True
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_rewrite_level: int = 0

    inject_method: str = "clipboard"

    openai_api_key: str | None = None


def parse_device(raw: Any) -> str | int | None:
    """Empty string → default device; integer string → index."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return s


def _load_dotenv_files(*, global_env: Path, project_env: Path) -> None:
    """Load env files: project ``.env`` overrides global config dir."""

    if global_env.is_file():
        load_dotenv(global_env, override=False)

    if project_env.is_file():
        load_dotenv(project_env, override=True)


def resolve_openai_api_key() -> str | None:
    """Return API key from process env (``VOICEIN_*`` first, then ``OPENAI_*``)."""

    for name in (VOICEIN_OPENAI_API_KEY, FALLBACK_OPENAI_API_KEY):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    return None


def load_config(
    *,
    base_path: Path | None = None,
    env_override: dict[str, str] | None = None,
) -> VoicEinConfig:
    cfg_path = (base_path or config_dir()) / "config.toml"
    global_env = (base_path or config_dir()) / ".env"
    project_env = project_env_path()

    _load_dotenv_files(global_env=global_env, project_env=project_env)

    raw = _read_toml(cfg_path)

    hk = raw.get("hotkey", {}) if isinstance(raw.get("hotkey"), dict) else {}
    au = raw.get("audio", {}) if isinstance(raw.get("audio"), dict) else {}
    st = raw.get("stt", {}) if isinstance(raw.get("stt"), dict) else {}
    lm = raw.get("llm", {}) if isinstance(raw.get("llm"), dict) else {}
    ij = raw.get("inject", {}) if isinstance(raw.get("inject"), dict) else {}

    shortcut = hk.get("shortcut", VoicEinConfig.hotkey_shortcut)
    shortcut_s = shortcut.strip() if isinstance(shortcut, str) else None
    cfg = VoicEinConfig(
        hotkey_shortcut=shortcut_s or None,
        audio_sample_rate=int(au.get("sample_rate", 16000)),
        audio_input_device=parse_device(au.get("input_device", "")),
        audio_max_duration_secs=int(au.get("max_duration_secs", 300)),
        stt_provider=str(st.get("provider", "openai")),
        stt_model=str(st.get("model", "gpt-4o-mini-transcribe")),
        stt_language=str(st.get("language", "en")),
        llm_enabled=bool(lm.get("enabled", True)),
        llm_provider=str(lm.get("provider", "openai")),
        llm_model=str(lm.get("model", "gpt-4o-mini")),
        llm_rewrite_level=max(0, min(10, int(lm.get("rewrite_level", 0)))),
        inject_method=str(ij.get("method", "clipboard")),
    )

    if env_override:
        for name in (VOICEIN_OPENAI_API_KEY, FALLBACK_OPENAI_API_KEY):
            key = env_override.get(name)
            if key:
                cfg.openai_api_key = key
                break

    resolved = resolve_openai_api_key()
    if resolved:
        cfg.openai_api_key = resolved

    return cfg
