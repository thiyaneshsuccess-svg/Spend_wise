"""API schemas (Pydantic v2).

These are the contract between backend and frontend. Amounts are exposed twice:
``*_minor`` integers for anything the client might compute with, and a
pre-formatted string for display. Formatting belongs on the server because it
depends on currency rules the client should not reimplement.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


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


class HealthOut(BaseModel):
    status: str = "ok"
    service: str = "spendwise"
    version: str = Field(default="0.1.0")
