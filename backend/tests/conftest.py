"""Shared test settings.

No test may call Clerk's API. Profile syncing is replaced with a fake that
fails, so signing in still works and nothing is fetched; test_admin_api.py
swaps in its own fake to test the sync itself.
"""

import pytest


@pytest.fixture(autouse=True)
def no_clerk_api(monkeypatch):
    def offline(clerk_id):
        raise RuntimeError("Clerk's API is not called in tests")

    monkeypatch.setattr("accounts.clerk_profile.fetch_clerk_user", offline)
