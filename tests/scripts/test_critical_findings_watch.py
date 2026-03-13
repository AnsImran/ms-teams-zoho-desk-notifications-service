"""Unit tests for critical_findings_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib    # Reload module under controlled env values.
import sys          # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


CRITICAL_FINDINGS_MODULE = "src.scripts.critical_findings_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"                      # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence critical_findings module-level constants/config.
CRITICAL_FINDINGS_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "CRITICAL_FINDINGS_ACTIVE_STATUSES",
    "CRITICAL_FINDINGS_TARGET_PRODUCT_NAMES",
    "CRITICAL_FINDINGS_KEYWORD_REGEX",
    "CRITICAL_FINDINGS_BANNER_TEXT",
    "CRITICAL_FINDINGS_MAX_AGE_HOURS",
    "CRITICAL_FINDINGS_MIN_AGE_MINUTES",
]

DEFAULT_CRITICAL_BANNER = "ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM"
                                                                                         # Mirror module default to assert fallback behavior.


def _import_critical_findings_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload critical_findings_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating CRITICAL_FINDINGS_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in CRITICAL_FINDINGS_ENV_KEYS:  # Remove untouched critical-finding keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(CRITICAL_FINDINGS_MODULE, None)  # Force fresh critical_findings module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)       # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(CRITICAL_FINDINGS_MODULE)  # Import with current env snapshot.


def test_critical_findings_config_uses_global_fallback_env_values(monkeypatch) -> None:
    """When CRITICAL_FINDINGS_* vars are absent, ACTIVE/TARGET fallbacks should be used."""  # Fallback behavior.
    module = _import_critical_findings_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Critical One,  Critical Two",
            "KEYWORD_REGEX": r"\\bignored\\b",
        },
    )

    assert module.CRITICAL_FINDINGS_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global ACTIVE_STATUSES fallback.
    assert module.CRITICAL_FINDINGS_TARGET_PRODUCTS == ["critical one", "critical two"]       # Global TARGET_PRODUCT_NAMES fallback.
    assert module.CRITICAL_FINDINGS_KEYWORD_REGEX   == r"\bcritical[\s-]?findings?\b"          # Uses module default regex (not KEYWORD_REGEX).
    assert module.CRITICAL_FINDINGS_BANNER_TEXT     == DEFAULT_CRITICAL_BANNER                  # Uses module default banner text.

    assert module.CRITICAL_FINDINGS_CONFIG.active_statuses      == module.CRITICAL_FINDINGS_ACTIVE_STATUSES  # Config wired to constants.
    assert module.CRITICAL_FINDINGS_CONFIG.target_product_names == module.CRITICAL_FINDINGS_TARGET_PRODUCTS   # Config wired to constants.
    assert module.CRITICAL_FINDINGS_CONFIG.keyword_regex        == module.CRITICAL_FINDINGS_KEYWORD_REGEX     # Config wired to constants.
    assert module.CRITICAL_FINDINGS_CONFIG.card_banner_text     == module.CRITICAL_FINDINGS_BANNER_TEXT       # Config wired to constants.


def test_critical_findings_config_prefers_specific_env_over_global(monkeypatch) -> None:
    """CRITICAL_FINDINGS_* env vars should override global fallback vars when both are present."""  # Override behavior.
    module = _import_critical_findings_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "CRITICAL_FINDINGS_ACTIVE_STATUSES": "Open, Waiting",
            "CRITICAL_FINDINGS_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "CRITICAL_FINDINGS_KEYWORD_REGEX": r"\\boverride\\b",
            "CRITICAL_FINDINGS_BANNER_TEXT": "  custom banner text  ",
            "CRITICAL_FINDINGS_MAX_AGE_HOURS": "72",
            "CRITICAL_FINDINGS_MIN_AGE_MINUTES": "15",
        },
    )

    assert module.CRITICAL_FINDINGS_ACTIVE_STATUSES == {"Open", "Waiting"}               # CRITICAL_FINDINGS_* should win.
    assert module.CRITICAL_FINDINGS_TARGET_PRODUCTS == ["override one", "override two"]  # CRITICAL_FINDINGS_* should win + normalize.
    assert module.CRITICAL_FINDINGS_KEYWORD_REGEX   == r"\boverride\b"                    # CRITICAL_FINDINGS_* regex should win and unescape.
    assert module.CRITICAL_FINDINGS_BANNER_TEXT     == "custom banner text"               # Banner text should be stripped.

    assert module.CRITICAL_FINDINGS_CONFIG.max_age_hours   == 72  # Integer env parsing for max age.
    assert module.CRITICAL_FINDINGS_CONFIG.min_age_minutes == 15  # Integer env parsing for min age.
    assert module.CRITICAL_FINDINGS_CONFIG.active_statuses == {"Open", "Waiting"}   # Config should reflect overrides.
    assert module.CRITICAL_FINDINGS_CONFIG.card_banner_text == "custom banner text"  # Config should reflect banner override.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_critical_findings_watch_with_env(monkeypatch)  # Base import with deterministic env state.

    calls: list[Dict[str, Any]] = []  # Capture delegation call payload.

    def fake_run_product_loop_once(config, token, pre_fetched_tickets=None) -> None:
        calls.append(  # Save positional intent explicitly.
            {
                "config": config,
                "token": token,
                "pre_fetched_tickets": pre_fetched_tickets,
            }
        )

    monkeypatch.setattr(module, "run_product_loop_once", fake_run_product_loop_once)  # Patch shared helper entrypoint.

    test_token   = "token-critical"
    test_tickets = [{"id": "1166045000005044432", "ticketNumber": "4682"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is module.CRITICAL_FINDINGS_CONFIG  # Must pass module config object.
    assert calls[0]["token"]               == test_token                      # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets                   # Must forward provided tickets object.
