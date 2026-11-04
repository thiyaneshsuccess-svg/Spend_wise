"""API schemas (Pydantic v2).

These are the contract between backend and frontend. Amounts are exposed twice:
``*_minor`` integers for anything the client might compute with, and a
pre-formatted string for display. Formatting belongs on the server because it
depends on currency rules the client should not reimplement.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

MatchTypeLiteral = Literal["exact", "prefix", "contains"]
MatchFieldLiteral = Literal["merchant", "raw"]


class AccountOut(BaseModel):
    id: int
    name: str
    kind: str
    institution: str | None = None


class CategoryOut(BaseModel):
    id: int
    name: str
    kind: str


class MetaOut(BaseModel):
    currency: str
    timezone: str
    demo_mode: bool
    accounts: list[AccountOut]
    categories: list[CategoryOut]
    transaction_count: int
    unknown_count: int = 0
    rule_count: int = 0
    first_transaction_on: date | None = None
    last_transaction_on: date | None = None


class TransactionOut(BaseModel):
    id: int
    posted_on: date
    merchant: str
    merchant_raw: str
    description: str | None
    amount_minor: int
    amount: str
    currency: str
    category: str | None
    category_id: int | None
    category_source: str
    confidence: float | None = None
    is_transfer: bool
    account: str
    account_id: int


class SummaryOut(BaseModel):
    inflow_minor: int
    inflow: str
    outflow_minor: int
    outflow: str
    net_minor: int
    net: str
    count: int


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int
    summary: SummaryOut


class ImportErrorOut(BaseModel):
    line: int
    message: str


class ImportSampleOut(BaseModel):
    line: int
    posted_on: date
    merchant: str
    amount_minor: int
    amount: str
    is_transfer: bool


class ImportPreviewOut(BaseModel):
    filename: str
    total_rows: int
    new_rows: int
    duplicates: int
    errors: list[ImportErrorOut]
    sample: list[ImportSampleOut]
    currency: str


class ImportResultOut(BaseModel):
    batch_id: int | None
    total_rows: int
    imported: int
    skipped: int
    errors: int
    currency: str


class SeedOut(BaseModel):
    created: int
    skipped: bool
    months: int
    start: date | None = None
    end: date | None = None


class RuleOut(BaseModel):
    id: int
    pattern: str
    match_type: MatchTypeLiteral
    field: MatchFieldLiteral
    category: str | None = None
    category_id: int | None = None
    priority: int
    confidence: float
    origin: str
    is_transfer: bool
    is_active: bool
    applied_count: int = 0


class RuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=120)
    category_id: int | None = None
    match_type: MatchTypeLiteral = "contains"
    field: MatchFieldLiteral = "merchant"
    priority: int = Field(default=100, ge=0, le=1000)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    is_transfer: bool = False


class RuleUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = None
    match_type: MatchTypeLiteral | None = None
    field: MatchFieldLiteral | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_transfer: bool | None = None
    is_active: bool | None = None


class RuleMutationOut(BaseModel):
    """A saved rule plus what the immediate re-run did with it."""

    rule: RuleOut
    applied: int
    remaining: int


class RulePreviewIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=120)
    match_type: MatchTypeLiteral = "contains"
    field: MatchFieldLiteral = "merchant"


class RulePreviewMatchOut(BaseModel):
    merchant: str
    amount_minor: int
    amount: str


class RulePreviewOut(BaseModel):
    matched: int
    uncategorised: int
    sample: list[RulePreviewMatchOut]


class CategorySpendOut(BaseModel):
    category_id: int | None = None
    category: str
    spent_minor: int
    spent: str
    count: int
    share: float


class BreakdownOut(BaseModel):
    month: str | None = None
    total_spent_minor: int
    total_spent: str
    slices: list[CategorySpendOut]


class ReviewGroupOut(BaseModel):
    merchant: str
    count: int
    total_minor: int
    total: str
    first_on: date
    last_on: date
    sample_raw: str


class ReviewOut(BaseModel):
    total_unknown: int
    groups: list[ReviewGroupOut]


class AssignCategoryIn(BaseModel):
    category_id: int | None = None
    remember: bool = True


class AssignMerchantIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=160)
    category_id: int
    remember: bool = True


class AssignOut(BaseModel):
    updated: int
    propagated: int
    learned: bool
    category: str | None = None


class CategoriseRunOut(BaseModel):
    applied: int
    remaining: int
    by_source: dict[str, int] = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: str = "ok"
    service: str = "spendwise"
    version: str = Field(default="0.1.0")
