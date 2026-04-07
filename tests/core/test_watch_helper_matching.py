"""Unit tests for extract_product_name and build_config_lookup helpers."""  # Module purpose.

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# extract_product_name
# ---------------------------------------------------------------------------

def test_extract_product_name_from_flat_string() -> None:
    """Should return the productName string directly."""  # Flat field contract.
    assert watch_helper.extract_product_name(_ticket(productName="Super Stat")) == "Super Stat"


def test_extract_product_name_from_nested_name() -> None:
    """Should find name inside a nested product dict."""  # Nested object contract.
    ticket = _ticket(productName=None, product={"name": "Code Stroke Alert"})
    assert watch_helper.extract_product_name(ticket) == "Code Stroke Alert"


def test_extract_product_name_from_nested_productName() -> None:
    """Should find productName inside a nested product dict."""  # Alternate nested key.
    ticket = _ticket(productName=None, product={"productName": "Amendments"})
    assert watch_helper.extract_product_name(ticket) == "Amendments"


def test_extract_product_name_returns_none_when_missing() -> None:
    """Should return None when no product field is present."""  # Missing field guard.
    ticket = _ticket(productName=None)
    ticket.pop("product", None)
    assert watch_helper.extract_product_name(ticket) is None


def test_extract_product_name_ignores_empty_strings() -> None:
    """Should return None when product fields are blank strings."""  # Blank string guard.
    assert watch_helper.extract_product_name(_ticket(productName="  ")) is None


# ---------------------------------------------------------------------------
# build_config_lookup
# ---------------------------------------------------------------------------

def test_build_config_lookup_maps_names_to_configs() -> None:
    """Lookup should map each lower-case product name to its config."""  # Core lookup contract.
    config_a = watch_helper.ProductConfig(
        name="Super-Stat", target_product_names=["Super Stat"],
        active_statuses={"Assigned"}, teams_webhook_env_var="WH_A",
        last_sent_filename="a.json",
    )
    config_b = watch_helper.ProductConfig(
        name="Password Reset", target_product_names=["Password Reset", "Unlock Account"],
        active_statuses={"Assigned"}, teams_webhook_env_var="WH_B",
        last_sent_filename="b.json",
    )
    lookup = watch_helper.build_config_lookup([config_a, config_b])

    assert lookup["super stat"]      is config_a                     # Lower-case key maps to config.
    assert lookup["password reset"]  is config_b                     # First name maps correctly.
    assert lookup["unlock account"]  is config_b                     # Second name maps to same config.
    assert "Super Stat" not in lookup                                # Original case should not appear as key.


def test_build_config_lookup_empty_configs() -> None:
    """Lookup from empty config list should be empty dict."""  # Empty guard.
    assert watch_helper.build_config_lookup([]) == {}
