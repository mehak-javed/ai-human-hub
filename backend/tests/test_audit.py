"""Tests for the team's audit log (A8): what is recorded, and the read-only page."""

import importlib
import json
from datetime import timedelta

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from projects import views
from projects.models import CONSENT_VERSION, AuditEvent, Project, StoryChange, Transcript, UserStory
from projects.retention import delete_project
from projects.stories import GeneratedStories, StoryDraft
from tests.test_github import REPO, admin, app_settings, fake_github, key_pair  # noqa: F401

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_throttle_history():
    cache.clear()


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice", first_name="Alice")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def actions(project):
    return list(AuditEvent.objects.filter(project=project).order_by("created_at", "id").values_list("action", flat=True))


def interviewing_project(owner):
    project = Project.objects.create(
        owner=owner,
        name="Bakery website",
        project_type="website",
        consent_given_at=timezone.now(),
        consent_version=CONSENT_VERSION,
    )
    Transcript.objects.create(project=project, text="My name is Sam Lee and I sell cakes.", provider="groq")
    return project


@pytest.fixture
def fake_stories(monkeypatch):
    draft = StoryDraft(
        role="customer", goal="order a cake", reason="it saves time", acceptance_criteria=["It works"], priority="must"
    )
    monkeypatch.setattr(views, "generate_stories", lambda *a, **k: GeneratedStories(stories=[draft], provider="groq"))


# --- What gets recorded -----------------------------------------------------------


@pytest.mark.django_db
def test_a_client_journey_is_recorded_in_order(alice, fake_stories):
    client = client_for(alice)
    created = client.post(
        reverse("project-list"), {"name": "Bakery website", "project_type": "website", "consent": True}, format="json"
    ).json()
    project = Project.objects.get(pk=created["id"])
    Transcript.objects.create(project=project, text="I sell cakes.", provider="groq")

    client.post(reverse("project-stories", args=[project.id]))
    story = project.stories.get()
    client.patch(reverse("project-story", args=[project.id, story.id]), {"goal": "order a cake online"}, format="json")
    client.post(reverse("project-approve", args=[project.id]))

    assert actions(project) == ["project_created", "stories_written", "story_edited", "approved"]
    written = AuditEvent.objects.get(project=project, action="stories_written")
    assert (written.actor, written.detail) == ("ai", "Groq wrote 1 story")
    approved = AuditEvent.objects.get(project=project, action="approved")
    assert (approved.actor, approved.user) == ("client", alice)


@pytest.mark.django_db
def test_team_changes_and_pushes_are_recorded(alice, admin, fake_github):  # noqa: F811
    project = interviewing_project(alice)
    Project.objects.filter(pk=project.pk).update(status=Project.Status.AWAITING_ADMIN, github_repo=REPO)
    for position in range(2):
        UserStory.objects.create(
            project=project,
            role="customer",
            goal=f"goal {position}",
            reason="it saves time",
            acceptance_criteria=["It works"],
            priority="must",
            position=position,
        )
    team = client_for(admin)
    first = project.stories.order_by("position").first()

    team.patch(reverse("admin-project-edit-story", args=[project.id, first.id]), {"goal": "pay online"}, format="json")
    team.post(reverse("admin-project-send", args=[project.id]))

    edit = AuditEvent.objects.get(project=project, action="team_edit")
    assert (edit.actor, edit.user, edit.detail) == ("team", admin, f"Story {first.id}")
    sent = AuditEvent.objects.get(project=project, action="sent_to_github")
    assert sent.detail == f"{REPO}: 2 issues created, 0 updated"
    assert StoryChange.objects.count() == 1


@pytest.mark.django_db
def test_the_log_never_holds_what_the_client_said(alice, fake_stories):
    project = interviewing_project(alice)
    client = client_for(alice)
    client.post(reverse("project-stories", args=[project.id]))
    story = project.stories.get()
    client.patch(
        reverse("project-story", args=[project.id, story.id]), {"goal": "call my manager Sam Lee"}, format="json"
    )

    everything = json.dumps(list(AuditEvent.objects.values()), default=str)

    assert "Sam" not in everything
    assert "cake" not in everything


