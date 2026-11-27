"""How much of a delivered project is built, from its GitHub issues (G4, C10).

A story is done while its issue is closed. GitHub tells us the moment an issue
is closed or reopened (a signed webhook). Webhooks can be missed, though: our
free API host sleeps when idle and GitHub doesn't resend a delivery that timed
out. So whenever someone opens a delivered project and the states are more
than a minute old, we also read them from GitHub. Progress is then never more
than a minute out of date while someone is looking at it.
"""

import hashlib
import hmac
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .audit import Action, Actor, record
from .delivery import SOURCE_LABEL
from .github import GitHub, GitHubError, make_http_client
from .models import Project, UserStory

logger = logging.getLogger(__name__)

MAX_AGE = timedelta(minutes=1)


def progress(project: Project) -> dict | None:
    """'3 of 5 done', for a project that has been sent to GitHub."""
    if project.status != Project.Status.SENT_TO_GITHUB:
        return None
    stories = project.stories.exclude(github_issue_number=None)
    return {
        "done": stories.filter(github_issue_closed=True).count(),
        "total": stories.count(),
        "synced_at": project.github_synced_at,
    }


def valid_signature(secret: str, body: bytes, header: str) -> bool:
    """GitHub signs each delivery: X-Hub-Signature-256 = 'sha256=' + HMAC(body)."""
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Constant-time comparison, so the signature can't be guessed byte by byte.
    return hmac.compare_digest(expected, header or "")


def apply_issue_event(payload: dict) -> int:
    """Record an issue being closed or reopened. Returns how many stories changed.

    The issue's current state is used rather than the action, so a repeated
    delivery changes nothing.
    """
    issue = payload.get("issue") or {}
    repo = (payload.get("repository") or {}).get("full_name", "")
    number = issue.get("number")
    if not repo or not number or "pull_request" in issue:
        return 0
    closed = issue.get("state") == "closed"
    changing = UserStory.objects.filter(
        project__github_repo__iexact=repo,
        project__status=Project.Status.SENT_TO_GITHUB,
        github_issue_number=number,
    ).exclude(github_issue_closed=closed)
    project_ids = set(changing.values_list("project_id", flat=True))
    updated = changing.update(github_issue_closed=closed)
    for project_id in project_ids:
        record(project_id, Action.PROGRESS_UPDATED, Actor.GITHUB, f"Issue #{number} {'closed' if closed else 'reopened'}")
    return updated


def refresh_if_stale(project: Project) -> None:
    """Read issue states from GitHub if they're over a minute old. Never raises."""
    if project.status != Project.Status.SENT_TO_GITHUB or not project.github_repo:
        return
    now = timezone.now()
    if project.github_synced_at and now - project.github_synced_at < MAX_AGE:
        return
    # Claim the refresh first, so two pages opened together don't both call GitHub.
    claimed = (
        Project.objects.filter(pk=project.pk, github_synced_at=project.github_synced_at)
        .update(github_synced_at=now)
    )
    if not claimed:
        return
    project.github_synced_at = now
    try:
        with make_http_client() as http:
            github = GitHub(http)
            repo = github.connect(project.github_repo)
            closed = github.closed_issue_numbers(repo, SOURCE_LABEL[0])
    except GitHubError as exc:
        # Keep showing the last known progress; the next view tries again.
        logger.warning("Couldn't refresh issue states for project %s: %s", project.pk, exc)
        return
    with transaction.atomic():
        stories = project.stories.exclude(github_issue_number=None)
        newly_closed = stories.filter(github_issue_number__in=closed, github_issue_closed=False).update(
            github_issue_closed=True
        )
        reopened = stories.exclude(github_issue_number__in=closed).filter(github_issue_closed=True).update(
            github_issue_closed=False
        )
    if newly_closed or reopened:
        record(
            project,
            Action.PROGRESS_UPDATED,
            Actor.GITHUB,
            f"Checked with GitHub: {newly_closed} closed, {reopened} reopened",
        )
