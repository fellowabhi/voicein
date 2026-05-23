"""OpenAI Speech-to-text adapter."""

from __future__ import annotations

from io import BytesIO

from openai import OpenAI


def transcribe_wav(client: OpenAI, *, wav_bytes: bytes, model: str, language: str) -> str:
    """Upload mono PCM WAV (`wav_bytes`) to OpenAI's transcription endpoint."""
    if not wav_bytes:
        return ""

    file_obj = BytesIO(wav_bytes)
    file_obj.name = "recording.wav"

    resp = client.audio.transcriptions.create(
        model=model,
        file=file_obj,
        language=language if language else None,
        response_format="text",
    )

    if hasattr(resp, "text"):
        text = getattr(resp, "text", "")
    else:
        text = resp  # pragma: no cover — SDK variability
    # With response_format=text, SDK may return plain str
    out = "" if text is None else str(text).strip()
    return out
