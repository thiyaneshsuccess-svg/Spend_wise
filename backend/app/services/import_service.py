"""CSV import: parse → normalise → dedupe → persist.

Two properties this service must guarantee:

1. **Idempotency.** Importing the same statement twice must not double the
   ledger. ``dedupe_key`` is derived from the row's content *and* its position
   among identical rows within the file, so a repeated import collides with the
   unique constraint and is skipped rather than duplicated.
2. **No silent guessing.** A row that cannot be parsed is reported with its line
   number, never coerced into a plausible-looking transaction. Bad data that
   imports "successfully" is worse than bad data that is rejected.

Column detection is alias-based, so both common export shapes
(date/description/amount and date/description/debit/credit) work without a
bespoke parser per bank.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ImportBatch, Transaction
from app.domain.merchant import looks_like_transfer, normalise_merchant
from app.domain.money import format_minor, parse_amount_minor

PARSER_VERSION = "1"
MAX_ROWS = 20_000
MAX_REPORTED_ERRORS = 25

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
)

_HEADER_ALIASES: dict[str, set[str]] = {
    "date": {
        "date",
        "posted on",
        "posted on date",
        "posted date",
        "transaction date",
        "txn date",
        "value date",
    },
    "merchant": {
        "merchant",
        "description",
        "narration",
        "particulars",
        "details",
        "payee",
        "remarks",
    },
    "amount": {"amount", "transaction amount", "amt", "amount inr"},
    "debit": {"debit", "withdrawal", "withdrawal amt", "debit amount", "dr"},
    "credit": {"credit", "deposit", "deposit amt", "credit amount", "cr"},
}


class StatementError(ValueError):
    """A file-level problem: unreadable, missing columns, or too large."""


@dataclass(frozen=True, slots=True)
class ParsedRow:
    line: int
    posted_on: date
    amount_minor: int
    merchant_raw: str
    merchant_norm: str
    description: str | None
    is_transfer: bool
    dedupe_key: str
    occurrence_index: int


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    message: str


@dataclass
class ImportAnalysis:
    filename: str
    rows: list[ParsedRow] = field(default_factory=list)
    new_rows: list[ParsedRow] = field(default_factory=list)
    duplicates: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    total_rows: int = 0


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch_id: int | None
    total_rows: int
    imported: int
    skipped: int
    errors: int
    currency: str


def _normalise_header(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _resolve_headers(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise StatementError("The file has no header row.")

    resolved: dict[str, str] = {}
    for header in fieldnames:
        if header is None:
            continue
        normalised = _normalise_header(header)
        for role, aliases in _HEADER_ALIASES.items():
            if normalised in aliases and role not in resolved:
                resolved[role] = header

    if "date" not in resolved:
        raise StatementError(
            "Could not find a date column. Expected one of: "
            + ", ".join(sorted(_HEADER_ALIASES["date"]))
        )
    if "merchant" not in resolved:
        raise StatementError(
            "Could not find a description column. Expected one of: "
            + ", ".join(sorted(_HEADER_ALIASES["merchant"]))
        )
    if "amount" not in resolved and "debit" not in resolved and "credit" not in resolved:
        raise StatementError("Could not find an amount, debit or credit column.")
    return resolved


def _parse_date(value: str) -> date:
    text = (value or "").strip()
    if not text:
        raise ValueError("date is empty")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {text!r}")


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementError("Could not decode the file. Save it as UTF-8 CSV and retry.")


def _dedupe_key(
    account_id: int,
    *,
    posted_on: date,
    amount_minor: int,
    merchant_norm: str,
    occurrence_index: int,
) -> str:
    payload = "|".join(
        [
            str(account_id),
            posted_on.isoformat(),
            str(amount_minor),
            merchant_norm,
            str(occurrence_index),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_amount(row: dict[str, str], headers: dict[str, str]) -> int:
    if "amount" in headers:
        return parse_amount_minor(row.get(headers["amount"], ""))

    debit_raw = (row.get(headers.get("debit", ""), "") or "").strip()
    credit_raw = (row.get(headers.get("credit", ""), "") or "").strip()
    if debit_raw and credit_raw:
        raise ValueError("row has both a debit and a credit amount")
    if debit_raw:
        return -abs(parse_amount_minor(debit_raw))
    if credit_raw:
        return abs(parse_amount_minor(credit_raw))
    raise ValueError("row has neither a debit nor a credit amount")


def parse_csv(content: bytes, *, account_id: int, filename: str = "upload.csv") -> ImportAnalysis:
    """Parse a CSV into analysed rows, without touching the database."""
    text = _decode(content)
    reader = csv.DictReader(io.StringIO(text))
    headers = _resolve_headers(list(reader.fieldnames or []))
    analysis = ImportAnalysis(filename=filename)
    occurrences: dict[str, int] = {}

    for line_number, raw_row in enumerate(reader, start=2):
        if analysis.total_rows >= MAX_ROWS:
            raise StatementError(
                f"File has more than {MAX_ROWS} rows. Split it into smaller statements."
            )
        analysis.total_rows += 1

        try:
            posted_on = _parse_date(raw_row.get(headers["date"], ""))
            merchant_raw = (raw_row.get(headers["merchant"], "") or "").strip()
            amount_minor = _row_amount(raw_row, headers)
            merchant_norm = normalise_merchant(merchant_raw) or merchant_raw.upper()
            if not merchant_norm:
                raise ValueError("row has no merchant description")
        except ValueError as exc:
            if len(analysis.errors) < MAX_REPORTED_ERRORS:
                analysis.errors.append(RowError(line=line_number, message=str(exc)))
            continue

        identity = f"{posted_on.isoformat()}|{amount_minor}|{merchant_norm}"
        occurrence_index = occurrences.get(identity, 0)
        occurrences[identity] = occurrence_index + 1

        analysis.rows.append(
            ParsedRow(
                line=line_number,
                posted_on=posted_on,
                amount_minor=amount_minor,
                merchant_raw=merchant_raw or merchant_norm,
                merchant_norm=merchant_norm,
                description=merchant_raw or None,
                is_transfer=looks_like_transfer(merchant_raw),
                dedupe_key=_dedupe_key(
                    account_id,
                    posted_on=posted_on,
                    amount_minor=amount_minor,
                    merchant_norm=merchant_norm,
                    occurrence_index=occurrence_index,
                ),
                occurrence_index=occurrence_index,
            )
        )

    return analysis


def analyse(
    session: Session, *, user_id: int, account_id: int, content: bytes, filename: str
) -> ImportAnalysis:
    """Parse a file and mark which rows already exist for this user."""
    analysis = parse_csv(content, account_id=account_id, filename=filename)
    if not analysis.rows:
        return analysis

    existing = set(
        session.scalars(
            select(Transaction.dedupe_key).where(
                Transaction.user_id == user_id,
                Transaction.dedupe_key.in_([row.dedupe_key for row in analysis.rows]),
            )
        )
    )
    for row in analysis.rows:
        if row.dedupe_key in existing:
            analysis.duplicates.append(row)
        else:
            analysis.new_rows.append(row)
    return analysis


def commit(
    session: Session,
    *,
    user_id: int,
    account_id: int,
    content: bytes,
    filename: str,
    currency: str = "INR",
) -> ImportResult:
    """Persist the new rows of a file, skipping anything already present."""
    analysis = analyse(
        session, user_id=user_id, account_id=account_id, content=content, filename=filename
    )

    batch = ImportBatch(
        user_id=user_id,
        filename=filename[:255],
        row_count=analysis.total_rows,
        imported_count=len(analysis.new_rows),
        skipped_count=len(analysis.duplicates),
        parser_version=PARSER_VERSION,
    )
    session.add(batch)
    session.flush()

    for row in analysis.new_rows:
        session.add(
            Transaction(
                user_id=user_id,
                account_id=account_id,
                posted_on=row.posted_on,
                amount_minor=row.amount_minor,
                currency=currency,
                merchant_raw=row.merchant_raw[:240],
                merchant_norm=row.merchant_norm[:160],
                description=row.description[:400] if row.description else None,
                category_source="unknown",
                is_transfer=row.is_transfer,
                dedupe_key=row.dedupe_key,
                occurrence_index=row.occurrence_index,
                import_batch_id=batch.id,
            )
        )

    session.commit()
    return ImportResult(
        batch_id=batch.id,
        total_rows=analysis.total_rows,
        imported=len(analysis.new_rows),
        skipped=len(analysis.duplicates),
        errors=len(analysis.errors),
        currency=currency,
    )


def preview_payload(analysis: ImportAnalysis, *, currency: str = "INR") -> dict[str, object]:
    """Shape an analysis for the API's dry-run response."""
    return {
        "filename": analysis.filename,
        "total_rows": analysis.total_rows,
        "new_rows": len(analysis.new_rows),
        "duplicates": len(analysis.duplicates),
        "errors": [{"line": e.line, "message": e.message} for e in analysis.errors],
        "sample": [
            {
                "line": row.line,
                "posted_on": row.posted_on.isoformat(),
                "merchant": row.merchant_norm,
                "amount_minor": row.amount_minor,
                "amount": format_minor(row.amount_minor, currency),
                "is_transfer": row.is_transfer,
            }
            for row in analysis.new_rows[:10]
        ],
        "currency": currency,
    }
