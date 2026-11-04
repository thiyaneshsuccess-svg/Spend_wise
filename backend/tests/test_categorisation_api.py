"""API-level behaviour of categorisation: rules, overrides, review queue.

These tests go through HTTP on purpose. The precedence rules are unit-tested in
``test_categorisation.py``; what is asserted here is that the *service* honours
them when rows are actually written, which is where stickiness bugs live.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import LOCAL_USER_EMAIL
from app.db.models import Account, Category, Transaction, User

TODAY = date(2026, 10, 12)


@pytest.fixture()
def app_user(client, session: Session) -> User:  # type: ignore[no-untyped-def]
    """The user the API acts as, bootstrapped through the real dependency."""
    client.get("/api/meta")
    user = session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    assert user is not None
    return user


@pytest.fixture()
def bank(session: Session, app_user: User) -> Account:
    row = Account(user_id=app_user.id, name="Test Bank", kind="bank")
    session.add(row)
    session.commit()
    return row


def category_named(session: Session, user: User, name: str) -> Category:
    row = session.scalar(
        select(Category).where(Category.user_id == user.id, Category.name == name)
    )
    assert row is not None
    return row


def add_transaction(
    session: Session,
    *,
    user: User,
    account: Account,
    merchant: str,
    amount_minor: int = -1_000_00,
    raw: str | None = None,
    posted_on: date = TODAY,
) -> Transaction:
    row = Transaction(
        user_id=user.id,
        account_id=account.id,
        posted_on=posted_on,
        amount_minor=amount_minor,
        currency="INR",
        merchant_raw=raw or f"UPI/{merchant}/9998887776/Payment",
        merchant_norm=merchant,
        description=raw,
        category_source="unknown",
        is_transfer=False,
        dedupe_key=uuid.uuid4().hex,
        occurrence_index=0,
    )
    session.add(row)
    session.commit()
    return row


def test_new_account_starts_with_seed_rules(client, app_user) -> None:  # type: ignore[no-untyped-def]
    rules = client.get("/api/rules").json()

    assert len(rules) > 20
    assert all(rule["origin"] == "seed" for rule in rules)


def test_run_categorises_unknown_rows_and_leaves_the_rest_alone(
    client, session: Session, app_user, bank
) -> None:
    zepto = add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    mystery = add_transaction(session, user=app_user, account=bank, merchant="BLUE TOKAI COFFEE")

    response = client.post("/api/categorise/run")

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] == 1
    assert body["by_source"] == {"seed": 1}
    assert body["remaining"] == 1

    session.refresh(zepto)
    session.refresh(mystery)
    assert zepto.category is not None and zepto.category.name == "Groceries"
    assert zepto.category_source == "seed"
    assert mystery.category_id is None


def test_a_new_rule_categorises_pending_rows_immediately(
    client, session: Session, app_user, bank
) -> None:
    row = add_transaction(session, user=app_user, account=bank, merchant="BLUE TOKAI COFFEE")
    dining = category_named(session, app_user, "Dining")

    response = client.post(
        "/api/rules",
        json={"pattern": "BLUE TOKAI", "category_id": dining.id},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["applied"] == 1
    assert body["rule"]["origin"] == "user"
    assert body["rule"]["applied_count"] == 1

    session.refresh(row)
    assert row.category is not None and row.category.name == "Dining"
    assert row.category_source == "rule"


def test_rule_preview_counts_without_saving(client, session: Session, app_user, bank) -> None:
    add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    add_transaction(session, user=app_user, account=bank, merchant="BIGBASKET")

    response = client.post(
        "/api/rules/preview", json={"pattern": "zepto", "match_type": "contains"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 2
    assert body["uncategorised"] == 2
    assert len(body["sample"]) == 2
    assert body["sample"][0]["amount"].startswith("-")


def test_overrides_are_never_rewritten_by_a_machine_pass(
    client, session: Session, app_user, bank
) -> None:
    row = add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    shopping = category_named(session, app_user, "Shopping")

    client.post(
        f"/api/transactions/{row.id}/category",
        json={"category_id": shopping.id, "remember": False},
    )
    client.post("/api/categorise/run")

    session.refresh(row)
    assert row.category is not None and row.category.name == "Shopping"
    assert row.category_source == "manual"


def test_a_correction_teaches_memory_and_beats_the_seed_guess(
    client, session: Session, app_user, bank
) -> None:
    """The full loop: fix one row, siblings follow, new rows inherit the choice."""
    first = add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    sibling = add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    shopping = category_named(session, app_user, "Shopping")

    response = client.post(
        f"/api/transactions/{first.id}/category",
        json={"category_id": shopping.id, "remember": True},
    )

    assert response.status_code == 200
    outcome = response.json()
    assert outcome["learned"] is True
    assert outcome["propagated"] == 1

    session.refresh(first)
    session.refresh(sibling)
    assert first.category_source == "manual"
    assert sibling.category is not None and sibling.category.name == "Shopping"
    assert sibling.category_source == "memory"

    # A brand-new Zepto row now follows the correction, not the built-in rule.
    fresh = add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")
    client.post("/api/categorise/run")
    session.refresh(fresh)
    assert fresh.category is not None and fresh.category.name == "Shopping"
    assert fresh.category_source == "memory"


def test_user_rule_rows_are_not_rewritten_by_memory(
    client, session: Session, app_user, bank
) -> None:
    """A rule is explicit intent, so it outranks a later learned preference."""
    row = add_transaction(session, user=app_user, account=bank, merchant="SWIGGY")
    dining = category_named(session, app_user, "Dining")
    shopping = category_named(session, app_user, "Shopping")

    client.post("/api/rules", json={"pattern": "SWIGGY", "category_id": dining.id})
    manual = add_transaction(session, user=app_user, account=bank, merchant="SWIGGY")
    client.post(
        f"/api/transactions/{manual.id}/category",
        json={"category_id": shopping.id, "remember": True},
    )

    session.refresh(row)
    assert row.category is not None and row.category.name == "Dining"
    assert row.category_source == "rule"


def test_review_queue_groups_uncategorised_rows_by_merchant(
    client, session: Session, app_user, bank
) -> None:
    for _ in range(3):
        add_transaction(session, user=app_user, account=bank, merchant="BLUE TOKAI COFFEE")
    add_transaction(session, user=app_user, account=bank, merchant="BOOKMYSHOW")

    body = client.get("/api/review").json()

    assert body["total_unknown"] == 4
    assert [group["merchant"] for group in body["groups"]] == [
        "BLUE TOKAI COFFEE",
        "BOOKMYSHOW",
    ]
    top = body["groups"][0]
    assert top["count"] == 3
    assert top["total_minor"] == -3_000_00
    assert top["first_on"] == TODAY.isoformat()


def test_bulk_assign_from_the_review_queue_clears_the_group(
    client, session: Session, app_user, bank
) -> None:
    for _ in range(2):
        add_transaction(session, user=app_user, account=bank, merchant="BLUE TOKAI COFFEE")
    dining = category_named(session, app_user, "Dining")

    response = client.post(
        "/api/review/assign",
        json={"merchant": "BLUE TOKAI COFFEE", "category_id": dining.id},
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 2
    assert client.get("/api/review").json()["total_unknown"] == 0


def test_disabling_a_rule_stops_future_matches_without_rewriting_history(
    client, session: Session, app_user, bank
) -> None:
    history = add_transaction(session, user=app_user, account=bank, merchant="NETFLIX COM")
    client.post("/api/categorise/run")
    session.refresh(history)
    assert history.category is not None

    rules = client.get("/api/rules").json()
    netflix = next(rule for rule in rules if rule["pattern"] == "netflix")
    assert client.patch(f"/api/rules/{netflix['id']}", json={"is_active": False}).status_code == 200

    future = add_transaction(session, user=app_user, account=bank, merchant="NETFLIX COM")
    client.post("/api/categorise/run")

    session.refresh(history)
    session.refresh(future)
    assert history.category is not None  # history keeps what it had
    assert future.category_id is None  # the disabled rule stops deciding


def test_rule_validation_messages_are_actionable(client, app_user) -> None:  # type: ignore[no-untyped-def]
    response = client.post("/api/rules", json={"pattern": "!!!", "category_id": None})

    assert response.status_code == 422
    assert "at least one letter" in response.json()["detail"]


def test_a_category_from_another_user_cannot_be_used(
    client, session: Session, app_user
) -> None:  # type: ignore[no-untyped-def]
    other = User(email="other@example.com", display_name="Other")
    session.add(other)
    session.flush()
    foreign = Category(user_id=other.id, name="Smuggled", kind="expense")
    session.add(foreign)
    session.commit()

    response = client.post(
        "/api/rules", json={"pattern": "anything", "category_id": foreign.id}
    )

    assert response.status_code == 404


def test_meta_reports_the_review_backlog(client, session: Session, app_user, bank) -> None:  # type: ignore[no-untyped-def]
    add_transaction(session, user=app_user, account=bank, merchant="BOOKMYSHOW")

    meta = client.get("/api/meta").json()

    assert meta["unknown_count"] == 1
    assert meta["rule_count"] > 20


def test_breakdown_sums_outflows_by_category(client, session: Session, app_user, bank) -> None:
    for merchant, amount in (
        ("ZEPTO MARKETPLACE", -500_00),
        ("BIGBASKET", -100_00),
        ("OLA CABS", -200_00),
    ):
        add_transaction(
            session, user=app_user, account=bank, merchant=merchant, amount_minor=amount
        )
    client.post("/api/categorise/run")

    body = client.get("/api/breakdown?month=2026-10").json()

    by_name = {row["category"]: row for row in body["slices"]}
    assert by_name["Groceries"]["spent_minor"] == 600_00
    assert by_name["Groceries"]["count"] == 2
    assert by_name["Transport"]["spent_minor"] == 200_00
    assert body["total_spent_minor"] == 800_00
    assert sum(row["share"] for row in body["slices"]) == pytest.approx(1.0)
    # Largest first: the UI draws its bars in this order.
    assert body["slices"][0]["category"] == "Groceries"


def test_breakdown_keeps_unknown_spend_visible(client, session: Session, app_user, bank) -> None:
    add_transaction(
        session, user=app_user, account=bank, merchant="BLUE TOKAI COFFEE", amount_minor=-300_00
    )
    add_transaction(
        session, user=app_user, account=bank, merchant="ACME TECHNOLOGIES", amount_minor=9_000_00
    )
    client.post("/api/categorise/run")

    body = client.get("/api/breakdown?month=2026-10").json()

    # Inflows are not spending, and unknown spend must never be hidden.
    assert [row["category"] for row in body["slices"]] == ["Uncategorised"]
    assert body["total_spent_minor"] == 300_00


def test_breakdown_respects_the_month_window(client, session: Session, app_user, bank) -> None:
    add_transaction(
        session,
        user=app_user,
        account=bank,
        merchant="ZEPTO MARKETPLACE",
        posted_on=date(2026, 9, 3),
    )
    add_transaction(session, user=app_user, account=bank, merchant="ZEPTO MARKETPLACE")

    september = client.get("/api/breakdown?month=2026-09").json()
    october = client.get("/api/breakdown?month=2026-10").json()

    assert september["total_spent_minor"] == 1_000_00
    assert october["total_spent_minor"] == 1_000_00


def test_breakdown_rejects_a_malformed_month(client, app_user) -> None:
    assert client.get("/api/breakdown?month=2026-13").status_code == 400
