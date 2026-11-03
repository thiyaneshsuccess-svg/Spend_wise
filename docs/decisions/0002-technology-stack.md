# ADR 0002 — Technology stack and security posture

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The stack must (a) support real statistical work, (b) stay learnable for a single undergraduate
developer, (c) run locally on Windows with no Docker and no Postgres install, and (d) remain
deployable later without a rewrite.

Two coherent candidates were on the table:

**A. TypeScript everywhere** — Next.js on Workers with D1, one language, one deploy target, instantly
hostable. Rejected as the primary path: the project's substance is numerical modelling and it would
be written in a language with no scientific-computing ecosystem, while the author's learning goals
and target roles are Python/AI/data.

**B. Python service + TypeScript SPA** — chosen.

## Decision

### Backend: Python 3.13 + FastAPI

- **FastAPI** over Flask/Django: Pydantic v2 gives request/response validation that doubles as living
  API documentation, dependency injection keeps auth/session handling testable, and async is
  available where it matters (none of the analytics is I/O-bound, which is fine — sync handlers are
  simpler and honest here).
- **SQLAlchemy 2.0 (typed, `Mapped[...]`) + Alembic.** Migrations from the first table, not bolted on
  later. SQLite for local/demo, Postgres for hosted, with no dialect-specific SQL in the domain.
- **NumPy for the forecast.** Path simulation is a `(paths × days)` matrix operation. Vectorising it
  is the difference between 40 ms and 4 s — that difference is a deliberate teaching point.
- **No pandas in the request path.** pandas is excellent for exploration and for the offline demo-data
  generator, but pulling it into the API adds ~100 MB of cold-start weight for operations that are
  `sum`, `median`, and array math. Deliberate constraint: `analytics/` depends on NumPy only.
- **Dependency policy:** every new dependency needs a one-line justification in its PR. Standard
  library first.

### Frontend: React + TypeScript + Vite

- **Vite SPA, not Next.js.** The backend already owns rendering data and routing; SSR would add a
  second build system and a second deploy target for no benefit. Build output is static files served
  by FastAPI, keeping auth same-origin and cookies simple.
- **TanStack Query** for server state, URL search params for filters. No global state library until a
  concrete case appears — most "app state" here is really cache state.
- **Tailwind + a small local component set** instead of a heavyweight UI kit, so the visual identity
  is designed rather than inherited. Charts: Recharts for standard views, hand-built SVG for the
  forecast fan chart where the range-band rendering is the signature visual.
- **Typed API client** generated from the OpenAPI schema, so a backend field rename becomes a
  TypeScript compile error rather than a production `undefined`.

### Money and time
- Money is `int` **minor units** (paise/cents) everywhere: DB, API, engine. Formatting to a decimal
  string happens only at the render boundary. No `float` may hold a currency value.
- Dates are `date` for posting, `timestamptz`/UTC for audit fields. Timezone is a user setting, used
  for "today" and period boundaries.

### Auth: self-hosted opaque sessions

Session ID in an `httpOnly`, `SameSite=Lax`, `Secure` (in prod) cookie; only a SHA-256 hash of the
token is stored server-side; passwords hashed with **argon2id**. Mutations additionally verify the
request `Origin`.

Rejected: JWT in `localStorage` — unrevocable, exposed to any XSS, and typically paired with sloppy
client-side role checks. Session-in-cookie is fewer moving parts and *more* secure for a same-origin
app. Rejected: a managed identity vendor — it would outsource the one security surface worth
understanding, and adds a config dependency for a local-first product.

**Data isolation rule:** every table carrying user data has `user_id`, and every query is scoped by
`user.sub`-equivalent server-side identity. Client-supplied IDs are treated as untrusted selectors,
never as authority. This is enforced in a repository layer, not remembered per-endpoint.

### Testing and CI
- `pytest` for domain/analytics (pure, fast, no fixtures needed) and API integration tests against
  in-memory SQLite.
- `ruff` (lint + format) and `mypy` on `domain/`, `analytics/`, `services/`.
- `vitest` for pure frontend utilities; no snapshot-testing the whole UI.
- GitHub Actions: lint → typecheck → test, on every push. Nothing merges red.
- **Playwright** deferred to M7; it is worth its cost only once flows are stable.

## Consequences

- Two languages is a real cost: two toolchains, two CI jobs, no shared types without codegen. Offset
  by generating the client from OpenAPI.
- Hosting needs a container host with persistent storage for SQLite (or a managed Postgres for a
  multi-user demo). Provider selection is deferred to M7 and will be evaluated then, on free-tier
  terms and region latency — not guessed now. This is why the app is built to run locally first.
- Python 3.13 on the author's machine is available via the `py -3` launcher only; local setup
  instructions must account for that.
