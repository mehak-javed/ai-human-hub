# ADR 0001: Monorepo with a Django + DRF backend and a Next.js frontend

## Status

Accepted (2026-11-19)

## Context

The system needs:

- a REST API for client-facing pages (projects, recordings, stories, approvals);
- an admin interface for reviewing, editing, merging and rejecting stories,
  with an audit trail;
- user roles (client, admin) and per-project access control;
- database models with migrations;
- a fast, mobile-friendly client interface for recording and approving.

Constraints: one developer, limited time, and the whole system must run on
free tiers. The slowest operations are transcription and LLM calls, which take
seconds, so raw framework speed is not the bottleneck.

## Decision

1. **Backend: Django + Django REST Framework.** Django provides the admin
   panel, ORM, migrations and authentication out of the box. Django Admin
   covers interview management, story editing and the audit log with little
   custom code. DRF provides serializers for validation and permission classes
   for role- and owner-based access control.
2. **Frontend: Next.js (React + TypeScript)**, deployed separately on
   Cloudflare Pages and calling the Django API. Client pages stay fast and
   always available, even when the free backend host is asleep.
3. **Monorepo**: backend, frontend and docs live in one repository, so a
   single pull request can change an API endpoint and the UI that uses it,
   with one CI configuration.

## Alternatives considered

- **FastAPI**: excellent for lightweight, high-throughput async APIs, but it
  would mean building the admin panel, migrations setup and auth ourselves.
  It may suit a future standalone transcription service.
- **Django templates only (no separate frontend)**: simpler, but gives a less
  responsive recording and approval experience on mobile, and ties the
  client pages to the backend's uptime.
- **Separate repositories**: better for independent teams; unnecessary
  overhead for a single developer.

## Consequences

**Positive**

- Admin use cases are largely covered by Django Admin, so effort goes into
  the AI pipeline and privacy controls.
- Clear separation between the API and the client UI.
- One place for code, docs, issues and CI.

**Negative**

- Two languages and toolchains (Python and TypeScript) to maintain.
- Django is synchronous by default; long AI calls must not block requests
  (to be addressed with background jobs if needed).
- CI needs path filters so frontend changes do not run backend tests and
  vice versa.
- Cross-origin requests (CORS) and token verification must be configured
  between the two apps.