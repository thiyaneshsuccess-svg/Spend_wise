"""Domain vocabulary shared by analytics, services and the API.

These are plain string enums with no persistence or framework dependency:
the domain must stay importable by a test that never touches a database.
"""

from __future__ import annotations

from enum import StrEnum


class CategoryKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class CategorySource(StrEnum):
    """How a transaction got its category — the provenance of the assignment."""

    OVERRIDE = "override"   # the user explicitly chose this for this merchant
    RULE = "rule"           # matched a user-defined rule
    MEMORY = "memory"       # learned from this user's previous assignments
    SEED = "seed"           # built-in pattern; demo data carries known truth
    MANUAL = "manual"       # set on the transaction itself
    UNKNOWN = "unknown"     # deliberately unassigned; never guessed silently


class AccountKind(StrEnum):
    BANK = "bank"
    CASH = "cash"
    CARD = "card"
