"""Parameterized tests for centralized product-registry env wiring behavior."""  # Module purpose.

from __future__ import annotations

from dataclasses import dataclass  # Keep per-product expectations explicit and typed.
from typing import List

import pytest  # Standard pytest decorators/parametrization.

from src.scripts import product_registry  # Registry module under test.


@dataclass(frozen=True)
class ProductCase:
    """One product case used by shared registry tests."""  # Brief class purpose.

    case_id:                      str
    product_id:                   str
    prefix:                       str
    use_global_target_fallback:   bool
    default_target_products:      List[str]
    banner_env_var:               str | None = None
    default_banner_text:          str | None = None

    def env_keys(self) -> List[str]:
        """Return env keys that influence this product configuration."""  # Brief helper docstring.
        keys = [
            "ACTIVE_STATUSES",
            "TARGET_PRODUCT_NAMES",
            f"{self.prefix}_ACTIVE_STATUSES",
            f"{self.prefix}_TARGET_PRODUCT_NAMES",
            f"{self.prefix}_MAX_AGE_HOURS",
            f"{self.prefix}_MIN_AGE_MINUTES",
            f"{self.prefix}_NOTIFY_COOLDOWN_SECONDS",
        ]
        if self.banner_env_var:
            keys.append(self.banner_env_var)
        return keys


PRODUCT_CASES = [
    ProductCase(
        case_id                     = "superstat",
        product_id                  = "superstat",
        prefix                      = "SUPERSTAT",
        use_global_target_fallback  = True,
        default_target_products     = [],
    ),
    ProductCase(
        case_id                     = "code_stroke",
        product_id                  = "code_stroke",
        prefix                      = "CODE_STROKE",
        use_global_target_fallback  = False,
        default_target_products     = [],
    ),
    ProductCase(
        case_id                     = "critical_findings",
        product_id                  = "critical_findings",
        prefix                      = "CRITICAL_FINDINGS",
        use_global_target_fallback  = True,
        default_target_products     = [],
        banner_env_var              = "CRITICAL_FINDINGS_BANNER_TEXT",
        default_banner_text         = "ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM",
    ),
    ProductCase(
        case_id                     = "amendments",
        product_id                  = "amendments",
        prefix                      = "AMENDMENTS",
        use_global_target_fallback  = True,
        default_target_products     = [],
    ),
    ProductCase(
        case_id                     = "nm_studies",
        product_id                  = "nm_studies",
        prefix                      = "NM_STUDIES",
        use_global_target_fallback  = False,
        default_target_products     = ["nm studies"],
        banner_env_var              = "NM_STUDIES_BANNER_TEXT",
        default_banner_text         = "Please verify whether any radiologist scheduled today is able to read this study. If none are available, notify the team immediately so we can secure a radiologist who can complete the read.",
    ),
    ProductCase(
        case_id                     = "it_system_studies",
        product_id                  = "it_system_studies",
        prefix                      = "IT_SYSTEM_STUDIES",
        use_global_target_fallback  = False,
        default_target_products     = ["it / system studies"],
    ),
    ProductCase(
        case_id                     = "reading_requests",
        product_id                  = "reading_requests",
        prefix                      = "READING_REQUESTS",
        use_global_target_fallback  = False,
        default_target_products     = ["reading requests"],
    ),
    ProductCase(
        case_id                     = "password_reset",
        product_id                  = "password_reset",
        prefix                      = "PASSWORD_RESET",
        use_global_target_fallback  = False,
        default_target_products     = ["password reset"],
    ),
    ProductCase(
        case_id                     = "general",
        product_id                  = "general",
        prefix                      = "GENERAL",
        use_global_target_fallback  = False,
        default_target_products     = ["general"],
    ),
    ProductCase(
        case_id                     = "consults_and_physician_connection",
        product_id                  = "consults_and_physician_connection",
        prefix                      = "CONSULTS_AND_PHYSICIAN_CONNECTION",
        use_global_target_fallback  = False,
        default_target_products     = ["consults & physician connection"],
    ),
]

ALL_PRODUCT_ENV_KEYS = sorted({key for case in PRODUCT_CASES for key in case.env_keys()})  # Union for deterministic env state.


