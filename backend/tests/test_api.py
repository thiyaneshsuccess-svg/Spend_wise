"""API contract tests.

These assert behaviour a client depends on: totals reconcile, filters narrow,
transfers are excluded by default, and a bad import is rejected with a 400
rather than a 500.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

CSV = b"""date,description,amount
2026-10-02,UPI/SWIGGY/1234/Payment,-450.00
2026-10-03,POS 4321 AMAZON INDIA,-1999.00
"""


def _seed(client: TestClient, months: int = 6) -> None:
    response = client.post("/api/dev/seed", params={"months": months})
    assert response.status_code == 200, response.text
    assert response.json()["created"] > 0


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_meta_bootstraps_accounts_and_categories(client: TestClient) -> None:
    _seed(client)
    payload = client.get("/api/meta").json()

    assert payload["currency"] == "INR"
    assert len(payload["accounts"]) == 3
    assert len(payload["categories"]) == 15
    assert payload["transaction_count"] > 0
    assert payload["first_transaction_on"] <= payload["last_transaction_on"]


def test_transactions_paginate_and_reconcile(client: TestClient) -> None:
    _seed(client)
    payload = client.get("/api/transactions", params={"limit": 5}).json()

    assert len(payload["items"]) == 5
    assert payload["total"] > 5
    summary = payload["summary"]
    assert summary["net_minor"] == summary["inflow_minor"] + summary["outflow_minor"]
    assert summary["outflow_minor"] <= 0
    assert summary["count"] == payload["total"]


def test_transfers_are_hidden_by_default(client: TestClient) -> None:
    _seed(client)

    default = client.get("/api/transactions", params={"limit": 500}).json()
    assert all(item["is_transfer"] is False for item in default["items"])

    with_transfers = client.get(
        "/api/transactions", params={"limit": 500, "include_transfers": "true"}
    ).json()
    assert with_transfers["total"] > default["total"]


def test_search_filters_by_merchant(client: TestClient) -> None:
    _seed(client)
    payload = client.get("/api/transactions", params={"q": "swiggy", "limit": 200}).json()

    assert payload["total"] > 0
    assert all("SWIGGY" in item["merchant"] for item in payload["items"])


def test_month_filter_returns_only_that_month(client: TestClient) -> None:
    _seed(client)
    meta = client.get("/api/meta").json()
    month = meta["last_transaction_on"][:7]

    payload = client.get("/api/transactions", params={"month": month, "limit": 500}).json()
    assert payload["total"] > 0
    assert all(item["posted_on"].startswith(month) for item in payload["items"])


def test_impossible_month_is_rejected(client: TestClient) -> None:
    _seed(client)
    # Syntactically a month, semantically impossible: the domain rejects it.
    assert client.get("/api/transactions", params={"month": "2026-13"}).status_code == 400
    assert client.get("/api/transactions", params={"month": "october"}).status_code == 422


def test_import_preview_does_not_write(client: TestClient) -> None:
    _seed(client)
    meta = client.get("/api/meta").json()
    account_id = meta["accounts"][0]["id"]

    response = client.post(
        "/api/imports/preview",
        files={"file": ("stmt.csv", CSV, "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["new_rows"] == 2

    # Preview must not have persisted anything.
    after = client.get("/api/meta").json()
    assert after["transaction_count"] == meta["transaction_count"]


def test_import_commit_is_idempotent(client: TestClient) -> None:
    _seed(client)
    account_id = client.get("/api/meta").json()["accounts"][0]["id"]

    first = client.post(
        "/api/imports/commit",
        files={"file": ("stmt.csv", CSV, "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 2

    second = client.post(
        "/api/imports/commit",
        files={"file": ("stmt.csv", CSV, "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert second.json()["imported"] == 0
    assert second.json()["skipped"] == 2


def test_bad_import_returns_400(client: TestClient) -> None:
    _seed(client)
    account_id = client.get("/api/meta").json()["accounts"][0]["id"]

    response = client.post(
        "/api/imports/preview",
        files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert response.status_code == 400
    assert "date column" in response.json()["detail"]


def test_import_to_unknown_account_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/imports/preview",
        files={"file": ("stmt.csv", CSV, "text/csv")},
        data={"account_id": "9999"},
    )
    assert response.status_code == 404
