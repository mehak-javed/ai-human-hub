# ADR 0003: Authentication with Clerk, verified by the Django API

## Status

Accepted (2026-11-23)

## Context

Clients sign in with email or Google (C1); admins invite clients (A1); every
API request must be checked for identity, role and ownership (P2). Building
password storage, social login, email verification and session handling
ourselves would be slow and risky.

## Decision

- Use Clerk for sign-up and sign-in (email and Google) in the Next.js app.
- The browser sends Clerk's short-lived session token as
  `Authorization: Bearer <token>` to the Django API.
- Django verifies every token itself with `clerk-backend-api`: signature,
  expiry, and that it was issued to one of our frontend origins
  (authorized parties). Invalid or missing tokens get 401.
- On first sign-in Django creates a matching user with the Client role,
  using a custom user model (`accounts.User`) with `clerk_id` and `role`.
- Pages are protected on the server, inside the page, with `auth()`; the API
  never trusts the frontend's check.
- Tests replace Clerk's `verify_token` with a fake, so they run offline.

## Alternatives considered

- **Django's own auth (sessions, django-allauth)**: no external dependency,
  but much more to build and secure for social login and a separate frontend.
- **Auth0 / Firebase Auth**: similar model; Clerk has a generous free tier
  (N1) and first-class Next.js components.

## Consequences

**Positive**

- No passwords stored in our database.
- Security checks happen in one place on the API, for every request.
- Disabling a user in Django Admin blocks them immediately.

**Negative**

- Dependency on Clerk's availability and pricing.
- Verifying tokens with the secret key may fetch Clerk's public keys over the
  network; using the static JWT public key (`jwt_key`) would avoid this.
- The user's email is not yet copied into Django; add it if admins need it.