"""The default category taxonomy.

Every account starts with the same fifteen system categories. They are created
once, are editable in name only, and are what seed rules and imports point at —
without them, a fresh database has nowhere to put a categorised transaction.

Kept in its own module (rather than inside the demo generator) because a user
who only ever imports CSVs needs the taxonomy just as much as the demo does.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, User
from app.domain.enums import CategoryKind

SYSTEM_CATEGORIES: tuple[tuple[str, CategoryKind], ...] = (
    ("Salary", CategoryKind.INCOME),
    ("Interest", CategoryKind.INCOME),
    ("Rent", CategoryKind.EXPENSE),
    ("Groceries", CategoryKind.EXPENSE),
    ("Dining", CategoryKind.EXPENSE),
    ("Transport", CategoryKind.EXPENSE),
    ("Utilities", CategoryKind.EXPENSE),
    ("Subscriptions", CategoryKind.EXPENSE),
    ("Shopping", CategoryKind.EXPENSE),
    ("Health", CategoryKind.EXPENSE),
    ("Education", CategoryKind.EXPENSE),
    ("Investments", CategoryKind.EXPENSE),
    ("Insurance", CategoryKind.EXPENSE),
    ("Fees", CategoryKind.EXPENSE),
    ("Transfers", CategoryKind.TRANSFER),
)

TRANSFER_CATEGORY = "Transfers"


def ensure_categories(session: Session, user: User) -> dict[str, int]:
    """Create any missing system category. Returns ``name → id``, idempotent."""
    existing = {
        category.name: category
        for category in session.scalars(select(Category).where(Category.user_id == user.id))
    }

    for order, (name, kind) in enumerate(SYSTEM_CATEGORIES):
        if name in existing:
            continue
        category = Category(
            user_id=user.id,
            name=name,
            kind=kind.value,
            is_system=True,
            sort_order=order,
        )
        session.add(category)
        session.flush()
        existing[name] = category

    return {name: existing[name].id for name in existing}
