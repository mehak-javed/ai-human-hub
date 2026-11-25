"""Tests for writing and listing a project's user stories (AI4, AI2, C5, P2).

The AI is replaced with a fake, so no provider is called. Retries and the
backup provider are tested in test_llm.py.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from projects import views
from projects.models import CONSENT_VERSION, FollowUpQuestion, Project, Transcript, UserStory
from projects.stories import GeneratedStories, StoryDraft, StoryGenerationError

User = get_user_model()

DRAFTS = [
    StoryDraft(
        role="customer",
        goal="order a cake online",
        reason="I don't have to visit the shop",
        acceptance_criteria=["I can choose a cake", "I can pick a collection time"],
        priority="must",
    ),
    StoryDraft(
        role="bakery owner",
        goal="see each day's orders",
        reason="I can plan my baking",
        acceptance_criteria=["Orders are listed by collection time"],
        priority="should",
    ),
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
        text="My name is Sam Lee, email sam@bakery.com. Customers should order cakes online.",
        provider="groq",
    )
    return project


@pytest.fixture
def fake_generate(monkeypatch):
    """Replace the real AI with one that records what it was sent."""
    calls = []

    def fake(masked_transcripts, answers=None):
        calls.append((masked_transcripts, answers))
        return GeneratedStories(stories=DRAFTS, provider="workers_ai")

    monkeypatch.setattr(views, "generate_stories", fake)
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


def write_stories(user, project):
    return client_for(user).post(reverse("project-stories", args=[project.id]))


@pytest.mark.django_db
def test_writing_stories_saves_them_in_order(alice, project, fake_generate):
    response = write_stories(alice, project)

    assert response.status_code == 201
    body = response.json()
    assert [s["goal"] for s in body] == ["order a cake online", "see each day's orders"]
    assert body[0]["acceptance_criteria"] == ["I can choose a cake", "I can pick a collection time"]
    assert body[0]["priority"] == "must"
    assert body[0]["provider"] == "workers_ai"
    assert project.stories.count() == 2


@pytest.mark.django_db
def test_only_masked_text_is_sent_to_the_ai(alice, project, fake_generate):
    write_stories(alice, project)

    # AI2: the AI gets the masked copy, never the client's real details.
    [(sent, answers)] = fake_generate
    assert sent == ["My name is [NAME], email [EMAIL]. Customers should order cakes online."]
    assert "Sam" not in str(sent)
    assert "sam@bakery.com" not in str(sent)
    assert answers == []


@pytest.mark.django_db
def test_follow_up_answers_are_sent_masked(alice, project, fake_generate):
    def ask(position, status, answer=""):
        FollowUpQuestion.objects.create(
            project=project,
            topic="users",
            question=f"Question {position}?",
            position=position,
            status=status,
            answer=answer,
            provider="groq",
        )

    ask(0, FollowUpQuestion.Status.ANSWERED, "My manager Priya Shah takes orders.")
    ask(1, FollowUpQuestion.Status.NOT_SURE)
    ask(2, FollowUpQuestion.Status.OPEN)

    write_stories(alice, project)

    [(_, answers)] = fake_generate
    # Unanswered questions are left out; "Not sure" is passed on as such.
    assert answers == [
        ("Question 0?", "My manager [NAME] takes orders."),
        ("Question 1?", "Not sure"),
    ]


@pytest.mark.django_db
def test_rewriting_replaces_the_old_stories(alice, project, fake_generate):
    write_stories(alice, project)
    write_stories(alice, project)

    assert project.stories.count() == 2


@pytest.mark.django_db
def test_list_returns_stories(alice, project, fake_generate):
    write_stories(alice, project)

    response = client_for(alice).get(reverse("project-stories", args=[project.id]))

    assert response.status_code == 200
    assert [s["role"] for s in response.json()] == ["customer", "bakery owner"]


@pytest.mark.django_db
def test_ai_outage_returns_503_and_keeps_the_old_stories(alice, project, fake_generate, monkeypatch):
    write_stories(alice, project)

    def failing(masked_transcripts, answers=None):
        raise StoryGenerationError("All story providers failed.")

    monkeypatch.setattr(views, "generate_stories", failing)

    response = write_stories(alice, project)

    assert response.status_code == 503
    assert project.stories.count() == 2


@pytest.mark.django_db
def test_needs_a_recording_first(alice, fake_generate):
    empty = make_project(alice)

    response = write_stories(alice, empty)

    assert response.status_code == 400
    assert fake_generate == []


@pytest.mark.django_db
def test_cannot_write_stories_for_another_clients_project(alice, bob, fake_generate):
    bobs_project = make_project(bob)
    Transcript.objects.create(project=bobs_project, text="Bob's idea", provider="groq")

    response = write_stories(alice, bobs_project)

    assert response.status_code == 404
    assert fake_generate == []


@pytest.mark.django_db
def test_cannot_read_another_clients_stories(alice, bob):
    bobs_project = make_project(bob)
    UserStory.objects.create(
        project=bobs_project,
        role="r",
        goal="g",
        reason="x",
        acceptance_criteria=["a"],
        priority="must",
        position=0,
        provider="groq",
    )

    response = client_for(alice).get(reverse("project-stories", args=[bobs_project.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_requires_sign_in(project):
    response = APIClient().post(reverse("project-stories", args=[project.id]))

    assert response.status_code == 401


@pytest.mark.django_db
def test_no_rewriting_after_interview_ends(alice, fake_generate):
    finished = make_project(alice, status=Project.Status.AWAITING_CLIENT)
    Transcript.objects.create(project=finished, text="Idea", provider="groq")

    response = write_stories(alice, finished)

    assert response.status_code == 409
    assert fake_generate == []


@pytest.mark.django_db
def test_story_writing_is_rate_limited(alice, project, fake_generate, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"stories": "2/hour"})

    statuses = [write_stories(alice, project).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]