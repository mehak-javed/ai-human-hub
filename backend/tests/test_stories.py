"""Tests for AI story generation: schema checks, retry and fallback (AI4, AI6).

No real HTTP calls: `httpx.post` is replaced with a fake that returns the
next canned answer for each provider and records every request.
"""

import json
import logging

import httpx
import pytest

from projects import stories
from projects.stories import InvalidAnswer, StoryGenerationError, generate_stories, parse_answer

WORKERS = "api.cloudflare.com"
GROQ = "api.groq.com"

VALID = {
    "stories": [
        {
            "role": "customer",
            "goal": "order a cake online",
            "reason": "I don't have to visit the shop",
            "acceptance_criteria": ["I can choose a cake", "I can pick a collection time"],
            "priority": "must",
        },
        {
            "role": "bakery owner",
            "goal": "see each day's orders",
            "reason": "I can plan my baking",
            "acceptance_criteria": ["Orders are listed by collection time"],
            "priority": "should",
        },
    ]
}


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
    monkeypatch.setattr(stories.httpx, "post", fake.post)
    return fake


def test_workers_ai_writes_the_stories(both_providers, fake_http):
    fake_http.replies[WORKERS].append(workers_reply(VALID))

    result = generate_stories(["I'm [NAME]. I want customers to order cakes online."])

    assert result.provider == "workers_ai"
    assert [s.goal for s in result.stories] == ["order a cake online", "see each day's orders"]
    assert result.stories[0].priority == "must"
    url, kwargs = fake_http.calls[0]
    assert url.endswith("/accounts/test-account/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    assert kwargs["json"]["response_format"]["type"] == "json_schema"
    assert fake_http.hosts() == [WORKERS]


def test_only_the_text_given_is_sent_inside_transcript_tags(both_providers, fake_http):
    fake_http.replies[WORKERS].append(workers_reply(VALID))

    generate_stories(["First recording by [NAME].", "Second recording."])

    messages = fake_http.calls[0][1]["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {
        "role": "user",
        "content": "<transcript>\nFirst recording by [NAME].\n\nSecond recording.\n</transcript>",
    }


def test_invalid_answer_is_retried_once(both_providers, fake_http, caplog):
    fake_http.replies[WORKERS] += [workers_reply({"stories": "oops"}), workers_reply(VALID)]

    with caplog.at_level(logging.WARNING, logger="projects.stories"):
        result = generate_stories(["text"])

    assert result.provider == "workers_ai"
    assert fake_http.hosts() == [WORKERS, WORKERS]
    assert "workers_ai attempt 1 failed: invalid answer" in caplog.text


def test_two_invalid_answers_fall_back_to_groq(both_providers, fake_http, caplog):
    bad = workers_reply({"stories": [{"role": "customer"}]})
    fake_http.replies[WORKERS] += [bad, bad]
    fake_http.replies[GROQ].append(groq_reply(VALID))

    with caplog.at_level(logging.WARNING, logger="projects.stories"):
        result = generate_stories(["Secret plans"])

    assert result.provider == "groq"
    assert fake_http.hosts() == [WORKERS, WORKERS, GROQ]
    groq_body = fake_http.calls[2][1]["json"]
    assert groq_body["model"] == "openai/gpt-oss-120b"
    assert groq_body["response_format"]["json_schema"]["strict"] is True
    # The switch is logged (AI6), without the client's words (privacy).
    assert "switched to backup provider groq" in caplog.text
    assert "Secret" not in caplog.text


def test_provider_error_falls_back_without_retrying(both_providers, fake_http, caplog):
    fake_http.replies[WORKERS].append((429, {"errors": [{"message": "daily limit"}]}))
    fake_http.replies[GROQ].append(groq_reply(VALID))

    with caplog.at_level(logging.WARNING, logger="projects.stories"):
        result = generate_stories(["text"])

    assert result.provider == "groq"
    # A limit or outage won't fix itself in a second, so no retry.
    assert fake_http.hosts() == [WORKERS, GROQ]
    assert "workers_ai failed: HTTP 429" in caplog.text


def test_error_when_every_provider_fails(both_providers, fake_http):
    fake_http.replies[WORKERS].append((500, {}))
    fake_http.replies[GROQ] += [groq_reply({"wrong": True}), groq_reply({"wrong": True})]

    with pytest.raises(StoryGenerationError):
        generate_stories(["text"])
    assert fake_http.hosts() == [WORKERS, GROQ, GROQ]


def test_unconfigured_provider_is_skipped(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = "test-groq-key"
    fake_http.replies[GROQ].append(groq_reply(VALID))

    assert generate_stories(["text"]).provider == "groq"
    assert fake_http.hosts() == [GROQ]


def test_error_when_no_provider_is_configured(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = ""

    with pytest.raises(StoryGenerationError):
        generate_stories(["text"])
    assert fake_http.calls == []


# --- The schema (AI4): what counts as a valid answer --------------------------


def story(**changes):
    return {**VALID["stories"][0], **changes}


def test_answer_can_be_a_json_string_or_a_markdown_code_block():
    text = json.dumps(VALID)
    assert len(parse_answer(text)) == 2
    assert len(parse_answer(f"```json\n{text}\n```")) == 2


def test_extra_whitespace_is_trimmed():
    [parsed] = parse_answer({"stories": [story(role="  customer  ")]})
    assert parsed.role == "customer"


@pytest.mark.parametrize(
    "answer",
    [
        "not json at all",
        [],
        {},
        {"stories": []},
        {"stories": [story(priority="urgent")]},
        {"stories": [story(goal="")]},
        {"stories": [story(goal="x" * 301)]},
        {"stories": [story(acceptance_criteria=[])]},
        {"stories": [story(acceptance_criteria=["ok"] * 9)]},
        {"stories": [{k: v for k, v in story().items() if k != "reason"}]},
        {"stories": [story()] * 31},
    ],
    ids=[
        "not-json",
        "list",
        "empty-object",
        "no-stories",
        "unknown-priority",
        "empty-goal",
        "goal-too-long",
        "no-criteria",
        "too-many-criteria",
        "missing-reason",
        "too-many-stories",
    ],
)
def test_invalid_answers_are_rejected(answer):
    with pytest.raises(InvalidAnswer):
        parse_answer(answer)