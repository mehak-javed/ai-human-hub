# ADR 0011: An append-only audit log that holds no client words

## Status

Accepted (2026-11-27)

## Context

The team must be able to see everything that happened to a project: every
AI output, edit, approval and GitHub push, filterable by project, and
read-only (A8). Parts of this already existed in different places
(StoryChange for team edits, GitHubPush, DeletionRecord), but client edits,
AI outputs and approvals left no trace beyond a timestamp.

## Decision

- **One `AuditEvent` table**, written next to each action: project, actor
  (client, team, AI, GitHub), the person if there was one, an action from a
  fixed list, a short detail and the time.
- **The detail never contains what the client said**: only counts, story
  IDs, AI providers, repo names and seconds of audio. So the log needs no
  masking, holds no personal data, and is safe to show the whole team. The
  content itself stays where it already is, behind the same access rules.
- **Writing never breaks the action.** Each write runs in its own savepoint
  and a failure is logged, not raised.
- **Read-only everywhere.** The API is GET only (`/api/admin/audit/`, team
  role); Django Admin has no add, change or delete.
- **Deletions.** Deleting a project deletes its events (the client asked us
  to remove their data, C11). The `DeletionRecord` stays and is shown in the
  log as "Project deleted", with no name.
- **History.** A data migration rebuilt events for existing projects from the
  records we had, at their real times, each marked "(from earlier records)".
- **Paging** is by time (`?before=`), 50 entries a page, newest first.

## Consequences

- Answers "who did what, when" for any project in one place.
- Two copies of team edits: StoryChange keeps the before/after content for
  the review page; the audit event keeps the fact.
- Entries with exactly the same timestamp could straddle a page boundary;
  with microsecond times this is very unlikely.
- Migration 0015 corrected our own wording slip ("storys") in entries
  written before the fix. That is the only time entries were touched, and
  only the app's formatting changed: no event was added, removed or moved.
