# SpendWise

> **Know what your money is doing — and what it will do next.**

SpendWise is a local-first personal finance workbench. It ingests your transactions, builds a
model of your recurring financial life, and answers forward-looking questions with evidence you
can inspect: *How much can I safely spend today? When does my money run short before payday?
Which subscription quietly went up? What actually changed in my spending this month, and why?*

It is not a dashboard of pie charts. It is an **explainable analytics engine with a UI on top**.

---

## The problem

Expense trackers fail for two reasons that have nothing to do with UI polish:

1. **Logging is work, and the payoff is backwards-looking.** You spend effort recording the past
   and receive a chart that confirms it. No decision changes.
2. **The output is unverifiable.** Apps show "You spent 23% more on food" and you have no way to
   audit that claim without re-reading every row yourself. Numbers you can't check are numbers you
   stop trusting — and once you stop trusting it, you stop opening the app.

Meanwhile the questions people actually ask are predictive and situational: *Can I afford this
now? Will I make rent? Why is this month different?*

## The idea

SpendWise answers those questions with five cooperating engines, each with a **single
responsibility** and a **pure, tested contract**:

| Engine | Question | Substance |
| --- | --- | --- |
| **Ledger** | *What happened?* | Import → normalise → idempotent dedupe → categorise with provenance |
| **Pulse** | *What changed, and why?* | Robust month-over-month variance attribution that reconciles exactly |
| **Radar** | *What am I not seeing?* | Recurring-obligation detection, price-hike alerts, zombie subscriptions, anomaly flags |
| **Horizon** | *What happens next?* | Seeded Monte Carlo cash-flow forecast with P10/P50/P90 bands and a "safe to spend today" number |
| **Lab** | *What if I change something?* | Scenario simulation and constrained natural-language queries over the ledger |

### The one number

The product's headline is a single, defensible figure: **Safe to spend today.**

```
Safe to spend today = ( P10 projected balance at next income − safety buffer )
                      ÷ days until that income
```

That formula is only meaningful if you can detect income events, model committed outflows, and
quantify uncertainty. So the hero number is a *consequence* of the engine work, not a decoration —
and it expands inline to show every component that produced it.

### Why this is different

- **Every insight cites its evidence.** Click "Dining is up ₹4,210" and the exact contributing
  transactions open, sorted by contribution. Deterministic, reproducible, versioned by
  `engine_version`.
- **Forecasts are seeded, so they are testable.** `rng = default_rng(seed)` means the same ledger
  produces the same forecast in tests, in CI, and on your machine.
- **Local-first.** No bank credentials, no aggregation vendor, no server holding your transactions.
  SQLite on your disk by default. This is a product stance, not a shortcut.
- **Money is integer minor units.** No floating-point currency anywhere in the domain.
- **Categorisation is rules + memory, not an LLM guess.** Deterministic, explainable, cheap, and it
  improves through your own overrides.

## Run it locally

Prerequisites: **Python 3.12+** and **Node 20+**. No Docker, no database server.

```bash
# 1. Backend
cd backend
py -3 -m venv .venv                       # macOS/Linux: python3 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.seed --months 18      # deterministic demo ledger
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

Or serve everything from one process: `npm run build`, then open <http://localhost:8000> — FastAPI
serves the built SPA.

```bash
# Checks
cd backend && .venv/Scripts/python -m pytest      # 69 tests, no database required
cd backend && .venv/Scripts/python -m ruff check .
cd frontend && npm run build                      # typecheck + production build
```

**What works today (M1):** CSV import with alias-based column detection and a dry-run preview,
idempotent dedupe (import the same statement twice — nothing doubles), merchant normalisation,
filterable ledger with reconciled totals, and a deterministic 18-month synthetic ledger.

**Not yet:** categorisation of imported rows (they arrive as `unknown` by design — guessing is M2),
recurring detection (M4), forecasting (M5), auth (M7).

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Analytics + API | Python 3.13, FastAPI, Pydantic v2 | Where the actual intellectual work lives; matches an AI/ML/data trajectory |
| Persistence | SQLAlchemy 2.0 + Alembic, SQLite (dev/demo) → Postgres (prod) | Zero-setup local runs, no vendor lock, real migrations |
| Numerics | NumPy (vectorised path simulation) | 2,000 forecast paths in milliseconds, not seconds |
| UI | React 19 + TypeScript + Vite + Tailwind + TanStack Query | Server-state isolation, typed contracts, fast feedback loop |
| Auth | Self-hosted opaque session cookies (argon2id) — M7 | Revocable, httpOnly, no tokens in JS |

One repository, one container in production, same-origin — so cookie auth needs no CORS gymnastics
and no third-party identity vendor.

## Repository layout

```
backend/
  app/
    domain/        # entities, value objects, invariants — no I/O
    analytics/     # pure engines: pulse, radar, horizon (M3+)
    services/      # orchestration: import, demo data, (insights, forecasting)
    api/           # FastAPI routers, schemas, dependencies
    db/            # models, session, repositories
  alembic/         # schema history, checked against models by `alembic check`
  tests/           # pure unit tests + API integration tests
frontend/
  src/
    features/      # ledger, (pulse, radar, horizon, lab)
    components/    # shell and design-system primitives
    lib/           # typed API client
docs/
  decisions/       # ADRs — the "why", kept current
  architecture.md
  roadmap.md
```

## Status

| Milestone | Scope | State |
| --- | --- | --- |
| M0 | Vision, ADRs, repo foundation | done |
| M1 | Ledger: domain, import, dedupe, demo generator, UI | done |
| M2 | Categorisation engine + rules UI | next |
| M3 | Pulse: variance attribution | not started |
| M4 | Radar: recurring + anomalies | not started |
| M5 | Horizon: forecast + safe-to-spend | not started |
| M6 | Lab: scenarios + constrained NL query | not started |
| M7 | Auth, hardening, deploy, portfolio polish | not started |

## Documents

- [`docs/decisions/0001-product-direction.md`](docs/decisions/0001-product-direction.md) — what
  SpendWise is, and the directions deliberately rejected
- [`docs/decisions/0002-technology-stack.md`](docs/decisions/0002-technology-stack.md) — stack and
  auth decisions with trade-offs
- [`docs/architecture.md`](docs/architecture.md) — layering, data model, engine specifications
- [`docs/roadmap.md`](docs/roadmap.md) — milestones, acceptance criteria, learning outcomes

## Design principles

1. **Explainability over cleverness.** An insight that cannot show its receipts does not ship.
2. **Pure cores, thin edges.** Engines are functions over data. I/O lives at the boundary, so the
   hard logic is unit-testable without a database or a browser.
3. **Determinism is a feature.** Seeded randomness, versioned engines, stable fingerprints.
4. **Boring where it doesn't matter.** No microservices, no message queue, no graph database. The
   interesting complexity budget is spent on the money model.
5. **The demo must be convincing in 30 seconds.** A seeded 18-month synthetic ledger ships with the
   app so the product is never shown empty.

## Assumptions

- Demo data and default currency are **INR**, assuming an Indian context (salary cycles, UPI-era
  merchant names, annual insurance premiums). Currency is a user setting; formatting goes through
  Indian digit grouping on the server.
- Primary use is **individual** finances, one or more accounts, one currency per user.
