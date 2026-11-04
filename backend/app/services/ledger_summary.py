"""Read-side aggregates for the ledger screen.

Deliberately separate from ``categorisation_service``: this module decides
nothing. It only rolls up rows the categoriser has already labelled, and it does
the grouping in SQL so the cost stays flat as history grows.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Category, Transaction
from app.domain.period import MonthPeriod


@dataclass(frozen=True, slots=True)
class CategorySpend:
    category_id: int | None
    category: str
    spent_minor: int
    count: int


def category_spend(
    session: Session,
    *,
    user_id: int,
    month: str | None = None,
    include_transfers: bool = False,
) -> list[CategorySpend]:
    """Outflow per category for one month (or all time), largest first.

    Only outflows count: a salary credit is not a category of spending, and
    including it would make the bars meaningless. Transfers are excluded for
    the same reason — moving money between your own accounts is not spend.
    """
    conditions = [Transaction.user_id == user_id, Transaction.amount_minor < 0]
    if not include_transfers:
        conditions.append(Transaction.is_transfer.is_(False))
    if month:
        period = MonthPeriod.parse(month)
        conditions.append(Transaction.posted_on >= period.start)
        conditions.append(Transaction.posted_on < period.end)

    spent = func.sum(Transaction.amount_minor)
    rows = session.execute(
        select(
            Transaction.category_id,
            Category.name,
            spent,
            func.count(Transaction.id),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(*conditions)
        .group_by(Transaction.category_id, Category.name)
        .order_by(spent.asc())
    ).all()

    return [
        CategorySpend(
            category_id=category_id,
            category=name or "Uncategorised",
            spent_minor=-int(total or 0),
            count=int(count),
        )
        for category_id, name, total, count in rows
    ]
