# ADR 0008: Deliver stories through a GitHub App, safe to retry

## Status

Accepted (2026-11-25)

## Context

After our team's review (ADR 0007), approved stories must land in the
client's private repository as issues, with a requirements file (A5, A6, G1,
G2). A push can fail halfway (GitHub down, rate limits, an expired token),
and re-sending must never create duplicate issues (G5, G6).

## Decision

- **A GitHub App, not a personal token.** The App is installed only on the
  repositories we're given. For every push we sign a 9-minute JWT with the
  App's private key and exchange it for an installation token limited to
  that **one** repository and to `issues: write`, `contents: write` and
  `metadata: read`. Tokens are never stored and expire within an hour.
- **Private repositories only.** Connecting checks the repository through
  the API and refuses public ones, and the check runs again on every push.
- **Idempotent pushes.** Each story stores its issue number the moment the
  issue is created. A retry updates those issues and creates only the
  missing ones; an issue deleted on GitHub is created again.
  `requirements.md` is replaced in place using the file's current SHA.
- **Retries and a record.** 429 and 5xx responses and network errors are
  retried twice with a short back-off. Every attempt is stored as a
  `GitHubPush` (who, when, counts, commit link, and a clear error message
  without tokens). Only a fully successful push moves the project to
  `sent_to_github`; a failed one leaves it in review for another try.
- **Synchronous for now.** A push runs inside the request (about half a
  second per story, well within gunicorn's 120 seconds for 30 stories).
- **What goes to GitHub:** the reviewed stories and, for the data model,
  the client's *masked* answers about the information the system keeps.

## Consequences

**Positive**

- A leaked token is useless within an hour and can only touch one repo.
- An admin can press Send again after any failure without cleaning up.

**Negative**

- Setting up the App is a manual, one-off step (docs/github-app-setup.md).
- A very large project could approach the request timeout; move pushes to a
  background job (and N3's queue) if projects grow past ~100 stories.
- Story edits made directly on GitHub are overwritten by a re-send, by
  design: the app is the source of truth until the project is sent.
