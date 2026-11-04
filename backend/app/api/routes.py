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
    AssignCategoryIn,
    AssignMerchantIn,
    AssignOut,
    BreakdownOut,
    CategoriseRunOut,
    CategoryOut,
    CategorySpendOut,
    PulseCategoryDeltaOut,
    PulseMerchantDeltaOut,
    PulseOut,
    HealthOut,
    ImportPreviewOut,
    ImportResultOut,
    MetaOut,
    ReviewGroupOut,
    ReviewOut,
    RuleCreate,
    RuleMutationOut,
    RuleOut,
    RulePreviewIn,
    RulePreviewMatchOut,
    RulePreviewOut,
    RuleUpdate,
    SeedOut,
    SummaryOut,
    TransactionOut,
    TransactionPage,
)
from app.config import get_settings
from app.db.models import Account, Category, CategoryRule, Transaction
from app.domain.categorisation import MatchField, MatchType, Rule, RuleError, RuleOrigin
from app.domain.money import format_minor
from app.domain.period import MonthPeriod
from app.services import categorisation_service, import_service, ledger_summary, pulse_service
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
        confidence=transaction.confidence,
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
    rule_count = session.scalar(
        select(func.count(CategoryRule.id)).where(CategoryRule.user_id == user.id)
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
        unknown_count=categorisation_service.unknown_count(session, user.id),
        rule_count=rule_count or 0,
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


@router.get("/breakdown", response_model=BreakdownOut)
def category_breakdown(
    session: SessionDep,
    user: CurrentUser,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{1,2}$")] = None,
    include_transfers: bool = False,
) -> BreakdownOut:
    """Where the money went, grouped into categories the user can recognise."""
    try:
        slices = ledger_summary.category_spend(
            session, user_id=user.id, month=month, include_transfers=include_transfers
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = sum(item.spent_minor for item in slices)
    return BreakdownOut(
        month=month,
        total_spent_minor=total,
        total_spent=format_minor(-total, user.currency),
        slices=[
            CategorySpendOut(
                category_id=item.category_id,
                category=item.category,
                spent_minor=item.spent_minor,
                spent=format_minor(-item.spent_minor, user.currency),
                count=item.count,
                share=round(item.spent_minor / total, 4) if total else 0.0,
            )
            for item in slices
        ],
    )


@router.get("/pulse", response_model=PulseOut)
def pulse(
    session: SessionDep,
    user: CurrentUser,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{1,2}$")],
    lookback: int = 6,
    include_transfers: bool = False,
) -> PulseOut:
    try:
        report = pulse_service.pulse(
            session, user_id=user.id, month=month, lookback=lookback, include_transfers=include_transfers
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PulseOut(
        month=report.month,
        baseline_months=report.baseline_months,
        total_current_minor=report.total_current_minor,
        total_current=format_minor(-report.total_current_minor, user.currency),
        total_baseline_minor=report.total_baseline_minor,
        total_baseline=format_minor(-report.total_baseline_minor, user.currency),
        total_delta_minor=report.total_delta_minor,
        total_delta=format_minor(-report.total_delta_minor, user.currency),
        categories=[
            PulseCategoryDeltaOut(
                category_id=c.category_id,
                category=c.category,
                current_minor=c.current_minor,
                current=format_minor(-c.current_minor, user.currency),
                baseline_minor=c.baseline_minor,
                baseline=format_minor(-c.baseline_minor, user.currency),
                delta_minor=c.delta_minor,
                delta=format_minor(-c.delta_minor, user.currency),
                current_count=c.current_count,
                baseline_count=c.baseline_count,
                change_pct=c.change_pct,
            )
            for c in report.categories
        ],
        top_drivers=[
            PulseMerchantDeltaOut(
                merchant=d.merchant,
                category=d.category,
                category_id=d.category_id,
                current_minor=d.current_minor,
                current=format_minor(-d.current_minor, user.currency),
                baseline_minor=d.baseline_minor,
                baseline=format_minor(-d.baseline_minor, user.currency),
                delta_minor=d.delta_minor,
                delta=format_minor(-d.delta_minor, user.currency),
            )
            for d in report.top_drivers
        ],
        reconciles=report.reconciles,
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


def _rule_out(rule: CategoryRule, applied: int) -> RuleOut:
    return RuleOut(
        id=rule.id,
        pattern=rule.pattern,
        match_type=rule.match_type,  # type: ignore[arg-type]
        field=rule.field,  # type: ignore[arg-type]
        category=rule.category.name if rule.category else None,
        category_id=rule.category_id,
        priority=rule.priority,
        confidence=rule.confidence,
        origin=rule.origin,
        is_transfer=rule.is_transfer,
        is_active=rule.is_active,
        applied_count=applied,
    )


def _rule_usage_for(session: SessionDep, user_id: int, rule_id: int) -> int:
    return (
        session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id, Transaction.category_rule_id == rule_id
            )
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=list[RuleOut])
def list_rules(session: SessionDep, user: CurrentUser) -> list[RuleOut]:
    usage = categorisation_service.rule_usage(session, user.id)
    rows = session.scalars(
        select(CategoryRule).where(CategoryRule.user_id == user.id)
    ).all()
    # User rules first, then by priority: the list mirrors the precedence order.
    ordered = sorted(
        rows, key=lambda row: (row.origin != RuleOrigin.USER.value, -row.priority, row.id)
    )
    return [_rule_out(row, usage.get(row.id, 0)) for row in ordered]


@router.post("/rules", response_model=RuleMutationOut, status_code=201)
def create_rule(
    payload: RuleCreate, session: SessionDep, user: CurrentUser
) -> RuleMutationOut:
    try:
        row = categorisation_service.create_rule(
            session,
            user=user,
            data=categorisation_service.RuleInput(
                pattern=payload.pattern,
                category_id=payload.category_id,
                match_type=MatchType(payload.match_type),
                field=MatchField(payload.field),
                priority=payload.priority,
                confidence=payload.confidence,
                is_transfer=payload.is_transfer,
            ),
        )
    except RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = categorisation_service.apply_pending(session, user_id=user.id)
    return RuleMutationOut(
        rule=_rule_out(row, _rule_usage_for(session, user.id, row.id)),
        applied=result.applied,
        remaining=result.remaining,
    )


@router.patch("/rules/{rule_id}", response_model=RuleMutationOut)
def update_rule(
    rule_id: int, payload: RuleUpdate, session: SessionDep, user: CurrentUser
) -> RuleMutationOut:
    row = session.get(CategoryRule, rule_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Rule not found")

    changes = payload.model_dump(exclude_unset=True)
    # ``None`` means "not supplied" for everything except clearing a category.
    changes = {k: v for k, v in changes.items() if v is not None or k == "category_id"}

    try:
        row = categorisation_service.update_rule(session, user=user, row=row, changes=changes)
    except RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = categorisation_service.apply_pending(session, user_id=user.id)
    return RuleMutationOut(
        rule=_rule_out(row, _rule_usage_for(session, user.id, row.id)),
        applied=result.applied,
        remaining=result.remaining,
    )


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: SessionDep, user: CurrentUser) -> None:
    row = session.get(CategoryRule, rule_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Rule not found")
    categorisation_service.delete_rule(session, row)


@router.post("/rules/preview", response_model=RulePreviewOut)
def preview_rule(
    payload: RulePreviewIn, session: SessionDep, user: CurrentUser
) -> RulePreviewOut:
    try:
        rule = Rule(
            pattern=payload.pattern,
            match_type=MatchType(payload.match_type),
            field=MatchField(payload.field),
        )
    except RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    preview = categorisation_service.preview_rule(session, user_id=user.id, rule=rule)
    return RulePreviewOut(
        matched=preview.matched,
        uncategorised=preview.uncategorised,
        sample=[
            RulePreviewMatchOut(
                merchant=merchant,
                amount_minor=amount,
                amount=format_minor(amount, user.currency),
            )
            for merchant, amount in preview.sample
        ],
    )


@router.post("/categorise/run", response_model=CategoriseRunOut)
def run_categorisation(session: SessionDep, user: CurrentUser) -> CategoriseRunOut:
    result = categorisation_service.apply_pending(session, user_id=user.id)
    return CategoriseRunOut(
        applied=result.applied, remaining=result.remaining, by_source=result.by_source
    )


@router.get("/review", response_model=ReviewOut)
def review_queue(session: SessionDep, user: CurrentUser) -> ReviewOut:
    groups = categorisation_service.review_groups(session, user.id)
    return ReviewOut(
        total_unknown=categorisation_service.unknown_count(session, user.id),
        groups=[
            ReviewGroupOut(
                merchant=group.merchant,
                count=group.count,
                total_minor=group.total_minor,
                total=format_minor(group.total_minor, user.currency),
                first_on=group.first_on,  # type: ignore[arg-type]
                last_on=group.last_on,  # type: ignore[arg-type]
                sample_raw=group.sample_raw,
            )
            for group in groups
        ],
    )


@router.post("/review/assign", response_model=AssignOut)
def assign_merchant(
    payload: AssignMerchantIn, session: SessionDep, user: CurrentUser
) -> AssignOut:
    category = session.get(Category, payload.category_id)
    if category is None or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")

    try:
        outcome = categorisation_service.assign_merchant(
            session,
            user=user,
            merchant_norm=payload.merchant.strip().upper(),
            category=category,
            remember=payload.remember,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AssignOut(
        updated=outcome.updated,
        propagated=outcome.propagated,
        learned=outcome.learned,
        category=outcome.category,
    )


@router.post("/transactions/{transaction_id}/category", response_model=AssignOut)
def set_transaction_category(
    transaction_id: int,
    payload: AssignCategoryIn,
    session: SessionDep,
    user: CurrentUser,
) -> AssignOut:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    category = None
    if payload.category_id is not None:
        category = session.get(Category, payload.category_id)
        if category is None or category.user_id != user.id:
            raise HTTPException(status_code=404, detail="Category not found")

    outcome = categorisation_service.set_transaction_category(
        session,
        user=user,
        transaction=transaction,
        category=category,
        remember=payload.remember,
    )
    return AssignOut(
        updated=outcome.updated,
        propagated=outcome.propagated,
        learned=outcome.learned,
        category=outcome.category,
    )


@router.post("/dev/seed", response_model=SeedOut)
def seed(session: SessionDep, user: CurrentUser, months: int = 18, seed: int = 42) -> SeedOut:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")
    if not 1 <= months <= 36:
        raise HTTPException(status_code=400, detail="months must be between 1 and 36")

    result = seed_demo_data(session, months=months, seed=seed, currency=user.currency)
    categorisation_service.ensure_seed_rules(session, user)
    return SeedOut(
        created=result.created,
        skipped=result.skipped,
        months=result.months,
        start=result.start,
        end=result.end,
    )
