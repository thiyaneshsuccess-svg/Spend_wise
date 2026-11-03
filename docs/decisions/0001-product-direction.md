# ADR 0001 — Product direction: explainable, local-first finance intelligence

- **Status:** Accepted
- **Date:** 2026-11-03
- **Deciders:** Project author

## Context

"Personal finance app" is one of the most saturated portfolio categories. The default shape —
transactions table, category pie chart, monthly bar chart, budget progress bars — is a CRUD exercise
with a charting library attached. It demonstrates that you can wire a form to a database, and
almost nothing about judgement, modelling, or product thinking.

The obvious differentiators were considered and rejected or kept only as ingredients:

**Rejected: bank-aggregation aggregator.** Connecting real accounts requires an aggregation vendor,
per-country regulation, credential custody, and ongoing cost. It adds integration plumbing, not
insight, and the demo becomes worthless without live accounts.

**Rejected: "chat with your expenses".** Thin wrapper over an LLM that writes SQL or guesses numbers.
Non-deterministic, unverifiable, expensive per query, and it hides the interesting engineering behind
a prompt. SpendWise will eventually have natural-language input, but as a *constrained parser over a
typed query model* — the model may translate intent, never execute it.

**Rejected: gamified/social budgeting.** Streaks and leaderboards optimise for retention theatre.
The project should be impressive to an engineer, not addictive to a user.

**Rejected (as the core): envelope budgeting clone.** Commodity. Zero algorithmic substance.

## Decision

SpendWise is a **local-first financial intelligence workbench**. Four commitments define it:

### 1. Insights must be auditable
Every generated insight stores its `evidence` (transaction/merchant references), the `params` used,
and the `engine_version` that produced it. The UI can always expand an insight into the exact rows
behind it. This inverts the usual relationship: the chart is a summary of a computable claim, not
the claim itself.

### 2. The product is forward-looking
The headline metric is **safe to spend today**, derived from a probabilistic projection of the
balance until the next income event — not a retrospective total. Backward-looking views exist to
explain the forecast, not as the destination.

### 3. Determination over inference for money facts
Categorisation, recurrence detection, and attribution are deterministic algorithms. Randomness is
confined to the forecast, where it is *seeded* and therefore reproducible. No money fact depends on
a model call.

### 4. Local-first by architecture
SQLite on disk, no credential custody, no telemetry. The same code runs as a single container for a
hosted demo, but privacy is the default posture rather than a settings toggle.

## Consequences

**Positive**
- The interesting work is statistical modelling and domain design — genuinely differentiating, and
  directly aligned with a data/AI learning trajectory.
- Determinism makes the hard parts unit-testable; forecast behaviour can be asserted in CI.
- A synthetic ledger can be shipped, so the app demos at full fidelity offline with no accounts.
- Clear narrative for a portfolio: *"I built an explainable forecasting engine for personal
  finance, and here is how I proved it correct."*

**Negative / costs**
- More design work than CRUD: the data model must support provenance, idempotent imports and
  evidence graphs from day one.
- Local-first limits the "sign in from any device" story. Accepted: hosted mode exists, but sync
  across devices is an explicit non-goal until v2.
- Forecast accuracy on sparse data is genuinely poor. Mitigation: confidence gating — below a
  threshold of history, the UI shows a range and states why, instead of pretending precision.

## Non-goals for v1

Multi-user sharing, bank API integrations, investment portfolio tracking, tax filing, mobile apps,
cross-device sync, receipt OCR.

## Open questions

- Should "safe to spend" use P10 or a configurable risk appetite (P10/P25/P50)? Leaning: fixed P10
  with the assumption documented in the UI, revisit after real user feedback.
- Do users trust a forecast enough to change behaviour, or is the attribution engine (Pulse) the real
  draw? This is the experiment that M5 exists to answer.
