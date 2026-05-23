"""STT (+ optional LLM) → clipboard paste."""

from __future__ import annotations

import logging

from openai import OpenAI

from voicein.config import VoicEinConfig
from voicein.inject.clipboard import paste_text
from voicein.llm import openai as fmt_openai
from voicein.stt import openai as stt_openai

logger = logging.getLogger(__name__)


def run_pipeline(
    *,
    client: OpenAI,
    cfg: VoicEinConfig,
    wav_bytes: bytes,
    rewrite_level: int,
) -> tuple[bool, str]:
    """Return ``(success, summary)`` for logging / tray diagnostics."""

    if not wav_bytes:
        return False, "Recording buffer empty"

    transcript = stt_openai.transcribe_wav(
        client,
        wav_bytes=wav_bytes,
        model=cfg.stt_model,
        language=cfg.stt_language,
    )

    if not transcript.strip():
        return False, "Transcription contained no usable text"

    formatted = transcript
    if cfg.llm_enabled:
        formatted = fmt_openai.format_transcript(
            client=client,
            transcript=transcript,
            rewrite_level=rewrite_level,
            model=cfg.llm_model,
        )

    if not formatted.strip():
        return False, "Formatter returned empty text"

    paste_text(formatted)
    snippet = formatted.replace("\r", "").splitlines()[0][:92]
    return True, f"Pasted ({len(formatted)} chars): {snippet!r}"
