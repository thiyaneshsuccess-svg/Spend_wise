"""The built-in rules shipped with the app.

These are ordinary rows in ``category_rules`` with ``origin = 'seed'``: visible,
editable and deletable like any rule the user writes. Nothing is hidden in code
at decision time, which matters because a categoriser whose behaviour cannot be
inspected is not explainable — and explainability is the product.

They sit *below* learned merchant memory in precedence, so a correction always
beats the default. Priorities are relative within a layer: a specific pattern
(110) outranks the generic fallback (50) that catches the same narration shape
for another bank.
"""

from __future__ import annotations

from app.domain.categorisation import MatchField, MatchType, Rule, RuleOrigin
from app.services.taxonomy import TRANSFER_CATEGORY


def _rule(
    pattern: str,
    category: str,
    *,
    match_type: MatchType = MatchType.CONTAINS,
    field: MatchField = MatchField.MERCHANT,
    priority: int = 100,
    confidence: float = 0.9,
    is_transfer: bool = False,
) -> Rule:
    return Rule(
        pattern=pattern,
        category=category,
        match_type=match_type,
        field=field,
        priority=priority,
        confidence=confidence,
        origin=RuleOrigin.SEED,
        is_transfer=is_transfer,
    )


SEED_RULES: tuple[Rule, ...] = (
    # --- income -----------------------------------------------------------
    _rule("salary credit", "Salary", field=MatchField.RAW, confidence=0.95),
    _rule("acme technologies", "Salary", priority=110, confidence=0.95),
    _rule("int credit", "Interest", match_type=MatchType.PREFIX),
    # --- committed obligations -------------------------------------------
    _rule("landlord", "Rent", confidence=0.95),
    _rule("act fibernet", "Utilities", confidence=0.95),
    _rule("bescom", "Utilities", confidence=0.95),
    _rule("jio", "Utilities", match_type=MatchType.PREFIX, confidence=0.85),
    _rule("airtel", "Utilities", match_type=MatchType.PREFIX, confidence=0.85),
    _rule("netflix", "Subscriptions", confidence=0.95),
    _rule("spotify", "Subscriptions", confidence=0.95),
    _rule("hotstar", "Subscriptions"),
    _rule("sip mutual fund", "Investments", confidence=0.95),
    _rule("mutual fund", "Investments", priority=90, confidence=0.8),
    # --- groceries --------------------------------------------------------
    _rule("bigbasket", "Groceries", confidence=0.95),
    _rule("zepto", "Groceries", confidence=0.95),
    _rule("reliance fresh", "Groceries", confidence=0.95),
    _rule("blinkit", "Groceries"),
    # --- dining -----------------------------------------------------------
    _rule("swiggy", "Dining", confidence=0.95),
    _rule("zomato", "Dining", confidence=0.95),
    _rule("dominos", "Dining", confidence=0.95),
    _rule("third wave", "Dining"),
    _rule("truffles", "Dining"),
    _rule("ccd coffee", "Dining"),
    _rule("canteen", "Dining"),
    # --- transport --------------------------------------------------------
    _rule("indian oil", "Transport"),
    _rule("uber", "Transport", confidence=0.95),
    _rule("ola", "Transport"),
    _rule("indigo", "Transport"),
    # --- discretionary ----------------------------------------------------
    _rule("amazon", "Shopping"),
    _rule("flipkart", "Shopping"),
    _rule("myntra", "Shopping"),
    _rule("croma", "Shopping"),
    _rule("apollo pharmacy", "Health"),
    _rule("manipal", "Health"),
    _rule("hdfc life", "Insurance", confidence=0.95),
    # --- transfers (never spending) ---------------------------------------
    _rule("hdfc credit card", TRANSFER_CATEGORY, confidence=0.95, is_transfer=True),
    _rule("atm cash withdrawal", TRANSFER_CATEGORY, confidence=0.95, is_transfer=True),
    _rule("imps to self", TRANSFER_CATEGORY, confidence=0.95, is_transfer=True),
    # Generic fallbacks: lower priority so a specific bank pattern wins.
    _rule(
        "credit card payment",
        TRANSFER_CATEGORY,
        field=MatchField.RAW,
        priority=60,
        is_transfer=True,
    ),
    _rule("to self", TRANSFER_CATEGORY, field=MatchField.RAW, priority=50, is_transfer=True),
)
