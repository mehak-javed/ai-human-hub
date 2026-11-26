"""Shared test settings.

No test may call Clerk's or GitHub's real API. Profile syncing is replaced
with a fake that fails, so signing in still works and nothing is fetched;
test_admin_api.py swaps in its own fake to test the sync itself. GitHub calls
go to a transport that refuses every request, unless a test uses the
fake_github fixture from test_github.py.
"""

import httpx
import pytest


@pytest.fixture(autouse=True)
def no_clerk_api(monkeypatch):
    def offline(clerk_id):
        raise RuntimeError("Clerk's API is not called in tests")

    monkeypatch.setattr("accounts.clerk_profile.fetch_clerk_user", offline)


@pytest.fixture(autouse=True)
def no_real_github(monkeypatch):
    from projects import delivery, github, progress

    def refuse(request):
        raise httpx.ConnectError("GitHub's real API is not called in tests", request=request)

    monkeypatch.setattr(
        github, "make_http_client", lambda: httpx.Client(base_url=github.API, transport=httpx.MockTransport(refuse))
    )
    # Looked up when called, so a test's fake_github client is used instead.
    monkeypatch.setattr(delivery, "make_http_client", lambda: github.make_http_client())
    monkeypatch.setattr(progress, "make_http_client", lambda: github.make_http_client())
    monkeypatch.setattr(github.time, "sleep", lambda seconds: None)
