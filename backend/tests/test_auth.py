"""Tests for Clerk token authentication and the /api/me/ endpoint.

We never call Clerk in tests: `verify_token` is replaced with a fake so the
tests are fast, offline and deterministic.
"""

import pytest
from clerk_backend_api.security import TokenVerificationError, TokenVerificationErrorReason
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

VALID_CLAIMS = {"sub": "user_test123", "azp": "http://localhost:3000"}


@pytest.fixture
def accept_token(monkeypatch):
    """Make every token verify successfully and return VALID_CLAIMS."""
    calls = []

    def fake_verify_token(token, options):
        calls.append((token, options))
        return VALID_CLAIMS

    monkeypatch.setattr("accounts.authentication.verify_token", fake_verify_token)
    return calls


@pytest.fixture
def reject_token(monkeypatch):
    """Make every token fail verification, like an expired or forged token."""

    def fake_verify_token(token, options):
        raise TokenVerificationError(TokenVerificationErrorReason.TOKEN_INVALID)

    monkeypatch.setattr("accounts.authentication.verify_token", fake_verify_token)


def get_me(token=None, scheme="Bearer"):
    client = APIClient()
    if token is not None:
        client.credentials(HTTP_AUTHORIZATION=f"{scheme} {token}")
    return client.get(reverse("me"))


@pytest.mark.django_db
def test_me_without_token_returns_401():
    response = get_me()

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
def test_me_with_invalid_token_returns_401(reject_token):
    response = get_me("forged-token")

    assert response.status_code == 401


@pytest.mark.django_db
def test_me_with_other_auth_scheme_returns_401(accept_token):
    response = get_me("dXNlcjpwYXNz", scheme="Basic")

    assert response.status_code == 401
    assert accept_token == []


@pytest.mark.django_db
def test_me_with_valid_token_returns_the_user(accept_token):
    response = get_me("valid-token")

    assert response.status_code == 200
    assert response.json()["clerk_id"] == "user_test123"
    assert response.json()["role"] == "client"


@pytest.mark.django_db
def test_token_is_checked_against_our_frontend_origin(accept_token):
    get_me("valid-token")

    token, options = accept_token[0]
    assert token == "valid-token"
    assert options.authorized_parties == ["http://localhost:3000"]


@pytest.mark.django_db
def test_first_sign_in_creates_user_only_once(accept_token):
    get_me("valid-token")
    get_me("valid-token")

    assert User.objects.filter(clerk_id="user_test123").count() == 1


@pytest.mark.django_db
def test_disabled_user_is_rejected(accept_token):
    User.objects.create(username="user_test123", clerk_id="user_test123", is_active=False)

    response = get_me("valid-token")

    assert response.status_code == 401