"""HTTP routes.

Thin by design: parse/validate input, call a service, map to a schema. Business
rules live in ``app.domain`` and ``app.services`` so they can be tested without
an HTTP client.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.api.schemas import (
    AccountOut,
    CategoryOut,
    HealthOut,
    ImportPreviewOut,
    ImportResultOut,
    MetaOut,
    SeedOut,
    SummaryOut,
    TransactionOut,
    TransactionPage,
)
from app.config import get_settings
from app.db.models import Account, Category, Transaction
from app.domain.money import format_minor
from app.domain.period import MonthPeriod
from app.services import import_service
from app.services.demo_data import seed_demo_data

router = APIRouter(prefix="/api")


def _to_out(transaction: Transaction, currency: str) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        posted_on=transaction.posted_on,
        merchant=transaction.merchant_norm,
        merchant_raw=transaction.merchant_raw,
        description=transaction.description,
        amount_minor=transaction.amount_minor,
        amount=format_minor(transaction.amount_minor, currency),
        currency=currency,
        category=transaction.category.name if transaction.category else None,
        category_id=transaction.category_id,
        category_source=transaction.category_source,
        is_transfer=transaction.is_transfer,
        account=transaction.account.name,
        account_id=transaction.account_id,
    )


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut()


@router.get("/meta", response_model=MetaOut)
def meta(session: SessionDep, user: CurrentUser) -> MetaOut:
    settings = get_settings()
    accounts = session.scalars(
        select(Account).where(Account.user_id == user.id).order_by(Account.id)
    ).all()
    categories = session.scalars(
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(Category.sort_order, Category.id)
    ).all()
    count = session.scalar(
        select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
    )
    first = session.scalar(
        select(func.min(Transaction.posted_on)).where(Transaction.user_id == user.id)
    )
    last = session.scalar(
        select(func.max(Transaction.posted_on)).where(Transaction.user_id == user.id)
    )
    return MetaOut(
        currency=user.currency,
        timezone=user.timezone,
        demo_mode=settings.demo_mode,
        accounts=[
            AccountOut(id=a.id, name=a.name, kind=a.kind, institution=a.institution)
            for a in accounts
        ],
        categories=[CategoryOut(id=c.id, name=c.name, kind=c.kind) for c in categories],
        transaction_count=count or 0,
        first_transaction_on=first,
        last_transaction_on=last,
    )


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    session: SessionDep,
    user: CurrentUser,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{1,2}$")] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    category_id: int | None = None,
    account_id: int | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    include_transfers: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    conditions = [Transaction.user_id == user.id]

    if month:
        try:
            period = MonthPeriod.parse(month)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        conditions.append(Transaction.posted_on >= period.start)
        conditions.append(Transaction.posted_on < period.end)
    if date_from:
        conditions.append(Transaction.posted_on >= date_from)
    if date_to:
        conditions.append(Transaction.posted_on < date_to + timedelta(days=1))
    if category_id is not None:
        conditions.append(Transaction.category_id == category_id)
    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    if q:
        pattern = f"%{q.strip().upper()}%"
        conditions.append(
            Transaction.merchant_norm.ilike(pattern) | Transaction.merchant_raw.ilike(pattern)
        )
    if not include_transfers:
        conditions.append(Transaction.is_transfer.is_(False))

    total = session.scalar(
        select(func.count(Transaction.id)).where(*conditions)
    ) or 0
    inflow = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            *conditions, Transaction.amount_minor > 0
        )
    ) or 0
    outflow = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            *conditions, Transaction.amount_minor < 0
        )
    ) or 0

    rows = session.scalars(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.posted_on.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return TransactionPage(
        items=[_to_out(row, user.currency) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        summary=SummaryOut(
            inflow_minor=inflow,
            inflow=format_minor(inflow, user.currency),
            outflow_minor=outflow,
            outflow=format_minor(outflow, user.currency),
            net_minor=inflow + outflow,
            net=format_minor(inflow + outflow, user.currency),
            count=total,
        ),
    )


@router.post("/imports/preview", response_model=ImportPreviewOut)
async def preview_import(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    account_id: Annotated[int, Form()],
) -> ImportPreviewOut:
    account = session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    content = await file.read()
    try:
        analysis = import_service.analyse(
            session,
            user_id=user.id,
            account_id=account.id,
            content=content,
            filename=file.filename or "upload.csv",
        )
    except import_service.StatementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImportPreviewOut(**import_service.preview_payload(analysis, currency=user.currency))


@router.post("/imports/commit", response_model=ImportResultOut)
async def commit_import(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    account_id: Annotated[int, Form()],
) -> ImportResultOut:
    account = session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    content = await file.read()
    try:
        result = import_service.commit(
            session,
            user_id=user.id,
            account_id=account.id,
            content=content,
            filename=file.filename or "upload.csv",
            currency=user.currency,
        )
    except import_service.StatementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImportResultOut(
        batch_id=result.batch_id,
        total_rows=result.total_rows,
        imported=result.imported,
        skipped=result.skipped,
        errors=result.errors,
        currency=result.currency,
    )


@router.post("/dev/seed", response_model=SeedOut)
def seed(session: SessionDep, user: CurrentUser, months: int = 18, seed: int = 42) -> SeedOut:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")
    if not 1 <= months <= 36:
        raise HTTPException(status_code=400, detail="months must be between 1 and 36")

    result = seed_demo_data(session, months=months, seed=seed, currency=user.currency)
    return SeedOut(
        created=result.created,
        skipped=result.skipped,
        months=result.months,
        start=result.start,
        end=result.end,
    )
