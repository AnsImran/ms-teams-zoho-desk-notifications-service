"""Unit tests for code_stroke_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib    # Reload module under controlled env values.
import sys          # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


CODE_STROKE_MODULE = "src.scripts.code_stroke_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"          # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence code_stroke module-level constants/config.
CODE_STROKE_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "CODE_STROKE_ACTIVE_STATUSES",
    "CODE_STROKE_TARGET_PRODUCT_NAMES",
    "CODE_STROKE_KEYWORD_REGEX",
    "CODE_STROKE_MAX_AGE_HOURS",
    "CODE_STROKE_MIN_AGE_MINUTES",
]


def _import_code_stroke_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload code_stroke_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating CODE_STROKE_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in CODE_STROKE_ENV_KEYS:  # Remove untouched code-stroke keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(CODE_STROKE_MODULE, None)  # Force fresh code_stroke module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)  # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(CODE_STROKE_MODULE)  # Import with current env snapshot.


def test_code_stroke_config_uses_defined_fallback_behavior(monkeypatch) -> None:
    """When CODE_STROKE_* vars are absent, module should use its defined fallback behavior."""  # Fallback behavior.
    module = _import_code_stroke_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Ignored Product One, Ignored Product Two",
            "KEYWORD_REGEX": r"\\bignored\\b",
        },
    )

    assert module.CODE_STROKE_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global ACTIVE_STATUSES fallback.
    assert module.CODE_STROKE_TARGET_PRODUCTS == []                                      # No TARGET_PRODUCT_NAMES fallback in this module.
    assert module.CODE_STROKE_KEYWORD_REGEX   == r"\bcode[\s-]?stroke\b"                 # Uses module default regex, not KEYWORD_REGEX.

    assert module.CODE_STROKE_CONFIG.active_statuses      == module.CODE_STROKE_ACTIVE_STATUSES  # Config wired to constants.
    assert module.CODE_STROKE_CONFIG.target_product_names == module.CODE_STROKE_TARGET_PRODUCTS   # Config wired to constants.
    assert module.CODE_STROKE_CONFIG.keyword_regex        == module.CODE_STROKE_KEYWORD_REGEX     # Config wired to constants.


def test_code_stroke_config_prefers_code_stroke_specific_env_over_global(monkeypatch) -> None:
    """CODE_STROKE_* env vars should override any global fallback vars when both are present."""  # Override behavior.
    module = _import_code_stroke_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "CODE_STROKE_ACTIVE_STATUSES": "Open, Waiting",
            "CODE_STROKE_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "CODE_STROKE_KEYWORD_REGEX": r"\\boverride\\b",
            "CODE_STROKE_MAX_AGE_HOURS": "36",
            "CODE_STROKE_MIN_AGE_MINUTES": "9",
        },
    )

    assert module.CODE_STROKE_ACTIVE_STATUSES == {"Open", "Waiting"}               # CODE_STROKE_* should win.
    assert module.CODE_STROKE_TARGET_PRODUCTS == ["override one", "override two"]  # CODE_STROKE_* should win + normalize.
    assert module.CODE_STROKE_KEYWORD_REGEX   == r"\boverride\b"                    # CODE_STROKE_* regex should win and unescape.

    assert module.CODE_STROKE_CONFIG.max_age_hours   == 36  # Integer env parsing for max age.
    assert module.CODE_STROKE_CONFIG.min_age_minutes == 9   # Integer env parsing for min age.
    assert module.CODE_STROKE_CONFIG.active_statuses == {"Open", "Waiting"}  # Config should reflect overrides.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_code_stroke_watch_with_env(monkeypatch)  # Base import with deterministic env state.

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

    test_token   = "token-code-stroke"
    test_tickets = [{"id": "1166045000005104162", "ticketNumber": "4689"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is module.CODE_STROKE_CONFIG  # Must pass module config object.
    assert calls[0]["token"]               == test_token                 # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets              # Must forward provided tickets object.
