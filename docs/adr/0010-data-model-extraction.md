# ADR 0010: The AI extracts a data model; the client confirms it by approving

## Status

Accepted (2026-11-26)

## Context

Developers need to know what the system stores, not only what it does
(AI5, C6). Clients describe their data loosely ("we keep the cake, the
time and a phone number"), mostly in answers to the "data" follow-up
question. Until now requirements.md only quoted those answers.

## Decision

- **A separate AI call**, `POST /api/projects/<id>/data-model/`, after the
  stories are written. It reads the masked transcripts, the masked answers
  and the stories. Chaining it onto story writing would risk the request
  timeout (two calls with retries and fallback can exceed 120 seconds), so
  the client's page starts it as soon as the stories appear.
- **A strict schema, checked twice.** Providers get a JSON schema; our
  Pydantic model then requires 1–15 entities, 1–25 fields each, field types
  from a fixed list (text, money, date and time, choice…), unique names,
  and relationships that only connect listed entities. An invalid answer is
  retried, then the backup provider is tried (`llm.ask_for_json`).
- **Only during the client's review.** The client reads it as small tables
  and plain sentences ("Each Customer has many Order records."). If
  something is wrong they say so in words; the AI rewrites the current
  model following the masked note. There is no field-by-field editor:
  clients describe changes better than they edit schemas.
- **Approving the stories confirms the data model** in the same
  transaction (`confirmed_at = approved_at`). Then it's locked, shown to the
  team, and written into requirements.md as one table per entity plus the
  relationships, followed by the client's own data answers.

## Consequences

- requirements.md now gives developers tables they can turn into a schema,
  and the client has checked them.
- One more AI call per project (counted in AI usage as "Data model"),
  rate-limited with story writing.
- If stories are rewritten after the summary was made, the summary isn't
  rewritten automatically; the client can ask for an update.
- The team can read the data model but not edit it yet.
