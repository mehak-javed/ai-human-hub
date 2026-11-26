"""Tests for sending reviewed stories to GitHub (A5, A6, G1, G2, G5, G6).

GitHub is never called: `make_http_client` returns an httpx client backed by
FakeGitHub, a tiny in-memory imitation of the REST endpoints we use.
"""

import base64
import json
import re
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from projects import delivery, github
from projects.delivery import requirements_markdown, send_to_github
from projects.github import GitHub, GitHubError, Repo
from projects.models import CONSENT_VERSION, FollowUpQuestion, GitHubPush, Project, UserStory

User = get_user_model()
REPO = "acme/bakery"


@pytest.fixture(scope="module")
def key_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return pem, key.public_key()


@pytest.fixture
def app_settings(settings, key_pair):
    settings.GITHUB_APP_ID = "12345"
    settings.GITHUB_APP_PRIVATE_KEY = key_pair[0]
    settings.GITHUB_APP_SLUG = "ai-human-hub"
    return settings


class FakeGitHub:
    """Just enough of GitHub's REST API, kept in memory."""

    def __init__(self):
        self.installed = {REPO}
        self.private = True
        self.labels: set[str] = set()
        self.issues: dict[int, dict] = {}
        self.files: dict[str, dict] = {}
        self.token_requests: list[dict] = []
        # Status codes to return for the next matching calls: {(method, path regex): [codes]}
        self.failures: dict[tuple[str, str], list[int]] = {}
        self.calls: list[tuple[str, str]] = []

    def fail(self, method, path_pattern, *codes):
        self.failures[(method, path_pattern)] = list(codes)

    def handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.calls.append((method, path))
        for (fail_method, pattern), codes in self.failures.items():
            if fail_method == method and re.fullmatch(pattern, path) and codes:
                return httpx.Response(codes.pop(0), json={"message": "Something broke"})
        body = json.loads(request.content) if request.content else {}
        owner_repo = "/".join(path.split("/")[2:4])

        if method == "GET" and path.endswith("/installation"):
            if owner_repo in self.installed:
                return httpx.Response(200, json={"id": 99})
            return httpx.Response(404, json={"message": "Not Found"})
        if method == "POST" and path == "/app/installations/99/access_tokens":
            self.token_requests.append(body)
            return httpx.Response(201, json={"token": "ghs_installation_token"})
        assert request.headers["Authorization"] == "Bearer ghs_installation_token"
        if method == "GET" and path == f"/repos/{REPO}":
            return httpx.Response(
                200,
                json={
                    "full_name": REPO,
                    "private": self.private,
                    "default_branch": "main",
                    "html_url": f"https://github.com/{REPO}",
                },
            )
        if method == "POST" and path.endswith("/labels"):
            if body["name"] in self.labels:
                return httpx.Response(422, json={"message": "Validation Failed"})
            self.labels.add(body["name"])
            return httpx.Response(201, json=body)
        if method == "POST" and path.endswith("/issues"):
            number = len(self.issues) + 1
            self.issues[number] = body
            return httpx.Response(201, json={"number": number, **body})
        if method == "PATCH" and "/issues/" in path:
            number = int(path.rsplit("/", 1)[1])
            if number not in self.issues:
                return httpx.Response(404, json={"message": "Not Found"})
            self.issues[number] = body
            return httpx.Response(200, json={"number": number, **body})
        if "/contents/" in path:
            name = path.split("/contents/", 1)[1]
            if method == "GET":
                if name in self.files:
                    return httpx.Response(200, json={"sha": self.files[name]["sha"]})
                return httpx.Response(404, json={"message": "Not Found"})
            if method == "PUT":
                if name in self.files:
                    assert body["sha"] == self.files[name]["sha"], "must send the current sha to replace a file"
                self.files[name] = {**body, "sha": f"sha{len(self.calls)}"}
                return httpx.Response(201, json={"commit": {"html_url": f"https://github.com/{REPO}/commit/abc"}})
        return httpx.Response(500, json={"message": f"FakeGitHub has no route for {method} {path}"})


@pytest.fixture
def fake_github(monkeypatch, app_settings):
    fake = FakeGitHub()
    monkeypatch.setattr(
        github, "make_http_client", lambda: httpx.Client(base_url=github.API, transport=httpx.MockTransport(fake.handle))
    )
    monkeypatch.setattr(delivery, "make_http_client", github.make_http_client)
    # No real waiting between requests or retries in tests.
    monkeypatch.setattr(github.time, "sleep", lambda seconds: None)
    return fake


@pytest.fixture
def admin():
    return User.objects.create(username="admin", clerk_id="user_admin", role=User.Role.ADMIN)


