"""Parameterized unit tests for watcher-script config wiring and delegation contracts."""  # Module purpose.

from __future__ import annotations

import importlib  # Reload modules under controlled env values.
import sys        # Clear cached modules from import state.
from dataclasses import dataclass  # Keep per-product test cases explicit and typed.
from typing import Any, Dict, List

import dotenv  # Patch dotenv loader to keep env deterministic during module import.
import pytest  # Standard pytest decorators/parametrization.


WATCH_HELPER_MODULE = "src.core.watch_helper"  # Reload this too because it loads dotenv at import time.


@dataclass(frozen=True)
class WatcherCase:
    """One product watcher case used by shared parameterized tests."""  # Brief class purpose.

    case_id:                      str
    module:                       str
    prefix:                       str
    active_attr:                  str
    target_attr:                  str
    regex_attr:                   str
    config_attr:                  str
    uses_global_target_fallback:  bool
    uses_global_keyword_fallback: bool
    default_target_products:      List[str]
    default_keyword_regex:        str
    banner_attr:                  str | None = None
    banner_env_var:               str | None = None
    default_banner_text:          str | None = None

    def env_keys(self) -> List[str]:
        """Return env keys that influence this watcher module's module-level constants."""  # Brief helper docstring.
        keys = [
            "ACTIVE_STATUSES",
            "TARGET_PRODUCT_NAMES",
            "KEYWORD_REGEX",
            f"{self.prefix}_ACTIVE_STATUSES",
            f"{self.prefix}_TARGET_PRODUCT_NAMES",
            f"{self.prefix}_KEYWORD_REGEX",
            f"{self.prefix}_MAX_AGE_HOURS",
            f"{self.prefix}_MIN_AGE_MINUTES",
        ]
        if self.banner_env_var:
            keys.append(self.banner_env_var)
        return keys


WATCHER_CASES = [
    WatcherCase(
        case_id                      = "superstat",
        module                       = "src.scripts.superstat_watch",
        prefix                       = "SUPERSTAT",
        active_attr                  = "SUPERSTAT_ACTIVE_STATUSES",
        target_attr                  = "SUPERSTAT_TARGET_PRODUCTS",
        regex_attr                   = "SUPERSTAT_KEYWORD_REGEX",
        config_attr                  = "SUPERSTAT_CONFIG",
        uses_global_target_fallback  = True,
        uses_global_keyword_fallback = True,
        default_target_products      = [],
        default_keyword_regex        = r"\bsuper[\s-]?stat\b",
    ),
    WatcherCase(
        case_id                      = "code_stroke",
        module                       = "src.scripts.code_stroke_watch",
        prefix                       = "CODE_STROKE",
        active_attr                  = "CODE_STROKE_ACTIVE_STATUSES",
        target_attr                  = "CODE_STROKE_TARGET_PRODUCTS",
        regex_attr                   = "CODE_STROKE_KEYWORD_REGEX",
        config_attr                  = "CODE_STROKE_CONFIG",
        uses_global_target_fallback  = False,
        uses_global_keyword_fallback = False,
        default_target_products      = [],
        default_keyword_regex        = r"\bcode[\s-]?stroke\b",
    ),
    WatcherCase(
        case_id="critical_findings",
        module="src.scripts.critical_findings_watch",
        prefix="CRITICAL_FINDINGS",
        active_attr="CRITICAL_FINDINGS_ACTIVE_STATUSES",
        target_attr="CRITICAL_FINDINGS_TARGET_PRODUCTS",
        regex_attr="CRITICAL_FINDINGS_KEYWORD_REGEX",
        config_attr="CRITICAL_FINDINGS_CONFIG",
        uses_global_target_fallback=True,
        uses_global_keyword_fallback=False,
        default_target_products=[],
        default_keyword_regex=r"\bcritical[\s-]?findings?\b",
        banner_attr="CRITICAL_FINDINGS_BANNER_TEXT",
        banner_env_var="CRITICAL_FINDINGS_BANNER_TEXT",
        default_banner_text="ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM",
    ),
    WatcherCase(
        case_id="amendments",
        module="src.scripts.amendments_watch",
        prefix="AMENDMENTS",
        active_attr="AMENDMENTS_ACTIVE_STATUSES",
        target_attr="AMENDMENTS_TARGET_PRODUCTS",
        regex_attr="AMENDMENTS_KEYWORD_REGEX",
        config_attr="AMENDMENTS_CONFIG",
        uses_global_target_fallback=True,
        uses_global_keyword_fallback=True,
        default_target_products=[],
        default_keyword_regex=r"\bamendments\b",
    ),
    WatcherCase(
        case_id="nm_studies",
        module="src.scripts.nm_studies_watch",
        prefix="NM_STUDIES",
        active_attr="NM_STUDIES_ACTIVE_STATUSES",
        target_attr="NM_STUDIES_TARGET_PRODUCTS",
        regex_attr="NM_STUDIES_KEYWORD_REGEX",
        config_attr="NM_STUDIES_CONFIG",
        uses_global_target_fallback=False,
        uses_global_keyword_fallback=False,
        default_target_products=["nm studies"],
        default_keyword_regex=r"\bnm[\s/-]*studies\b",
        banner_attr="NM_STUDIES_BANNER_TEXT",
        banner_env_var="NM_STUDIES_BANNER_TEXT",
        default_banner_text="Please verify whether any radiologist scheduled today is able to read this study. If none are available, notify the team immediately so we can secure a radiologist who can complete the read.",
    ),
    WatcherCase(
        case_id="it_system_studies",
        module="src.scripts.it_system_studies_watch",
        prefix="IT_SYSTEM_STUDIES",
        active_attr="IT_SYSTEM_STUDIES_ACTIVE_STATUSES",
        target_attr="IT_SYSTEM_STUDIES_TARGET_PRODUCTS",
        regex_attr="IT_SYSTEM_STUDIES_KEYWORD_REGEX",
        config_attr="IT_SYSTEM_STUDIES_CONFIG",
        uses_global_target_fallback=False,
        uses_global_keyword_fallback=False,
        default_target_products=["it / system studies"],
        default_keyword_regex=r"\bit\s*/\s*system\s*studies\b",
    ),
]

