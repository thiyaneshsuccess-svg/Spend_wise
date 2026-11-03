"""Import is the highest-risk surface: it decides what the ledger believes."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction
from app.services import import_service

SIGNED_CSV = b"""date,merchant,amount
01/10/2026,UPI/SWIGGY/1234/Payment,-450.00
01/10/2026,UPI/SWIGGY/1234/Payment,-450.00
02/10/2026,POS AMAZON INDIA,-1999.00
03/10/2026,SALARY CREDIT NEFT/ACME/991,92000.00
not-a-date,UNKNOWN ROW,-1.00
"""

DEBIT_CREDIT_CSV = b"""Date,Description,Debit,Credit
2026-10-05,RENT PAYMENT,28000,
2026-10-01,SALARY CREDIT,,92000.00
"""


def _user_id(session: Session, account: Account) -> int:
    return account.user_id


def test_parse_reports_bad_rows_without_importing_them(account: Account) -> None:
    analysis = import_service.parse_csv(SIGNED_CSV, account_id=account.id)

    assert analysis.total_rows == 5
    assert len(analysis.rows) == 4
    assert len(analysis.errors) == 1
    assert analysis.errors[0].line == 6
    assert "date" in analysis.errors[0].message.lower()


def test_identical_rows_in_one_file_are_both_kept(account: Account) -> None:
    analysis = import_service.parse_csv(SIGNED_CSV, account_id=account.id)
    swiggy = [row for row in analysis.rows if row.merchant_norm == "SWIGGY"]

    assert len(swiggy) == 2
    assert {row.occurrence_index for row in swiggy} == {0, 1}
    assert len({row.dedupe_key for row in swiggy}) == 2


def test_signs_are_normalised(session: Session, account: Account) -> None:
    result = import_service.commit(
        session,
        user_id=_user_id(session, account),
        account_id=account.id,
        content=SIGNED_CSV,
        filename="oct.csv",
    )

    assert result.imported == 4
    salary = session.scalar(
        select(Transaction.amount_minor).where(Transaction.amount_minor > 0)
    )
    amazon = session.scalar(
        select(Transaction.amount_minor).where(Transaction.merchant_norm == "AMAZON")
    )
    assert salary == 9_200_000
    assert amazon == -199_900


def test_reimporting_the_same_file_changes_nothing(session: Session, account: Account) -> None:
    user_id = _user_id(session, account)
    first = import_service.commit(
        session, user_id=user_id, account_id=account.id, content=SIGNED_CSV, filename="oct.csv"
    )
    second = import_service.commit(
        session, user_id=user_id, account_id=account.id, content=SIGNED_CSV, filename="oct.csv"
    )

    assert first.imported == 4
    assert second.imported == 0
    assert second.skipped == 4

    total = session.scalar(select(func.count(Transaction.id)))
    assert total == 4


def test_debit_credit_statements_are_supported(session: Session, account: Account) -> None:
    result = import_service.commit(
        session,
        user_id=account.user_id,
        account_id=account.id,
        content=DEBIT_CREDIT_CSV,
        filename="bank.csv",
    )

    assert result.imported == 2
    amounts = set(session.scalars(select(Transaction.amount_minor)))
    assert amounts == {-2_800_000, 9_200_000}


def test_unknown_categories_are_not_guessed(session: Session, account: Account) -> None:
    import_service.commit(
        session,
        user_id=account.user_id,
        account_id=account.id,
        content=SIGNED_CSV,
        filename="oct.csv",
    )

    sources = set(session.scalars(select(Transaction.category_source)))
    assert sources == {"unknown"}
    assert session.scalar(select(Transaction.category_id)) is None


def test_transfers_are_flagged(account: Account) -> None:
    content = b"""date,merchant,amount
2026-10-26,CREDIT CARD PAYMENT HDFC,-9000.00
"""
    analysis = import_service.parse_csv(content, account_id=account.id)
    assert analysis.rows[0].is_transfer is True


def test_missing_columns_fail_loudly(account: Account) -> None:
    content = b"""foo,bar
1,2
"""
    try:
        import_service.parse_csv(content, account_id=account.id)
    except import_service.StatementError as exc:
        assert "date column" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected StatementError")
