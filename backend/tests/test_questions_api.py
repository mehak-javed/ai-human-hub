"""Tests for follow-up questions and answers (AI3, C5, AI2, P2).

The AI and the transcription service are replaced with fakes, so no
provider is called.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from projects import views
from projects.models import CONSENT_VERSION, FollowUpQuestion, Project, Transcript
from projects.questions import GeneratedQuestions, QuestionDraft, QuestionGenerationError
from projects.transcription import Transcription

User = get_user_model()

DRAFTS = [
    QuestionDraft(topic="payments", question="Should customers pay online when they order?"),
    QuestionDraft(topic="deadlines", question="When would you like the website to be ready?"),
]


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
    project = make_project(alice)
    Transcript.objects.create(
        project=project,
        text="My name is Sam Lee. I want customers to order cakes online.",
        provider="groq",
    )
    return project


@pytest.fixture
def fake_generate(monkeypatch):
    """Replace the real AI with one that records what it was sent."""
    calls = []

    def fake(masked_transcripts):
        calls.append(masked_transcripts)
        return GeneratedQuestions(questions=DRAFTS, provider="workers_ai")

    monkeypatch.setattr(views, "generate_questions", fake)
    return calls


@pytest.fixture
def fake_transcribe(monkeypatch):
    calls = []

    def fake(audio, content_type):
        calls.append(content_type)
        return Transcription(
            text="Yes, by card. Email me at sam@bakery.com.", provider="groq", duration_seconds=6.0
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


def make_question(project, position=0):
    return FollowUpQuestion.objects.create(
        project=project,
        topic="payments",
        question="Should customers pay online?",
        position=position,
        provider="groq",
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def ask_questions(user, project):
    return client_for(user).post(reverse("project-questions", args=[project.id]))


def answer_url(project, question):
    return reverse("project-answer-question", args=[project.id, question.id])


def answer(user, project, question, data):
    return client_for(user).post(answer_url(project, question), data, format="json")


def recording():
    return SimpleUploadedFile("answer.webm", b"fake-audio", content_type="audio/webm")


# --- Asking (AI3) ------------------------------------------------------------


@pytest.mark.django_db
def test_asking_saves_questions_in_order(alice, project, fake_generate):
    response = ask_questions(alice, project)

    assert response.status_code == 201
    body = response.json()
    assert [q["topic"] for q in body] == ["payments", "deadlines"]
    assert body[0]["status"] == "open"
    assert body[0]["answer"] == ""
    assert project.questions.count() == 2


@pytest.mark.django_db
def test_only_masked_text_is_sent_to_the_ai(alice, project, fake_generate):
    ask_questions(alice, project)

    assert fake_generate == [["My name is [NAME]. I want customers to order cakes online."]]


@pytest.mark.django_db
def test_questions_are_only_asked_once(alice, project, fake_generate):
    ask_questions(alice, project)

    response = ask_questions(alice, project)

    assert response.status_code == 409
    assert len(fake_generate) == 1


@pytest.mark.django_db
def test_list_returns_questions(alice, project, fake_generate):
    ask_questions(alice, project)

    response = client_for(alice).get(reverse("project-questions", args=[project.id]))

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.django_db
def test_needs_a_recording_first(alice, fake_generate):
    response = ask_questions(alice, make_project(alice))

    assert response.status_code == 400
    assert fake_generate == []


@pytest.mark.django_db
def test_ai_outage_returns_503_and_saves_nothing(alice, project, monkeypatch):
    def failing(masked_transcripts):
        raise QuestionGenerationError("All AI providers failed.")

    monkeypatch.setattr(views, "generate_questions", failing)

    response = ask_questions(alice, project)

    assert response.status_code == 503
    assert not FollowUpQuestion.objects.exists()


@pytest.mark.django_db
def test_cannot_ask_or_read_questions_on_another_clients_project(alice, bob, fake_generate):
    bobs_project = make_project(bob)
    Transcript.objects.create(project=bobs_project, text="Bob's idea", provider="groq")

    assert ask_questions(alice, bobs_project).status_code == 404
    assert client_for(alice).get(reverse("project-questions", args=[bobs_project.id])).status_code == 404
    assert fake_generate == []


@pytest.mark.django_db
def test_asking_is_rate_limited(alice, monkeypatch, fake_generate):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"questions": "2/hour"})
    # Projects without recordings return 400, but each call still counts.
    statuses = [ask_questions(alice, make_project(alice)).status_code for _ in range(3)]

    assert statuses == [400, 400, 429]


# --- Answering (C5) ----------------------------------------------------------


@pytest.mark.django_db
def test_typed_answer_is_saved_and_masked(alice, project):
    question = make_question(project)

    response = answer(alice, project, question, {"answer": "Yes. Call me on 07700 900123."})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["answer"] == "Yes. Call me on 07700 900123."
    # AI2: the masked copy is what later goes to the AI.
    assert body["masked_answer"] == "Yes. Call me on [PHONE]."
    assert body["answered_at"] is not None


@pytest.mark.django_db
def test_not_sure_is_saved(alice, project):
    question = make_question(project)

    response = answer(alice, project, question, {"not_sure": True})

    assert response.status_code == 200
    assert response.json()["status"] == "not_sure"
    assert response.json()["answer"] == ""


@pytest.mark.django_db
def test_an_answer_can_be_changed(alice, project):
    question = make_question(project)
    answer(alice, project, question, {"not_sure": True})

    response = answer(alice, project, question, {"answer": "Yes, by card."})

    assert response.json()["status"] == "answered"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [{}, {"answer": "   "}, {"answer": "Yes", "not_sure": True}, {"answer": "x" * 2001}],
    ids=["nothing", "blank", "both", "too-long"],
)
def test_invalid_answers_are_rejected(alice, project, data):
    question = make_question(project)

    response = answer(alice, project, question, data)

    assert response.status_code == 400
    question.refresh_from_db()
    assert question.status == FollowUpQuestion.Status.OPEN


@pytest.mark.django_db
def test_spoken_answer_is_transcribed_and_masked(alice, project, fake_transcribe):
    question = make_question(project)

    response = client_for(alice).post(
        answer_url(project, question), {"audio": recording()}, format="multipart"
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Yes, by card. Email me at sam@bakery.com."
    assert response.json()["masked_answer"] == "Yes, by card. Email me at [EMAIL]."
    assert fake_transcribe == ["audio/webm"]


@pytest.mark.django_db
def test_spoken_answers_count_as_recordings_for_the_rate_limit(alice, project, fake_transcribe, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"transcription": "1/hour"})
    question = make_question(project)
    url = answer_url(project, question)

    first = client_for(alice).post(url, {"audio": recording()}, format="multipart")
    second = client_for(alice).post(url, {"audio": recording()}, format="multipart")
    typed = answer(alice, project, question, {"answer": "Typed answers aren't limited."})

    assert [first.status_code, second.status_code, typed.status_code] == [200, 429, 200]


@pytest.mark.django_db
def test_cannot_answer_another_clients_question(alice, bob, project):
    bobs_question = make_question(make_project(bob))

    # Neither through Bob's project, nor by pairing Bob's question with Alice's project.
    assert answer(alice, bobs_question.project, bobs_question, {"answer": "Hi"}).status_code == 404
    assert answer(alice, project, bobs_question, {"answer": "Hi"}).status_code == 404
    bobs_question.refresh_from_db()
    assert bobs_question.status == FollowUpQuestion.Status.OPEN


@pytest.mark.django_db
def test_no_answers_after_interview_ends(alice):
    finished = make_project(alice, status=Project.Status.AWAITING_CLIENT)
    question = make_question(finished)

    response = answer(alice, finished, question, {"answer": "Too late"})

    assert response.status_code == 409


@pytest.mark.django_db
def test_answering_requires_sign_in(project):
    question = make_question(project)

    response = APIClient().post(answer_url(project, question), {"answer": "Hi"}, format="json")

    assert response.status_code == 401