ALL_WATCHER_ENV_KEYS = sorted({key for case in WATCHER_CASES for key in case.env_keys()})  # Union for deterministic import state.


def _import_watcher_with_env(monkeypatch, case: WatcherCase, *, set_env: Dict[str, str] | None = None):
    """Import/reload watcher module after applying case-specific env state."""   # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)    # Prevent .env from repopulating watcher vars.
    for name in ALL_WATCHER_ENV_KEYS:                                            # Clear untouched keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(case.module, None)           # Force fresh watcher module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)   # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(case.module)  # Import with current env snapshot.


@pytest.mark.parametrize("case", WATCHER_CASES, ids=[case.case_id for case in WATCHER_CASES])
def test_watcher_config_uses_defined_fallback_behavior(monkeypatch, case: WatcherCase) -> None:
    """Absent product-specific env vars should yield each module's documented fallback behavior."""  # Shared fallback contract.
    module = _import_watcher_with_env(
        monkeypatch,
        case,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Global Product One,  Global Product Two",
            "KEYWORD_REGEX": r"\\bignored\\b",
        },
    )

    expected_active = {"Assigned", "Pending", "Escalated"}                                             # Shared active fallback.
    expected_target = ["global product one", "global product two"] if case.uses_global_target_fallback else case.default_target_products
    expected_regex  = r"\bignored\b" if case.uses_global_keyword_fallback else case.default_keyword_regex

    active = getattr(module, case.active_attr)  # Resolve module constant by case metadata.
    target = getattr(module, case.target_attr)  # Resolve module constant by case metadata.
    regex  = getattr(module, case.regex_attr)   # Resolve module constant by case metadata.
    config = getattr(module, case.config_attr)  # Resolve module ProductConfig object by case metadata.

    assert active                      == expected_active   # Active statuses should follow module fallback behavior.
    assert target                      == expected_target   # Target products should follow module fallback behavior.
    assert regex                       == expected_regex    # Keyword regex should follow module fallback behavior.
    assert config.active_statuses      == active            # Config must be wired to module active constant.
    assert config.target_product_names == target            # Config must be wired to module target constant.
    assert config.keyword_regex        == regex             # Config must be wired to module regex constant.

    if case.banner_attr:                                            # Only products with banner text define and wire this field.
        banner_text = getattr(module, case.banner_attr)             # Resolve module banner constant.
        assert banner_text == case.default_banner_text              # Banner fallback should match module default.
        assert config.card_banner_text == case.default_banner_text  # Config should carry banner through unchanged.
    else:
        assert config.card_banner_text == ""                        # Products without banner config should keep empty string default.


