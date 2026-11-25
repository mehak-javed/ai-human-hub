"""Tests for the client's review: edit, remove, add, rewrite, approve (C8, C9).

The AI is replaced with a fake, so no provider is called.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from projects import views
from projects.models import CONSENT_VERSION, Project, Transcript, UserStory
from projects.stories import GeneratedStories, StoryDraft, StoryGenerationError

User = get_user_model()

REWRITTEN = [
    StoryDraft(
        role="customer",
        goal="order cupcakes online",
        reason="I don't have to visit the shop",
        acceptance_criteria=["I can choose cupcakes"],
        priority="must",
    ),
]

NEW_STORY = {
    "role": "bakery owner",
    "goal": "print each day's orders",
    "reason": "my team can work from paper",
    "acceptance_criteria": ["Orders print on one page", "Each order shows its collection time"],
    "priority": "nice",
}


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
    """A project whose stories are waiting for Alice's review."""
    return make_project(alice)


@pytest.fixture
def fake_generate(monkeypatch):
    """Replace the real AI with one that records what it was sent."""
    calls = []

    def fake(masked_transcripts, answers=None, current_stories=None, change_request=None):
        calls.append({"current_stories": current_stories, "change_request": change_request})
        return GeneratedStories(stories=REWRITTEN, provider="groq")

    monkeypatch.setattr(views, "generate_stories", fake)
    return calls


def make_project(owner, status=Project.Status.AWAITING_CLIENT):
    project = Project.objects.create(
        owner=owner,
        name="Bakery website",
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )
    Transcript.objects.create(project=project, text="I want customers to order cakes.", provider="groq")
    for position, goal in enumerate(["order a cake online", "see each day's orders"]):
        UserStory.objects.create(
            project=project,
            role="customer",
            goal=goal,
            reason="it saves time",
            acceptance_criteria=["It works"],
            priority="must",
            position=position,
            provider="workers_ai",
        )
    return project


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def story_url(project, story):
    return reverse("project-story", args=[project.id, story.id])


def edit(user, project, story, data):
    return client_for(user).patch(story_url(project, story), data, format="json")


def remove(user, project, story):
    return client_for(user).delete(story_url(project, story))


def add(user, project, data=NEW_STORY):
    return client_for(user).post(reverse("project-add-story", args=[project.id]), data, format="json")


def revise(user, project, note="Make it about cupcakes."):
    url = reverse("project-revise-stories", args=[project.id])
    return client_for(user).post(url, {"note": note}, format="json")


def approve(user, project):
    return client_for(user).post(reverse("project-approve", args=[project.id]))


# --- Edit, remove, add (C8) --------------------------------------------------


@pytest.mark.django_db
def test_client_can_edit_a_story(alice, project):
    story = project.stories.first()

    response = edit(alice, project, story, {"goal": "order a birthday cake", "priority": "should"})

    assert response.status_code == 200
    assert response.json()["goal"] == "order a birthday cake"
    assert response.json()["priority"] == "should"
    # AI7: the change from the AI's version is recorded.
    assert response.json()["client_edited"] is True
    story.refresh_from_db()
    assert story.reason == "it saves time"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        {"goal": ""},
        {"goal": "x" * 301},
        {"priority": "urgent"},
        {"acceptance_criteria": []},
        {"acceptance_criteria": [""]},
        {"acceptance_criteria": ["ok"] * 9},
    ],
    ids=["empty-goal", "goal-too-long", "unknown-priority", "no-criteria", "blank-criterion", "too-many"],
)
def test_invalid_edits_are_rejected(alice, project, data):
    story = project.stories.first()

    response = edit(alice, project, story, data)

    assert response.status_code == 400
    story.refresh_from_db()
    assert story.client_edited is False


@pytest.mark.django_db
def test_client_can_remove_a_story(alice, project):
    story = project.stories.first()

    response = remove(alice, project, story)

    assert response.status_code == 204
    assert project.stories.count() == 1


@pytest.mark.django_db
def test_client_can_add_a_missing_story_at_the_end(alice, project):
    response = add(alice, project)

    assert response.status_code == 201
    body = response.json()
    assert body["goal"] == "print each day's orders"
    assert body["origin"] == "client"
    assert body["acceptance_criteria"] == NEW_STORY["acceptance_criteria"]
    assert [s.goal for s in project.stories.all()][-1] == "print each day's orders"


@pytest.mark.django_db
def test_added_story_must_be_complete(alice, project):
    response = add(alice, project, {"goal": "print orders"})

    assert response.status_code == 400
    assert project.stories.count() == 2


