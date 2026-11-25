"""Copy a user's name and email from Clerk into Django (A1, A3).

Session tokens only carry the Clerk user ID, so admins couldn't tell clients
apart. The first time we see a user we fetch their profile from Clerk's API
once. A failure is logged and retried on a later request; it never blocks
sign-in.
"""

import logging

from clerk_backend_api import Clerk
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

CLERK_TIMEOUT_MS = 5000


def fetch_clerk_user(clerk_id: str):
    with Clerk(bearer_auth=settings.CLERK_SECRET_KEY, timeout_ms=CLERK_TIMEOUT_MS) as clerk:
        return clerk.users.get(user_id=clerk_id)


def primary_email(clerk_user) -> str:
    for address in clerk_user.email_addresses or []:
        if address.id == clerk_user.primary_email_address_id:
            return address.email_address
    return ""


def sync_profile(user) -> None:
    """Fill in the user's email and name from Clerk, if not done yet."""
    if user.clerk_synced_at is not None or not user.clerk_id:
        return
    try:
        clerk_user = fetch_clerk_user(user.clerk_id)
    except Exception as exc:  # noqa: BLE001
        # Never block sign-in because Clerk's API is slow or down.
        logger.warning("Could not fetch Clerk profile: %s", type(exc).__name__)
        return

    user.email = primary_email(clerk_user)
    user.first_name = (clerk_user.first_name or "")[:150]
    user.last_name = (clerk_user.last_name or "")[:150]
    user.clerk_synced_at = timezone.now()
    user.save(update_fields=["email", "first_name", "last_name", "clerk_synced_at"])
