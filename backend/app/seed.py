"""Seed the database with the synthetic demo ledger.

Usage:
    python -m app.seed --months 18 --seed 42

Requires the schema to exist (``alembic upgrade head``). The CLI fails with a
clear hint rather than silently creating tables behind the migration's back.
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import inspect, select
from sqlalchemy.exc import OperationalError

from app.db.models import User
from app.db.session import SessionLocal, engine
from app.services.categorisation_service import ensure_seed_rules
from app.services.demo_data import seed_demo_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SpendWise with demo data")
    parser.add_argument("--months", type=int, default=18)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--currency", default="INR")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=None,
        help="Last day of generated data (YYYY-MM-DD); defaults to the end of last month",
    )
    args = parser.parse_args()

    if "transactions" not in inspect(engine).get_table_names():
        print("Schema missing. Run: alembic upgrade head")
        raise SystemExit(1)

    try:
        with SessionLocal() as session:
            result = seed_demo_data(
                session,
                months=args.months,
                seed=args.seed,
                end=args.end,
                currency=args.currency,
            )
            user = session.scalar(select(User).order_by(User.id))
            rules = ensure_seed_rules(session, user) if user is not None else 0
    except OperationalError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc

    if result.skipped:
        print(
            f"Ledger already has data ({result.start} to {result.end}); nothing inserted. "
            f"Added {rules} missing seed rules."
        )
        return
    # ASCII only: the Windows console defaults to cp1252 and chokes on arrows.
    print(f"Seeded {result.created} transactions over {args.months} months "
          f"({result.start} to {result.end}) and {rules} seed rules.")


if __name__ == "__main__":
    main()
