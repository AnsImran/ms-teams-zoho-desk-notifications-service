"""Unit tests for it_system_studies_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib  # Reload module under controlled env values.
import sys        # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


IT_SYSTEM_STUDIES_MODULE = "src.scripts.it_system_studies_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"                      # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence it_system_studies module-level constants/config.
IT_SYSTEM_STUDIES_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "IT_SYSTEM_STUDIES_ACTIVE_STATUSES",
    "IT_SYSTEM_STUDIES_TARGET_PRODUCT_NAMES",
    "IT_SYSTEM_STUDIES_KEYWORD_REGEX",
    "IT_SYSTEM_STUDIES_MAX_AGE_HOURS",
    "IT_SYSTEM_STUDIES_MIN_AGE_MINUTES",
]


def _import_it_system_studies_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload it_system_studies_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating IT_SYSTEM_STUDIES_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in IT_SYSTEM_STUDIES_ENV_KEYS:  # Remove untouched it-system-studies keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(IT_SYSTEM_STUDIES_MODULE, None)  # Force fresh it_system_studies module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)       # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(IT_SYSTEM_STUDIES_MODULE)  # Import with current env snapshot.


def test_it_system_studies_config_uses_defined_fallback_behavior(monkeypatch) -> None:
    """When IT_SYSTEM_STUDIES_* vars are absent, module should use its defined fallback behavior."""  # Fallback behavior.
    module = _import_it_system_studies_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Ignored Product One, Ignored Product Two",
            "KEYWORD_REGEX": r"\\bignored\\b",
        },
    )

    assert module.IT_SYSTEM_STUDIES_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global ACTIVE_STATUSES fallback.
    assert module.IT_SYSTEM_STUDIES_TARGET_PRODUCTS == ["it / system studies"]                 # Uses module default product target.
    assert module.IT_SYSTEM_STUDIES_KEYWORD_REGEX   == r"\bit\s*/\s*system\s*studies\b"       # Uses module default regex.

    assert module.IT_SYSTEM_STUDIES_CONFIG.active_statuses      == module.IT_SYSTEM_STUDIES_ACTIVE_STATUSES  # Config wired to constants.
    assert module.IT_SYSTEM_STUDIES_CONFIG.target_product_names == module.IT_SYSTEM_STUDIES_TARGET_PRODUCTS   # Config wired to constants.
    assert module.IT_SYSTEM_STUDIES_CONFIG.keyword_regex        == module.IT_SYSTEM_STUDIES_KEYWORD_REGEX     # Config wired to constants.


def test_it_system_studies_config_prefers_specific_env_over_global(monkeypatch) -> None:
    """IT_SYSTEM_STUDIES_* env vars should override any global fallback vars when both are present."""  # Override behavior.
    module = _import_it_system_studies_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "IT_SYSTEM_STUDIES_ACTIVE_STATUSES": "Open, Waiting",
            "IT_SYSTEM_STUDIES_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "IT_SYSTEM_STUDIES_KEYWORD_REGEX": r"\\boverride\\b",
            "IT_SYSTEM_STUDIES_MAX_AGE_HOURS": "36",
            "IT_SYSTEM_STUDIES_MIN_AGE_MINUTES": "9",
        },
    )

    assert module.IT_SYSTEM_STUDIES_ACTIVE_STATUSES == {"Open", "Waiting"}               # IT_SYSTEM_STUDIES_* should win.
    assert module.IT_SYSTEM_STUDIES_TARGET_PRODUCTS == ["override one", "override two"]  # IT_SYSTEM_STUDIES_* should win + normalize.
    assert module.IT_SYSTEM_STUDIES_KEYWORD_REGEX   == r"\boverride\b"                    # IT_SYSTEM_STUDIES_* regex should win and unescape.

    assert module.IT_SYSTEM_STUDIES_CONFIG.max_age_hours   == 36  # Integer env parsing for max age.
    assert module.IT_SYSTEM_STUDIES_CONFIG.min_age_minutes == 9   # Integer env parsing for min age.
    assert module.IT_SYSTEM_STUDIES_CONFIG.active_statuses == {"Open", "Waiting"}  # Config should reflect overrides.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_it_system_studies_watch_with_env(monkeypatch)  # Base import with deterministic env state.

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

    test_token   = "token-it-system-studies"
    test_tickets = [{"id": "1166045000005110000", "ticketNumber": "4708"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is module.IT_SYSTEM_STUDIES_CONFIG  # Must pass module config object.
    assert calls[0]["token"]               == test_token                        # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets                     # Must forward provided tickets object.
