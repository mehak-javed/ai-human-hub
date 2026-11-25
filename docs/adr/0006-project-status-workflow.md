# ADR 0006: A one-way status workflow for each project

## Status

Accepted (2026-11-25)

## Context

C8 and C9 let the client edit, remove and add stories, ask the AI to rewrite
them with a note, and finally approve them so they lock and go to the admin.
Until now the client could press "Write my stories" again at any time, which
would have thrown away their edits (noted as a risk in ADR 0005), and nothing
stopped recordings or answers changing after the stories were written.

## Decision

Each project moves one way through four statuses. The server checks the
status on every request that changes something, and refuses with 409
Conflict when the action doesn't belong to the current stage.

| Status | The client can | Moves on when |
|---|---|---|
| `interviewing` | record, answer follow-up questions | the AI writes the stories |
| `awaiting_client` | edit, remove and add stories, ask the AI to rewrite them with a note | the client approves |
| `awaiting_admin` | only read (stories are locked) | the admin sends them to GitHub (step 7) |
| `sent_to_github` | only read | (end) |

- A rewrite sends the AI the **current** stories, including the client's own
  edits, plus their note, so nothing the client changed is silently lost.
- Client edits and notes are masked before any AI call, like transcripts (AI2).
- Each story records whether the client added it or changed the AI's
  version, for measuring AI quality later (AI7).
- Approving is only possible with at least one story, and asks the client to
  confirm in the UI.

## Consequences

**Positive**

- Simple to reason about and test: every action has one stage where it's
  allowed, and a test proves it is refused everywhere else.
- Approved requirements can't change underneath the admin.

**Negative**

- A client who forgot something after the AI wrote the stories can't record
  again; they add a story or ask for a rewrite instead. Reopening an
  interview could be added later as an explicit admin action.
- Removed stories are deleted, not kept, so AI7 can count edits and
  additions but not removals yet.