@pytest.mark.django_db
def test_a_failed_log_write_never_undoes_the_action(alice, fake_stories, monkeypatch):
    project = interviewing_project(alice)
    client = client_for(alice)
    client.post(reverse("project-stories", args=[project.id]))

    def broken(*args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(AuditEvent.objects, "create", broken)
    response = client.post(reverse("project-approve", args=[project.id]))

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.status == Project.Status.AWAITING_ADMIN


# --- The page (A8) ----------------------------------------------------------------


def get_log(user, **params):
    return client_for(user).get(reverse("admin-audit"), params)


@pytest.mark.django_db
def test_only_the_team_can_read_the_log(alice, admin):  # noqa: F811
    assert get_log(alice).status_code == 403
    assert APIClient().get(reverse("admin-audit")).status_code == 401
    assert get_log(admin).status_code == 200


@pytest.mark.django_db
def test_the_log_is_read_only(admin):  # noqa: F811
    team = client_for(admin)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(team, method)(reverse("admin-audit")).status_code == 405


@pytest.mark.django_db
def test_the_log_filters_by_project(alice, admin):  # noqa: F811
    bakery = interviewing_project(alice)
    salon = interviewing_project(alice)
    AuditEvent.objects.create(project=bakery, actor="client", action="approved")
    AuditEvent.objects.create(project=salon, actor="client", action="approved")

    body = get_log(admin, project=bakery.id).json()

    assert {row["project_id"] for row in body["events"]} == {bakery.id}
    assert {"id": bakery.id, "name": "Bakery website"} in body["projects"]
    assert get_log(admin, project="nope").status_code == 400


@pytest.mark.django_db
def test_the_log_pages_back_in_time(alice, admin):  # noqa: F811
    project = interviewing_project(alice)
    now = timezone.now()
    for minutes in range(60):
        AuditEvent.objects.create(
            project=project, actor="ai", action="recording_transcribed", created_at=now - timedelta(minutes=minutes)
        )

    first = get_log(admin).json()
    second = get_log(admin, before=first["next"]).json()

    assert len(first["events"]) == 50
    assert len(second["events"]) == 10
    assert second["next"] is None
    seen = [row["id"] for row in first["events"] + second["events"]]
    assert len(seen) == len(set(seen)) == 60


@pytest.mark.django_db
def test_deleted_projects_still_show_without_their_name(alice, admin):  # noqa: F811
    project = interviewing_project(alice)
    project_id = project.id
    delete_project(project, "client_request")

    [row] = get_log(admin).json()["events"]

    assert row["project_id"] == project_id
    assert row["project_name"] is None
    assert row["label"] == "Project deleted (deleted by the client)"
    assert not AuditEvent.objects.exists()


# --- History from before the log ---------------------------------------------------


@pytest.mark.django_db
def test_existing_projects_get_their_history(alice, admin):  # noqa: F811
    project = interviewing_project(alice)
    Project.objects.filter(pk=project.pk).update(approved_at=timezone.now(), status=Project.Status.AWAITING_ADMIN)
    UserStory.objects.create(
        project=project,
        role="customer",
        goal="order a cake",
        reason="it saves time",
        acceptance_criteria=["It works"],
        priority="must",
        position=0,
        provider="groq",
    )
    StoryChange.objects.create(project=project, action="edit", changed_by=admin, before=[{"id": 7}], after=[])
    AuditEvent.objects.all().delete()

    migration = importlib.import_module("projects.migrations.0014_backfill_audit_events")
    migration.backfill(apps, None)

    assert set(actions(project)) == {
        "project_created",
        "recording_transcribed",
        "stories_written",
        "approved",
        "team_edit",
    }
    assert all(e.endswith("(from earlier records)") for e in AuditEvent.objects.values_list("detail", flat=True))
    # Running it again adds nothing.
    migration.backfill(apps, None)
    assert AuditEvent.objects.count() == 5
