"""Deterministic synthetic ledger.

A finance app with no data is a screenshot of an empty table. This generator
produces 18 months of *structured* personal finance — a salary with a raise, a
rent hike, seasonal electricity, weekend dining, an annual insurance premium, a
subscription price increase, one large anomalous purchase, and two identical
coffees on the same day — so the dashboard, the recurring detector and the
forecast all have something real to chew on from the first run.

Everything is driven by ``random.Random(seed)``: same seed, same ledger, byte for
byte. That determinism is what lets the analytics engines be tested against a
fixture instead of against whatever today's random numbers produce.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction, User
from app.domain.enums import AccountKind, CategorySource
from app.domain.period import MonthPeriod
from app.services.taxonomy import TRANSFER_CATEGORY, ensure_categories

#: A row the demo deliberately leaves uncategorised (empty category name).
UNCATEGORISED = ""

#: Merchants that appear only in the last few months and that no default rule
#: knows — the work the review queue exists for.
UNKNOWN_TAIL: tuple[tuple[str, int, int], ...] = (
    ("BOOKMYSHOW", 350, 1_100),
    ("METRO CARD RECHARGE", 200, 500),
    ("URBAN CLAP", 600, 2_400),
)

DEMO_ACCOUNTS: tuple[tuple[str, AccountKind, str | None, int], ...] = (
    ("HDFC Savings", AccountKind.BANK, "HDFC Bank", 125_000_00),
    ("Cash Wallet", AccountKind.CASH, None, 4_000_00),
    ("HDFC Millennia Card", AccountKind.CARD, "HDFC Bank", 0),
)


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    created: int
    months: int
    start: date | None
    end: date | None
    skipped: bool


def _ref(rng: random.Random) -> str:
    return str(rng.randint(10**9, 10**10 - 1))


def _rupees(low: int, high: int, rng: random.Random) -> int:
    return rng.randint(low, high) * 100


def _previous_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


def _day_in_month(period: MonthPeriod, day: int) -> date:
    return date(period.year, period.month, min(day, period.days))


def _weekend_day(rng: random.Random, period: MonthPeriod) -> date:
    """Pick a Saturday/Sunday inside the month (first four weeks only)."""
    first = date(period.year, period.month, 1)
    offset = (5 - first.weekday()) % 7  # days until Saturday
    saturdays = [first + timedelta(days=offset + 7 * k) for k in range(4)]
    chosen = rng.choice(saturdays)
    if rng.random() < 0.4:
        chosen += timedelta(days=1)
    return min(chosen, date(period.year, period.month, period.days))


def _ensure_user(session: Session, currency: str) -> User:
    user = session.scalar(select(User).order_by(User.id))
    if user is None:
        user = User(
            email="local@spendwise.app",
            display_name="Local User",
            currency=currency,
            timezone="Asia/Kolkata",
        )
        session.add(user)
        session.flush()
    return user


def _ensure_taxonomy(session: Session, user: User) -> dict[str, dict[str, int]]:
    """Create system categories and demo accounts. Returns name → [ids]."""
    categories = ensure_categories(session, user)

    existing_accounts = {
        a.name for a in session.scalars(select(Account).where(Account.user_id == user.id))
    }
    for name, kind, institution, opening in DEMO_ACCOUNTS:
        if name in existing_accounts:
            continue
        session.add(
            Account(
                user_id=user.id,
                name=name,
                kind=kind.value,
                institution=institution,
                opening_balance_minor=opening,
            )
        )
    session.flush()

    account_ids = {
        a.name: a.id for a in session.scalars(select(Account).where(Account.user_id == user.id))
    }
    return {"categories": categories, "accounts": account_ids}


def default_end(today: date | None = None) -> date:
    """Demo data covers *complete* months.

    Ending mid-month would open the app on a three-day stub of spending, which
    reads as an empty ledger on the very first screen — the opposite of what a
    demo dataset is for.
    """
    today = today or date.today()
    return today.replace(day=1) - timedelta(days=1)


def build_rows(
    *, months: int = 18, seed: int = 42, end: date | None = None
) -> list[tuple[date, int, str, str, str, str]]:
    """Generate (posted_on, amount_minor, raw, norm, category, account) rows."""
    rng = random.Random(seed)
    end = end or default_end()
    end_period = MonthPeriod.from_date(end)
    periods = [end_period.shift(-offset) for offset in range(months - 1, -1, -1)]
    rows: list[tuple[date, int, str, str, str, str]] = []

    def add(
        when: date, amount: int, raw: str, norm: str, category: str, account: str = "HDFC Savings"
    ) -> None:
        if when > end:
            return
        rows.append((when, amount, raw, norm, category, account))

    for index, period in enumerate(periods):
        # --- income -------------------------------------------------------
        salary = 92_000_00 if index < 10 else 106_000_00
        add(
            _previous_weekday(_day_in_month(period, 1)),
            salary,
            f"SALARY CREDIT NEFT/ACME TECHNOLOGIES/{_ref(rng)}",
            "ACME TECHNOLOGIES",
            "Salary",
        )
        if index % 6 == 3:
            add(
                _day_in_month(period, 28),
                _rupees(180, 420, rng),
                "INT CREDIT SB A/C",
                "INT CREDIT SB A C",
                "Interest",
            )

        # --- committed obligations ---------------------------------------
        rent = 28_000_00 if index < 12 else 29_680_00
        add(_day_in_month(period, 5), -rent, f"UPI/LANDLORD RENT/{_ref(rng)}/Payment",
            "LANDLORD RENT", "Rent")

        add(_day_in_month(period, 8), -999_00, "ACT FIBERNET AUTOPAY MANDATE",
            "ACT FIBERNET", "Utilities")

        seasonal = 900 if period.month in (4, 5, 6) else 0
        add(_day_in_month(period, 12), -_rupees(1_050 + seasonal, 2_600 + seasonal, rng),
            f"BESCOM ELECTRICITY BILL {_ref(rng)}", "BESCOM ELECTRICITY", "Utilities")

        add(_day_in_month(period, 15), -399_00, "JIO PREPAID RECHARGE",
            "JIO PREPAID RECHARGE", "Utilities")

        netflix = 649_00 if index < 9 else 799_00
        add(_day_in_month(period, 3), -netflix, "NETFLIX COM AUTOPAY",
            "NETFLIX COM", "Subscriptions")
        add(_day_in_month(period, 22), -119_00, "SPOTIFY INDIA",
            "SPOTIFY INDIA", "Subscriptions")
        add(_day_in_month(period, 7), -10_000_00, "SIP MUTUAL FUND NACH",
            "SIP MUTUAL FUND", "Investments")

        # --- groceries (weekly-ish) --------------------------------------
        grocery_merchants = (
            ("BIGBASKET", "BIGBASKET"),
            ("ZEPTO MARKETPLACE", "ZEPTO MARKETPLACE"),
            ("RELIANCE FRESH", "RELIANCE FRESH"),
        )
        for week in range(rng.choice((4, 4, 5))):
            day = 2 + week * 7 + rng.randint(0, 2)
            norm = rng.choice(grocery_merchants)
            add(_day_in_month(period, day), -_rupees(1_150, 3_150, rng),
                f"UPI/{norm[0]}/{_ref(rng)}/Payment", norm[1], "Groceries")

        # --- dining (weekend-weighted) ------------------------------------
        for _ in range(rng.choice((2, 3, 3, 4))):
            if rng.random() < 0.65:
                merchant = rng.choice(
                    (("SWIGGY", "SWIGGY"), ("ZOMATO", "ZOMATO"), ("DOMINOS", "DOMINOS PIZZA"))
                )
                when = _weekend_day(rng, period)
                amount = _rupees(280, 1_250, rng)
            else:
                merchant = rng.choice(
                    (("THIRD WAVE COFFEE", "THIRD WAVE COFFEE"), ("TRUFFLES", "TRUFFLES"))
                )
                when = _day_in_month(period, rng.randint(1, period.days))
                amount = _rupees(450, 1_950, rng)
            add(when, -amount, f"UPI/{merchant[0]}/{_ref(rng)}/Payment", merchant[1], "Dining")

        # --- transport ----------------------------------------------------
        for _ in range(2):
            add(_day_in_month(period, rng.randint(1, period.days)), -_rupees(1_400, 2_600, rng),
                f"POS {rng.randint(1000, 9999)} INDIAN OIL", "INDIAN OIL", "Transport")
        for _ in range(rng.choice((3, 4, 5))):
            ride = rng.choice((("UBER", "UBER"), ("OLA", "OLA CABS")))
            add(_day_in_month(period, rng.randint(1, period.days)), -_rupees(120, 460, rng),
                f"UPI/{ride[0]}/{_ref(rng)}/Payment", ride[1], "Transport")

        # --- discretionary shopping / health ------------------------------
        for _ in range(rng.choice((0, 1, 1, 2))):
            shop = rng.choice(
                (("AMAZON", "AMAZON"), ("FLIPKART", "FLIPKART"), ("MYNTRA", "MYNTRA"))
            )
            add(_day_in_month(period, rng.randint(1, period.days)), -_rupees(350, 3_600, rng),
                f"POS {rng.randint(1000, 9999)} {shop[0]} INDIA", shop[1], "Shopping")
        if rng.random() < 0.6:
            add(_day_in_month(period, rng.randint(1, period.days)), -_rupees(210, 940, rng),
                "APOLLO PHARMACY", "APOLLO PHARMACY", "Health")

        # --- transfers (not spending) -------------------------------------
        add(_day_in_month(period, 26), -_rupees(8_000, 15_000, rng),
            "CREDIT CARD PAYMENT HDFC", "HDFC CREDIT CARD", "Transfers")
        add(_day_in_month(period, 10), -5_000_00, "ATM CASH WITHDRAWAL",
            "ATM CASH WITHDRAWAL", "Transfers")
        add(_day_in_month(period, 11), 5_000_00, "IMPS TO SELF CASH WALLET",
            "IMPS TO SELF", "Transfers", "Cash Wallet")
        for _ in range(2):
            add(_day_in_month(period, rng.randint(12, period.days)), -_rupees(40, 220, rng),
                "CANTEEN", "CANTEEN", "Dining", "Cash Wallet")

        # --- one-off events ------------------------------------------------
        if index == 7:
            add(_day_in_month(period, 19), -79_900_00, "POS 8891 CROMA ELECTRONICS",
                "CROMA ELECTRONICS", "Shopping")
        if index == 4:
            add(_day_in_month(period, 16), -12_400_00, "HDFC LIFE INSURANCE PREMIUM",
                "HDFC LIFE INSURANCE", "Insurance")
        if index == 11:
            add(_day_in_month(period, 21), -8_900_00, "INDIGO AIRLINES 6E-2143",
                "INDIGO AIRLINES", "Transport")
        if index == 3:
            add(_day_in_month(period, 9), -3_500_00, "MANIPAL HOSPITAL ANNUAL CHECKUP",
                "MANIPAL HOSPITAL", "Health")
        if index == 9:
            add(_day_in_month(period, 14), 2_499_00, "REFUND AMAZON ORDER",
                "AMAZON REFUND", "Shopping")
        if index == 6:
            # Two identical coffees, same day, same amount: the duplicate case
            # that a naive content hash would silently collapse.
            day = _day_in_month(period, 17)
            for _ in range(2):
                add(day, -240_00, "UPI/CCD COFFEE/991122/Payment", "CCD COFFEE", "Dining")

        # --- a realistic unknown tail --------------------------------------
        # Real ledgers always contain a handful of merchants nothing knows yet.
        # Without them the review queue would be permanently empty, and the most
        # interesting screen in the product could never be exercised by hand.
        if index >= months - 3:
            add(
                _day_in_month(period, rng.randint(6, 26)),
                -_rupees(240, 620, rng),
                f"UPI/BLUE TOKAI COFFEE/{_ref(rng)}/Payment",
                "BLUE TOKAI COFFEE",
                UNCATEGORISED,
            )
            name, low, high = rng.choice(UNKNOWN_TAIL)
            add(
                _day_in_month(period, rng.randint(3, 27)),
                -_rupees(low, high, rng),
                f"UPI/{name}/{_ref(rng)}/Payment",
                name,
                UNCATEGORISED,
            )

    rows.sort(key=lambda row: row[0])
    return rows


def seed_demo_data(
    session: Session,
    *,
    months: int = 18,
    seed: int = 42,
    end: date | None = None,
    currency: str = "INR",
) -> DemoSeedResult:
    """Populate the database with a deterministic demo ledger.

    Idempotent: if the user already has transactions, nothing is inserted. That
    makes the "generate demo data" button safe to press twice.
    """
    user = _ensure_user(session, currency)
    taxonomy = _ensure_taxonomy(session, user)

    existing = session.scalar(
        select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
    )
    if existing:
        first = session.scalar(
            select(func.min(Transaction.posted_on)).where(Transaction.user_id == user.id)
        )
        last = session.scalar(
            select(func.max(Transaction.posted_on)).where(Transaction.user_id == user.id)
        )
        session.commit()
        return DemoSeedResult(created=0, months=months, start=first, end=last, skipped=True)

    rows = build_rows(months=months, seed=seed, end=end)
    for position, (posted_on, amount, raw, norm, category, account) in enumerate(rows):
        # An empty category name is the deliberate "nothing knows this merchant"
        # case: it lands exactly where an imported row would, as ``unknown``.
        category_id = taxonomy["categories"].get(category) if category else None
        session.add(
            Transaction(
                user_id=user.id,
                account_id=taxonomy["accounts"][account],
                posted_on=posted_on,
                amount_minor=amount,
                currency=currency,
                merchant_raw=raw,
                merchant_norm=norm,
                description=raw,
                category_id=category_id,
                category_source=(
                    CategorySource.SEED.value if category_id else CategorySource.UNKNOWN.value
                ),
                confidence=1.0 if category_id else None,
                is_transfer=category == TRANSFER_CATEGORY,
                dedupe_key=hashlib.sha256(f"demo|{seed}|{position}".encode()).hexdigest(),
                occurrence_index=0,
            )
        )
    session.commit()

    return DemoSeedResult(
        created=len(rows),
        months=months,
        start=rows[0][0] if rows else None,
        end=rows[-1][0] if rows else None,
        skipped=False,
    )
