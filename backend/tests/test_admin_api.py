"""Tests for the team's review of client-approved stories (A3, A4, P2).

Admins are users with the Admin role; everyone else must be refused.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import CONSENT_VERSION, FollowUpQuestion, Project, StoryChange, Transcript, UserStory

User = get_user_model()

STORY = {
    "role": "customer",
    "goal": "order and pay for a cake online",
    "reason": "I don't have to visit the shop",
    "acceptance_criteria": ["I can choose a cake", "I can pay by card"],
    "priority": "must",
}


@pytest.fixture
def admin():
    return User.objects.create(
        username="admin", clerk_id="user_admin", role=User.Role.ADMIN, first_name="Ada", last_name="Lovelace"
    )


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice", email="alice@bakery.com")


@pytest.fixture
def bob():
    return User.objects.create(username="bob", clerk_id="user_bob", email="bob@dentist.com")


@pytest.fixture
def project(alice):
    return make_project(alice)


def make_project(owner, status=Project.Status.AWAITING_ADMIN, goals=("order a cake", "pay online", "see orders")):
    project = Project.objects.create(
        owner=owner,
        name=f"{owner.username}'s website",
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )
    Transcript.objects.create(
        project=project, text="My name is Sam Lee. Customers order cakes online.", provider="groq"
    )
    for position, goal in enumerate(goals):
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


def goals(project):
    return list(project.stories.order_by("position").values_list("goal", flat=True))


def story_at(project, position):
    return project.stories.get(position=position)


def url(name, *args):
    return reverse(f"admin-project-{name}", args=args)


# --- Who may use it (P2) -------------------------------------------------------


@pytest.mark.django_db
def test_clients_are_refused_everywhere(alice, project):
    story = story_at(project, 0)
    client = client_for(alice)

    assert client.get(url("list")).status_code == 403
    assert client.get(url("detail", project.id)).status_code == 403
    assert client.patch(url("edit-story", project.id, story.id), {"goal": "x"}, format="json").status_code == 403
    assert client.post(url("reject-story", project.id, story.id), {"reason": "x"}, format="json").status_code == 403
    assert goals(project) == ["order a cake", "pay online", "see orders"]


@pytest.mark.django_db
def test_signed_out_users_are_refused(project):
    assert APIClient().get(url("list")).status_code == 401


# --- Listing and viewing (A3) ----------------------------------------------------


@pytest.mark.django_db
def test_admin_sees_every_clients_projects(admin, alice, bob):
    make_project(alice)
    make_project(bob, status=Project.Status.INTERVIEWING)

    response = client_for(admin).get(url("list"))

    assert response.status_code == 200
    body = response.json()
    assert {p["client"]["email"] for p in body} == {"alice@bakery.com", "bob@dentist.com"}
    assert body[0]["story_count"] == 3


@pytest.mark.django_db
def test_admin_can_filter_by_status_and_client(admin, alice, bob):
    make_project(alice)
    make_project(alice, status=Project.Status.INTERVIEWING)
    make_project(bob)

    by_status = client_for(admin).get(url("list"), {"status": "awaiting_admin"}).json()
    by_client = client_for(admin).get(url("list"), {"client": alice.id}).json()

    assert len(by_status) == 2
    assert {p["status"] for p in by_status} == {"awaiting_admin"}
    assert len(by_client) == 2
    assert {p["client"]["id"] for p in by_client} == {alice.id}


@pytest.mark.django_db
def test_admin_sees_only_masked_client_words(admin, project):
    FollowUpQuestion.objects.create(
        project=project,
        topic="users",
        question="Who takes the orders?",
        position=0,
        status=FollowUpQuestion.Status.ANSWERED,
        answer="My manager Priya Shah.",
        provider="groq",
    )

    response = client_for(admin).get(url("detail", project.id))

    body = response.json()
    assert body["masked_transcripts"] == ["My name is [NAME]. Customers order cakes online."]
    assert body["answers"] == [{"question": "Who takes the orders?", "answer": "My manager [NAME]."}]
    # Least privilege: the raw personal details never reach the team's screen.
    assert "Sam" not in response.content.decode()
    assert "Priya" not in response.content.decode()
    assert [s["goal"] for s in body["stories"]] == ["order a cake", "pay online", "see orders"]


# --- Edit, reject, merge, split (A4) ------------------------------------------


@pytest.mark.django_db
def test_admin_edit_is_saved_and_logged(admin, project):
    story = story_at(project, 1)

    response = client_for(admin).patch(
        url("edit-story", project.id, story.id), {"goal": "pay online by card"}, format="json"
    )

    assert response.status_code == 200
    assert goals(project) == ["order a cake", "pay online by card", "see orders"]
    [change] = StoryChange.objects.all()
    assert change.action == "edit"
    assert change.changed_by == admin
    assert change.before[0]["goal"] == "pay online"
    assert change.after[0]["goal"] == "pay online by card"


@pytest.mark.django_db
def test_saving_without_changes_is_not_logged(admin, project):
    # Seen live: pressing Save again on an unchanged story logged it again.
    story = story_at(project, 1)
    client = client_for(admin)
    edit = {"goal": "pay online by card"}

    client.patch(url("edit-story", project.id, story.id), edit, format="json")
    response = client.patch(url("edit-story", project.id, story.id), edit, format="json")

    assert response.status_code == 200
    assert StoryChange.objects.count() == 1


@pytest.mark.django_db
def test_invalid_edit_changes_nothing(admin, project):
    story = story_at(project, 0)

    response = client_for(admin).patch(url("edit-story", project.id, story.id), {"priority": "urgent"}, format="json")

    assert response.status_code == 400
    assert not StoryChange.objects.exists()


@pytest.mark.django_db
def test_admin_can_reject_a_story_with_a_reason(admin, project):
    story = story_at(project, 0)

    response = client_for(admin).post(
        url("reject-story", project.id, story.id), {"reason": "Out of scope for version one"}, format="json"
    )

    assert response.status_code == 204
    assert goals(project) == ["pay online", "see orders"]
    # Positions are kept tidy, starting from 0.
    assert list(project.stories.values_list("position", flat=True)) == [0, 1]
    [change] = StoryChange.objects.all()
    assert (change.action, change.note) == ("reject", "Out of scope for version one")
    assert change.before[0]["goal"] == "order a cake"
    assert change.after == []


@pytest.mark.django_db
def test_rejecting_needs_a_reason(admin, project):
    response = client_for(admin).post(url("reject-story", project.id, story_at(project, 0).id), {}, format="json")

    assert response.status_code == 400
    assert project.stories.count() == 3


@pytest.mark.django_db
def test_admin_can_merge_stories(admin, project):
    first, third = story_at(project, 0), story_at(project, 2)

    response = client_for(admin).post(
        url("merge-stories", project.id), {"story_ids": [third.id, first.id], "story": STORY}, format="json"
    )

    assert response.status_code == 201
    assert response.json()["origin"] == "admin"
    # The merged story takes the place of the earliest one.
    assert goals(project) == ["order and pay for a cake online", "pay online"]
    [change] = StoryChange.objects.all()
    assert change.action == "merge"
    assert [s["goal"] for s in change.before] == ["order a cake", "see orders"]
    assert change.after[0]["goal"] == "order and pay for a cake online"


@pytest.mark.django_db
@pytest.mark.parametrize("ids", [[], "one"], ids=["none", "only-one"])
def test_merge_needs_at_least_two_stories(admin, project, ids):
    story_ids = [story_at(project, 0).id] if ids == "one" else []

    response = client_for(admin).post(
        url("merge-stories", project.id), {"story_ids": story_ids, "story": STORY}, format="json"
    )

    assert response.status_code == 400
    assert project.stories.count() == 3


@pytest.mark.django_db
def test_cannot_merge_in_another_projects_story(admin, project, bob):
    bobs_story = story_at(make_project(bob), 0)

    response = client_for(admin).post(
        url("merge-stories", project.id),
        {"story_ids": [story_at(project, 0).id, bobs_story.id], "story": STORY},
        format="json",
    )

    assert response.status_code == 400
    assert project.stories.count() == 3
    assert UserStory.objects.filter(pk=bobs_story.pk).exists()


@pytest.mark.django_db
def test_admin_can_split_a_story(admin, project):
    middle = story_at(project, 1)
    parts = [{**STORY, "goal": "pay by card"}, {**STORY, "goal": "pay by bank transfer"}]

    response = client_for(admin).post(url("split-story", project.id, middle.id), {"stories": parts}, format="json")

    assert response.status_code == 201
    # The parts take the original story's place, in order.
    assert goals(project) == ["order a cake", "pay by card", "pay by bank transfer", "see orders"]
    assert list(project.stories.values_list("position", flat=True)) == [0, 1, 2, 3]
    [change] = StoryChange.objects.all()
    assert change.action == "split"
    assert change.before[0]["goal"] == "pay online"
    assert [s["goal"] for s in change.after] == ["pay by card", "pay by bank transfer"]


@pytest.mark.django_db
def test_split_needs_at_least_two_parts(admin, project):
    response = client_for(admin).post(
        url("split-story", project.id, story_at(project, 0).id), {"stories": [STORY]}, format="json"
    )

    assert response.status_code == 400
    assert project.stories.count() == 3


@pytest.mark.django_db
def test_change_log_is_shown_newest_first(admin, project):
    client = client_for(admin)
    client.patch(url("edit-story", project.id, story_at(project, 0).id), {"goal": "first change"}, format="json")
    client.patch(url("edit-story", project.id, story_at(project, 1).id), {"goal": "second change"}, format="json")

    changes = client.get(url("detail", project.id)).json()["changes"]

    assert [c["after"][0]["goal"] for c in changes] == ["second change", "first change"]
    assert changes[0]["changed_by"] == "Ada Lovelace"


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["interviewing", "awaiting_client", "sent_to_github"])
def test_stories_only_change_while_awaiting_admin(admin, alice, status):
    other = make_project(alice, status=status)
    story = story_at(other, 0)
    client = client_for(admin)

    assert client.patch(url("edit-story", other.id, story.id), {"goal": "x"}, format="json").status_code == 409
    assert client.post(url("reject-story", other.id, story.id), {"reason": "x"}, format="json").status_code == 409
    assert (
        client.post(url("split-story", other.id, story.id), {"stories": [STORY, STORY]}, format="json").status_code
        == 409
    )
    merge = {"story_ids": [story.id, story_at(other, 1).id], "story": STORY}
    assert client.post(url("merge-stories", other.id), merge, format="json").status_code == 409
    assert goals(other) == ["order a cake", "pay online", "see orders"]
    assert not StoryChange.objects.exists()


@pytest.mark.django_db
def test_story_from_another_project_is_not_found(admin, project, bob):
    bobs_story = story_at(make_project(bob), 0)

    response = client_for(admin).patch(url("edit-story", project.id, bobs_story.id), {"goal": "x"}, format="json")

    assert response.status_code == 404
