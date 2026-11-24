"""Tests for the Whisper providers and the switch to the backup (AI1, AI6).

No real HTTP calls: `httpx.post` is replaced with a fake that records each
request and returns a canned response.
"""

import base64
import logging

import httpx
import pytest

from projects import transcription
from projects.transcription import TranscriptionError, transcribe

AUDIO = b"fake-webm-bytes"
WORKERS_URL_PART = "api.cloudflare.com"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


@pytest.fixture
def both_providers(settings):
    settings.CLOUDFLARE_ACCOUNT_ID = "test-account"
    settings.CLOUDFLARE_AI_TOKEN = "test-cf-token"
    settings.GROQ_API_KEY = "test-groq-key"


@pytest.fixture
def fake_http(monkeypatch):
    """Replace httpx.post. Set `fake_http.responses[url_part] = (status, json)`."""

    class FakeHttp:
        def __init__(self):
            self.calls = []
            self.responses = {}

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            for url_part, (status, body) in self.responses.items():
                if url_part in url:
                    return httpx.Response(status, json=body, request=httpx.Request("POST", url))
            raise httpx.ConnectError("no fake response", request=httpx.Request("POST", url))

    fake = FakeHttp()
    monkeypatch.setattr(transcription.httpx, "post", fake.post)
    return fake


def test_workers_ai_is_used_first(both_providers, fake_http):
    fake_http.responses[WORKERS_URL_PART] = (
        200,
        {"result": {"text": " Hello there. ", "transcription_info": {"duration": 4.2}}, "success": True},
    )

    result = transcribe(AUDIO, "audio/webm")

    assert result.text == "Hello there."
    assert result.provider == "workers_ai"
    assert result.duration_seconds == 4.2
    url, kwargs = fake_http.calls[0]
    assert url.endswith("/accounts/test-account/ai/run/@cf/openai/whisper-large-v3-turbo")
    assert kwargs["headers"]["Authorization"] == "Bearer test-cf-token"
    assert kwargs["json"] == {"audio": base64.b64encode(AUDIO).decode("ascii")}
    assert len(fake_http.calls) == 1


def test_falls_back_to_groq_when_workers_ai_fails(both_providers, fake_http, caplog):
    fake_http.responses[WORKERS_URL_PART] = (429, {"errors": [{"message": "daily limit"}]})
    fake_http.responses["api.groq.com"] = (200, {"text": "Secret project details", "duration": 3.0})

    with caplog.at_level(logging.WARNING, logger="projects.transcription"):
        result = transcribe(AUDIO, "audio/webm")

    assert result.provider == "groq"
    assert result.text == "Secret project details"
    url, kwargs = fake_http.calls[1]
    assert url == GROQ_URL
    assert kwargs["files"]["file"] == ("recording.webm", AUDIO, "audio/webm")
    assert kwargs["data"]["model"] == "whisper-large-v3-turbo"
    # The switch is logged (AI6), without the transcript (privacy).
    assert "workers_ai failed: HTTP 429" in caplog.text
    assert "switched to backup provider groq" in caplog.text
    assert "Secret" not in caplog.text


def test_malformed_response_also_falls_back(both_providers, fake_http):
    fake_http.responses[WORKERS_URL_PART] = (200, {"result": {"unexpected": True}})
    fake_http.responses["api.groq.com"] = (200, {"text": "Backup worked"})

    result = transcribe(AUDIO, "audio/mp4")

    assert result.provider == "groq"
    assert result.duration_seconds is None
    assert fake_http.calls[1][1]["files"]["file"][0] == "recording.mp4"


def test_error_when_every_provider_fails(both_providers, fake_http):
    fake_http.responses[WORKERS_URL_PART] = (500, {})
    fake_http.responses["api.groq.com"] = (503, {})

    with pytest.raises(TranscriptionError):
        transcribe(AUDIO, "audio/webm")


def test_unconfigured_provider_is_skipped(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = "test-groq-key"
    fake_http.responses["api.groq.com"] = (200, {"text": "Only Groq"})

    result = transcribe(AUDIO, "audio/webm")

    assert result.provider == "groq"
    assert len(fake_http.calls) == 1


def test_error_when_no_provider_is_configured(settings, fake_http):
    settings.CLOUDFLARE_ACCOUNT_ID = ""
    settings.CLOUDFLARE_AI_TOKEN = ""
    settings.GROQ_API_KEY = ""

    with pytest.raises(TranscriptionError):
        transcribe(AUDIO, "audio/webm")
    assert fake_http.calls == []