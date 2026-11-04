"""Categorisation service: load evidence, decide, persist, learn.

The interesting logic lives in :mod:`app.domain.categorisation`; this module is
the persistence and orchestration shell around it. Three behaviours are worth
calling out because they are product decisions, not plumbing:

* **Assignments are sticky.** Re-running the engine only fills rows that have no
  category. A machine pass must never overwrite a human decision.
* **A correction generalises.** Choosing a category for one transaction updates
  merchant memory and re-decides the *other* rows for that merchant — except
  rows a user rule or a manual pick already owns, because those are more
  specific intent.
* **Removing a rule is not retroactive.** History keeps the categories it had;
  deleting a rule changes future decisions only. Rewriting the past when a rule
  changes would make every total unstable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Category, CategoryRule, MerchantMemory, Transaction, User
from app.domain.categorisation import (
    Categoriser,
    Decision,
    MatchField,
    MatchType,
    MemoryEntry,
    Rule,
    RuleError,
    RuleOrigin,
)
from app.domain.enums import CategoryKind, CategorySource
from app.services import taxonomy
from app.services.seed_rules import SEED_RULES

#: Sources a machine pass must never rewrite: a human chose them explicitly.
LOCKED_SOURCES = frozenset({CategorySource.MANUAL.value, CategorySource.OVERRIDE.value})

#: Sources that memory is allowed to replace: seed guesses and older memory.
SOFT_SOURCES = frozenset(
    {
        CategorySource.UNKNOWN.value,
        CategorySource.SEED.value,
        CategorySource.MEMORY.value,
    }
)


@dataclass(frozen=True, slots=True)
class RuleInput:
    pattern: str
    category_id: int | None = None
    match_type: MatchType = MatchType.CONTAINS
    field: MatchField = MatchField.MERCHANT
    priority: int = 100
    confidence: float = 0.9
    is_transfer: bool = False


@dataclass(frozen=True, slots=True)
class ApplyResult:
    applied: int
    remaining: int
    by_source: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssignOutcome:
    updated: int
    propagated: int
    learned: bool
    category: str | None


@dataclass(frozen=True, slots=True)
class ReviewGroup:
    merchant: str
    count: int
    total_minor: int
    first_on: object
    last_on: object
    sample_raw: str


@dataclass(frozen=True, slots=True)
class RulePreview:
    matched: int
    uncategorised: int
    sample: list[tuple[str, int]]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_rules(
    session: Session, user_id: int, *, include_inactive: bool = False
) -> list[Rule]:
    """Materialise this user's rules as pure domain objects."""
    query = (
        select(CategoryRule, Category.name)
        .outerjoin(Category, CategoryRule.category_id == Category.id)
        .where(CategoryRule.user_id == user_id)
        .order_by(CategoryRule.priority.desc(), CategoryRule.id)
    )
    if not include_inactive:
        query = query.where(CategoryRule.is_active.is_(True))

    rules: list[Rule] = []
    for row, category_name in session.execute(query):
        try:
            rules.append(
                Rule(
                    id=row.id,
                    pattern=row.pattern,
                    category=category_name,
                    match_type=MatchType(row.match_type),
                    field=MatchField(row.field),
                    priority=row.priority,
                    confidence=row.confidence,
                    origin=RuleOrigin(row.origin),
                    is_transfer=row.is_transfer,
                )
            )
        except (RuleError, ValueError):
            # A row that can no longer be interpreted (category deleted, value
            # edited out of range) is skipped rather than crashing every request.
            continue
    return rules


def load_memory(session: Session, user_id: int) -> dict[str, MemoryEntry]:
    rows = session.execute(
        select(MerchantMemory.merchant_norm, Category.name, MerchantMemory.hits)
        .join(Category, MerchantMemory.category_id == Category.id)
        .where(MerchantMemory.user_id == user_id)
    )
    return {merchant: MemoryEntry(category=name, hits=hits) for merchant, name, hits in rows}


def categoriser_for(session: Session, user_id: int) -> Categoriser:
    return Categoriser(load_rules(session, user_id), load_memory(session, user_id))


# ---------------------------------------------------------------------------
# Applying decisions
# ---------------------------------------------------------------------------


def _write_decision(
    transaction: Transaction, decision: Decision, *, category_id: int | None
) -> None:
    transaction.category_id = category_id
    transaction.category_source = decision.source.value
    transaction.confidence = decision.confidence
    transaction.category_rule_id = decision.rule_id
    if decision.is_transfer:
        transaction.is_transfer = True


def _category_lookup(session: Session, user_id: int) -> dict[str, int]:
    return dict(
        session.execute(
            select(Category.name, Category.id).where(Category.user_id == user_id)
        ).all()
    )