@pytest.mark.parametrize("case", WATCHER_CASES, ids=[case.case_id for case in WATCHER_CASES])
def test_watcher_config_prefers_product_specific_env_over_global(monkeypatch, case: WatcherCase) -> None:
    """Product-specific env vars should override globals for active/target/regex and age settings."""  # Shared override contract.
    set_env = {
        "ACTIVE_STATUSES": "Assigned,Pending",
        "TARGET_PRODUCT_NAMES": "Ignored Product",
        "KEYWORD_REGEX": r"\\bignored\\b",
        f"{case.prefix}_ACTIVE_STATUSES": "Open, Waiting",
        f"{case.prefix}_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
        f"{case.prefix}_KEYWORD_REGEX": r"\\boverride\\b",
        f"{case.prefix}_MAX_AGE_HOURS": "36",
        f"{case.prefix}_MIN_AGE_MINUTES": "9",
    }
    if case.banner_env_var:
        set_env[case.banner_env_var] = "  custom banner text  "  # Ensure trim behavior is tested for banner-enabled products.

    module = _import_watcher_with_env(monkeypatch, case, set_env=set_env)

    active = getattr(module, case.active_attr)  # Resolve module constant by case metadata.
    target = getattr(module, case.target_attr)  # Resolve module constant by case metadata.
    regex  = getattr(module, case.regex_attr)   # Resolve module constant by case metadata.
    config = getattr(module, case.config_attr)  # Resolve module ProductConfig object by case metadata.

    assert active == {"Open", "Waiting"}                # Product-specific ACTIVE_STATUSES should win.
    assert target == ["override one", "override two"]   # Product-specific TARGET_PRODUCT_NAMES should win.
    assert regex  == r"\boverride\b"                    # Product-specific KEYWORD_REGEX should win.
    assert config.max_age_hours   == 36                 # Product-specific max-age override should parse as int.
    assert config.min_age_minutes == 9                  # Product-specific min-age override should parse as int.
    assert config.active_statuses == {"Open", "Waiting"}  # Config should reflect overridden active statuses.

    if case.banner_attr:
        banner_text = getattr(module, case.banner_attr)         # Resolve module banner constant.
        assert banner_text == "custom banner text"              # Product-specific banner should be stripped.
        assert config.card_banner_text == "custom banner text"  # Config should reflect banner override.


@pytest.mark.parametrize("case", WATCHER_CASES, ids=[case.case_id for case in WATCHER_CASES])
def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch, case: WatcherCase) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Shared delegation contract.
    module = _import_watcher_with_env(monkeypatch, case)                                        # Base import with deterministic env state.

    calls: list[Dict[str, Any]] = []                                                            # Capture delegation call payload.

    def fake_run_product_loop_once(config, token, pre_fetched_tickets=None) -> None:
        calls.append(                                                                           # Save delegation payload explicitly.
            {
                "config": config,
                "token": token,
                "pre_fetched_tickets": pre_fetched_tickets,
            }
        )

    monkeypatch.setattr(module, "run_product_loop_once", fake_run_product_loop_once)  # Patch shared helper entrypoint.

    test_token   = f"token-{case.case_id}"
    test_tickets = [{"id": "1166045000005103001", "ticketNumber": "4679"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)                    # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is getattr(module, case.config_attr)       # Must pass module config object.
    assert calls[0]["token"]               == test_token                              # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets                            # Must forward provided tickets object.
