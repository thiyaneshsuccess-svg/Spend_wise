"""Money is the one place where a rounding bug silently corrupts everything."""

from __future__ import annotations

import pytest

from app.domain.money import (
    CurrencyMismatchError,
    Money,
    format_minor,
    parse_amount_minor,
)


def test_addition_is_exact_where_floats_are_not() -> None:
    assert (Money(10) + Money(20)).minor == 30
    assert (Money(1) + Money(2)).minor == 3  # 0.01 + 0.02


def test_subtraction_and_negation() -> None:
    assert (Money(500) - Money(1250)).minor == -750
    assert (-Money(750)).minor == -750


def test_arithmetic_across_currencies_is_refused() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(100, "INR") + Money(100, "USD")


def test_minor_must_be_an_integer() -> None:
    with pytest.raises(TypeError):
        Money(10.5)  # type: ignore[arg-type]


def test_only_integers_may_scale_money() -> None:
    assert (Money(250) * 3).minor == 750
    with pytest.raises(TypeError):
        Money(250) * 1.5  # type: ignore[operator]


def test_indian_digit_grouping() -> None:
    assert format_minor(123_456_78) == "₹1,23,456.78"
    assert format_minor(100_00) == "₹100.00"
    assert format_minor(1_000_000_00) == "₹10,00,000.00"


def test_negative_formatting() -> None:
    assert format_minor(-450_50) == "-₹450.50"


def test_western_grouping_for_other_currencies() -> None:
    assert format_minor(123_456_78, "USD") == "USD 123,456.78"
    assert format_minor(123_456_789, "USD") == "USD 1,234,567.89"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,23,456.78", 123_456_78),
        ("₹ 1 200", 120_000),
        ("-450.00", -45_000),
        ("(500.00)", -50_000),
        ("28000 Dr", -2_800_000),
        ("92000.00 Cr", 9_200_000),
        ("+75.5", 7_550),
    ],
)
def test_parse_statement_amounts(text: str, expected: int) -> None:
    assert parse_amount_minor(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "1.2.3", "₹"])
def test_unparseable_amounts_raise(text: str) -> None:
    with pytest.raises(ValueError):
        parse_amount_minor(text)
