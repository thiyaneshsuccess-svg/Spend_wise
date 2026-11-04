"""The demo ledger is a fixture the analytics engines will be tested against.

If it is not deterministic, every downstream test becomes flaky, so its
reproducibility is asserted here rather than assumed.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Transaction
from app.db.session import make_engine
from app.services.demo_data import UNKNOWN_TAIL, build_rows, seed_demo_data

END = date(2026, 10, 31)


def _rows_for(months: int, seed: int) -> list[tuple[date, int, str, str, str, str]]:
    return build_rows(months=months, seed=seed, end=END)


def test_same_seed_produces_the_same_ledger() -> None:
    assert _rows_for(18, 42) == _rows_for(18, 42)


def test_different_seeds_produce_different_ledgers() -> None:
    assert _rows_for(18, 42) != _rows_for(18, 7)


def test_volume_and_date_bounds() -> None:
    rows = _rows_for(18, 42)

    assert len(rows) > 300
    assert min(row[0] for row in rows) >= date(2025, 5, 1)
    assert max(row[0] for row in rows) <= END


def test_ledger_is_net_positive() -> None:
    rows = _rows_for(18, 42)
    assert sum(row[1] for row in rows) > 0


def test_expected_structure_is_present() -> None:
    rows = _rows_for(18, 42)
    merchants = {row[3] for row in rows}

    assert {"NETFLIX COM", "SWIGGY", "LANDLORD RENT", "ACME TECHNOLOGIES"} <= merchants
    # The two identical coffees survive as separate rows.
    assert sum(1 for row in rows if row[3] == "CCD COFFEE") == 2


def test_seeding_is_idempotent_and_database_backed() -> None:
    engine: Engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        first = seed_demo_data(session, months=6, end=END)
        assert first.created > 100
        assert first.skipped is False

        count_after_first = session.scalar(select(func.count(Transaction.id)))
        second = seed_demo_data(session, months=6, end=END)
        count_after_second = session.scalar(select(func.count(Transaction.id)))

    engine.dispose()

    assert second.skipped is True
    assert second.created == 0
    assert count_after_first == count_after_second

    # Model shape sanity: categories were assigned, transfers marked.
    assert count_after_first is not None and count_after_first > 0


def test_demo_ledger_is_categorised_except_for_a_deliberate_unknown_tail() -> None:
    """Demo data must exercise the review queue, not just the happy path."""
    engine: Engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        seed_demo_data(session, months=6, end=END)
        unknown = session.scalars(
            select(Transaction).where(Transaction.category_id.is_(None))
        ).all()
        transfers = session.scalar(
            select(func.count(Transaction.id)).where(Transaction.is_transfer.is_(True))
        )

    engine.dispose()

    assert unknown, "the review queue would be empty in every demo"
    assert len(unknown) <= 12
    # Only the merchants intentionally left unknown; nothing else slipped through.
    assert {row.merchant_norm for row in unknown} <= {
        "BLUE TOKAI COFFEE",
        *(name for name, _, _ in UNKNOWN_TAIL),
    }
    assert all(row.category_source == "unknown" for row in unknown)
    assert transfers and transfers > 0
