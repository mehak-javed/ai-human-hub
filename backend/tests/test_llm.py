"""Tests for asking an AI for JSON: retry, fallback and logging (AI4, AI6).

No real HTTP calls: `httpx.post` is replaced with a fake that returns the
next canned reply for each provider and records every request.
"""

import json
import logging

import httpx
import pytest

from projects import llm
from projects.llm import InvalidAnswer, LLMError, ask_for_json, load_json

WORKERS = "api.cloudflare.com"
GROQ = "api.groq.com"
MESSAGES = [{"role": "user", "content": "Secret plans"}]
SCHEMA = {"type": "object"}
GOOD = {"ok": True}


def parse(answer):
    """Accept only {"ok": true}, like a real schema would."""
    answer = load_json(answer)
    if answer != GOOD:
        raise InvalidAnswer("wrong shape")
    return "parsed"


def workers_reply(answer):
    # Workers AI returns the parsed JSON object under result.response.
    return (200, {"result": {"response": answer}, "success": True})


def groq_reply(answer):
    # Groq returns the answer as a JSON string, like OpenAI's API.
    return (200, {"choices": [{"message": {"content": json.dumps(answer)}}]})


@pytest.fixture
def both_providers(settings):
    settings.CLOUDFLARE_ACCOUNT_ID = "test-account"
    settings.CLOUDFLARE_AI_TOKEN = "test-cf-token"
    settings.GROQ_API_KEY = "test-groq-key"


@pytest.fixture
def fake_http(monkeypatch):
    """Replace httpx.post. Queue replies with `fake_http.replies[host].append(...)`."""

    class FakeHttp:
        def __init__(self):
            self.calls = []
            self.replies = {WORKERS: [], GROQ: []}

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            host = WORKERS if WORKERS in url else GROQ
            request = httpx.Request("POST", url)
            if not self.replies[host]:
                raise httpx.ConnectError("no fake reply", request=request)
            status, body = self.replies[host].pop(0)
            return httpx.Response(status, json=body, request=request)

        def hosts(self):
            return [WORKERS if WORKERS in url else GROQ for url, _ in self.calls]

    fake = FakeHttp()
    monkeypatch.setattr(llm.httpx, "post", fake.post)
    return fake


def ask():
    return ask_for_json(MESSAGES, "test_schema", SCHEMA, parse)


def test_workers_ai_is_asked_first(both_providers, fake_http):
    fake_http.replies[WORKERS].append(workers_reply(GOOD))

    assert ask() == ("parsed", "workers_ai")
    url, kwargs = fake_http.calls[0]
    assert url.endswith("/accounts/test-account/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    assert kwargs["headers"]["Authorization"] == "Bearer test-cf-token"
    assert kwargs["json"]["messages"] == MESSAGES
    assert kwargs["json"]["response_format"] == {"type": "json_schema", "json_schema": SCHEMA}
    assert fake_http.hosts() == [WORKERS]


def test_invalid_answer_is_retried_once(both_providers, fake_http, caplog):
    fake_http.replies[WORKERS] += [workers_reply({"ok": False}), workers_reply(GOOD)]

    with caplog.at_level(logging.WARNING, logger="projects.llm"):
        assert ask() == ("parsed", "workers_ai")

    assert fake_http.hosts() == [WORKERS, WORKERS]
    assert "workers_ai attempt 1 for test_schema failed: invalid answer" in caplog.text


def test_two_invalid_answers_fall_back_to_groq(both_providers, fake_http, caplog):
    bad = workers_reply({"ok": False})
    fake_http.replies[WORKERS] += [bad, bad]
    fake_http.replies[GROQ].append(groq_reply(GOOD))

    with caplog.at_level(logging.WARNING, logger="projects.llm"):
        assert ask() == ("parsed", "groq")

    assert fake_http.hosts() == [WORKERS, WORKERS, GROQ]
    groq_body = fake_http.calls[2][1]["json"]
    assert groq_body["model"] == "openai/gpt-oss-120b"
    assert groq_body["response_format"]["json_schema"] == {
        "name": "test_schema",
        "strict": True,
        "schema": SCHEMA,
    }
    # The switch is logged (AI6), without the client's words (privacy).
    assert "switched to backup provider groq" in caplog.text
    assert "Secret" not in caplog.text


def test_provider_error_falls_back_without_retrying(both_providers, fake_http, caplog):
    fake_http.replies[WORKERS].append((429, {"errors": [{"message": "daily limit"}]}))
    fake_http.replies[GROQ].append(groq_reply(GOOD))

    with caplog.at_level(logging.WARNING, logger="projects.llm"):
        assert ask() == ("parsed", "groq")

    # A limit or outage won't fix itself in a second, so no retry.
    assert fake_http.hosts() == [WORKERS, GROQ]
    assert "workers_ai for test_schema failed: HTTP 429" in caplog.text


def test_misconfigured_provider_falls_back(both_providers, fake_http, settings, monkeypatch):
    # A line break pasted into a key raises InvalidURL, not an HTTP error.
    def strict_post(url, **kwargs):
        if WORKERS in url:
            raise httpx.InvalidURL("Invalid non-printable ASCII character in URL")
        return fake_http.post(url, **kwargs)

    fake_http.replies[GROQ].append(groq_reply(GOOD))
    monkeypatch.setattr(llm.httpx, "post", strict_post)

    assert ask() == ("parsed", "groq")


def test_error_when_every_provider_fails(both_providers, fake_http):
    fake_http.replies[WORKERS].append((500, {}))
    fake_http.replies[GROQ] += [groq_reply({"ok": False}), groq_reply({"ok": False})]

    with pytest.raises(LLMError):
        ask()
    assert fake_http.hosts() == [WORKERS, GROQ, GROQ]


def test_unconfigured_provider_is_skipped(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = "test-groq-key"
    fake_http.replies[GROQ].append(groq_reply(GOOD))

    assert ask() == ("parsed", "groq")
    assert fake_http.hosts() == [GROQ]


def test_error_when_no_provider_is_configured(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = ""

    with pytest.raises(LLMError):
        ask()
    assert fake_http.calls == []


def test_load_json_accepts_objects_strings_and_code_blocks():
    assert load_json(GOOD) == GOOD
    assert load_json('{"ok": true}') == GOOD
    assert load_json('```json\n{"ok": true}\n```') == GOOD
    with pytest.raises(InvalidAnswer):
        load_json("not json at all")