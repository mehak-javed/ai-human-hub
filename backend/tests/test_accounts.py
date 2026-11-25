"""Tests for copying profiles from Clerk and for giving users a role (A1, A3).

Clerk's API is never called: `fetch_clerk_user` is replaced with a fake.
"""

import logging
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.urls import reverse
from rest_framework.test import APIClient

from accounts import clerk_profile
from accounts.clerk_profile import sync_profile

User = get_user_model()


def clerk_user(email="sam@bakery.com", first="Sam", last="Lee"):
    return SimpleNamespace(
        primary_email_address_id="email_1",
        email_addresses=[
            SimpleNamespace(id="email_0", email_address="old@example.com"),
            SimpleNamespace(id="email_1", email_address=email),
        ],
        first_name=first,
        last_name=last,
    )


@pytest.fixture
def fake_clerk(monkeypatch):
    calls = []

    def fake(clerk_id):
        calls.append(clerk_id)
        return clerk_user()

    monkeypatch.setattr(clerk_profile, "fetch_clerk_user", fake)
    return calls


@pytest.mark.django_db
def test_profile_is_copied_from_clerk_once(fake_clerk):
    user = User.objects.create(username="user_sam", clerk_id="user_sam")

    sync_profile(user)
    sync_profile(user)

    user.refresh_from_db()
    assert (user.email, user.first_name, user.last_name) == ("sam@bakery.com", "Sam", "Lee")
    assert user.display_name == "Sam Lee"
    assert user.clerk_synced_at is not None
    assert fake_clerk == ["user_sam"]


@pytest.mark.django_db
def test_clerk_failure_is_logged_and_retried_later(caplog):
    # The autouse fixture in conftest.py makes every Clerk call fail.
    user = User.objects.create(username="user_sam", clerk_id="user_sam")

    with caplog.at_level(logging.WARNING, logger="accounts.clerk_profile"):
        sync_profile(user)

    user.refresh_from_db()
    assert user.clerk_synced_at is None
    assert "Could not fetch Clerk profile: RuntimeError" in caplog.text


@pytest.mark.django_db
def test_signing_in_fills_in_the_profile(fake_clerk, monkeypatch):
    monkeypatch.setattr("accounts.authentication.verify_token", lambda token, options: {"sub": "user_sam"})
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer valid-token")

    response = client.get(reverse("me"))

    assert response.status_code == 200
    assert response.json()["email"] == "sam@bakery.com"
    assert response.json()["name"] == "Sam Lee"


@pytest.mark.django_db
def test_set_role_by_email_or_clerk_id():
    user = User.objects.create(username="user_sam", clerk_id="user_sam", email="Sam@Bakery.com")

    call_command("set_role", "sam@bakery.com", "admin")
    user.refresh_from_db()
    assert user.role == User.Role.ADMIN

    call_command("set_role", "user_sam", "client")
    user.refresh_from_db()
    assert user.role == User.Role.CLIENT


@pytest.mark.django_db
def test_set_role_needs_an_existing_user():
    with pytest.raises(CommandError, match="must sign in once"):
        call_command("set_role", "nobody@example.com", "admin")
