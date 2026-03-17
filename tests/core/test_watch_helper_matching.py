"""Unit tests for product-only matching helpers in watch_helper."""  # Module purpose.

from __future__ import annotations

from datetime import datetime, timedelta  # Build deterministic age conditions.
from typing import Any, Dict

from src.core import watch_helper  # Module under test.


def _ticket(**overrides: Any) -> Dict[str, Any]:
    """Build baseline ticket payload with optional field overrides."""  # Keep tests concise.
    base = {
        "id": "1166045000005103001",
        "ticketNumber": "4679",
        "status": "Assigned",
        "statusType": "Open",
        "createdTime": "2026-01-01T11:00:00.000Z",
        "productName": "Password Reset",
    }
    base.update(overrides)
    return base


def test_product_matches_supports_flat_and_nested_product_fields() -> None:
    """product_matches should match flat string and nested product object fields."""  # Matching contract.
    targets = ["password reset", "consults & physician connection"]

    assert watch_helper.product_matches(_ticket(productName="Password Reset"), targets) is True
    assert watch_helper.product_matches(_ticket(product={"name": "Password Reset"}), targets) is True
    assert watch_helper.product_matches(_ticket(product={"productName": "Password Reset"}), targets) is True
    assert watch_helper.product_matches(_ticket(productName="General"), targets) is False


def test_should_alert_requires_product_match(monkeypatch) -> None:
    """should_alert should return no-product-match when product is outside target list."""  # Product-only rule.
    monkeypatch.setattr(watch_helper, "is_unresolved", lambda _ticket: True)
    result = watch_helper.should_alert(_ticket(productName="General"), ["password reset"], min_age_minutes=5)
    assert result == (False, "no product match")


def test_should_alert_returns_age_reason_when_product_matches(monkeypatch) -> None:
    """should_alert should delegate age decision after successful product match."""  # Age branch contract.
    monkeypatch.setattr(watch_helper, "is_unresolved", lambda _ticket: True)
    monkeypatch.setattr(watch_helper, "older_than_min_age", lambda _ticket, _minutes: (True, "age ok (12m old)"))
    result = watch_helper.should_alert(_ticket(productName="Password Reset"), ["password reset"], min_age_minutes=5)
    assert result == (True, "product match; age ok (12m old)")


def test_should_alert_rejects_resolved_or_closed(monkeypatch) -> None:
    """should_alert should reject resolved/closed tickets before product checks."""  # Unresolved guard.
    monkeypatch.setattr(watch_helper, "is_unresolved", lambda _ticket: False)
    result = watch_helper.should_alert(_ticket(productName="Password Reset"), ["password reset"], min_age_minutes=5)
    assert result == (False, "resolved/closed")


def test_older_than_min_age_handles_missing_created_time() -> None:
    """older_than_min_age should reject tickets with missing createdTime."""  # Missing-time guard.
    assert watch_helper.older_than_min_age({"createdTime": ""}, 5) == (False, "missing createdTime")


def test_older_than_min_age_returns_too_new_and_age_ok(monkeypatch) -> None:
    """older_than_min_age should report both too-new and age-ok outcomes."""  # Core age behavior.
    fixed_now = datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(minutes=3))
    too_new = watch_helper.older_than_min_age(_ticket(createdTime="ignored"), 5)
    assert too_new == (False, "too new (3m old)")

    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(minutes=8))
    age_ok = watch_helper.older_than_min_age(_ticket(createdTime="ignored"), 5)
    assert age_ok == (True, "age ok (8m old)")

