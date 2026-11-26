"""Tests for AI usage tracking and the team's dashboard (A2, A7, A9, AI7, N8)."""

from datetime import timedelta

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from projects import llm
from projects.models import CONSENT_VERSION, AIUsage, GitHubPush, Project, StoryChange, UserStory
from projects.usage import record_ai_call

User = get_user_model()


@pytest.fixture
def admin():
    return User.objects.create(username="admin", clerk_id="user_admin", role=User.Role.ADMIN)


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice", first_name="Alice", last_name="Baker")


def make_project(owner, status=Project.Status.AWAITING_ADMIN):
    return Project.objects.create(
        owner=owner,
        name="Bakery website",
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )


def add_story(project, position, origin=UserStory.Origin.AI, client_edited=False, priority="must"):
    return UserStory.objects.create(
        project=project,
        role="customer",
        goal=f"goal {position}",
        reason="it saves time",
        acceptance_criteria=["It works"],
        priority=priority,
        position=position,
        provider="groq",
        origin=origin,
        client_edited=client_edited,
    )


def get_dashboard(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(reverse("admin-dashboard"))


# --- Recording usage (A7, N8) ----------------------------------------------------


@pytest.mark.django_db
def test_workers_ai_neurons_add_up_per_day_and_feature():
    record_ai_call("workers_ai", "user_stories", neurons=40.5)
    record_ai_call("workers_ai", "user_stories", neurons=9.5)
    record_ai_call("workers_ai", "transcription", neurons=2)

    stories = AIUsage.objects.get(provider="workers_ai", feature="user_stories")
    assert (stories.calls, stories.neurons) == (2, 50.0)
    assert stories.day == timezone.now().date()
    assert AIUsage.objects.count() == 2


@pytest.mark.django_db
def test_groq_limits_come_from_its_headers():
    record_ai_call("groq", "user_stories", headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "999"})
    record_ai_call("groq", "user_stories", headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "998"})

    row = AIUsage.objects.get(provider="groq")
    assert (row.calls, row.request_limit, row.requests_remaining) == (2, 1000, 998)


def test_recording_never_breaks_an_ai_call():
    # No database access is allowed in this test, so saving fails; the call must not.
    record_ai_call("workers_ai", "user_stories", neurons=1)


@pytest.mark.django_db
def test_every_ai_call_is_counted(settings, monkeypatch):
    settings.CLOUDFLARE_ACCOUNT_ID = "acc"
    settings.CLOUDFLARE_AI_TOKEN = "tok"
    settings.GROQ_API_KEY = ""

    def fake_post(url, **kwargs):
        body = {"result": {"response": {"ok": True}, "usage": {"neurons": 42.0}}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    llm.ask_for_json([{"role": "user", "content": "hi"}], "user_stories", {}, lambda answer: answer)

    row = AIUsage.objects.get()
    assert (row.provider, row.feature, row.calls, row.neurons) == ("workers_ai", "user_stories", 1, 42.0)


# --- The dashboard (A2, A9) -------------------------------------------------------


@pytest.mark.django_db
def test_only_admins_see_the_dashboard(alice, admin):
    assert get_dashboard(alice).status_code == 403
    assert APIClient().get(reverse("admin-dashboard")).status_code == 401
    assert get_dashboard(admin).status_code == 200


@pytest.mark.django_db
def test_overview_matches_the_database(admin, alice):
    bob = User.objects.create(username="bob", clerk_id="user_bob")
    project = make_project(alice)
    add_story(project, 0)
    add_story(project, 1)
    old = make_project(bob, status=Project.Status.INTERVIEWING)
    Project.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=60), updated_at=timezone.now() - timedelta(days=60)
    )
    GitHubPush.objects.create(project=project, repo="a/b", status="succeeded", issues_created=2)
    GitHubPush.objects.create(project=project, repo="a/b", status="failed", issues_created=1)

    overview = get_dashboard(admin).json()["overview"]

    assert overview == {
        # Bob's only project hasn't changed for 60 days.
        "active_clients": 1,
        "interviews_this_week": 1,
        "stories_created": 2,
        # Only successful pushes count.
        "issues_pushed": 2,
    }


@pytest.mark.django_db
def test_charts_have_every_week_and_priority(admin, alice):
    project = make_project(alice)
    add_story(project, 0, priority="must")
    add_story(project, 1, priority="nice")

    body = get_dashboard(admin).json()

    weeks = body["interviews_by_week"]
    assert len(weeks) == 12
    assert weeks[-1]["count"] == 1
    assert sum(w["count"] for w in weeks) == 1
    assert body["stories_by_priority"] == [
        {"priority": "must", "count": 1},
        {"priority": "should", "count": 0},
        {"priority": "nice", "count": 1},
    ]
    [client] = body["projects_by_client"]
    assert client["client"] == "Alice Baker"
    assert client["by_status"]["awaiting_admin"] == 1


# --- AI quality (AI7) -------------------------------------------------------------


@pytest.mark.django_db
def test_acceptance_rate_counts_every_kind_of_change(admin, alice):
    project = make_project(alice)
    add_story(project, 0)
    add_story(project, 1, client_edited=True)
    edited_by_team = add_story(project, 2)
    add_story(project, 3, origin=UserStory.Origin.CLIENT)  # not written by AI: not counted
    StoryChange.objects.create(project=project, action="edit", before=[edited_by_team.snapshot()], after=[])
    rejected = {"id": 999, "goal": "gone", "origin": "ai"}
    StoryChange.objects.create(project=project, action="reject", before=[rejected], after=[])
    # Projects still in review aren't counted yet.
    in_review = make_project(alice, status=Project.Status.AWAITING_CLIENT)
    add_story(in_review, 0)

    quality = get_dashboard(admin).json()["ai_quality"]

    assert quality == {
        "ai_stories": 4,
        "accepted_unchanged": 1,
        "edited_by_client": 1,
        "edited_by_team": 1,
        "removed_by_team": 1,
        "acceptance_rate": 0.25,
    }


@pytest.mark.django_db
def test_no_rate_before_anything_is_approved(admin):
    assert get_dashboard(admin).json()["ai_quality"]["acceptance_rate"] is None


# --- AI usage on the dashboard (A7) -----------------------------------------------


@pytest.mark.django_db
def test_usage_shows_14_days_and_warns_at_80_percent(admin, settings):
    settings.WORKERS_AI_DAILY_NEURONS = 1000
    record_ai_call("workers_ai", "user_stories", neurons=850)
    record_ai_call(
        "groq", "user_stories", headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "100"}
    )

    usage = get_dashboard(admin).json()["ai_usage"]

    assert len(usage["days"]) == 14
    assert usage["days"][-1] == {"day": timezone.now().date().isoformat(), "workers_ai_neurons": 850.0, "groq_calls": 1}
    assert usage["groq_today"] == [
        {"feature": "user_stories", "calls": 1, "request_limit": 1000, "requests_remaining": 100}
    ]
    assert len(usage["warnings"]) == 2
    assert "85%" in usage["warnings"][0]
    assert "90%" in usage["warnings"][1]


@pytest.mark.django_db
def test_no_warning_below_80_percent(admin, settings):
    settings.WORKERS_AI_DAILY_NEURONS = 1000
    record_ai_call("workers_ai", "user_stories", neurons=500)

    assert get_dashboard(admin).json()["ai_usage"]["warnings"] == []
