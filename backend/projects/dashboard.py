"""Numbers for the team's dashboard (A2, A7, A9, AI7, N8).

Everything is computed with a few aggregate queries, so the page stays fast
however many projects there are (A9: charts load in under 2 seconds).
"""

from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from .models import AIUsage, GitHubPush, Project, StoryChange, UserStory

WEEKS_SHOWN = 12
DAYS_SHOWN = 14
TOP_CLIENTS = 8
# A client counts as active if one of their projects changed this recently.
ACTIVE_DAYS = 30
APPROVED = (Project.Status.AWAITING_ADMIN, Project.Status.SENT_TO_GITHUB)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def overview(now) -> dict:
    """A2: the business at a glance."""
    return {
        "active_clients": Project.objects.filter(updated_at__gte=now - timedelta(days=ACTIVE_DAYS))
        .values("owner")
        .distinct()
        .count(),
        "interviews_this_week": Project.objects.filter(created_at__date__gte=week_start(now.date())).count(),
        "stories_created": UserStory.objects.count(),
        "issues_pushed": GitHubPush.objects.filter(status=GitHubPush.Status.SUCCEEDED).aggregate(
            total=Sum("issues_created")
        )["total"]
        or 0,
    }


def interviews_by_week(now) -> list[dict]:
    """A9: new interviews per week, for the last 12 weeks (empty weeks included)."""
    first = week_start(now.date()) - timedelta(weeks=WEEKS_SHOWN - 1)
    counts = {
        row["week"].date() if hasattr(row["week"], "date") else row["week"]: row["count"]
        for row in Project.objects.filter(created_at__date__gte=first)
        .annotate(week=TruncWeek("created_at"))
        .values("week")
        .annotate(count=Count("id"))
    }
    weeks = [first + timedelta(weeks=i) for i in range(WEEKS_SHOWN)]
    return [{"week": week.isoformat(), "count": counts.get(week, 0)} for week in weeks]


def stories_by_priority() -> list[dict]:
    """A9: how the current stories split by priority."""
    counts = dict(UserStory.objects.values_list("priority").annotate(count=Count("id")))
    return [{"priority": p.value, "count": counts.get(p.value, 0)} for p in UserStory.Priority]


def projects_by_client() -> list[dict]:
    """A9: each client's projects by stage, busiest clients first."""
    statuses = [s.value for s in Project.Status]
    rows = (
        Project.objects.values("owner_id", "owner__first_name", "owner__last_name", "owner__email", "owner__username")
        .annotate(total=Count("id"), **{s: Count("id", filter=Q(status=s)) for s in statuses})
        .order_by("-total", "owner_id")[:TOP_CLIENTS]
    )
    clients = []
    for row in rows:
        name = f"{row['owner__first_name']} {row['owner__last_name']}".strip()
        clients.append(
            {
                "client": name or row["owner__email"] or row["owner__username"],
                "total": row["total"],
                "by_status": {s: row[s] for s in statuses},
            }
        )
    return clients


def ai_quality() -> dict:
    """AI7: how often stories the AI wrote were approved without changes.

    Counted over projects the client has approved. A story counts as changed
    if the client edited it, or our team edited, merged, split or rejected it.
    Stories the client removed before approving are not counted: they are
    deleted at that point (ADR 0006).
    """
    approved = Project.objects.filter(status__in=APPROVED)
    ai_now = UserStory.objects.filter(project__in=approved, origin=UserStory.Origin.AI)

    edited_by_team: set[int] = set()
    removed_by_team = 0
    for change in StoryChange.objects.filter(project__in=approved).only("action", "before"):
        for story in change.before:
            if story.get("origin", UserStory.Origin.AI) != UserStory.Origin.AI:
                continue
            if change.action == StoryChange.Action.EDIT:
                edited_by_team.add(story["id"])
            else:
                # Rejected, merged or split: that AI story no longer exists as written.
                removed_by_team += 1

    current = list(ai_now.values_list("id", "client_edited"))
    edited_by_client = sum(1 for _, edited in current if edited)
    edited_by_team_only = sum(1 for pk, edited in current if not edited and pk in edited_by_team)
    unchanged = len(current) - edited_by_client - edited_by_team_only
    total = len(current) + removed_by_team
    return {
        "ai_stories": total,
        "accepted_unchanged": unchanged,
        "edited_by_client": edited_by_client,
        "edited_by_team": edited_by_team_only,
        "removed_by_team": removed_by_team,
        "acceptance_rate": round(unchanged / total, 3) if total else None,
    }


def ai_usage(now) -> dict:
    """A7: daily use of each provider against its free limit, with warnings."""
    today = now.date()
    first = today - timedelta(days=DAYS_SHOWN - 1)
    rows = list(AIUsage.objects.filter(day__gte=first))

    by_day = {first + timedelta(days=i): {"workers_ai_neurons": 0.0, "groq_calls": 0} for i in range(DAYS_SHOWN)}
    for row in rows:
        if row.provider == "workers_ai":
            by_day[row.day]["workers_ai_neurons"] += row.neurons
        elif row.provider == "groq":
            by_day[row.day]["groq_calls"] += row.calls

    limit = settings.WORKERS_AI_DAILY_NEURONS
    warn_at = settings.AI_USAGE_WARNING_SHARE
    used_today = by_day[today]["workers_ai_neurons"]
    warnings = []
    if limit and used_today >= warn_at * limit:
        warnings.append(
            f"Workers AI has used {used_today / limit:.0%} of today's free neurons. "
            "New requests will switch to Groq when it runs out."
        )

    groq_today = []
    for row in sorted((r for r in rows if r.day == today and r.provider == "groq"), key=lambda r: r.feature):
        entry = {
            "feature": row.feature,
            "calls": row.calls,
            "request_limit": row.request_limit,
            "requests_remaining": row.requests_remaining,
        }
        groq_today.append(entry)
        if row.request_limit and row.requests_remaining is not None:
            used_share = 1 - row.requests_remaining / row.request_limit
            if used_share >= warn_at:
                warnings.append(f"Groq ({row.feature}) has used {used_share:.0%} of its request limit.")

    return {
        "workers_ai_daily_neurons": limit,
        "warning_share": warn_at,
        "days": [
            {"day": day.isoformat(), "workers_ai_neurons": round(v["workers_ai_neurons"], 1), "groq_calls": v["groq_calls"]}
            for day, v in by_day.items()
        ],
        "groq_today": groq_today,
        "warnings": warnings,
    }


def dashboard() -> dict:
    now = timezone.now()
    return {
        "overview": overview(now),
        "interviews_by_week": interviews_by_week(now),
        "stories_by_priority": stories_by_priority(),
        "projects_by_client": projects_by_client(),
        "ai_quality": ai_quality(),
        "ai_usage": ai_usage(now),
    }
