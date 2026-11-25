"""Ask an AI model for JSON, with validation, one retry and a backup (AI4, AI6).

Shared by every AI feature (user stories, follow-up questions). Providers are
tried in order: Cloudflare Workers AI first, Groq as the backup. A provider
is skipped when its keys aren't configured.

- The caller's `parse` function checks every answer. An invalid answer is
  retried once with the same provider, then the next provider is tried.
- An HTTP error, timeout or bad configuration goes straight to the next
  provider: retrying an outage or a daily limit would just fail again.

Callers must only send masked text (AI2). Logs record which provider failed
and why, but never the prompt or the answer.
"""

import json
import logging
from collections.abc import Callable
from typing import TypeVar

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

WORKERS_AI_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
GROQ_MODEL = "openai/gpt-oss-120b"
# Up to four calls (two providers, one retry each) must fit inside
# gunicorn's 120-second timeout.
PROVIDER_TIMEOUT_SECONDS = 25
MAX_OUTPUT_TOKENS = 4096
# Each request tries a provider at most this many times: once, plus one retry.
ATTEMPTS_PER_PROVIDER = 2

Messages = list[dict[str, str]]
T = TypeVar("T")


class LLMError(Exception):
    """No provider produced a valid answer."""


class InvalidAnswer(Exception):
    """The model answered, but not in the shape we asked for."""


def load_json(answer: object) -> object:
    """Accept an answer that is already parsed, a JSON string, or a Markdown code block."""
    if not isinstance(answer, str):
        return answer
    text = answer.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidAnswer("not JSON") from exc


def ask_workers_ai(messages: Messages, schema_name: str, json_schema: dict) -> object:
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.CLOUDFLARE_ACCOUNT_ID}/ai/run/{WORKERS_AI_MODEL}"
    )
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.CLOUDFLARE_AI_TOKEN}"},
        json={
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": json_schema},
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
        },
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    # With a JSON schema the answer usually comes back already parsed.
    return response.json()["result"]["response"]


def ask_groq(messages: Messages, schema_name: str, json_schema: dict) -> object:
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
            },
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
        },
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


Provider = Callable[[Messages, str, dict], object]


def configured_providers() -> list[tuple[str, Provider]]:
    providers: list[tuple[str, Provider]] = []
    if settings.CLOUDFLARE_ACCOUNT_ID and settings.CLOUDFLARE_AI_TOKEN:
        providers.append(("workers_ai", ask_workers_ai))
    if settings.GROQ_API_KEY:
        providers.append(("groq", ask_groq))
    return providers


def describe_failure(exc: Exception) -> str:
    """A log-safe reason: the error type and HTTP status, never the body."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, InvalidAnswer):
        return f"invalid answer ({exc})"
    return type(exc).__name__


def ask_for_json(
    messages: Messages,
    schema_name: str,
    json_schema: dict,
    parse: Callable[[object], T],
) -> tuple[T, str]:
    """Return `parse(answer)` and the name of the provider that gave it.

    `parse` must raise InvalidAnswer for an answer it can't accept.
    """
    providers = configured_providers()
    if not providers:
        raise LLMError("No AI provider is configured.")

    for index, (name, ask) in enumerate(providers):
        for attempt in range(1, ATTEMPTS_PER_PROVIDER + 1):
            try:
                result = parse(ask(messages, schema_name, json_schema))
            except InvalidAnswer as exc:
                logger.warning(
                    "AI provider %s attempt %d for %s failed: %s",
                    name,
                    attempt,
                    schema_name,
                    describe_failure(exc),
                )
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("AI provider %s for %s failed: %s", name, schema_name, describe_failure(exc))
                break
            if index > 0:
                logger.warning("AI switched to backup provider %s for %s", name, schema_name)
            return result, name

    raise LLMError(f"All AI providers failed for {schema_name}.")