def apply_pending(
    session: Session, *, user_id: int, categoriser: Categoriser | None = None
) -> ApplyResult:
    """Categorise every row that currently has no category."""
    engine = categoriser or categoriser_for(session, user_id)
    lookup = _category_lookup(session, user_id)

    rows = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.category_id.is_(None),
        )
    ).all()

    by_source: dict[str, int] = {}
    applied = 0
    for transaction in rows:
        decision = engine.decide(
            merchant=transaction.merchant_norm, raw=transaction.merchant_raw
        )
        if decision.category is None:
            continue
        category_id = lookup.get(decision.category)
        if category_id is None:
            continue
        _write_decision(transaction, decision, category_id=category_id)
        by_source[decision.source.value] = by_source.get(decision.source.value, 0) + 1
        applied += 1

    session.commit()
    remaining = session.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id, Transaction.category_id.is_(None)
        )
    )
    return ApplyResult(applied=applied, remaining=remaining or 0, by_source=by_source)


# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------


def _remember(
    session: Session, user_id: int, merchant_norm: str, category: Category
) -> MemoryEntry:
    row = session.scalar(
        select(MerchantMemory).where(
            MerchantMemory.user_id == user_id, MerchantMemory.merchant_norm == merchant_norm
        )
    )
    if row is None:
        row = MerchantMemory(
            user_id=user_id,
            merchant_norm=merchant_norm,
            category_id=category.id,
            hits=1,
        )
        session.add(row)
    else:
        row.category_id = category.id
        row.hits += 1
        row.last_confirmed_at = datetime.now(UTC)
    session.flush()
    return MemoryEntry(category=category.name, hits=row.hits)


def _apply_category(transaction: Transaction, category: Category, source: CategorySource,
                    confidence: float) -> None:
    transaction.category_id = category.id
    transaction.category_source = source.value
    transaction.confidence = confidence
    transaction.category_rule_id = None
    if category.kind == CategoryKind.TRANSFER.value:
        transaction.is_transfer = True


def _propagate(
    session: Session,
    *,
    user_id: int,
    merchant_norm: str,
    category: Category,
    memory: MemoryEntry,
    exclude_id: int | None = None,
) -> int:
    """Re-decide sibling rows of a merchant from the learned choice."""
    query = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.merchant_norm == merchant_norm,
        Transaction.category_source.in_(SOFT_SOURCES),
    )
    if exclude_id is not None:
        query = query.where(Transaction.id != exclude_id)

    updated = 0
    for sibling in session.scalars(query).all():
        _apply_category(sibling, category, CategorySource.MEMORY, memory.confidence)
        updated += 1
    return updated


def set_transaction_category(
    session: Session,
    *,
    user: User,
    transaction: Transaction,
    category: Category | None,
    remember: bool = True,
) -> AssignOutcome:
    """Set one transaction's category, optionally teaching merchant memory."""
    if category is None:
        transaction.category_id = None
        transaction.category_source = CategorySource.UNKNOWN.value
        transaction.confidence = None
        transaction.category_rule_id = None
        session.commit()
        return AssignOutcome(updated=1, propagated=0, learned=False, category=None)

    _apply_category(transaction, category, CategorySource.MANUAL, 1.0)
    propagated = 0
    memory: MemoryEntry | None = None
    if remember:
        memory = _remember(session, user.id, transaction.merchant_norm, category)
        propagated = _propagate(
            session,
            user_id=user.id,
            merchant_norm=transaction.merchant_norm,
            category=category,
            memory=memory,
            exclude_id=transaction.id,
        )
    session.commit()
    return AssignOutcome(
        updated=1,
        propagated=propagated,
        learned=memory is not None,
        category=category.name,
    )


def assign_merchant(
    session: Session,
    *,
    user: User,
    merchant_norm: str,
    category: Category,
    remember: bool = True,
) -> AssignOutcome:
    """Assign every row of one merchant — the review queue's bulk action."""
    rows = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.merchant_norm == merchant_norm,
            Transaction.category_source.not_in(LOCKED_SOURCES),
        )
    ).all()
    if not rows:
        raise LookupError("No transactions for that merchant.")

    for row in rows:
        _apply_category(row, category, CategorySource.MANUAL, 1.0)

    memory: MemoryEntry | None = None
    if remember:
        memory = _remember(session, user.id, merchant_norm, category)
    session.commit()
    return AssignOutcome(
        updated=len(rows),
        propagated=0,
        learned=memory is not None,
        category=category.name,
    )


def review_groups(session: Session, user_id: int) -> list[ReviewGroup]:
    """Uncategorised rows grouped by merchant, biggest offenders first."""
    rows = session.execute(
        select(
            Transaction.merchant_norm,
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount_minor), 0),
            func.min(Transaction.posted_on),
            func.max(Transaction.posted_on),
            func.min(Transaction.merchant_raw),
        )
        .where(Transaction.user_id == user_id, Transaction.category_id.is_(None))
        .group_by(Transaction.merchant_norm)
        .order_by(func.count(Transaction.id).desc(), Transaction.merchant_norm)
    ).all()

    return [
        ReviewGroup(
            merchant=merchant,
            count=count,
            total_minor=total,
            first_on=first_on,
            last_on=last_on,
            sample_raw=sample_raw or merchant,
        )
        for merchant, count, total, first_on, last_on, sample_raw in rows
    ]


def unknown_count(session: Session, user_id: int) -> int:
    return (
        session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id, Transaction.category_id.is_(None)
            )
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------


