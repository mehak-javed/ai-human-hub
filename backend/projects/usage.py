"""Count AI calls against the free limits (A7, N1).

`record_ai_call` is called after every successful provider response. It must
never break an AI request, so any failure here is only logged.
"""

import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def _int_header(headers, name):
    try:
        return int(headers.get(name))
    except (TypeError, ValueError):
        return None


def record_ai_call(provider: str, feature: str, *, neurons=None, headers=None) -> None:
    from .models import AIUsage  # imported here: models import modules that use this one

    try:
        row, _ = AIUsage.objects.get_or_create(
            day=timezone.now().date(), provider=provider, feature=feature
        )
        changes = {"calls": F("calls") + 1, "updated_at": timezone.now()}
        if isinstance(neurons, (int, float)):
            changes["neurons"] = F("neurons") + neurons
        if headers is not None:
            limit = _int_header(headers, "x-ratelimit-limit-requests")
            remaining = _int_header(headers, "x-ratelimit-remaining-requests")
            if limit is not None:
                changes["request_limit"] = limit
            if remaining is not None:
                changes["requests_remaining"] = remaining
        # One UPDATE with F() expressions, so parallel requests can't lose counts.
        AIUsage.objects.filter(pk=row.pk).update(**changes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not record AI usage: %s", type(exc).__name__)
