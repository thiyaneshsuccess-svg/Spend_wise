# Architecture

## Layering

```
┌───────────────────────────────────────────────────────────────┐
│  frontend/  React SPA — features/ledger pulse radar horizon lab│
└───────────────────────────┬───────────────────────────────────┘
                            │ typed client (OpenAPI-derived)
┌───────────────────────────▼───────────────────────────────────┐
│  api/         routers · Pydantic schemas · auth dependencies   │
├───────────────────────────────────────────────────────────────┤
│  services/    import · insights orchestration · forecasting    │
├───────────────────────────────────────────────────────────────┤
│  analytics/   PURE. pulse · radar · horizon. NumPy only.       │
│  domain/      entities · invariants · money · periods          │
├───────────────────────────────────────────────────────────────┤
│  db/          SQLAlchemy models · repositories · Alembic       │
└───────────────────────────────────────────────────────────────┘
```

**The rule:** `domain` and `analytics` import nothing from `db`, `api`, or FastAPI. They are
functions over plain dataclasses/arrays. This is what makes the hard parts testable without a
database, a server, or a browser — and it is the single most important structural decision in the
codebase.

Dependencies point downward only. `services/` may read the DB and call `analytics/`; `analytics/`
never reaches back up.

## Data model

All money columns are `int` minor units. All user-owned tables carry `user_id` with a composite
index on `(user_id, <primary access path>)`.

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `users` | identity + preferences | `email` (unique), `password_hash`, `currency`, `timezone` |
| `sessions` | revocable auth | `token_hash`, `expires_at`, `user_agent`, `last_seen_at` |
| `accounts` | source of funds | `kind` (bank/cash/card), `opening_balance_minor` |
| `transactions` | the ledger | `posted_on`, `amount_minor` (signed), `merchant_raw`, `merchant_norm`, `category_id`, `category_source` (rule/override/memory/unknown), `confidence`, `is_transfer`, `dedupe_key` (unique per user), `import_batch_id` |
| `categories` | taxonomy | `parent_id`, `kind` (expense/income/transfer), `is_system` |
| `rules` | user categorisation | `priority`, `matcher` (JSON: exact/token/regex/amount band), `target_category_id` |
| `recurring_series` | detected obligations | `cadence`, `expected_amount_minor`, `amount_cv`, `next_expected_on`, `confidence`, `status` (active/paused/cancelled) |
| `insights` | materialised, explainable findings | `kind`, `period`, `severity`, `title`, `body`, `evidence` (JSON), `params` (JSON), `engine_version`, `fingerprint` (unique → idempotent regeneration) |
| `budgets` | soft limits | `category_id`, `period`, `amount_minor` |
| `scenarios` | saved "what if" assumptions | `assumptions` (JSON) |
| `import_batches` | provenance of bulk loads | `filename`, `row_count`, `imported_count`, `skipped_count`, `parser_version` |

Design notes:

- **`dedupe_key`** is a hash of `(account_id, posted_on, amount_minor, merchant_norm, occurrence_index)`.
  `occurrence_index` disambiguates genuinely identical same-day rows (two coffees). Re-importing an
  overlapping statement is a no-op instead of double-counting — the most common real-world failure of
  hand-built expense apps.
- **`evidence` / `params`** are the audit trail. Deleting a transaction invalidates insights that
  cite it via fingerprint change, so stale insights cannot survive a ledger edit.
- **`is_transfer`** exists because moving money between your own accounts is not spending. Getting
  this wrong inflates every total, so it is modelled explicitly rather than inferred at query time.

## Engine specifications

### Categorisation (M2)
Deterministic cascade, first match wins:
1. user override for exact `merchant_norm`
2. user rule, ordered by `priority` (exact → token → regex)
3. learned merchant memory: the modal category the user has previously assigned to that merchant
4. built-in seed rules (Indian merchant patterns: `SWIGGY`, `ZOMATO`, `BIGBASKET`, `IRCTC`, …)
5. `unknown` — **never guessed silently**

