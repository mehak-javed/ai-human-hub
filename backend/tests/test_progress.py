"""Tests for progress from GitHub: the webhook and the catch-up sync (G4, C10)."""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from projects.delivery import send_to_github
from projects.models import Project
from tests.test_github import REPO, admin, app_settings, client_for, fake_github, key_pair, project  # noqa: F401

SECRET = "test-webhook-secret"


@pytest.fixture
def sent(fake_github, project, admin):  # noqa: F811
    """The bakery project, delivered: three stories are issues #1-#3."""
    send_to_github(project, admin)
    project.refresh_from_db()
    assert project.status == Project.Status.SENT_TO_GITHUB
    return project


def deliver(payload, event="issues", secret=SECRET, signature=None):
    body = json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return APIClient().post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


def issue_event(number, action, repo=REPO):
    return {
        "action": action,
        "issue": {"number": number, "state": "closed" if action == "closed" else "open"},
        "repository": {"full_name": repo},
    }


def done(project):
    return sorted(project.stories.filter(github_issue_closed=True).values_list("github_issue_number", flat=True))


# --- The webhook (G4) -------------------------------------------------------------


@pytest.fixture
def webhook_secret(settings):
    settings.GITHUB_WEBHOOK_SECRET = SECRET


@pytest.mark.django_db
def test_closing_an_issue_marks_its_story_done(sent, webhook_secret):
    response = deliver(issue_event(2, "closed"))

    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    assert done(sent) == [2]


@pytest.mark.django_db
def test_reopening_an_issue_marks_it_not_done(sent, webhook_secret):
    deliver(issue_event(2, "closed"))
    deliver(issue_event(2, "reopened"))

    assert done(sent) == []


@pytest.mark.django_db
def test_a_repeated_delivery_changes_nothing(sent, webhook_secret):
    deliver(issue_event(1, "closed"))
    response = deliver(issue_event(1, "closed"))

    assert response.json() == {"updated": 0}
    assert done(sent) == [1]


@pytest.mark.django_db
@pytest.mark.parametrize("signature", ["", "sha256=" + "0" * 64, "sha1=abc"])
def test_unsigned_or_badly_signed_deliveries_are_refused(sent, webhook_secret, signature):
    response = deliver(issue_event(1, "closed"), signature=signature)

    assert response.status_code == 401
    assert done(sent) == []


@pytest.mark.django_db
def test_a_delivery_signed_with_another_secret_is_refused(sent, webhook_secret):
    assert deliver(issue_event(1, "closed"), secret="someone-elses").status_code == 401
    assert done(sent) == []


@pytest.mark.django_db
def test_without_a_secret_the_webhook_is_off(sent, settings):
    settings.GITHUB_WEBHOOK_SECRET = ""

    assert deliver(issue_event(1, "closed")).status_code == 503


@pytest.mark.django_db
def test_other_repos_and_events_are_ignored(sent, webhook_secret):
    assert deliver(issue_event(1, "closed", repo="acme/other")).json() == {"updated": 0}
    assert deliver(issue_event(1, "labeled")).status_code == 204
    assert deliver({"zen": "hi"}, event="ping").status_code == 200
    assert done(sent) == []


@pytest.mark.django_db
def test_the_webhook_needs_no_sign_in_but_only_accepts_post(webhook_secret):
    assert APIClient().get(reverse("github-webhook")).status_code == 405


# --- Catch-up sync when a project is opened ---------------------------------------


@pytest.mark.django_db
def test_opening_a_project_reads_states_from_github(sent, fake_github):  # noqa: F811
    # The webhook was missed: #1 and #3 were closed while our API slept.
    fake_github.closed = {1, 3}

    response = client_for(sent.owner).get(reverse("project-detail", args=[sent.id]))

    assert response.json()["progress"]["done"] == 2
    assert response.json()["progress"]["total"] == 3
    assert done(sent) == [1, 3]


@pytest.mark.django_db
def test_github_is_asked_at_most_once_a_minute(sent, fake_github):  # noqa: F811
    client = client_for(sent.owner)
    client.get(reverse("project-detail", args=[sent.id]))
    calls = len(fake_github.calls)

    fake_github.closed = {1}
    client.get(reverse("project-detail", args=[sent.id]))
    client.get(reverse("project-stories", args=[sent.id]))

    assert len(fake_github.calls) == calls
    assert done(sent) == []

    Project.objects.filter(pk=sent.pk).update(github_synced_at=timezone.now() - timedelta(minutes=2))
    client.get(reverse("project-detail", args=[sent.id]))
    assert done(sent) == [1]


@pytest.mark.django_db
def test_github_being_down_keeps_the_last_known_progress(sent, fake_github, webhook_secret):  # noqa: F811
    deliver(issue_event(2, "closed"))
    fake_github.fail("GET", r"/repos/.+/installation", 503, 503, 503)

    response = client_for(sent.owner).get(reverse("project-detail", args=[sent.id]))

    assert response.status_code == 200
    assert response.json()["progress"]["done"] == 1


@pytest.mark.django_db
def test_no_progress_before_the_project_is_sent(project):  # noqa: F811
    response = client_for(project.owner).get(reverse("project-detail", args=[project.id]))

    assert response.json()["progress"] is None


@pytest.mark.django_db
def test_stories_say_which_are_done(sent, fake_github, webhook_secret):  # noqa: F811
    fake_github.closed = {3}
    deliver(issue_event(3, "closed"))

    stories = client_for(sent.owner).get(reverse("project-stories", args=[sent.id])).json()

    assert [(s["github_issue_number"], s["github_issue_closed"]) for s in stories] == [
        (1, False),
        (2, False),
        (3, True),
    ]


@pytest.mark.django_db
def test_the_team_sees_progress_too(sent, admin, fake_github, webhook_secret):  # noqa: F811
    fake_github.closed = {1}
    deliver(issue_event(1, "closed"))

    body = client_for(admin).get(reverse("admin-project-detail", args=[sent.id])).json()

    assert body["progress"]["done"] == 1
