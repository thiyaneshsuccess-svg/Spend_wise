"""Half-open month ranges: the boundary bug that inflates or hides a month."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.period import MonthPeriod


def test_end_is_exclusive_and_rolls_the_year() -> None:
    period = MonthPeriod(2026, 12)
    assert period.start == date(2026, 12, 1)
    assert period.end == date(2027, 1, 1)


def test_february_in_a_leap_year() -> None:
    assert MonthPeriod(2028, 2).days == 29


def test_shift_crosses_year_boundaries_both_ways() -> None:
    assert MonthPeriod(2026, 1).shift(-1) == MonthPeriod(2025, 12)
    assert MonthPeriod(2026, 12).shift(1) == MonthPeriod(2027, 1)
    assert MonthPeriod(2026, 1).shift(-13) == MonthPeriod(2024, 12)


def test_parse_and_key_round_trip() -> None:
    assert MonthPeriod.parse("2026-3") == MonthPeriod(2026, 3)
    assert MonthPeriod(2026, 3).key() == "2026-03"
    assert MonthPeriod(2026, 3).label() == "Mar 2026"


@pytest.mark.parametrize("value", ["2026-13", "2026", "March", ""])
def test_invalid_periods_raise(value: str) -> None:
    with pytest.raises(ValueError):
        MonthPeriod.parse(value)