Each assignment records `category_source` and `confidence`, so the UI can show "3 transactions need
a category" instead of quietly miscategorising them. Defaults are suggestions, not assertions.

### Recurring detection (M4)
Per normalised merchant, over ≥3 occurrences:
- median inter-arrival gap → cadence bucket (weekly 5–9d, biweekly 12–17d, monthly 26–35d,
  quarterly, annual ±15d)
- reject if gap `CV > 0.35`
- amount stability: `CV < 0.25` → fixed (subscriptions, rent, EMIs); `CV < 0.60` → variable (utilities)
- `next_expected_on = last_seen + cadence`, snapped to the observed day-of-month for monthly series
- `confidence = w₁·regularity + w₂·amount_stability + w₃·count_factor`
- **price hike:** last amount exceeds the prior median by >8% → insight with both amounts as evidence
- **zombie subscription:** recurring obligations with no overlapping usage signal are surfaced as a
  review prompt, not a verdict (no usage data exists; honesty over cleverness)

### Variance attribution (M3)
Baseline per merchant = median of the three preceding complete months (robust to one-off spikes).
`Δ = current − baseline`, ranked by `|Δ|`. Merchant deltas **must sum exactly to the period delta** —
asserted in tests, because a decomposition that doesn't reconcile is a lie with decimals.

### Forecast (M5)
Daily-step simulation over a 45-day horizon, `2,000` paths, seeded `default_rng(seed)`:

1. **Committed outflows** — every active recurring series with `next_expected_on` inside the window is
   applied deterministically at its expected amount.
2. **Income** — detected recurring inflows (salary) applied on their expected date. If no income is
   detected, the forecast refuses to produce "safe to spend" and says why.
3. **Variable spend** — empirical bootstrap: for each future day, sample a historical *daily total* for
   the same weekday class (weekday/weekend) from the trailing 12 weeks, **excluding transactions
   already covered by a recurring series** (double-counting guard).
4. Percentile bands at P10/P50/P90 per day → the fan chart.

```
safe_to_spend = max(0, (P10_balance(at next income) − buffer) / days_until_income)
```

Returns a breakdown object (`committed`, `variable_median`, `p10_end`, `buffer`, `days`), so the
number can be explained component by component in the UI.

**Performance budget:** < 150 ms for a 45-day, 2,000-path run on a laptop, enforced by a benchmark
test. Vectorised NumPy, no per-path Python loops.

**Honesty gate:** with < 6 weeks of history or < 2 detected income events, the forecast is labelled
low-confidence and the hero number is suppressed in favour of a range. A confident wrong number is
worse than a stated uncertainty.

### Query language (M6)
A controlled grammar over a typed query AST — `metric` (spend/income/net), `dimension`
(category/merchant/week), `period`, `filters`, `comparison`. The parser is deterministic and its
output is validated against a closed schema; unsupported phrasings fail loudly with suggestions.
An LLM may later *propose* an AST, but never execute anything.

## Security model

- argon2id password hashing; opaque session tokens (32 bytes, hashed at rest); rotation on login.
- `httpOnly`, `SameSite=Lax`, `Secure` cookies; `Origin` verification on state-changing requests.
- Rate limiting on auth endpoints; uniform error messages to avoid account enumeration.
- Every repository query scoped by session user; IDs from the client are selectors only.
- No secrets in the repo; `.env` ignored, `.env.example` documented. No transaction data in logs.
- CSV import treats cell values as data, never as formulas or HTML; parsed by a schema, not `eval`.
- Dependency audit in CI once the dependency set stabilises.

## Frontend structure

Signature interactions, not just screens:
1. **`Safe to spend` hero** — one number, expandable into its full derivation.
2. **Evidence drawer** — any insight opens the contributing transactions inline (Radar/Pulse → Ledger).
3. **Horizon fan chart** — percentile bands with a today marker and payday marker.
4. **Command palette (⌘K)** — jump, filter, or run a query; keyboard-first, accessible.
5. **Import review** — dry-run preview showing new vs duplicate vs uncategorised before commit.
