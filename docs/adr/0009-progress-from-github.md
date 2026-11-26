# ADR 0009: Progress from GitHub issues, by webhook with a catch-up read

## Status

Accepted (2026-11-26)

## Context

Once a project is sent to GitHub (ADR 0008), the client wants to see how much
is built (C10), and the team wants the same number (G4). Our team works in
GitHub: a feature is built when its issue is closed. The number must update
within a minute.

Two facts shape the design:

- Our API runs on Render's free plan, which **sleeps when idle** and takes
  about 50 seconds to wake. GitHub waits 10 seconds for a webhook reply and
  **doesn't resend** a delivery that timed out. Webhooks alone would lose
  events.
- The webhook URL is public. Anyone could post a fake "issue closed".

## Decision

- **A story is done while its issue is closed.** `UserStory.github_issue_closed`
  holds it; progress is "closed issues of this project / issues sent".
- **Webhook first.** The GitHub App subscribes to *Issues* events and posts
  them to `POST /api/github/webhook/`. A delivery is trusted only if its
  `X-Hub-Signature-256` matches HMAC-SHA256 of the body with
  `GITHUB_WEBHOOK_SECRET`, compared in constant time. No secret set → 503;
  bad signature → 401; other events → 204.
- **The issue's state, not the action, is applied**, and only rows that differ
  are updated. Repeated or replayed deliveries change nothing.
- **Catch-up read.** Whenever a delivered project is opened (client or team)
  and its states are over a minute old, we list the repo's closed issues with
  our `from: ai-human-hub` label and set every story's state from that.
  GitHub is the source of truth, so this also corrects any lost or
  out-of-order webhook. A conditional update on `github_synced_at` claims the
  refresh, so two pages opened together call GitHub once. If GitHub is down,
  the last known progress is shown.

## Consequences

- Progress is never more than a minute old while someone is looking at it,
  even if every webhook is lost; with webhooks it's near-instant.
- Opening a delivered project costs up to four GitHub calls once a minute,
  far inside the App's limit of 5,000 an hour.
- No background worker is needed, which keeps us on free plans (N1).
- One more secret to manage (P6): it lives only in the App's settings and in
  Render's environment.
- Pull requests are ignored; issues deleted on GitHub keep their last state.
