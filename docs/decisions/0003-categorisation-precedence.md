# ADR 0003: Categorisation precedence and explainability

Date: 2026-11-04
Status: Accepted

## Context

SpendWise must categorise merchants without forcing the user to classify every
transaction manually. "Auto-categorise" is only useful if it is legible: the user
must be able to say why a row is labelled the way it is, and undo it without
corrupting a global model they did not intend to train.

## Decision

### Precedence (highest to lowest)

1. **Transaction manual/override** (`category_source = manual|override`) — explicitly
   set by the user. Never overwritten by rules, memory or seeds.
2. **User rules** (`origin = user`) — explicit regex-free matches (`exact | prefix | contains`)
   against `merchant | raw`. Higher priority first; within equal priority, the first
   match applies.
3. **Learned merchant memory** (`learned_merchants`) — one row per `(user_id, merchant_key)`.
   Written when the user assigns a category from the Review queue or edits a row inline.
   Confidence is derived as `hits / (hits + 1)` (not stored) to avoid a frozen 1.0 that
   blocks legitimate corrections.
4. **Seed rules** (`origin = seed`) — shipped as ordinary DB rows installed at user
   creation so that disabling a built-in suggestion is the same operation as disabling
   a user rule.
5. **`unknown`** — remains uncategorised and visible in the Review queue.

### Matching rules

- Token-aware comparison via `flatten()`; **no regex**. A typo in a pattern cannot
  accidentally compile into a catastrophic match.
- Matches only `merchant | raw` with `exact | prefix | contains`.
- Transfers are flagged by rules or import metadata (`is_transfer`), excluded from
  "spend" breakdowns by default.

### Propagation and stickiness

- **Sticky machine passes.** `categorise/run` and import-time classification only write
  to rows whose source is in `SOFT_SOURCES = {unknown, seed, memory}`. It never touches
  `LOCKED_SOURCES = {manual, override}`.
- **Correction propagates.** When the user assigns a category to a merchant, propagation
  overwrites only soft-source rows for that user/merchant. Existing manual choices
  remain intact.
- **Learning is deliberate.** `remember=true` on assign/inline edit upserts merchant
  memory. Review is grouped by merchant (one decision fixes every occurrence).
- **Rules are non-retroactive on deletion.** Deleting a user rule does not strip
  categories already applied; it only changes future behaviour.

### Explainability

- Every transaction exposes `category_source` (`manual|override|rule|memory|unknown`).
- The UI shows "set by you / by rule / remembered / needs a category" next to the
  inline category selector so the precedence is visible at the moment of correction.
- Rules are fully inspectable and toggleable in the Rules tab; seed rules are
  first-class rows, not hidden heuristics.
- The breakdown makes "Uncategorised" spend impossible to miss (warning colour, bucketed).

## Consequences

- Corrections do not create feedback loops that re-classify a deliberate manual choice.
- New heuristics can be shipped as data (seeds) and audited by the same UI.
- The system remains testable: precedence is a pure function (`domain/categorisation.py`)
  with unit tests and API tests covering propagation, stickiness and transfer handling.
- A slightly more verbose data model (`origin`, `applied_count`, `learned_merchants`)
  is justified by predictability and debuggability for a CS learning project.
