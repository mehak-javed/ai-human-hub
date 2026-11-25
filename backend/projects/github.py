"""Deliver approved stories to a client's private GitHub repo (A5, A6, G1, G2).

We act as a GitHub App, never as a person:

1. Sign a short-lived JWT with the App's private key.
2. Exchange it for an installation token limited to the one repository and
   to the permissions we need (issues and contents). Tokens last an hour and
   are fetched fresh for every push, so an expired token can't break one.
3. Call the REST API with that token.

Pushing is safe to repeat (G5, G6): each story remembers its issue number as
soon as the issue exists, so a retry after a failure updates those issues
instead of creating duplicates.
"""

import base64
import logging
import re
import time
from dataclasses import dataclass

import httpx
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

API = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT_SECONDS = 15
# Transient failures (GitHub down, rate limited) are retried this many times.
RETRIES = 2
RETRY_DELAY_SECONDS = 1.0
# GitHub asks integrations to pause between requests that create content.
PAUSE_BETWEEN_WRITES_SECONDS = 0.5
REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
REQUIREMENTS_PATH = "requirements.md"
# The permissions we ask for in every installation token, and no more.
TOKEN_PERMISSIONS = {"issues": "write", "contents": "write", "metadata": "read"}


class GitHubError(Exception):
    """Something went wrong; the message is safe to show to an admin."""


@dataclass(frozen=True)
class Repo:
    full_name: str
    default_branch: str
    html_url: str


def is_configured() -> bool:
    return bool(settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY)


def install_url() -> str:
    slug = settings.GITHUB_APP_SLUG
    return f"https://github.com/apps/{slug}/installations/new" if slug else ""


def private_key() -> str:
    """The App's PEM key. Hosting dashboards may store it base64-encoded."""
    key = settings.GITHUB_APP_PRIVATE_KEY.strip()
    if key.startswith("-----BEGIN"):
        return key.replace("\\n", "\n")
    return base64.b64decode(key).decode()


def app_jwt() -> str:
    now = int(time.time())
    # Backdated a minute for clock drift; GitHub allows at most 10 minutes.
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": str(settings.GITHUB_APP_ID)}
    return jwt.encode(payload, private_key(), algorithm="RS256")


def make_http_client() -> httpx.Client:
    """Replaced in tests with a client that never reaches GitHub."""
    return httpx.Client(base_url=API, timeout=TIMEOUT_SECONDS)


def describe(response: httpx.Response) -> str:
    """A short, log-safe reason for a failed call: status code and GitHub's message."""
    try:
        message = response.json().get("message", "")
    except ValueError:
        message = ""
    return f"HTTP {response.status_code}" + (f": {message[:200]}" if message else "")


class GitHub:
    """A small GitHub REST client for one repository."""

    def __init__(self, http: httpx.Client, token: str = ""):
        self.http = http
        self.token = token

    def request(self, method: str, path: str, *, auth: str | None = None, **kwargs) -> httpx.Response:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "Authorization": f"Bearer {auth or self.token}",
        }
        for attempt in range(RETRIES + 1):
            try:
                response = self.http.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                if attempt == RETRIES:
                    raise GitHubError("GitHub can't be reached right now. Please try again.") from exc
            else:
                # Retry only what may succeed a moment later (G6).
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                    return response
            logger.warning("GitHub %s %s failed, retrying (attempt %d)", method, path, attempt + 1)
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
        raise AssertionError("unreachable")

    # --- Connecting (A6) -----------------------------------------------------

    def connect(self, full_name: str) -> Repo:
        """Get an installation token for one repo and check it is private."""
        if not REPO_PATTERN.match(full_name):
            raise GitHubError("Enter the repository as owner/name, for example acme/bakery-website.")
        app_token = app_jwt()

        found = self.request("GET", f"/repos/{full_name}/installation", auth=app_token)
        if found.status_code == 404:
            raise GitHubError(
                "Our GitHub App isn't installed on that repository, or it doesn't exist. "
                "Install the App on the repository first."
            )
        if found.status_code != 200:
            raise GitHubError(f"GitHub refused the connection ({describe(found)}).")

        installation_id = found.json()["id"]
        repo_name = full_name.split("/", 1)[1]
        token = self.request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            auth=app_token,
            json={"repositories": [repo_name], "permissions": TOKEN_PERMISSIONS},
        )
        if token.status_code != 201:
            raise GitHubError(
                "The GitHub App doesn't have the permissions it needs (issues and contents: "
                f"read and write) ({describe(token)})."
            )
        self.token = token.json()["token"]

        repo = self.request("GET", f"/repos/{full_name}")
        if repo.status_code != 200:
            raise GitHubError(f"Couldn't read the repository ({describe(repo)}).")
        data = repo.json()
        # Client requirements must never land in a public repository (A6).
        if not data.get("private"):
            raise GitHubError("That repository is public. Stories can only be sent to a private repository.")
        return Repo(full_name=data["full_name"], default_branch=data["default_branch"], html_url=data["html_url"])

    # --- Delivering (G1, G2) ---------------------------------------------------

    def ensure_labels(self, repo: Repo, labels: dict[str, str]) -> None:
        """Create the labels we use, if the repo doesn't have them yet."""
        for name, colour in labels.items():
            response = self.request("POST", f"/repos/{repo.full_name}/labels", json={"name": name, "color": colour})
            # 422 means the label already exists, which is fine.
            if response.status_code not in (201, 422):
                raise GitHubError(f"Couldn't create the label {name!r} ({describe(response)}).")

    def create_issue(self, repo: Repo, issue: dict) -> dict:
        response = self.request("POST", f"/repos/{repo.full_name}/issues", json=issue)
        if response.status_code != 201:
            raise GitHubError(f"Couldn't create an issue ({describe(response)}).")
        time.sleep(PAUSE_BETWEEN_WRITES_SECONDS)
        return response.json()

    def update_issue(self, repo: Repo, number: int, issue: dict) -> dict | None:
        """Update an issue we created before. Returns None if it was deleted."""
        response = self.request("PATCH", f"/repos/{repo.full_name}/issues/{number}", json=issue)
        if response.status_code in (404, 410):
            return None
        if response.status_code != 200:
            raise GitHubError(f"Couldn't update issue #{number} ({describe(response)}).")
        time.sleep(PAUSE_BETWEEN_WRITES_SECONDS)
        return response.json()

    def write_file(self, repo: Repo, path: str, content: str, message: str) -> str:
        """Create or replace a file on the default branch. Returns the commit URL."""
        url = f"/repos/{repo.full_name}/contents/{path}"
        existing = self.request("GET", url, params={"ref": repo.default_branch})
        body = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": repo.default_branch,
        }
        if existing.status_code == 200:
            body["sha"] = existing.json()["sha"]
        elif existing.status_code != 404:
            raise GitHubError(f"Couldn't read {path} ({describe(existing)}).")

        response = self.request("PUT", url, json=body)
        if response.status_code not in (200, 201):
            raise GitHubError(f"Couldn't commit {path} ({describe(response)}).")
        return response.json()["commit"]["html_url"]