@pytest.fixture
def project():
    alice = User.objects.create(username="alice", clerk_id="user_alice")
    project = Project.objects.create(
        owner=alice,
        name="Bakery website",
        project_type="website",
        status=Project.Status.AWAITING_ADMIN,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
        approved_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        github_repo=REPO,
    )
    stories = [
        ("customer", "order a cake online", "must"),
        ("customer", "pay by card", "should"),
        ("owner", "see each day's orders", "nice"),
    ]
    for position, (role, goal, priority) in enumerate(stories):
        UserStory.objects.create(
            project=project,
            role=role,
            goal=goal,
            reason="it saves time.",
            acceptance_criteria=["It works", "It is fast"],
            priority=priority,
            position=position,
            provider="groq",
        )
    return project


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# --- Signing in as the App -------------------------------------------------------


def test_app_jwt_is_signed_with_the_app_key(app_settings, key_pair):
    token = github.app_jwt()

    claims = jwt.decode(token, key_pair[1], algorithms=["RS256"])
    assert claims["iss"] == "12345"
    # GitHub refuses App tokens that last more than 10 minutes.
    assert claims["exp"] - claims["iat"] <= 10 * 60


def test_private_key_can_be_base64_encoded(app_settings, key_pair):
    app_settings.GITHUB_APP_PRIVATE_KEY = base64.b64encode(key_pair[0].encode()).decode()

    assert jwt.decode(github.app_jwt(), key_pair[1], algorithms=["RS256"])["iss"] == "12345"


@pytest.mark.parametrize("value", ["not base64 at all!", "LS0tLS1CRUdJTg", base64.b64encode(b"hello").decode()])
def test_an_unreadable_key_is_a_clear_error(app_settings, value):
    app_settings.GITHUB_APP_PRIVATE_KEY = value

    with pytest.raises(GitHubError, match="private key"):
        github.app_jwt()


def test_text_pasted_around_the_key_is_ignored(app_settings, key_pair):
    # Seen live: a new key pasted after the old, broken value instead of over it.
    app_settings.GITHUB_APP_PRIVATE_KEY = 'LS0tLS1CRUdJTiBSU0Eg"\n' + key_pair[0] + "\nleftover"

    assert jwt.decode(github.app_jwt(), key_pair[1], algorithms=["RS256"])["iss"] == "12345"


def test_a_key_without_its_begin_and_end_lines_works(app_settings, key_pair):
    # Seen live: the dashboard kept only the lines between BEGIN and END.
    body = "\n".join(line for line in key_pair[0].splitlines() if not line.startswith("-----"))
    app_settings.GITHUB_APP_PRIVATE_KEY = body

    assert jwt.decode(github.app_jwt(), key_pair[1], algorithms=["RS256"])["iss"] == "12345"


def test_a_key_with_literal_backslash_n_works(app_settings, key_pair):
    app_settings.GITHUB_APP_PRIVATE_KEY = key_pair[0].replace("\n", "\\n")

    assert jwt.decode(github.app_jwt(), key_pair[1], algorithms=["RS256"])["iss"] == "12345"


def test_a_key_pasted_with_line_breaks_still_works(app_settings, key_pair):
    encoded = base64.b64encode(key_pair[0].encode()).decode()
    app_settings.GITHUB_APP_PRIVATE_KEY = "\n".join(encoded[i : i + 64] for i in range(0, len(encoded), 64))

    assert jwt.decode(github.app_jwt(), key_pair[1], algorithms=["RS256"])["iss"] == "12345"


# --- Connecting a repo (A6) ------------------------------------------------------


def connect(name=REPO):
    with github.make_http_client() as http:
        return GitHub(http).connect(name)


def test_connecting_a_private_repo(fake_github):
    repo = connect()

    assert repo == Repo(full_name=REPO, default_branch="main", html_url=f"https://github.com/{REPO}")
    # The token is limited to this one repository and the permissions we need.
    assert fake_github.token_requests == [
        {"repositories": ["bakery"], "permissions": {"issues": "write", "contents": "write", "metadata": "read"}}
    ]


@pytest.mark.parametrize("pasted", [f"https://github.com/{REPO}", f"github.com/{REPO}/", f"https://github.com/{REPO}.git"])
def test_a_pasted_github_address_is_accepted(fake_github, pasted):
    assert connect(pasted).full_name == REPO


def test_public_repos_are_refused(fake_github):
    fake_github.private = False

    with pytest.raises(GitHubError, match="public"):
        connect()


def test_repo_without_the_app_is_refused(fake_github):
    with pytest.raises(GitHubError, match="isn't installed"):
        connect("acme/other-repo")


