# ADR 0007: Admin review with least privilege and a change log

## Status

Accepted (2026-11-25)

## Context

Once a client approves their stories (ADR 0006), our team reviews them
before anything goes to GitHub (A3, A4): list projects by status and client,
then edit, merge, split or reject stories, with every change recorded with
who made it and when. The team must not be able to change a project at any
other stage, and clients must never reach these endpoints.

Clerk session tokens only carry a user ID, so admins had no way to tell
clients apart.

## Decision

- **Role in our own database.** `User.role` is the source of truth for who
  is an admin. It is set with `python manage.py set_role <email> admin` and
  checked by the `IsAdminRole` permission on every admin endpoint. Nothing
  the browser sends can change it; the frontend only hides links.
- **Separate endpoints** under `/api/admin/projects/` (`projects/admin_api.py`),
  so client code and team code never share a queryset by accident.
- **Least privilege.** Admins see the *masked* transcripts and answers, the
  same text the AI sees, never the raw recordings' text. They need the
  requirements, not the client's personal details.
- **Change log.** Every edit, rejection, merge and split writes a
  `StoryChange` row: action, admin, time, the stories before and after, and
  the reason for a rejection. The app never edits or deletes these rows, and
  Django Admin shows them read-only.
- **Stage check.** Story changes are only allowed while the project is
  `awaiting_admin`; anything else gets 409.
- **Profiles from Clerk.** On a user's first request we fetch their name and
  email from Clerk's API once (`accounts/clerk_profile.py`). A failure is
  logged and retried later; it never blocks sign-in. Tests never call Clerk.

## Consequences

**Positive**

- Every change to approved requirements can be traced to a person and a
  time, and the original wording is kept even when a story is removed.
- A client account can't see or change other clients' work through the admin
  endpoints; tests prove they get 403 everywhere.

**Negative**

- Making the first admin needs `set_role` run against the production
  database from a local machine (Render's free plan has no shell).
- Sign-up is still open to anyone. Invite-only sign-up (A1) is a Clerk
  dashboard setting ("Restricted" mode), to switch on before real clients.
- Profiles are copied once, so a client who changes their name in Clerk
  keeps the old one here until a sync is added.
