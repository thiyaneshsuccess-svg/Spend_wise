"""Money as integer minor units.

Why integers: `0.1 + 0.2 != 0.3` in binary floating point. A ledger that cannot
add up is not a ledger. Every amount in SpendWise is stored and computed as a
whole number of paise/cents, and converted to a display string only at the very
edge (formatting, CSV export).

This module is pure: standard library only, no app imports, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CURRENCY_SYMBOLS = "₹$€£¥"
_NOISE = re.compile(r"[\s,_'" + _CURRENCY_SYMBOLS + r"]")
_CURRENCY_CODE = re.compile(r"\b(INR|USD|EUR|GBP|JPY)\b", re.IGNORECASE)


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic mixes two currencies."""


def _group_indian(digits: str) -> str:
    """Group digits the Indian way: 1,23,456 (last three, then pairs)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


def _group_western(digits: str) -> str:
    parts: list[str] = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return ",".join(parts)


def format_minor(minor: int, currency: str = "INR", *, with_symbol: bool = True) -> str:
    """Render minor units as a human string, e.g. ``₹1,23,456.78``."""
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 100)
    digits = str(whole)
    grouped = _group_indian(digits) if currency.upper() == "INR" else _group_western(digits)
    symbol = "₹" if currency.upper() == "INR" else f"{currency.upper()} "
    prefix = symbol if with_symbol else ""
    return f"{sign}{prefix}{grouped}.{frac:02d}"


def parse_amount_minor(text: str) -> int:
    """Parse a statement amount into minor units.

    Handles ``1,23,456.78``, ``₹ 1 200``, ``(500.00)`` for negatives and a
    trailing ``Dr``/``Cr`` marker. Raises ``ValueError`` on anything else so the
    caller can report the row instead of silently importing a wrong number.
    """
    if text is None:
        raise ValueError("amount is empty")
    raw = str(text).strip()
    if not raw:
        raise ValueError("amount is empty")

    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]
    if raw.lower().endswith("dr"):
        negative = True
        raw = raw[:-2]
    elif raw.lower().endswith("cr"):
        raw = raw[:-2]

    raw = _CURRENCY_CODE.sub("", raw)
    cleaned = _NOISE.sub("", raw)
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned or not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise ValueError(f"not a valid amount: {text!r}")

    try:
        value = Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"not a valid amount: {text!r}") from exc

    minor = int(value * 100)
    return -minor if negative else minor


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """An amount in minor units, bound to a currency."""

    minor: int
    currency: str = "INR"

    def __post_init__(self) -> None:
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise TypeError("Money.minor must be an int (minor units)")
        if not self.currency or len(self.currency) != 3:
            raise ValueError("currency must be a 3-letter code")

    # -- arithmetic ---------------------------------------------------------
    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor - other.minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.minor, self.currency)

    def __mul__(self, factor: int) -> Money:
        if isinstance(factor, bool) or not isinstance(factor, int):
            raise TypeError("Money can only be multiplied by an int")
        return Money(self.minor * factor, self.currency)

    __rmul__ = __mul__

    def is_zero(self) -> bool:
        return self.minor == 0

    def is_inflow(self) -> bool:
        return self.minor > 0

    def format(self, *, with_symbol: bool = True) -> str:
        return format_minor(self.minor, self.currency, with_symbol=with_symbol)

    @classmethod
    def zero(cls, currency: str = "INR") -> Money:
        return cls(0, currency)

    @classmethod
    def from_rupees(cls, value: str | int | float, currency: str = "INR") -> Money:
        return cls(parse_amount_minor(str(value)), currency)
