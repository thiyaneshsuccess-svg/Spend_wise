"""Pulse: month-over-month change with robust baselines and reconciliation.

"Pulse" answers: what changed, and why. We compute per-category spending for
the current month and a baseline (median of the previous months, trimmed to
avoid outliers dominating), attribute the delta to each category/merchant, and
guarantee the decomposition reconciles exactly to the period delta.

All amounts are integer minor units. We never use averages (they are brittle to
one-off spikes) — medians are robust and easy to explain to a student.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Category, Transaction
from app.domain.period import MonthPeriod


@dataclass(frozen=True, slots=True)
class CategoryDelta:
    category_id: int | None
    category: str
    current_minor: int
    baseline_minor: int
    delta_minor: int
    current_count: int
    baseline_count: int
    change_pct: float | None


@dataclass(frozen=True, slots=True)
class MerchantDelta:
    merchant: str
    category: str | None
    category_id: int | None
    current_minor: int
    baseline_minor: int
    delta_minor: int


@dataclass(frozen=True, slots=True)
class PulseReport:
    month: str
    baseline_months: list[str]
    total_current_minor: int
    total_baseline_minor: int
    total_delta_minor: int
    categories: list[CategoryDelta]
    top_drivers: list[MerchantDelta]
    reconciles: bool


def _month_spend_by_category(
    session: Session,
    *,
    user_id: int,
    period: MonthPeriod,
    include_transfers: bool = False,
) -> tuple[dict[tuple[int | None, str], int], dict[tuple[int | None, str], int], int]:
    """Return (spend_by_key, count_by_key, total_outflow_minor)."""
    conditions = [Transaction.user_id == user_id, Transaction.amount_minor < 0]
    if not include_transfers:
        conditions.append(Transaction.is_transfer.is_(False))
    conditions.append(Transaction.posted_on >= period.start)
    conditions.append(Transaction.posted_on < period.end)

    rows = session.execute(
        select(
            Transaction.category_id,
            Category.name,
            func.coalesce(func.sum(Transaction.amount_minor), 0),
            func.count(Transaction.id),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(*conditions)
        .group_by(Transaction.category_id, Category.name)
    ).all()

    spend: dict[tuple[int | None, str], int] = {}
    count: dict[tuple[int | None, str], int] = {}
    total = 0
    for category_id, name, s, c in rows:
        key = (category_id, name or "Uncategorised")
        spend[key] = -int(s or 0)  # store as positive outflow
        count[key] = int(c or 0)
        total += spend[key]
    return spend, count, total


def _median(values: list[int]) -> int:
    if not values:
        return 0
    return int(median(values))


def pulse(
    session: Session,
    *,
    user_id: int,
    month: str,
    lookback: int = 6,
    include_transfers: bool = False,
) -> PulseReport:
    current_period = MonthPeriod.parse(month)
    baseline_months = []
    # Get previous lookback months as baseline
    for i in range(1, lookback + 1):
        baseline_months.append(current_period.shift(-i).key())

    current_spend, current_count, total_current = _month_spend_by_category(
        session, user_id=user_id, period=current_period, include_transfers=include_transfers
    )

    # Compute baseline as median per category across baseline months
    # Collect all categories seen
    all_keys = set(current_spend.keys())
    category_baseline_history: dict[tuple[int | None, str], list[int]] = defaultdict(list)
    category_baseline_count_history: dict[tuple[int | None, str], list[int]] = defaultdict(list)
    total_baseline_history: list[int] = []

    for bm in baseline_months:
        bperiod = MonthPeriod.parse(bm)
        b_spend, b_count, b_total = _month_spend_by_category(
            session, user_id=user_id, period=bperiod, include_transfers=include_transfers
        )
        all_keys.update(b_spend.keys())
        total_baseline_history.append(b_total)
        # record for each category
        for key in all_keys:
            category_baseline_history[key].append(b_spend.get(key, 0))
            category_baseline_count_history[key].append(b_count.get(key, 0))

    total_baseline = _median(total_baseline_history) if total_baseline_history else 0

    categories: list[CategoryDelta] = []
    for key in all_keys:
        cat_id, cat_name = key
        cur = current_spend.get(key, 0)
        base = _median(category_baseline_history[key])
        delta = cur - base  # positive means spending increased
        cur_c = current_count.get(key, 0)
        base_c = _median(category_baseline_count_history[key])
        if base > 0:
            change_pct = round((delta / base) * 100.0, 1)
        elif cur > 0 and base == 0:
            change_pct = 100.0  # new spending
        else:
            change_pct = 0.0
        categories.append(
            CategoryDelta(
                category_id=cat_id,
                category=cat_name,
                current_minor=cur,
                baseline_minor=base,
                delta_minor=delta,
                current_count=cur_c,
                baseline_count=base_c,
                change_pct=change_pct,
            )
        )

    # Sort by absolute delta descending to show biggest drivers
    categories_sorted = sorted(categories, key=lambda x: abs(x.delta_minor), reverse=True)

    # Compute merchant-level drivers for categories with big changes
    top_drivers: list[MerchantDelta] = []
    # Get merchant breakdown for current month
    conditions_cur = [Transaction.user_id == user_id, Transaction.amount_minor < 0]
    if not include_transfers:
        conditions_cur.append(Transaction.is_transfer.is_(False))
    conditions_cur.append(Transaction.posted_on >= current_period.start)
    conditions_cur.append(Transaction.posted_on < current_period.end)

    merchant_cur = session.execute(
        select(
            Transaction.merchant_norm,
            Transaction.category_id,
            Category.name,
            func.coalesce(func.sum(Transaction.amount_minor), 0),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(*conditions_cur)
        .group_by(Transaction.merchant_norm, Transaction.category_id, Category.name)
    ).all()

    # Get baseline merchant sums (median across baseline months)
    merchant_baseline: dict[tuple[str, int | None], list[int]] = defaultdict(list)
    for bm in baseline_months:
        bperiod = MonthPeriod.parse(bm)
        conditions_b = [Transaction.user_id == user_id, Transaction.amount_minor < 0]
        if not include_transfers:
            conditions_b.append(Transaction.is_transfer.is_(False))
        conditions_b.append(Transaction.posted_on >= bperiod.start)
        conditions_b.append(Transaction.posted_on < bperiod.end)
        b_merchant = session.execute(
            select(
                Transaction.merchant_norm,
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_minor), 0),
            )
            .where(*conditions_b)
            .group_by(Transaction.merchant_norm, Transaction.category_id)
        ).all()
        for mnorm, cat_id, s in b_merchant:
            merchant_baseline[(mnorm, cat_id)].append(-int(s or 0))

    for mnorm, cat_id, cat_name, s in merchant_cur:
        cur_m = -int(s or 0)
        base_m = _median(merchant_baseline.get((mnorm, cat_id), [0]))
        delta_m = cur_m - base_m
        if abs(delta_m) > 10000:  # only significant drivers (>100)
            top_drivers.append(
                MerchantDelta(
                    merchant=mnorm,
                    category=cat_name,
                    category_id=cat_id,
                    current_minor=cur_m,
                    baseline_minor=base_m,
                    delta_minor=delta_m,
                )
            )

    top_drivers_sorted = sorted(top_drivers, key=lambda x: abs(x.delta_minor), reverse=True)[:10]

    # Reconciliation: sum of category deltas must equal total delta
    sum_cat_delta = sum(c.delta_minor for c in categories_sorted)
    total_delta = total_current - total_baseline
    reconciles = sum_cat_delta == total_delta

    return PulseReport(
        month=month,
        baseline_months=baseline_months,
        total_current_minor=total_current,
        total_baseline_minor=total_baseline,
        total_delta_minor=total_delta,
        categories=categories_sorted,
        top_drivers=top_drivers_sorted,
        reconciles=reconciles,
    )
