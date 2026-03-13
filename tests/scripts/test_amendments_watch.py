"""Unit tests for amendments_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib  # Reload module under controlled env values.
import sys        # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


AMENDMENTS_MODULE = "src.scripts.amendments_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"       # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence amendments module-level constants/config.
AMENDMENTS_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "AMENDMENTS_ACTIVE_STATUSES",
    "AMENDMENTS_TARGET_PRODUCT_NAMES",
    "AMENDMENTS_KEYWORD_REGEX",
    "AMENDMENTS_MAX_AGE_HOURS",
    "AMENDMENTS_MIN_AGE_MINUTES",
]


def _import_amendments_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload amendments_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating AMENDMENTS_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in AMENDMENTS_ENV_KEYS:  # Remove untouched amendments keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(AMENDMENTS_MODULE, None)     # Force fresh amendments module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)   # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(AMENDMENTS_MODULE)  # Import with current env snapshot.


def test_amendments_config_uses_global_fallback_env_values(monkeypatch) -> None:
    """When AMENDMENTS_* vars are absent, global ACTIVE/TARGET/KEYWORD values should be used."""  # Fallback behavior.
    module = _import_amendments_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Amendments,  Another Product",
            "KEYWORD_REGEX": r"\\bamendments\\b",
        },
    )

    assert module.AMENDMENTS_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global status fallback.
    assert module.AMENDMENTS_TARGET_PRODUCTS == ["amendments", "another product"]      # Global product fallback + normalization.
    assert module.AMENDMENTS_KEYWORD_REGEX   == r"\bamendments\b"                       # Escaped regex should be unescaped once.

    assert module.AMENDMENTS_CONFIG.active_statuses      == module.AMENDMENTS_ACTIVE_STATUSES  # Config wired to constants.
    assert module.AMENDMENTS_CONFIG.target_product_names == module.AMENDMENTS_TARGET_PRODUCTS   # Config wired to constants.
    assert module.AMENDMENTS_CONFIG.keyword_regex        == module.AMENDMENTS_KEYWORD_REGEX     # Config wired to constants.


def test_amendments_config_prefers_specific_env_over_global(monkeypatch) -> None:
    """AMENDMENTS_* env vars should override global fallback vars when both are present."""  # Override behavior.
    module = _import_amendments_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "AMENDMENTS_ACTIVE_STATUSES": "Open, Waiting",
            "AMENDMENTS_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "AMENDMENTS_KEYWORD_REGEX": r"\\boverride\\b",
            "AMENDMENTS_MAX_AGE_HOURS": "48",
            "AMENDMENTS_MIN_AGE_MINUTES": "12",
        },
    )

    assert module.AMENDMENTS_ACTIVE_STATUSES == {"Open", "Waiting"}               # AMENDMENTS_* should win.
    assert module.AMENDMENTS_TARGET_PRODUCTS == ["override one", "override two"]  # AMENDMENTS_* should win + normalize.
    assert module.AMENDMENTS_KEYWORD_REGEX   == r"\boverride\b"                    # AMENDMENTS_* regex should win and unescape.

    assert module.AMENDMENTS_CONFIG.max_age_hours   == 48  # Integer env parsing for max age.
    assert module.AMENDMENTS_CONFIG.min_age_minutes == 12  # Integer env parsing for min age.
    assert module.AMENDMENTS_CONFIG.active_statuses == {"Open", "Waiting"}  # Config should reflect overrides.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_amendments_watch_with_env(monkeypatch)  # Base import with deterministic env state.

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

    test_token   = "token-amendments"
    test_tickets = [{"id": "1166045000005044432", "ticketNumber": "4682"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is module.AMENDMENTS_CONFIG  # Must pass module config object.
    assert calls[0]["token"]               == test_token                # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets             # Must forward provided tickets object.
