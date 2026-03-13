"""Unit tests for nm_studies_watch config wiring and run_cycle delegation."""  # Module purpose.

from __future__ import annotations

import importlib  # Reload module under controlled env values.
import sys        # Clear cached modules from import state.
from typing import Any, Dict, Iterable  # Keep helper typing explicit.

import dotenv  # Patch dotenv loader to keep env deterministic during module import.


NM_STUDIES_MODULE = "src.scripts.nm_studies_watch"  # Module under test.
WATCH_HELPER_MODULE = "src.core.watch_helper"       # Must also be reloaded because it calls load_dotenv() at import time.

# Env keys that influence nm_studies module-level constants/config.
NM_STUDIES_ENV_KEYS = [
    "ACTIVE_STATUSES",
    "TARGET_PRODUCT_NAMES",
    "KEYWORD_REGEX",
    "NM_STUDIES_ACTIVE_STATUSES",
    "NM_STUDIES_TARGET_PRODUCT_NAMES",
    "NM_STUDIES_KEYWORD_REGEX",
    "NM_STUDIES_MAX_AGE_HOURS",
    "NM_STUDIES_MIN_AGE_MINUTES",
]


def _import_nm_studies_watch_with_env(
    monkeypatch,
    *,
    set_env: Dict[str, str] | None = None,
    unset_env: Iterable[str] | None = None,
):
    """Import/reload nm_studies_watch after applying per-test env state."""  # Helper intent.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # Prevent .env from repopulating NM_STUDIES_* vars.
    if unset_env:  # Remove explicit keys first.
        for name in unset_env:
            monkeypatch.delenv(name, raising=False)
    for name in NM_STUDIES_ENV_KEYS:  # Remove untouched nm-studies keys for deterministic imports.
        if not set_env or name not in set_env:
            monkeypatch.delenv(name, raising=False)
    if set_env:  # Apply requested env values.
        for key, value in set_env.items():
            monkeypatch.setenv(key, value)
    sys.modules.pop(NM_STUDIES_MODULE, None)     # Force fresh nm_studies module import.
    sys.modules.pop(WATCH_HELPER_MODULE, None)   # Force fresh watch_helper import with patched load_dotenv.
    return importlib.import_module(NM_STUDIES_MODULE)  # Import with current env snapshot.


def test_nm_studies_config_uses_defined_fallback_behavior(monkeypatch) -> None:
    """When NM_STUDIES_* vars are absent, module should use its defined fallback behavior."""  # Fallback behavior.
    module = _import_nm_studies_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned, Pending ,Escalated",
            "TARGET_PRODUCT_NAMES": "Ignored Product One, Ignored Product Two",
            "KEYWORD_REGEX": r"\\bignored\\b",
        },
    )

    assert module.NM_STUDIES_ACTIVE_STATUSES == {"Assigned", "Pending", "Escalated"}  # Global ACTIVE_STATUSES fallback.
    assert module.NM_STUDIES_TARGET_PRODUCTS == ["nm studies"]                          # Uses module default product target.
    assert module.NM_STUDIES_KEYWORD_REGEX   == r"\bnm[\s/-]*studies\b"                 # Uses module default regex.

    assert module.NM_STUDIES_CONFIG.active_statuses      == module.NM_STUDIES_ACTIVE_STATUSES  # Config wired to constants.
    assert module.NM_STUDIES_CONFIG.target_product_names == module.NM_STUDIES_TARGET_PRODUCTS   # Config wired to constants.
    assert module.NM_STUDIES_CONFIG.keyword_regex        == module.NM_STUDIES_KEYWORD_REGEX     # Config wired to constants.


def test_nm_studies_config_prefers_nm_studies_specific_env_over_global(monkeypatch) -> None:
    """NM_STUDIES_* env vars should override any global fallback vars when both are present."""  # Override behavior.
    module = _import_nm_studies_watch_with_env(
        monkeypatch,
        set_env={
            "ACTIVE_STATUSES": "Assigned,Pending",
            "TARGET_PRODUCT_NAMES": "Ignored Product",
            "KEYWORD_REGEX": r"\\bignored\\b",
            "NM_STUDIES_ACTIVE_STATUSES": "Open, Waiting",
            "NM_STUDIES_TARGET_PRODUCT_NAMES": "  Override One , Override Two ",
            "NM_STUDIES_KEYWORD_REGEX": r"\\boverride\\b",
            "NM_STUDIES_MAX_AGE_HOURS": "36",
            "NM_STUDIES_MIN_AGE_MINUTES": "9",
        },
    )

    assert module.NM_STUDIES_ACTIVE_STATUSES == {"Open", "Waiting"}               # NM_STUDIES_* should win.
    assert module.NM_STUDIES_TARGET_PRODUCTS == ["override one", "override two"]  # NM_STUDIES_* should win + normalize.
    assert module.NM_STUDIES_KEYWORD_REGEX   == r"\boverride\b"                    # NM_STUDIES_* regex should win and unescape.

    assert module.NM_STUDIES_CONFIG.max_age_hours   == 36  # Integer env parsing for max age.
    assert module.NM_STUDIES_CONFIG.min_age_minutes == 9   # Integer env parsing for min age.
    assert module.NM_STUDIES_CONFIG.active_statuses == {"Open", "Waiting"}  # Config should reflect overrides.


def test_run_cycle_delegates_to_run_product_loop_once_with_expected_arguments(monkeypatch) -> None:
    """run_cycle should forward config/token/tickets to run_product_loop_once exactly once."""  # Delegation contract.
    module = _import_nm_studies_watch_with_env(monkeypatch)  # Base import with deterministic env state.

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

    test_token   = "token-nm-studies"
    test_tickets = [{"id": "1166045000005109999", "ticketNumber": "4707"}]
    module.run_cycle(test_token, pre_fetched_tickets=test_tickets)  # Execute function under test.

    assert len(calls) == 1  # Must delegate exactly once.
    assert calls[0]["config"]              is module.NM_STUDIES_CONFIG  # Must pass module config object.
    assert calls[0]["token"]               == test_token                 # Must forward token unchanged.
    assert calls[0]["pre_fetched_tickets"] is test_tickets              # Must forward provided tickets object.
