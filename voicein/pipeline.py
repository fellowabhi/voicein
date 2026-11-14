"""STT (+ optional LLM) → clipboard paste."""

from __future__ import annotations

import logging

from openai import OpenAI

from voicein.clips import save_clip
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

    save_clip(data=wav_bytes, filename="recording.wav", source="laptop")

    transcript = stt_openai.transcribe_audio(
        client,
        data=wav_bytes,
        filename="recording.wav",
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
    return True, f"On clipboard + pasted ({len(formatted)} chars): {snippet!r}"


def run_pipeline_audio(
    *,
    client: OpenAI,
    cfg: VoicEinConfig,
    data: bytes,
    filename: str,
    rewrite_level: int,
) -> tuple[bool, str]:
    """Same as ``run_pipeline`` but accepts webm/mp4/wav uploads from the phone page."""

    if not data:
        return False, "Recording buffer empty"

    save_clip(data=data, filename=filename, source="phone")

    transcript = stt_openai.transcribe_audio(
        client,
        data=data,
        filename=filename,
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
    return True, f"On clipboard + pasted ({len(formatted)} chars): {snippet!r}"
