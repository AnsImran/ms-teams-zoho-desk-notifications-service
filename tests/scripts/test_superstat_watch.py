"""Unit tests for superstat_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib    # Reload module under controlled env values.
import sys          # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


SUPERSTAT_MODULE = "src.scripts.superstat_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"     # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence superstat module-level constants/config.
SUPERSTAT_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "SUPERSTAT_ACTIVE_STATUSES",
    "SUPERSTAT_TARGET_PRODUCT_NAMES",
    "SUPERSTAT_KEYWORD_REGEX",
    "SUPERSTAT_MAX_AGE_HOURS",
    "SUPERSTAT_MIN_AGE_MINUTES",
]


def _import_superstat_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload superstat_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating SUPERSTAT_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in SUPERSTAT_ENV_KEYS:  # Remove untouched superstat keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(SUPERSTAT_MODULE, None)       # Force fresh superstat module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)    # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(SUPERSTAT_MODULE)  # Import with current env snapshot.


def test_superstat_config_uses_global_fallback_env_values(monkeypatch) -> None:
    """When SUPERSTAT_* vars are absent, global ACTIVE/TARGET/KEYWORD values should be used."""  # Fallback behavior.
    module = _import_superstat_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Super Stat,  Another Product",
            "KEYWORD_REGEX": r"\\bsuper\\s+stat\\b",
        },
    )

    assert module.SUPERSTAT_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global status fallback.
    assert module.SUPERSTAT_TARGET_PRODUCTS == ["super stat", "another product"]      # Global product fallback + normalization.
    assert module.SUPERSTAT_KEYWORD_REGEX   == r"\bsuper\s+stat\b"                     # Escaped regex should be unescaped once.

    assert module.SUPERSTAT_CONFIG.active_statuses      == module.SUPERSTAT_ACTIVE_STATUSES  # Config wired to constants.
    assert module.SUPERSTAT_CONFIG.target_product_names == module.SUPERSTAT_TARGET_PRODUCTS   # Config wired to constants.
    assert module.SUPERSTAT_CONFIG.keyword_regex        == module.SUPERSTAT_KEYWORD_REGEX     # Config wired to constants.


def test_superstat_config_prefers_superstat_specific_env_over_global(monkeypatch) -> None:
    """SUPERSTAT_* env vars should override global fallback vars when both are present."""  # Override behavior.
    module = _import_superstat_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "SUPERSTAT_ACTIVE_STATUSES": "Open, Waiting",
            "SUPERSTAT_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "SUPERSTAT_KEYWORD_REGEX": r"\\boverride\\b",
            "SUPERSTAT_MAX_AGE_HOURS": "48",
            "SUPERSTAT_MIN_AGE_MINUTES": "12",
        },
    )

    assert module.SUPERSTAT_ACTIVE_STATUSES == {"Open", "Waiting"}               # SUPERSTAT_* should win.
    assert module.SUPERSTAT_TARGET_PRODUCTS == ["override one", "override two"]  # SUPERSTAT_* should win + normalize.
    assert module.SUPERSTAT_KEYWORD_REGEX   == r"\boverride\b"                    # SUPERSTAT_* regex should win and unescape.

    assert module.SUPERSTAT_CONFIG.max_age_hours   == 48  # Integer env parsing for max age.
    assert module.SUPERSTAT_CONFIG.min_age_minutes == 12  # Integer env parsing for min age.
    assert module.SUPERSTAT_CONFIG.active_statuses == {"Open", "Waiting"}  # Config should reflect overrides.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_superstat_watch_with_env(monkeypatch)  # Base import with deterministic env state.

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

    test_token   = "token-abc"
    test_tickets = [{"id": "1166045000005103001", "ticketNumber": "4679"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]               is module.SUPERSTAT_CONFIG  # Must pass module config object.
    assert calls[0]["token"]                == test_token               # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"]  is test_tickets             # Must forward provided tickets object.
