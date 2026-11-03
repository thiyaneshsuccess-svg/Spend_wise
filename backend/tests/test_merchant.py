"""Merchant normalisation decides every grouping downstream, so it is pinned."""

from __future__ import annotations

import pytest

from app.domain.merchant import looks_like_transfer, normalise_merchant


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UPI/SWIGGY/4429183091/Payment", "SWIGGY"),
        ("Swiggy*Order 8891", "SWIGGY"),
        ("POS 4321 AMAZON INDIA", "AMAZON"),
        ("UPI/ZOMATO/99112233/Payment", "ZOMATO"),
        ("NETFLIX COM AUTOPAY", "NETFLIX"),
        ("  reliance   fresh  ", "RELIANCE FRESH"),
        ("UPI/BIGBASKET/1234/Payment", "BIGBASKET"),
        # Short numeric references must not leak into the merchant key, and
        # direction words (CREDIT/DEBIT) are rail noise, not merchant identity.
        ("SALARY CREDIT NEFT/ACME/991", "SALARY ACME"),
    ],
)
def test_noise_is_stripped(raw: str, expected: str) -> None:
    assert normalise_merchant(raw) == expected


def test_empty_input_is_empty_output() -> None:
    assert normalise_merchant("") == ""
    assert normalise_merchant("   ") == ""


def test_normalisation_is_deterministic() -> None:
    raw = "UPI/SWIGGY/4429183091/Payment"
    assert normalise_merchant(raw) == normalise_merchant(raw)


def test_all_noise_falls_back_to_raw_text() -> None:
    # Never return an empty key: an empty merchant would merge unrelated rows.
    assert normalise_merchant("UPI PAYMENT") == "UPI PAYMENT"


@pytest.mark.parametrize(
    "raw",
    ["CREDIT CARD PAYMENT HDFC", "IMPS TO SELF CASH WALLET", "SELF TRANSFER TO SAVINGS"],
)
def test_transfer_hints_detected(raw: str) -> None:
    assert looks_like_transfer(raw) is True


def test_spending_is_not_a_transfer() -> None:
    assert looks_like_transfer("UPI/SWIGGY/123/Payment") is False