def ensure_seed_rules(session: Session, user: User) -> int:
    """Install the built-in rules for an account. Idempotent."""
    categories = taxonomy.ensure_categories(session, user)
    existing = {
        (row.pattern, row.match_type, row.field)
        for row in session.scalars(
            select(CategoryRule).where(
                CategoryRule.user_id == user.id,
                CategoryRule.origin == RuleOrigin.SEED.value,
            )
        )
    }

    created = 0
    for rule in SEED_RULES:
        key = (rule.pattern, rule.match_type.value, rule.field.value)
        if key in existing:
            continue
        category_id = categories.get(rule.category) if rule.category else None
        if category_id is None and not rule.is_transfer:
            continue
        session.add(
            CategoryRule(
                user_id=user.id,
                pattern=rule.pattern,
                match_type=rule.match_type.value,
                field=rule.field.value,
                category_id=category_id,
                priority=rule.priority,
                confidence=rule.confidence,
                origin=RuleOrigin.SEED.value,
                is_transfer=rule.is_transfer,
                is_active=True,
            )
        )
        created += 1
    session.commit()
    return created


def rule_usage(session: Session, user_id: int) -> dict[int, int]:
    rows = session.execute(
        select(Transaction.category_rule_id, func.count(Transaction.id))
        .where(Transaction.user_id == user_id, Transaction.category_rule_id.is_not(None))
        .group_by(Transaction.category_rule_id)
    )
    return dict(rows.all())


def _validate_rule(
    session: Session, *, user_id: int, pattern: str, category_id: int | None,
    match_type: MatchType, field: MatchField, priority: int, confidence: float,
    is_transfer: bool,
) -> Category:
    category = None
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None or category.user_id != user_id:
            raise LookupError("Category not found.")

    Rule(
        pattern=pattern,
        category=category.name if category else None,
        match_type=match_type,
        field=field,
        priority=priority,
        confidence=confidence,
        is_transfer=is_transfer,
    )
    if category is None:
        raise RuleError("A rule must set a category, mark the row as a transfer, or both.")
    return category


def create_rule(session: Session, *, user: User, data: RuleInput) -> CategoryRule:
    category = _validate_rule(
        session,
        user_id=user.id,
        pattern=data.pattern,
        category_id=data.category_id,
        match_type=data.match_type,
        field=data.field,
        priority=data.priority,
        confidence=data.confidence,
        is_transfer=data.is_transfer,
    )
    duplicate = session.scalar(
        select(CategoryRule).where(
            CategoryRule.user_id == user.id,
            CategoryRule.origin == RuleOrigin.USER.value,
            CategoryRule.pattern == data.pattern.strip(),
            CategoryRule.match_type == data.match_type.value,
            CategoryRule.field == data.field.value,
        )
    )
    if duplicate is not None:
        raise RuleError("An identical rule already exists. Edit that one instead.")

    row = CategoryRule(
        user_id=user.id,
        pattern=data.pattern.strip(),
        match_type=data.match_type.value,
        field=data.field.value,
        category_id=category.id,
        priority=data.priority,
        confidence=data.confidence,
        origin=RuleOrigin.USER.value,
        is_transfer=data.is_transfer,
        is_active=True,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_rule(
    session: Session, *, user: User, row: CategoryRule, changes: Mapping[str, Any]
) -> CategoryRule:
    merged = {
        "pattern": changes.get("pattern", row.pattern),
        "category_id": changes.get("category_id", row.category_id),
        "match_type": MatchType(changes.get("match_type", row.match_type)),
        "field": MatchField(changes.get("field", row.field)),
        "priority": changes.get("priority", row.priority),
        "confidence": changes.get("confidence", row.confidence),
        "is_transfer": changes.get("is_transfer", row.is_transfer),
    }
    category = _validate_rule(session, user_id=user.id, **merged)

    row.pattern = str(merged["pattern"]).strip()
    row.match_type = merged["match_type"].value
    row.field = merged["field"].value
    row.category_id = category.id
    row.priority = int(merged["priority"])
    row.confidence = float(merged["confidence"])
    row.is_transfer = bool(merged["is_transfer"])
    if "is_active" in changes:
        row.is_active = bool(changes["is_active"])
    session.commit()
    session.refresh(row)
    return row


def delete_rule(session: Session, row: CategoryRule) -> None:
    session.delete(row)
    session.commit()


def preview_rule(session: Session, *, user_id: int, rule: Rule) -> RulePreview:
    """Dry run: what would this rule match, before it is saved?"""
    rows: Sequence[tuple[str, str, int, int | None]] = session.execute(
        select(
            Transaction.merchant_norm,
            Transaction.merchant_raw,
            Transaction.amount_minor,
            Transaction.category_id,
        ).where(Transaction.user_id == user_id)
    ).all()

    matched = 0
    uncategorised = 0
    sample: list[tuple[str, int]] = []
    for merchant, raw, amount, category_id in rows:
        if not rule.matches(merchant=merchant, raw=raw):
            continue
        matched += 1
        if category_id is None:
            uncategorised += 1
        if len(sample) < 5:
            sample.append((merchant, amount))
    return RulePreview(matched=matched, uncategorised=uncategorised, sample=sample)
