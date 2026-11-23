# ADR 0002: PostgreSQL on Neon, configured through DATABASE_URL

## Status

Accepted (2026-11-23)

## Context

The starter SQLite database behaves differently from PostgreSQL (types,
concurrency, constraints), so bugs could appear only in production. The
system must also stay within free tiers (N1).

## Decision

- Use PostgreSQL 17 in every environment.
- Host it on Neon's free tier. The Neon `main` branch is reserved for
  production; local development uses a separate `dev` branch.
- CI runs against a throwaway PostgreSQL 17 service container.
- Django reads a single `DATABASE_URL` variable (parsed by dj-database-url)
  and refuses to start without it.
- Connections are reused (`conn_max_age=600`) with health checks, because
  Neon suspends idle compute and drops connections.

## Alternatives considered

- **SQLite in development, Postgres in production**: simpler setup, but
  breaks dev/prod parity.
- **Local Postgres via Docker**: works offline, but adds a tool to install
  and maintain; can be added later.
- **Supabase or Render Postgres**: also viable; Neon was chosen for its
  database branching and generous free compute.

## Consequences

**Positive**

- Same database engine and version in development, CI and production.
- Neon branches give isolated databases for development without touching
  production data.
- Switching provider only means changing `DATABASE_URL`.

**Negative**

- Local development needs an internet connection.
- The first query after Neon has been idle is slower (cold start).
- The free tier caps storage at 1 GB and compute hours per month (N1).