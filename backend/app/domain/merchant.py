"""Merchant name normalisation.

Bank statements are hostile text. The same merchant appears as
``UPI/SWIGGY/4429183091/Payment``, ``Swiggy*Order 8891`` and
``POS SWIGGY BANGALORE``. Everything downstream — recurring detection, merchant
memory, attribution — groups by merchant, so this normalisation is load-bearing
and must be deterministic and conservative.

Rule: strip payment-rail noise and reference numbers, keep the brand tokens.
Never stem, never correct spelling: a wrong merge is silent data corruption.
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[/*\-|#:>]+")
_WHITESPACE = re.compile(r"\s+")

# Payment rails, card networks and boilerplate that carry no merchant identity.
_NOISE_TOKENS = {
    "UPI", "IMPS", "NEFT", "RTGS", "ACH", "POS", "ATM", "CASH", "PAYMENT", "PAYMENTS",
    "PAY", "PAID", "TXN", "TRANSACTION", "REF", "REFNO", "RRN", "AUTH", "AUTOPAY",
    "MANDATE", "NACH", "BILLPAY", "BILL", "DEBIT", "CREDIT", "CARD", "VISA",
    "MASTERCARD", "RUPAY", "PVT", "LTD", "PRIVATE", "LIMITED", "INDIA", "IN",
    "BANGALORE", "BENGALURU", "MUMBAI", "DELHI", "CHENNAI", "HYDERABAD", "PUNE",
    "ONLINE", "ORDER", "STORE", "BRANCH", "MOBILE", "APP", "COM",
}

_REFERENCE = re.compile(r"^(?=.*\d)[A-Z0-9]{4,}$")
_SHORT_NUMBER = re.compile(r"^\d{3,}$")

TRANSFER_HINTS = (
    "SELF TRANSFER",
    "TO SAVINGS",
    "FROM SAVINGS",
    "CREDIT CARD PAYMENT",
    "CARD PAYMENT",
    "IMPS TO SELF",
    "OWN ACCOUNT",
)


def normalise_merchant(raw: str) -> str:
    """Return a stable uppercase brand-ish token string for a raw narration."""
    if raw is None:
        return ""
    text = str(raw).upper().strip()
    if not text:
        return ""

    text = _SEPARATORS.sub(" ", text)
    tokens = _WHITESPACE.sub(" ", text).split(" ")

    kept: list[str] = []
    for token in tokens:
        if not token:
            continue
        if token in _NOISE_TOKENS:
            continue
        if _REFERENCE.match(token) or _SHORT_NUMBER.match(token):
            continue
        kept.append(token)

    # If noise stripping removed everything (e.g. narration was "UPI PAYMENT"),
    # fall back to the raw uppercase text so we never produce an empty key.
    if not kept:
        return _WHITESPACE.sub(" ", text).strip()
    return " ".join(kept)


def looks_like_transfer(raw: str) -> bool:
    """Cheap pre-check for internal transfers.

    Transfers are not spending; getting this wrong inflates every total. The
    final decision is still a user override — this only pre-flags the obvious.
    """
    text = _WHITESPACE.sub(" ", str(raw or "").upper())
    return any(hint in text for hint in TRANSFER_HINTS)
