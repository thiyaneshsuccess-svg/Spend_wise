# Roadmap

Each milestone is a mergeable, demoable slice: the app is runnable at the end of every one, and the
README's status table moves with it. Order is chosen so that **the interesting engine work is not
blocked on UI work**, and so that each stage produces something screenshot-worthy.

## M0 — Foundation *(current)*
Vision, ADRs, architecture, repository structure, tooling conventions.
**Done when:** docs are reviewed, repo is initialised with a clean first commit, `.gitignore` protects
secrets and build output.
**Learning:** writing an ADR; why layering is decided before code exists.

## M1 — Ledger
Domain entities (`Transaction`, `Money`, `Period`), SQLAlchemy models, Alembic baseline, CSV import
with a column-mapping dry run, idempotent dedupe, seeded synthetic ledger generator (18 months),
transaction list API + table UI with filters.
**Done when:** importing the same file twice creates zero duplicates; 18 months of demo data renders;
`pytest` covers money arithmetic and dedupe.
**Learning:** normalisation, idempotency, integer money, deterministic data generation, migration
discipline.

## M2 — Categorisation *(done)*
Rule engine + learned merchant memory + seed rules + provenance fields; review queue for
uncategorised transactions (grouped by merchant); rules management UI with live preview;
inline category edit + propagation; category spend breakdown.
**Done when:** every demo transaction has a category or an explicit `unknown`; overrides retrain
merchant memory; rule precedence is covered by tests.
**Learning:** precedence design, confidence as data, why "unknown" beats a wrong default; explainability over blind auto-categorisation.

## M3 — Pulse *(done)*
Monthly aggregates, robust baselines (median), merchant-level variance attribution, reconciliation
invariant test.
**Done when:** the decomposition sums exactly to the period delta in property-style tests; the UI can
drill from an insight to its rows.
**Learning:** robust statistics, decomposition, invariant testing.

## M4 — Radar
Interval clustering, cadence classification, CV-based confidence, price-hike and zombie-subscription
insights, MAD-based anomaly detection with small-sample guards.
**Done when:** fixtures with known recurring structures are detected at target precision; seasonal
and one-off spending is not.
**Learning:** signal detection on messy data, false-positive control, precision/recall tradeoffs.

## M5 — Horizon
Vectorised Monte Carlo forecast, percentile bands, income detection, `safe_to_spend` with breakdown,
low-confidence gating, fan-chart UI, performance benchmark.
**Done when:** forecast is reproducible from a seed; the benchmark meets its budget; the hero number
expands into its components.
**Learning:** simulation, vectorisation, percentile reasoning, communicating uncertainty.

## M6 — Lab
Scenario assumptions (cancel subscriptions, cap a category, one-off expense) applied to the forecast;
deterministic query parser over a typed AST.
**Done when:** a scenario changes the forecast predictably and is covered by tests; unsupported queries
fail with helpful messages.
**Learning:** pure-function composition (scenario as a transformation of inputs), grammar/AST design,
why constrained NL beats free-form SQL generation.

## M7 — Identity, hardening, portfolio
Session auth, per-user isolation tests, import/export, GitHub Actions CI across both stacks,
container build, hosted demo, README with architecture diagram + GIF, ADR updates.
**Done when:** two accounts provably cannot see each other's data; CI is green on a clean clone; a
stranger can run the demo in under five minutes.
**Learning:** session security, test isolation, deployment as engineering rather than an afterthought.

## Explicitly deferred
Multi-device sync, bank integrations, mobile client, receipt OCR, shared/household accounts,
investment tracking. Each is a v2 conversation, not a v1 distraction.
