# ADR 0004: Host the API on Render and the frontend on Vercel

## Status

Accepted (2026-11-23)

## Context

The use-case document planned the Next.js client on Cloudflare Pages. The
frontend uses Next.js 16 with `cacheComponents` and Clerk's `proxy.ts`
(middleware) for server-side sign-in checks.

Before deploying, the frontend was built with Cloudflare's OpenNext adapter
(@opennextjs/cloudflare 1.20) and run locally in the Workers runtime:

- With `cacheComponents` on, every page hung and returned 500. The adapter
  warns that Cache Components are not fully supported yet.
- With it off, pages rendered, but Node middleware (`proxy.ts`) is marked
  experimental and "not officially maintained".
- Cloudflare Pages is now only recommended for static Next.js exports.

## Decision

- **Frontend: Vercel (Hobby plan)**, which supports every Next.js 16 feature
  we use with no code changes. Root directory `frontend`.
- **Backend: Render free web service**, defined in `render.yaml`: gunicorn,
  WhiteNoise for admin static files, migrations in the build step, health
  check on `/api/health/`, HTTPS hardening via `DJANGO_HTTPS_ONLY`.
- **Database: Neon `production` branch.**
- CI runs `manage.py check --deploy` with production security settings.

## Consequences

**Positive**

- No experimental adapters in the sign-in path.
- Both platforms deploy automatically from `main`; Vercel also builds a
  preview for every pull request.
- Server configuration is versioned in `render.yaml`.

**Negative**

- Differs from the original plan; revisit Cloudflare when OpenNext fully
  supports Cache Components and Node middleware.
- Render's free service sleeps after 15 minutes idle; the first request
  then takes about a minute (N5). Move to a paid instance before real clients.
- The free plan has no shell, so admin users are created from a local
  machine against the production database.
- Vercel preview URLs are not in the API's CORS allow-list, so previews can
  show pages but not call the API.
- Clerk still uses its development instance (test keys) until the project
  has its own domain.