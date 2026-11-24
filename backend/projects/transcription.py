"""Turn recorded audio into text with Whisper (AI1).

Providers are tried in order: Cloudflare Workers AI first, Groq as the
backup (AI6). A provider is skipped when its keys aren't configured.

Privacy (P1): audio is passed in as bytes, sent to the provider over HTTPS
and never written anywhere. Logs record which provider failed and why, but
never audio or transcript text.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-large-v3-turbo"
# Each provider gets this long; both together stay under gunicorn's timeout.
PROVIDER_TIMEOUT_SECONDS = 45

# Groq works out the audio format from the file name's extension.
FILE_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


@dataclass(frozen=True)
class Transcription:
    text: str
    provider: str
    duration_seconds: float | None


class TranscriptionError(Exception):
    """No provider could transcribe the audio."""


def transcribe_with_workers_ai(audio: bytes, content_type: str) -> Transcription:
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/openai/{WHISPER_MODEL}"
    )
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.CLOUDFLARE_AI_TOKEN}"},
        json={"audio": base64.b64encode(audio).decode("ascii")},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    result = body.get("result", body)
    info = result.get("transcription_info") or {}
    return Transcription(
        text=result["text"].strip(),
        provider="workers_ai",
        duration_seconds=info.get("duration"),
    )


def transcribe_with_groq(audio: bytes, content_type: str) -> Transcription:
    filename = f"recording.{FILE_EXTENSIONS.get(content_type, 'webm')}"
    response = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        data={"model": WHISPER_MODEL, "response_format": "verbose_json", "temperature": "0"},
        files={"file": (filename, audio, content_type)},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    return Transcription(
        text=body["text"].strip(),
        provider="groq",
        duration_seconds=body.get("duration"),
    )


Provider = Callable[[bytes, str], Transcription]


def configured_providers() -> list[tuple[str, Provider]]:
    providers: list[tuple[str, Provider]] = []
    if settings.CLOUDFLARE_ACCOUNT_ID and settings.CLOUDFLARE_AI_TOKEN:
        providers.append(("workers_ai", transcribe_with_workers_ai))
    if settings.GROQ_API_KEY:
        providers.append(("groq", transcribe_with_groq))
    return providers


def describe_failure(exc: Exception) -> str:
    """A log-safe reason: the error type and HTTP status, never the body."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def transcribe(audio: bytes, content_type: str) -> Transcription:
    providers = configured_providers()
    if not providers:
        raise TranscriptionError("No transcription provider is configured.")

    for index, (name, provider) in enumerate(providers):
        try:
            result = provider(audio, content_type)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Transcription provider %s failed: %s", name, describe_failure(exc))
            continue
        if index > 0:
            logger.warning("Transcription switched to backup provider %s", name)
        return result

    raise TranscriptionError("All transcription providers failed.")