@pytest.mark.parametrize("name", ["bakery", "acme/bakery/extra", "../etc/passwd", "acme/ba kery"])
def test_badly_written_repo_names_are_refused(fake_github, name):
    with pytest.raises(GitHubError, match="owner/name"):
        connect(name)
    assert fake_github.calls == []


# --- Sending (A5, G1, G2) ---------------------------------------------------------


@pytest.mark.django_db
def test_sending_creates_one_issue_per_story(fake_github, project, admin):
    push = send_to_github(project, admin)

    assert push.status == GitHubPush.Status.SUCCEEDED
    assert (push.issues_created, push.issues_updated) == (3, 0)
    assert len(fake_github.issues) == project.stories.count()
    first = fake_github.issues[1]
    assert first["title"] == "Order a cake online"
    assert "**As a** customer, **I want to** order a cake online, **so that** it saves time." in first["body"]
    # Acceptance criteria become a checklist.
    assert "- [ ] It works\n- [ ] It is fast" in first["body"]
    assert first["labels"] == ["priority: must", "from: ai-human-hub"]
    assert fake_github.issues[3]["labels"][0] == "priority: nice to have"
    assert list(project.stories.values_list("github_issue_number", flat=True)) == [1, 2, 3]


@pytest.mark.django_db
def test_sending_commits_requirements_and_marks_the_project_sent(fake_github, project, admin):
    push = send_to_github(project, admin)

    requirements = base64.b64decode(fake_github.files["requirements.md"]["content"]).decode()
    assert requirements.startswith("# Bakery website: requirements")
    assert "### Order a cake online ([#1](https://github.com/acme/bakery/issues/1))" in requirements
    assert fake_github.files["requirements.md"]["message"] == (
        "docs: update requirements for Bakery website from AI Human Hub"
    )
    assert fake_github.files["requirements.md"]["branch"] == "main"
    assert push.commit_url == "https://github.com/acme/bakery/commit/abc"
    project.refresh_from_db()
    assert project.status == Project.Status.SENT_TO_GITHUB
    assert project.sent_to_github_at is not None


@pytest.mark.django_db
def test_requirements_include_what_the_client_said_about_data(project):
    FollowUpQuestion.objects.create(
        project=project,
        topic="data",
        question="What do you keep about each order?",
        position=0,
        status=FollowUpQuestion.Status.ANSWERED,
        answer="The cake, the collection time, and a phone number for my manager Sam Lee.",
        provider="groq",
    )
    repo = Repo(REPO, "main", f"https://github.com/{REPO}")

    text = requirements_markdown(project, list(project.stories.all()), repo)

    assert "## Information the system keeps" in text
    assert "What do you keep about each order?" in text
    # Only the masked answer goes into the repo.
    assert "Sam" not in text


@pytest.mark.django_db
def test_failure_is_recorded_and_the_project_stays_in_review(fake_github, project, admin):
    # GitHub keeps failing from the third issue on, even after retries.
    real_handle = fake_github.handle
    created = []

    def flaky(request):
        if request.method == "POST" and request.url.path.endswith("/issues"):
            created.append(1)
            if len(created) >= 3:
                return httpx.Response(500, json={"message": "Server Error"})
        return real_handle(request)

    fake_github.handle = flaky

    push = send_to_github(project, admin)

    assert push.status == GitHubPush.Status.FAILED
    assert "Couldn't create an issue (HTTP 500: Server Error)" in push.error
    assert "ghs_" not in push.error
    project.refresh_from_db()
    assert project.status == Project.Status.AWAITING_ADMIN
    # The two issues that were created are remembered…
    assert list(project.stories.values_list("github_issue_number", flat=True)) == [1, 2, None]


@pytest.mark.django_db
def test_retrying_after_a_failure_never_duplicates_issues(fake_github, project, admin):
    stories = list(project.stories.all())
    stories[0].github_issue_number = 1
    stories[0].save()
    fake_github.issues[1] = {"title": "old"}

    push = send_to_github(project, admin)

    assert push.status == GitHubPush.Status.SUCCEEDED
    assert (push.issues_created, push.issues_updated) == (2, 1)
    assert len(fake_github.issues) == 3
    assert fake_github.issues[1]["title"] == "Order a cake online"


@pytest.mark.django_db
def test_issue_deleted_on_github_is_created_again(fake_github, project, admin):
    story = project.stories.first()
    story.github_issue_number = 42
    story.save()

    send_to_github(project, admin)

    story.refresh_from_db()
    assert story.github_issue_number != 42
    assert len(fake_github.issues) == 3


