"""Precedence is the whole contract of the categoriser, so it is asserted here.

These tests are pure: no database, no HTTP. If one fails, the product's promise
("your corrections stick, your rules win") has changed.
"""

from __future__ import annotations

import pytest

from app.domain.categorisation import (
    Categoriser,
    MatchField,
    MatchType,
    MemoryEntry,
    Rule,
    RuleError,
    RuleOrigin,
)
from app.domain.enums import CategorySource


def user_rule(pattern: str, category: str, **kwargs: object) -> Rule:
    return Rule(pattern=pattern, category=category, origin=RuleOrigin.USER, **kwargs)


def seed_rule(pattern: str, category: str, **kwargs: object) -> Rule:
    return Rule(pattern=pattern, category=category, origin=RuleOrigin.SEED, **kwargs)


def test_user_rule_beats_memory_and_seed_rules() -> None:
    categoriser = Categoriser(
        rules=[
            user_rule("zepto", "Shopping"),
            seed_rule("zepto", "Groceries"),
        ],
        memory={"ZEPTO MARKETPLACE": MemoryEntry(category="Dining", hits=9)},
    )

    decision = categoriser.decide(merchant="ZEPTO MARKETPLACE")

    assert decision.category == "Shopping"
    assert decision.source is CategorySource.RULE


def test_memory_beats_seed_rules_so_corrections_stick() -> None:
    """The bug this prevents: a user fixes Zepto, and the built-in guess returns."""
    categoriser = Categoriser(
        rules=[seed_rule("zepto", "Groceries")],
        memory={"ZEPTO MARKETPLACE": MemoryEntry(category="Dining", hits=1)},
    )

    decision = categoriser.decide(merchant="ZEPTO MARKETPLACE")

    assert decision.category == "Dining"
    assert decision.source is CategorySource.MEMORY
    assert "1 confirmation" in decision.reason


def test_seed_rule_applies_when_nothing_more_specific_exists() -> None:
    categoriser = Categoriser(rules=[seed_rule("netflix", "Subscriptions")])

    decision = categoriser.decide(merchant="NETFLIX COM")

    assert decision.category == "Subscriptions"
    assert decision.source is CategorySource.SEED


def test_no_evidence_produces_an_explicit_unknown() -> None:
    """A wrong category silently poisons every total; ``unknown`` does not."""
    categoriser = Categoriser(rules=[seed_rule("netflix", "Subscriptions")])

    decision = categoriser.decide(merchant="BLUE TOKAI COFFEE")

    assert decision.category is None
    assert decision.source is CategorySource.UNKNOWN
    assert decision.is_categorised is False


def test_contains_matches_whole_words_not_substrings() -> None:
    """``OLA`` must not fire inside ``COLAB`` — the classic substring bug."""
    categoriser = Categoriser(rules=[seed_rule("ola", "Transport")])

    assert categoriser.decide(merchant="OLA CABS").category == "Transport"
    assert categoriser.decide(merchant="COLAB SPACES").category is None


def test_matching_ignores_statement_punctuation() -> None:
    categoriser = Categoriser(rules=[seed_rule("reliance fresh", "Groceries")])

    decision = categoriser.decide(
        merchant="RELIANCE FRESH", raw="UPI/RELIANCE-FRESH/8715177240/Payment"
    )

    assert decision.category == "Groceries"


def test_exact_requires_the_whole_value() -> None:
    categoriser = Categoriser(
        rules=[seed_rule("jio", "Utilities", match_type=MatchType.EXACT)]
    )

    assert categoriser.decide(merchant="JIO").category == "Utilities"
    assert categoriser.decide(merchant="JIO PREPAID RECHARGE").category is None


def test_prefix_requires_a_word_boundary() -> None:
    categoriser = Categoriser(
        rules=[seed_rule("airtel", "Utilities", match_type=MatchType.PREFIX)]
    )

    assert categoriser.decide(merchant="AIRTEL POSTPAID").category == "Utilities"
    assert categoriser.decide(merchant="AIRTELXPRESS").category is None


def test_priority_decides_between_rules_in_the_same_layer() -> None:
    categoriser = Categoriser(
        rules=[
            user_rule("amazon", "Shopping", priority=50),
            user_rule("amazon refund", "Salary", priority=200),
        ]
    )

    assert categoriser.decide(merchant="AMAZON REFUND").category == "Salary"
    assert categoriser.decide(merchant="AMAZON").category == "Shopping"


def test_equal_priority_falls_back_to_creation_order() -> None:
    categoriser = Categoriser(
        rules=[
            user_rule("uber", "Transport", id=7),
            user_rule("uber", "Dining", id=3),
        ]
    )

    assert categoriser.decide(merchant="UBER").category == "Dining"


def test_raw_field_rules_read_the_bank_narration() -> None:
    """``SALARY CREDIT`` is stripped by normalisation, so it needs the raw field."""
    categoriser = Categoriser(
        rules=[seed_rule("salary credit", "Salary", field=MatchField.RAW)]
    )

    decision = categoriser.decide(
        merchant="ACME TECHNOLOGIES", raw="SALARY CREDIT NEFT/ACME TECHNOLOGIES/1234"
    )

    assert decision.category == "Salary"


def test_memory_confidence_is_monotone_and_bounded() -> None:
    assert MemoryEntry(category="X", hits=1).confidence == pytest.approx(0.5)
    assert MemoryEntry(category="X", hits=3).confidence == pytest.approx(0.75)
    assert MemoryEntry(category="X", hits=10_000).confidence < 1.0


def test_transfer_rules_flag_the_decision() -> None:
    categoriser = Categoriser(
        rules=[
            seed_rule(
                "credit card payment", "Transfers", field=MatchField.RAW, is_transfer=True
            )
        ]
    )

    decision = categoriser.decide(
        merchant="HDFC CREDIT CARD", raw="CREDIT CARD PAYMENT HDFC"
    )

    assert decision.category == "Transfers"
    assert decision.is_transfer is True


@pytest.mark.parametrize("pattern", ["", "   ", "!!!", "-/-"])
def test_patterns_without_alphanumerics_are_rejected(pattern: str) -> None:
    with pytest.raises(RuleError):
        Rule(pattern=pattern, category="Dining")


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    with pytest.raises(RuleError):
        Rule(pattern="swiggy", category="Dining", confidence=1.5)


def test_rule_count_reports_both_layers() -> None:
    categoriser = Categoriser(rules=[user_rule("a", "B"), seed_rule("c", "D")])

    assert categoriser.rule_count == 2
