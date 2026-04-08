"""Tests for product_registry.py — loading product configs from products.json."""  # Module purpose.

from __future__ import annotations

import json                              # Write test JSON fixtures.
import os                                # Build file paths.
from typing import Any, Dict, List       # Keep helper typing explicit.

import pytest                            # Test runner and assertions.

from src.core import config_manager      # Module that reads products.json.
from src.scripts import product_registry # Module under test.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_products_json(tmp_path, products: Dict[str, Any]) -> str:           # Write a test products.json and return its path.
    """Write a products.json file in tmp_path and return the file path."""     # Docstring in plain words.
    path = os.path.join(str(tmp_path), "products.json")                        # Build path inside pytest temp dir.
    with open(path, "w", encoding="utf-8") as f:                               # Open for writing.
        json.dump({"products": products}, f, indent=2)                         # Write formatted JSON.
    return path                                                                # Return the path for monkeypatching.


SAMPLE_PRODUCT = {                                                             # Minimal valid product entry for tests.
    "name": "Super-Stat",
    "teams_webhook_url": "https://teams.example/wh",
    "min_age_minutes": 5,
    "max_age_hours": 24,
    "target_product_names": ["Super Stat"],
    "active_statuses": ["Assigned", "Pending", "Escalated"],
    "banner_text": "",
    "notify_cooldown_seconds": None,
}


# ---------------------------------------------------------------------------
# build_product_config_from_json tests
# ---------------------------------------------------------------------------

def test_build_config_from_json_uses_all_fields() -> None:
    """All JSON fields should map to the correct ProductConfig attributes."""  # Core mapping contract.
    config = product_registry.build_product_config_from_json("superstat", SAMPLE_PRODUCT)

    assert config.name                    == "Super-Stat"
    assert config.teams_webhook_url       == "https://teams.example/wh"
    assert config.min_age_minutes         == 5
    assert config.max_age_hours           == 24
    assert config.target_product_names    == ["Super Stat"]
    assert config.active_statuses         == {"Assigned", "Pending", "Escalated"}
    assert config.card_banner_text        == ""
    assert config.notify_cooldown_seconds is None
    assert config.last_sent_filename      == "sent_superstat_notifications.json"


def test_build_config_defaults_target_names_to_product_name() -> None:
    """If target_product_names is missing, it should default to [name]."""    # Default fallback.
    entry = {"name": "My Product", "teams_webhook_url": "https://wh"}
    config = product_registry.build_product_config_from_json("my_product", entry)

    assert config.target_product_names == ["My Product"]


def test_build_config_defaults_statuses_when_missing() -> None:
    """If active_statuses is missing, it should use the default set."""       # Default statuses.
    entry = {"name": "Test", "teams_webhook_url": "https://wh"}
    config = product_registry.build_product_config_from_json("test", entry)

    assert config.active_statuses == set(product_registry.DEFAULT_ACTIVE_STATUSES)


def test_build_config_parses_cooldown_seconds() -> None:
    """notify_cooldown_seconds should be parsed as int when present."""       # Cooldown parsing.
    entry = {**SAMPLE_PRODUCT, "notify_cooldown_seconds": 120}
    config = product_registry.build_product_config_from_json("test", entry)

    assert config.notify_cooldown_seconds == 120


def test_build_config_uses_banner_text() -> None:
    """banner_text from JSON should appear on the config."""                  # Banner field.
    entry = {**SAMPLE_PRODUCT, "banner_text": "Important instructions here"}
    config = product_registry.build_product_config_from_json("test", entry)

    assert config.card_banner_text == "Important instructions here"


# ---------------------------------------------------------------------------
# load_product_configs_from_env tests (reads products.json via config_manager)
# ---------------------------------------------------------------------------

def test_load_configs_from_json_file(monkeypatch, tmp_path) -> None:
    """load_product_configs_from_env should read products.json and return configs."""  # Integration test.
    products = {
        "super_stat": SAMPLE_PRODUCT,
        "amendments": {
            "name": "Amendments",
            "teams_webhook_url": "https://teams.example/amendments",
            "min_age_minutes": 60,
            "target_product_names": ["Amendments"],
        },
    }
    path = _write_products_json(tmp_path, products)
    monkeypatch.setattr(config_manager, "PRODUCTS_JSON_PATH", path)            # Point config_manager at test file.

    configs = product_registry.load_product_configs_from_env()

    assert len(configs) == 2
    assert configs[0].name == "Super-Stat"
    assert configs[1].name == "Amendments"
    assert configs[1].min_age_minutes == 60


def test_load_configs_returns_empty_when_file_missing(monkeypatch, tmp_path) -> None:
    """Should return empty list when products.json does not exist."""          # Missing file guard.
    missing_path = os.path.join(str(tmp_path), "nonexistent.json")
    monkeypatch.setattr(config_manager, "PRODUCTS_JSON_PATH", missing_path)

    configs = product_registry.load_product_configs_from_env()

    assert configs == []


def test_load_configs_preserves_order(monkeypatch, tmp_path) -> None:
    """Configs should be returned in the same order as products.json keys."""  # Order contract.
    products = {
        "zzz_last": {"name": "ZZZ", "teams_webhook_url": "https://wh"},
        "aaa_first": {"name": "AAA", "teams_webhook_url": "https://wh"},
    }
    path = _write_products_json(tmp_path, products)
    monkeypatch.setattr(config_manager, "PRODUCTS_JSON_PATH", path)

    configs = product_registry.load_product_configs_from_env()

    assert [c.name for c in configs] == ["ZZZ", "AAA"]                         # Insertion order preserved.