# --- Rewrite with a note (C9) ------------------------------------------------


@pytest.mark.django_db
def test_ai_rewrites_the_stories_from_a_note(alice, project, fake_generate):
    response = revise(alice, project)

    assert response.status_code == 201
    assert [s["goal"] for s in response.json()] == ["order cupcakes online"]
    # The AI starts from the current stories, including the client's edits.
    [call] = fake_generate
    assert [s["goal"] for s in call["current_stories"]] == ["order a cake online", "see each day's orders"]
    assert call["change_request"] == "Make it about cupcakes."
    project.refresh_from_db()
    assert project.status == Project.Status.AWAITING_CLIENT


@pytest.mark.django_db
def test_note_and_edited_stories_are_masked_before_the_ai_sees_them(alice, project, fake_generate):
    edit(alice, project, project.stories.first(), {"reason": "my manager Priya Shah asked for it"})

    revise(alice, project, note="Email the orders to priya@bakery.com.")

    [call] = fake_generate
    assert call["change_request"] == "Email the orders to [EMAIL]."
    assert call["current_stories"][0]["reason"] == "my manager [NAME] asked for it"
    assert "Priya" not in str(call)


@pytest.mark.django_db
@pytest.mark.parametrize("note", ["", "x" * 1001], ids=["empty", "too-long"])
def test_rewrite_needs_a_sensible_note(alice, project, fake_generate, note):
    response = revise(alice, project, note=note)

    assert response.status_code == 400
    assert fake_generate == []


@pytest.mark.django_db
def test_ai_outage_during_rewrite_keeps_the_stories(alice, project, monkeypatch):
    def failing(*args, **kwargs):
        raise StoryGenerationError("All AI providers failed.")

    monkeypatch.setattr(views, "generate_stories", failing)

    response = revise(alice, project)

    assert response.status_code == 503
    assert project.stories.count() == 2


@pytest.mark.django_db
def test_rewrites_share_the_story_rate_limit(alice, project, fake_generate, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"stories": "1/hour"})

    statuses = [revise(alice, project).status_code for _ in range(2)]

    assert statuses == [201, 429]


# --- Approve (C9) --------------------------------------------------------------


@pytest.mark.django_db
def test_approving_sends_the_stories_to_the_admin(alice, project):
    response = approve(alice, project)

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_admin"
    assert response.json()["approved_at"] is not None
    project.refresh_from_db()
    assert project.status == Project.Status.AWAITING_ADMIN


@pytest.mark.django_db
def test_cannot_approve_with_no_stories(alice, project):
    project.stories.all().delete()

    response = approve(alice, project)

    assert response.status_code == 400
    project.refresh_from_db()
    assert project.status == Project.Status.AWAITING_CLIENT


@pytest.mark.django_db
def test_approved_stories_are_locked(alice, project, fake_generate):
    story = project.stories.first()
    approve(alice, project)

    assert edit(alice, project, story, {"goal": "something else"}).status_code == 409
    assert remove(alice, project, story).status_code == 409
    assert add(alice, project).status_code == 409
    assert revise(alice, project).status_code == 409
    assert approve(alice, project).status_code == 409
    assert fake_generate == []
    story.refresh_from_db()
    assert story.goal == "order a cake online"


@pytest.mark.django_db
def test_no_review_while_still_interviewing(alice, fake_generate):
    interviewing = make_project(alice, status=Project.Status.INTERVIEWING)

    assert add(alice, interviewing).status_code == 409
    assert approve(alice, interviewing).status_code == 409
    assert revise(alice, interviewing).status_code == 409


# --- Access (P2) ---------------------------------------------------------------


@pytest.mark.django_db
def test_cannot_review_another_clients_stories(alice, bob, project, fake_generate):
    bobs_project = make_project(bob)
    bobs_story = bobs_project.stories.first()

    assert edit(alice, bobs_project, bobs_story, {"goal": "hacked"}).status_code == 404
    # Pairing Bob's story with Alice's own project doesn't work either.
    assert edit(alice, project, bobs_story, {"goal": "hacked"}).status_code == 404
    assert remove(alice, project, bobs_story).status_code == 404
    assert add(alice, bobs_project).status_code == 404
    assert revise(alice, bobs_project).status_code == 404
    assert approve(alice, bobs_project).status_code == 404
    bobs_story.refresh_from_db()
    assert bobs_story.goal == "order a cake online"


@pytest.mark.django_db
def test_review_requires_sign_in(project):
    assert APIClient().post(reverse("project-approve", args=[project.id])).status_code == 401
