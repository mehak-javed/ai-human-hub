"""Write and read the team's audit log (A8).

`record()` is called next to every AI output, client or team change,
approval and GitHub push. It writes counts, IDs, providers and repo names
only: never the client's words, so the log needs no masking and holds no
personal data.
"""

import logging

from django.db import transaction

from .models import AuditEvent

logger = logging.getLogger(__name__)

Action = AuditEvent.Action
Actor = AuditEvent.Actor

PROVIDERS = {"workers_ai": "Workers AI", "groq": "Groq"}


def provider_name(provider: str) -> str:
    return PROVIDERS.get(provider, provider or "AI")


def record(project, action: str, actor: str, detail: str = "", user=None) -> None:
    """Add one event. A failure is logged, never raised: the action itself
    has already succeeded and must not be undone by its log entry."""
    try:
        # Its own savepoint: a failed write can't spoil the caller's transaction.
        with transaction.atomic():
            AuditEvent.objects.create(
                # A project, or just its id (e.g. from a GitHub webhook).
                project_id=project if isinstance(project, int) else project.pk,
                action=action,
                actor=actor,
                user=user if getattr(user, "is_authenticated", False) else None,
                detail=detail[:200],
            )
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception("Could not write audit event %s for project %s", action, getattr(project, "pk", project))


def plural(count: int, word: str) -> str:
    """'1 story', '5 stories', '2 issues'."""
    if count == 1:
        return f"{count} {word}"
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return f"{count} {word[:-1]}ies"
    return f"{count} {word}s"