@pytest.mark.django_db
def test_requirements_file_is_replaced_not_duplicated(fake_github, project, admin):
    fake_github.files["requirements.md"] = {"sha": "old-sha"}

    push = send_to_github(project, admin)

    assert push.status == GitHubPush.Status.SUCCEEDED
    assert "Bakery website" in base64.b64decode(fake_github.files["requirements.md"]["content"]).decode()


@pytest.mark.django_db
def test_temporary_github_errors_are_retried(fake_github, project, admin):
    fake_github.fail("POST", r"/repos/acme/bakery/issues", 502, 503)

    push = send_to_github(project, admin)

    assert push.status == GitHubPush.Status.SUCCEEDED
    assert len(fake_github.issues) == 3


# --- The API (A5, A6, P2) ---------------------------------------------------------


@pytest.mark.django_db
def test_admin_connects_a_repo(fake_github, project, admin):
    project.github_repo = ""
    project.save()

    response = client_for(admin).post(
        reverse("admin-project-connect-github", args=[project.id]), {"repo": REPO}, format="json"
    )

    assert response.status_code == 200
    assert response.json() == {"repo": REPO, "url": f"https://github.com/{REPO}"}
    project.refresh_from_db()
    assert project.github_repo == REPO


@pytest.mark.django_db
def test_a_broken_key_is_explained_not_a_server_error(fake_github, project, admin, app_settings):
    # Seen live: a base64 key cut short when it was pasted into the dashboard.
    app_settings.GITHUB_APP_PRIVATE_KEY = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVB1"
    project.github_repo = ""
    project.save()

    response = client_for(admin).post(
        reverse("admin-project-connect-github", args=[project.id]), {"repo": REPO}, format="json"
    )

    assert response.status_code == 400
    assert "private key" in response.json()["detail"]
    assert fake_github.calls == []


@pytest.mark.django_db
def test_connecting_a_public_repo_is_refused_and_not_saved(fake_github, project, admin):
    project.github_repo = ""
    project.save()
    fake_github.private = False

    response = client_for(admin).post(
        reverse("admin-project-connect-github", args=[project.id]), {"repo": REPO}, format="json"
    )

    assert response.status_code == 400
    assert "public" in response.json()["detail"]
    project.refresh_from_db()
    assert project.github_repo == ""


@pytest.mark.django_db
def test_send_endpoint_reports_success(fake_github, project, admin):
    response = client_for(admin).post(reverse("admin-project-send", args=[project.id]))

    assert response.status_code == 200
    assert response.json()["status"] == "sent_to_github"
    assert response.json()["push"]["issues_created"] == 3


@pytest.mark.django_db
def test_send_endpoint_reports_failure_as_502(fake_github, project, admin):
    fake_github.fail("POST", r"/repos/acme/bakery/labels", 403)

    response = client_for(admin).post(reverse("admin-project-send", args=[project.id]))

    assert response.status_code == 502
    assert response.json()["status"] == "awaiting_admin"
    assert "label" in response.json()["push"]["error"]


@pytest.mark.django_db
def test_send_needs_a_connected_repo(fake_github, project, admin):
    project.github_repo = ""
    project.save()

    response = client_for(admin).post(reverse("admin-project-send", args=[project.id]))

    assert response.status_code == 400
    assert fake_github.calls == []


@pytest.mark.django_db
@pytest.mark.parametrize("stage", ["interviewing", "awaiting_client", "sent_to_github"])
def test_send_only_while_awaiting_admin(fake_github, project, admin, stage):
    project.status = stage
    project.save()

    response = client_for(admin).post(reverse("admin-project-send", args=[project.id]))

    assert response.status_code == 409
    assert fake_github.calls == []


@pytest.mark.django_db
def test_nothing_is_sent_when_the_app_is_not_set_up(project, admin, settings):
    settings.GITHUB_APP_ID = ""

    response = client_for(admin).post(reverse("admin-project-send", args=[project.id]))

    assert response.status_code == 503


@pytest.mark.django_db
def test_clients_cannot_connect_or_send(fake_github, project):
    client = client_for(project.owner)

    assert client.post(reverse("admin-project-send", args=[project.id])).status_code == 403
    assert (
        client.post(reverse("admin-project-connect-github", args=[project.id]), {"repo": REPO}, format="json")
        .status_code
        == 403
    )
    assert fake_github.calls == []


@pytest.mark.django_db
def test_detail_shows_pushes_and_github_setup(fake_github, project, admin):
    send_to_github(project, admin)

    body = client_for(admin).get(reverse("admin-project-detail", args=[project.id])).json()

    assert body["github"] == {
        "configured": True,
        "install_url": "https://github.com/apps/ai-human-hub/installations/new",
    }
    assert body["pushes"][0]["status"] == "succeeded"
    assert body["github_repo"] == REPO