def _clear_product_env(monkeypatch) -> None:
    """Clear all env vars that can influence product config loading."""  # Helper intent.
    for key in ALL_PRODUCT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _build_case_config(case: ProductCase):
    """Build one ProductConfig from registry metadata for the provided case."""  # Brief helper docstring.
    spec = product_registry.PRODUCT_REGISTRY[case.product_id]
    return product_registry.build_product_config(case.product_id, spec)


@pytest.mark.parametrize("case", PRODUCT_CASES, ids=[case.case_id for case in PRODUCT_CASES])
def test_registry_config_uses_defined_fallback_behavior(monkeypatch, case: ProductCase) -> None:
    """Absent product-specific env vars should follow each product's documented fallback behavior."""  # Shared fallback contract.
    _clear_product_env(monkeypatch)
    monkeypatch.setenv("ACTIVE_STATUSES", "Assigned, Pending ,Escalated")
    monkeypatch.setenv("TARGET_PRODUCT_NAMES", "Global Product One,  Global Product Two")

    config = _build_case_config(case)

    expected_active = {"Assigned", "Pending", "Escalated"}                                              # Shared active fallback.
    expected_target = ["global product one", "global product two"] if case.use_global_target_fallback else case.default_target_products

    assert config.active_statuses      == expected_active  # Active statuses should follow fallback behavior.
    assert config.target_product_names == expected_target  # Target products should follow fallback behavior.
    assert config.min_age_minutes      == product_registry.MIN_AGE_MINUTES_DEFAULT  # Default min-age should be inherited.
    assert config.max_age_hours        == product_registry.MAX_AGE_HOURS_DEFAULT    # Default max-age should be inherited.

    if case.banner_env_var:
        assert config.card_banner_text == case.default_banner_text  # Banner fallback should match product default.
    else:
        assert config.card_banner_text == ""                        # Products without banner should keep empty text.


@pytest.mark.parametrize("case", PRODUCT_CASES, ids=[case.case_id for case in PRODUCT_CASES])
def test_registry_config_prefers_product_specific_env_over_global(monkeypatch, case: ProductCase) -> None:
    """Product-specific env vars should override globals for active/target/regex and age settings."""  # Shared override contract.
    _clear_product_env(monkeypatch)
    monkeypatch.setenv("ACTIVE_STATUSES", "Assigned,Pending")
    monkeypatch.setenv("TARGET_PRODUCT_NAMES", "Ignored Product")
    monkeypatch.setenv(f"{case.prefix}_ACTIVE_STATUSES", "Open, Waiting")
    monkeypatch.setenv(f"{case.prefix}_TARGET_PRODUCT_NAMES", "  Override One , Override Two ")
    monkeypatch.setenv(f"{case.prefix}_MAX_AGE_HOURS", "36")
    monkeypatch.setenv(f"{case.prefix}_MIN_AGE_MINUTES", "9")
    monkeypatch.setenv(f"{case.prefix}_NOTIFY_COOLDOWN_SECONDS", "120")
    if case.banner_env_var:
        monkeypatch.setenv(case.banner_env_var, "  custom banner text  ")

    config = _build_case_config(case)

    assert config.active_statuses         == {"Open", "Waiting"}      # Product-specific active statuses should win.
    assert config.target_product_names    == ["override one", "override two"]  # Product-specific targets should win.
    assert config.max_age_hours           == 36                        # Product-specific max-age override should parse as int.
    assert config.min_age_minutes         == 9                         # Product-specific min-age override should parse as int.
    assert config.notify_cooldown_seconds == 120                       # Product-specific cooldown override should parse as int.

    if case.banner_env_var:
        assert config.card_banner_text == "custom banner text"         # Product-specific banner should be stripped.


def test_load_product_configs_from_env_returns_all_products_in_registry_order(monkeypatch) -> None:
    """Loader should return all registry products in deterministic insertion order."""  # Loader contract.
    _clear_product_env(monkeypatch)

    configs         = product_registry.load_product_configs_from_env()
    expected_names  = [spec["name"] for spec in product_registry.PRODUCT_REGISTRY.values()]
    expected_length = len(product_registry.PRODUCT_REGISTRY)

    assert len(configs) == expected_length                    # Should load exactly one config per registry product.
    assert [cfg.name for cfg in configs] == expected_names    # Order should follow registry insertion order.
