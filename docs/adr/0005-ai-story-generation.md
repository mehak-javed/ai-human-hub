# ADR 0005: Generate user stories with validated JSON and a backup provider

## Status

Accepted (2026-11-25)

## Context

AI4 needs the interview turned into user stories ("As a [role], I want to
[goal], so that [reason]") with acceptance criteria and a priority. AI
models sometimes return broken or badly shaped JSON, hit daily limits, or
go down. The stories feed a human review (C8) and, later, GitHub issues, so
bad output must never be saved. Only masked text may be sent (AI2), and
the whole flow must stay on free tiers (N1).

In November 2026 Groq no longer offered Llama 3.3; its current
general-purpose models are OpenAI's open-weight gpt-oss models.

## Decision

- **Primary: Cloudflare Workers AI, `@cf/meta/llama-3.3-70b-instruct-fp8-fast`**
  with JSON-schema mode. A typical interview costs about 40–100 neurons of the
  10,000 free each day.
- **Backup: Groq, `openai/gpt-oss-120b`** with strict structured outputs.
- **Our own validation on every answer** (Pydantic `StoryList`): required
  fields, allowed priorities, length limits, 1–8 criteria, 1–30 stories.
  Provider-side JSON modes help, but they are never trusted on their own.
- **Retry rules:** an invalid answer is retried once with the same provider.
  An HTTP error, timeout or bad configuration goes straight to the next
  provider, because retrying an outage or a limit wastes time.
- **Prompt-injection guard:** the transcript is wrapped in `<transcript>`
  tags, and the system prompt says it is data, not instructions. The output
  schema also limits what an injected instruction could produce.
- New stories replace old drafts in one database transaction, only while
  the project is still in the interview stage.

## Consequences

**Positive**

- Invalid AI output can't reach the database or the client.
- No single provider outage or limit stops clients (AI6). Every switch is
  logged without client content.
- Providers, retries and the fallback live in one module (`projects/llm.py`),
  shared by stories and follow-up questions, so models can be swapped with a
  one-line change.

**Negative**

- The two providers use different models, so wording varies with whichever
  one answered. The client reviews and edits every story anyway (C8).
- Up to four calls (two per provider) must fit in gunicorn's 120-second
  timeout, so each call is limited to 25 seconds.
- Rewriting stories replaces earlier drafts. Once clients can edit stories
  (C8), rewriting will need a confirmation step.