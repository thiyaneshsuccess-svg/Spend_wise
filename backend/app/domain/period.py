"""Calendar periods used by reporting, budgeting and the forecast.

A ``MonthPeriod`` is a closed-open range ``[start, end)``. Half-open ranges
avoid the classic off-by-one-day bug where a transaction posted on the 1st is
counted in two months, or in none.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month out of range: {self.month}")

    @classmethod
    def from_date(cls, value: date) -> MonthPeriod:
        return cls(value.year, value.month)

    @classmethod
    def parse(cls, value: str) -> MonthPeriod:
        match = _MONTH_RE.match(value.strip())
        if not match:
            raise ValueError(f"expected YYYY-MM, got {value!r}")
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end(self) -> date:
        """First day of the next month (exclusive)."""
        return self.shift(1).start

    @property
    def days(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    def shift(self, months: int) -> MonthPeriod:
        index = (self.year * 12 + (self.month - 1)) + months
        return MonthPeriod(index // 12, index % 12 + 1)

    def label(self) -> str:
        return f"{calendar.month_abbr[self.month]} {self.year}"

    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"
