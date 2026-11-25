"""Tests for deleting projects, exporting requirements and retention (C11, P3, P4)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from projects.models import (
    CONSENT_VERSION,
    DeletionRecord,
    FollowUpQuestion,
    Project,
    StoryChange,
    Transcript,
    UserStory,
)

User = get_user_model()


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice")


@pytest.fixture
def bob():
    return User.objects.create(username="bob", clerk_id="user_bob")


def make_project(owner, status=Project.Status.AWAITING_ADMIN, name="Bakery website"):
    project = Project.objects.create(
        owner=owner,
        name=name,
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )
    Transcript.objects.create(project=project, text="My name is Sam Lee. I sell cakes.", provider="groq")
    FollowUpQuestion.objects.create(
        project=project, topic="data", question="What do you keep?", position=0, provider="groq"
    )
    for position, (goal, priority) in enumerate([("order a cake online", "must"), ("print orders", "nice")]):
        UserStory.objects.create(
            project=project,
            role="customer",
            goal=goal,
            reason="it saves time",
            acceptance_criteria=["It works"],
            priority=priority,
            position=position,
            provider="groq",
        )
    StoryChange.objects.create(project=project, action="edit", before=[], after=[])
    return project


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def age(project, days, field="updated_at"):
    """Pretend a project was last changed (or sent) `days` ago."""
    Project.objects.filter(pk=project.pk).update(**{field: timezone.now() - timedelta(days=days)})


# --- Delete my data (C11) ---------------------------------------------------------


@pytest.mark.django_db
def test_client_deletes_their_project_and_everything_in_it(alice):
    project = make_project(alice)

    response = client_for(alice).delete(reverse("project-detail", args=[project.id]))

    assert response.status_code == 204
    assert not Project.objects.exists()
    assert not Transcript.objects.exists()
    assert not FollowUpQuestion.objects.exists()
    assert not UserStory.objects.exists()
    assert not StoryChange.objects.exists()


@pytest.mark.django_db
def test_deletion_is_logged_without_any_content(alice):
    project = make_project(alice)

    client_for(alice).delete(reverse("project-detail", args=[project.id]))

    [record] = DeletionRecord.objects.all()
    assert record.project_id == project.id
    assert record.owner_id == alice.id
    assert record.reason == "client_request"
    assert (record.transcripts, record.stories) == (1, 2)
    # The record keeps nothing the client said, not even the project's name.
    values = " ".join(str(v) for v in DeletionRecord.objects.values().first().values())
    assert "Bakery" not in values
    assert "Sam" not in values


@pytest.mark.django_db
def test_cannot_delete_another_clients_project(alice, bob):
    bobs = make_project(bob)

    response = client_for(alice).delete(reverse("project-detail", args=[bobs.id]))

    assert response.status_code == 404
    assert Project.objects.filter(pk=bobs.pk).exists()
    assert not DeletionRecord.objects.exists()


@pytest.mark.django_db
def test_delete_requires_sign_in(alice):
    project = make_project(alice)

    assert APIClient().delete(reverse("project-detail", args=[project.id])).status_code == 401
    assert Project.objects.exists()


# --- Export (P4) ------------------------------------------------------------------


@pytest.mark.django_db
def test_client_downloads_approved_requirements_as_markdown(alice):
    project = make_project(alice)

    response = client_for(alice).get(reverse("project-export", args=[project.id]))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="bakery-website-requirements.md"'
    text = response.content.decode()
    assert text.startswith("# Bakery website: requirements")
    # The file matches the stories in the app, in order and by priority.
    assert text.index("### Order a cake online") < text.index("### Print orders")
    assert "## Must have" in text and "## Nice to have" in text


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["interviewing", "awaiting_client"])
def test_export_waits_for_approval(alice, status):
    project = make_project(alice, status=status)

    response = client_for(alice).get(reverse("project-export", args=[project.id]))

    assert response.status_code == 409


@pytest.mark.django_db
def test_cannot_export_another_clients_project(alice, bob):
    bobs = make_project(bob)

    assert client_for(alice).get(reverse("project-export", args=[bobs.id])).status_code == 404


# --- Retention (P3) ---------------------------------------------------------------


@pytest.mark.django_db
def test_expired_projects_are_deleted_and_logged(alice, settings):
    settings.DATA_RETENTION_DAYS = 365
    sent_long_ago = make_project(alice, status=Project.Status.SENT_TO_GITHUB, name="Old")
    age(sent_long_ago, 400, field="sent_to_github_at")
    abandoned = make_project(alice, status=Project.Status.INTERVIEWING, name="Abandoned")
    age(abandoned, 400)
    recent = make_project(alice, status=Project.Status.SENT_TO_GITHUB, name="Recent")
    age(recent, 30, field="sent_to_github_at")
    make_project(alice, status=Project.Status.INTERVIEWING, name="Active")

    call_command("delete_expired_projects")

    assert set(Project.objects.values_list("name", flat=True)) == {"Recent", "Active"}
    assert set(DeletionRecord.objects.values_list("reason", flat=True)) == {"retention"}
    assert DeletionRecord.objects.count() == 2


@pytest.mark.django_db
def test_sent_projects_are_kept_by_send_date_not_last_change(alice, settings):
    # Sent 30 days ago, even though nothing has changed for over a year.
    settings.DATA_RETENTION_DAYS = 365
    project = make_project(alice, status=Project.Status.SENT_TO_GITHUB)
    age(project, 30, field="sent_to_github_at")
    age(project, 400)

    call_command("delete_expired_projects")

    assert Project.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
def test_dry_run_deletes_nothing(alice, capsys):
    project = make_project(alice, status=Project.Status.INTERVIEWING)
    age(project, 400)

    call_command("delete_expired_projects", "--dry-run")

    assert "1 project(s) would be deleted." in capsys.readouterr().out
    assert Project.objects.filter(pk=project.pk).exists()
    assert not DeletionRecord.objects.exists()
