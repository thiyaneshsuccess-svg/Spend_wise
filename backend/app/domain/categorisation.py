"""Explainable categorisation: a pure decision function over rules and memory.

Nothing here touches the database, FastAPI or SQLAlchemy, so the precedence
rules below are unit-testable in microseconds. The service layer's only job is
to load rules and memory into a :class:`Categoriser` and persist its decisions.

**Precedence, highest first.**

1. A category set on the transaction itself (``manual``/``override``).
2. **User rules** — the user's explicit declarations, ordered by
   ``priority`` (higher wins), then by creation order.
3. **Merchant memory** — what this user has previously chosen for this merchant.
4. **Seed rules** — the built-in patterns shipped with the app.
5. **Unknown** — no evidence, so no category.

The ordering is chosen so that explicit intent always beats inference, and so
that a correction *sticks*: memory outranks the seed patterns, so once a user
reclassifies Zepto, future Zepto rows follow the correction instead of falling
back to the built-in "Groceries" guess.

Two subtleties worth knowing:

* **Matching is token-aware.** ``contains`` means "contains this phrase as whole
  words, ignoring punctuation", not a raw substring test. A naive ``"OLA" in
  narration`` would fire on ``COLAB`` or ``ZOMATO``-adjacent noise; token
  matching keeps the cheap, predictable semantics without that class of bug.
* **Confidence is declared, not learned.** A rule's ``confidence`` is the number
  its author asserted. Memory's confidence is derived from how many times the
  merchant has been confirmed (``hits / (hits + 1)``): 0.5 after one
  confirmation, approaching — but never reaching — 1.0. Repetition is evidence,
  not proof.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import StrEnum

from app.domain.enums import CategorySource

MAX_PATTERN_LENGTH = 120
"""Longer patterns are almost always pasted text, not a merchant name."""

_SEPARATORS = re.compile(r"[^A-Z0-9]+")


def flatten(value: str | None) -> str:
    """Uppercase a string and reduce every non-alphanumeric run to one space.

    Both statement chatter (``UPI/OLA/449/Payment``) and merchant keys
    (``OLA CABS``) collapse to the same token vocabulary, which is what makes
    token-aware matching work across the two fields.
    """
    return _SEPARATORS.sub(" ", (value or "").upper()).strip()


class MatchType(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    CONTAINS = "contains"


class MatchField(StrEnum):
    """Which text a rule looks at."""

    MERCHANT = "merchant"  # the normalised key, e.g. "ZEPTO MARKETPLACE"
    RAW = "raw"            # the bank's narration, e.g. "SALARY CREDIT NEFT/ACME/123"


class RuleOrigin(StrEnum):
    SEED = "seed"  # shipped default; lower precedence than learned memory
    USER = "user"  # written by this user; beats everything except a manual pick


class RuleError(ValueError):
    """A rule that could never behave predictably."""


@dataclass(frozen=True, slots=True)
class Rule:
    """One categorisation rule — a matcher plus the effect it declares.

    ``category`` may be ``None`` only transiently, when the rule builder is
    previewing a pattern that has not been given a category yet. Persisted rules
    must have an effect (a category, the transfer flag, or both); that check
    lives in the service, at the point where a rule becomes permanent.
    """

    pattern: str
    category: str | None = None
    match_type: MatchType = MatchType.CONTAINS
    field: MatchField = MatchField.MERCHANT
    priority: int = 100
    confidence: float = 0.9
    origin: RuleOrigin = RuleOrigin.USER
    is_transfer: bool = False
    id: int | None = None
    # Cached, flattened pattern: computed once at construction, never exposed.
    needle: str = dc_field(init=False, repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        needle = flatten(self.pattern)
        if not needle:
            raise RuleError("A rule needs a pattern containing at least one letter or digit.")
        if len(needle) > MAX_PATTERN_LENGTH:
            raise RuleError(f"A pattern may be at most {MAX_PATTERN_LENGTH} characters.")
        if not 0.0 <= self.confidence <= 1.0:
            raise RuleError("Confidence must be between 0 and 1.")
        if self.priority < 0:
            raise RuleError("Priority cannot be negative.")
        object.__setattr__(self, "needle", needle)

    def matches(self, *, merchant: str, raw: str = "") -> bool:
        haystack = flatten(merchant if self.field is MatchField.MERCHANT else raw)
        if not haystack:
            return False
        if self.match_type is MatchType.EXACT:
            return haystack == self.needle
        if self.match_type is MatchType.PREFIX:
            return haystack == self.needle or haystack.startswith(f"{self.needle} ")
        return f" {self.needle} " in f" {haystack} "

    def describe(self) -> str:
        """A short human sentence used as the decision's explanation."""
        where = "narration" if self.field is MatchField.RAW else "merchant"
        verb = {
            MatchType.EXACT: "is exactly",
            MatchType.PREFIX: "starts with",
            MatchType.CONTAINS: "contains",
        }[self.match_type]
        return f"{where} {verb} '{self.pattern.strip()}'"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """What the user has previously decided for one merchant."""

    category: str
    hits: int

    @property
    def confidence(self) -> float:
        return self.hits / (self.hits + 1)


@dataclass(frozen=True, slots=True)
class Decision:
    category: str | None
    source: CategorySource
    confidence: float
    reason: str
    rule_id: int | None = None
    is_transfer: bool = False

    @property
    def is_categorised(self) -> bool:
        return self.category is not None


def _order(rule: Rule) -> tuple[int, int, str]:
    """Deterministic rule ordering: priority desc, then oldest first."""
    return (-rule.priority, rule.id if rule.id is not None else 0, rule.pattern)


class Categoriser:
    """Decides a category for a transaction from rules plus learned memory."""

    def __init__(
        self,
        rules: Sequence[Rule] = (),
        memory: Mapping[str, MemoryEntry] | None = None,
    ) -> None:
        self._user_rules = sorted(
            (rule for rule in rules if rule.origin is RuleOrigin.USER), key=_order
        )
        self._seed_rules = sorted(
            (rule for rule in rules if rule.origin is RuleOrigin.SEED), key=_order
        )
        self._memory = {flatten(key): value for key, value in (memory or {}).items()}

    @property
    def rule_count(self) -> int:
        return len(self._user_rules) + len(self._seed_rules)

    def decide(self, *, merchant: str, raw: str = "") -> Decision:
        for rule in self._user_rules:
            if rule.matches(merchant=merchant, raw=raw):
                return Decision(
                    category=rule.category,
                    source=CategorySource.RULE,
                    confidence=rule.confidence,
                    reason=rule.describe(),
                    rule_id=rule.id,
                    is_transfer=rule.is_transfer,
                )

        entry = self._memory.get(flatten(merchant))
        if entry is not None:
            confirmations = "confirmation" if entry.hits == 1 else "confirmations"
            return Decision(
                category=entry.category,
                source=CategorySource.MEMORY,
                confidence=entry.confidence,
                reason=f"learned from {entry.hits} {confirmations}",
            )

        for rule in self._seed_rules:
            if rule.matches(merchant=merchant, raw=raw):
                return Decision(
                    category=rule.category,
                    source=CategorySource.SEED,
                    confidence=rule.confidence,
                    reason=rule.describe(),
                    rule_id=rule.id,
                    is_transfer=rule.is_transfer,
                )

        return Decision(
            category=None,
            source=CategorySource.UNKNOWN,
            confidence=0.0,
            reason="no rule matched this merchant",
        )
