"""Tests for uploading a recording and listing transcripts (C4, AI1, P1, N2).

The transcription service is replaced with a fake, so no AI provider is
called. The provider logic itself is tested in test_transcription.py.
"""

import pytest
from django.apps import apps
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from projects import views
from projects.models import CONSENT_VERSION, Project, Transcript
from projects.transcription import Transcription, TranscriptionError

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_throttle_history():
    cache.clear()


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice")


@pytest.fixture
def bob():
    return User.objects.create(username="bob", clerk_id="user_bob")


@pytest.fixture
def project(alice):
    return make_project(alice)


@pytest.fixture
def fake_transcribe(monkeypatch):
    """Replace the real transcription with one that records its calls."""
    calls = []

    def fake(audio, content_type):
        calls.append((audio, content_type))
        return Transcription(
            text="I'm Sam, my name is Sam Lee. I need a booking website.",
            provider="groq",
            duration_seconds=12.5,
        )

    monkeypatch.setattr(views, "transcribe", fake)
    return calls


def make_project(owner, status=Project.Status.INTERVIEWING):
    return Project.objects.create(
        owner=owner,
        name="Bakery website",
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def recording(content=b"fake-audio", content_type="audio/webm;codecs=opus"):
    return SimpleUploadedFile("recording.webm", content, content_type=content_type)


def upload(user, project, audio=None):
    data = {"audio": audio} if audio is not None else {}
    url = reverse("project-transcripts", args=[project.id])
    return client_for(user).post(url, data, format="multipart")


@pytest.mark.django_db
def test_upload_saves_transcript(alice, project, fake_transcribe):
    response = upload(alice, project, recording())

    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "I'm Sam, my name is Sam Lee. I need a booking website."
    # AI2: the masked copy is saved alongside and returned for transparency.
    assert body["masked_text"] == "I'm [NAME], my name is [NAME]. I need a booking website."
    assert body["duration_seconds"] == 12.5
    assert fake_transcribe == [(b"fake-audio", "audio/webm")]
    assert project.transcripts.count() == 1


@pytest.mark.django_db
def test_masked_text_is_kept_in_step_with_text(project):
    transcript = Transcript.objects.create(project=project, text="Email sam@shop.com", provider="groq")
    assert transcript.masked_text == "Email [EMAIL]"

    transcript.text = "Call 07700 900123"
    transcript.save()
    transcript.refresh_from_db()

    assert transcript.masked_text == "Call [PHONE]"


@pytest.mark.django_db
def test_list_returns_transcripts_oldest_first(alice, project):
    Transcript.objects.create(project=project, text="First", provider="groq")
    Transcript.objects.create(project=project, text="Second", provider="groq")

    response = client_for(alice).get(reverse("project-transcripts", args=[project.id]))

    assert response.status_code == 200
    assert [t["text"] for t in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_cannot_upload_to_another_clients_project(alice, bob, fake_transcribe):
    bobs_project = make_project(bob)

    response = upload(alice, bobs_project, recording())

    assert response.status_code == 404
    assert fake_transcribe == []


@pytest.mark.django_db
def test_cannot_read_another_clients_transcripts(alice, bob):
    bobs_project = make_project(bob)

    response = client_for(alice).get(reverse("project-transcripts", args=[bobs_project.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_upload_requires_sign_in(project):
    url = reverse("project-transcripts", args=[project.id])

    response = APIClient().post(url, {"audio": recording()}, format="multipart")

    assert response.status_code == 401


@pytest.mark.django_db
def test_missing_file_is_rejected(alice, project, fake_transcribe):
    response = upload(alice, project)

    assert response.status_code == 400
    assert "audio" in response.json()


@pytest.mark.django_db
def test_non_audio_file_is_rejected(alice, project, fake_transcribe):
    response = upload(alice, project, recording(b"<html>", content_type="text/html"))

    assert response.status_code == 400
    assert fake_transcribe == []


@pytest.mark.django_db
def test_too_large_recording_is_rejected(alice, project, fake_transcribe, settings):
    settings.MAX_RECORDING_BYTES = 1000

    response = upload(alice, project, recording(b"x" * 2000))

    assert response.status_code == 413
    assert fake_transcribe == []


@pytest.mark.django_db
def test_provider_outage_returns_503_and_saves_nothing(alice, project, monkeypatch):
    def failing(audio, content_type):
        raise TranscriptionError("All transcription providers failed.")

    monkeypatch.setattr(views, "transcribe", failing)

    response = upload(alice, project, recording())

    assert response.status_code == 503
    assert not Transcript.objects.exists()


@pytest.mark.django_db
def test_silence_is_not_saved(alice, project, monkeypatch):
    monkeypatch.setattr(
        views, "transcribe", lambda audio, content_type: Transcription("", "groq", 3.0)
    )

    response = upload(alice, project, recording())

    assert response.status_code == 422
    assert not Transcript.objects.exists()


@pytest.mark.django_db
def test_no_recordings_after_interview_ends(alice, fake_transcribe):
    finished = make_project(alice, status=Project.Status.AWAITING_CLIENT)

    response = upload(alice, finished, recording())

    assert response.status_code == 409
    assert fake_transcribe == []


@pytest.mark.django_db
def test_interview_audio_is_capped_at_15_minutes(alice, project, fake_transcribe):
    Transcript.objects.create(project=project, text="Long", provider="groq", duration_seconds=900)

    response = upload(alice, project, recording())

    assert response.status_code == 400
    assert fake_transcribe == []


@pytest.mark.django_db
def test_uploads_are_rate_limited(alice, project, fake_transcribe, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"transcription": "2/hour"})

    statuses = [upload(alice, project, recording()).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]


def test_uploads_are_never_written_to_disk():
    # P1: Django's default handlers write large uploads to a temporary file.
    # We only allow the in-memory handler, sized to fit the largest recording.
    assert django_settings.FILE_UPLOAD_HANDLERS == [
        "django.core.files.uploadhandler.MemoryFileUploadHandler"
    ]
    assert django_settings.FILE_UPLOAD_MAX_MEMORY_SIZE >= django_settings.MAX_RECORDING_BYTES


def test_no_model_can_store_audio():
    # P1: there must be no file or binary column anywhere in our own apps.
    for app_label in ("accounts", "core", "projects"):
        for model in apps.get_app_config(app_label).get_models():
            for field in model._meta.get_fields():
                assert not isinstance(field, (models.FileField, models.BinaryField)), (
                    f"{model.__name__}.{field.name} could store audio"
                )