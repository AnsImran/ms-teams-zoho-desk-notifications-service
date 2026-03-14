"""Unit tests for run_single_product_cycle and run_product_loop_once orchestration behavior."""  # Module purpose.

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from src.core import watch_helper


class _FakeFuture:
    """Minimal Future-like object used by fake executor submit calls."""  # Keep threading behavior deterministic.

    def __init__(self, *, value: Any = None, error: Exception | None = None) -> None:
        self._value = value
        self._error = error

    def result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._value


def _install_fake_executor(monkeypatch, *, submit_error: Exception | None = None):
    """Patch ThreadPoolExecutor with a deterministic in-process executor."""  # Avoid real threads in unit tests.
    submissions: List[Dict[str, Any]] = []

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            submissions.append(
                {
                    "fn": fn,
                    "args": args,
                    "kwargs": kwargs,
                    "max_workers": self.max_workers,
                }
            )
            if submit_error is not None:
                return _FakeFuture(error=submit_error)
            return _FakeFuture(value=fn(*args, **kwargs))

    monkeypatch.setattr(watch_helper, "ThreadPoolExecutor", _FakeExecutor)
    return submissions


def _make_ticket(
    *,
    ticket_id: str | None = "1166045000005103001",
    ticket_number: str = "4679",
    status: str = "Assigned",
    status_type: str = "Open",
    subject: str = "Test subject",
    description: str = "Test description",
    created_time: str = "2026-01-01T11:00:00.000Z",
    web_url: str = "https://desk.zoho.com/support/webzter/ShowHomePage.do#Cases/dv/1166045000005103001",
) -> Dict[str, Any]:
    """Build one baseline ticket payload with per-test overrides."""  # Keep test setup concise.
    return {
        "id": ticket_id,
        "ticketNumber": ticket_number,
        "status": status,
        "statusType": status_type,
        "subject": subject,
        "description": description,
        "createdTime": created_time,
        "webUrl": web_url,
    }


@pytest.fixture
def fixed_now() -> datetime:
    """Deterministic 'current time' used across product-cycle tests."""  # Avoid clock flakiness.
    return datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def product_config() -> watch_helper.ProductConfig:
    """Reusable ProductConfig fixture for product-loop tests."""  # Shared config reduces duplication.
    return watch_helper.ProductConfig(
        name="Test Product",
        keyword_regex=r"\\btest\\b",
        target_product_names=["test product"],
        active_statuses={"Assigned", "Pending"},
        teams_webhook_env_var="TEAMS_WEBHOOK_TEST_PRODUCT",
        last_sent_filename="sent_test_product_notifications.json",
        max_age_hours=24,
        min_age_minutes=5,
    )


def test_run_single_product_cycle_uses_prefetched_tickets_without_search(monkeypatch, product_config, fixed_now) -> None:
    """When pre_fetched_tickets are provided, search_tickets should not be called."""  # Branch: prefetched path.
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (False, "no match"))
    monkeypatch.setattr(
        watch_helper,
        "search_tickets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search_tickets should not be called")),
    )
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket()],
    )

    assert hits == 0
    assert changed is False


def test_run_single_product_cycle_calls_search_when_prefetched_missing(monkeypatch, product_config) -> None:
    """When pre_fetched_tickets are missing, search_tickets should be called with sorted statuses."""  # Branch: fetch path.
    calls: List[Dict[str, Any]] = []

    def fake_search(token: str, statuses: List[str], hours: int) -> List[Dict[str, Any]]:
        calls.append({"token": token, "statuses": statuses, "hours": hours})
        return []

    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "search_tickets", fake_search)
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-abc",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=None,
    )

    assert hits == 0
    assert changed is False
    assert len(calls) == 1
    assert calls[0]["token"] == "token-abc"
    assert calls[0]["statuses"] == sorted(product_config.active_statuses)
    assert calls[0]["hours"] == product_config.max_age_hours


def test_run_single_product_cycle_skips_ticket_when_id_missing(monkeypatch, product_config) -> None:
    """Tickets without IDs should be skipped before alert checks."""  # Branch: missing ticket id.
    should_alert_calls = {"count": 0}

    def fake_should_alert(*_args, **_kwargs):
        should_alert_calls["count"] += 1
        return True, "should not run"

    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "should_alert", fake_should_alert)
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket(ticket_id=None)],
    )

    assert hits == 0
    assert changed is False
    assert should_alert_calls["count"] == 0


def test_run_single_product_cycle_skips_ticket_when_status_not_active(monkeypatch, product_config) -> None:
    """Tickets outside active statuses should be skipped before parse/alert checks."""  # Branch: status filter.
    should_alert_calls = {"count": 0}

    def fake_should_alert(*_args, **_kwargs):
        should_alert_calls["count"] += 1
        return True, "should not run"

    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "should_alert", fake_should_alert)
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket(status="Closed")],
    )

    assert hits == 0
    assert changed is False
    assert should_alert_calls["count"] == 0


def test_run_single_product_cycle_skips_ticket_older_than_window(monkeypatch, product_config, fixed_now) -> None:
    """Tickets older than max_age_hours should be skipped before should_alert."""  # Branch: age window filter.
    should_alert_calls = {"count": 0}

    def fake_should_alert(*_args, **_kwargs):
        should_alert_calls["count"] += 1
        return True, "should not run"

    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=30))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", fake_should_alert)
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket()],
    )

    assert hits == 0
    assert changed is False
    assert should_alert_calls["count"] == 0


def test_run_single_product_cycle_skips_when_should_alert_false(monkeypatch, product_config, fixed_now) -> None:
    """Tickets should be skipped when should_alert returns False."""  # Branch: should_alert negative.
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (False, "no match"))
    submissions = _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket()],
    )

    assert hits == 0
    assert changed is False
    assert submissions == []


def test_run_single_product_cycle_skips_when_cooldown_active(monkeypatch, product_config, fixed_now) -> None:
    """Cooldown should block repeat alerts before webhook submission."""  # Branch: cooldown skip.
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 3600)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    submissions = _install_fake_executor(monkeypatch)

    ticket = _make_ticket()
    last_sent = {ticket["id"]: datetime.now()}  # Real now is sufficient; elapsed will stay below 1 hour.
    before = dict(last_sent)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent=last_sent,
        pre_fetched_tickets=[ticket],
    )

    assert hits == 0
    assert changed is False
    assert last_sent == before
    assert submissions == []


def test_run_single_product_cycle_skips_send_when_webhook_missing(monkeypatch, product_config, fixed_now) -> None:
    """If webhook is missing and no magic route applies, ticket should not be sent."""  # Branch: no webhook configured.
    monkeypatch.delenv(product_config.teams_webhook_env_var, raising=False)
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    submissions = _install_fake_executor(monkeypatch)

    last_sent: Dict[str, datetime] = {}
    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent=last_sent,
        pre_fetched_tickets=[_make_ticket()],
    )

    assert hits == 0
    assert changed is False
    assert last_sent == {}
    assert submissions == []


def test_run_single_product_cycle_routes_to_normal_webhook_when_magic_not_matched(monkeypatch, product_config, fixed_now) -> None:
    """Non-magic tickets should use product webhook env var."""  # Branch: normal webhook route.
    monkeypatch.setenv(product_config.teams_webhook_env_var, "https://teams.example/webhook")
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kwargs: {"payload": "card"})

    posted: List[Dict[str, Any]] = []

    def fake_post_to_teams(webhook_url: str, payload: Dict[str, Any]) -> None:
        posted.append({"webhook_url": webhook_url, "payload": payload})

    monkeypatch.setattr(watch_helper, "post_to_teams", fake_post_to_teams)
    _install_fake_executor(monkeypatch)

    ticket = _make_ticket()
    last_sent: Dict[str, datetime] = {}
    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent=last_sent,
        pre_fetched_tickets=[ticket],
    )

    assert hits == 1
    assert changed is True
    assert ticket["id"] in last_sent
    assert posted == [{"webhook_url": "https://teams.example/webhook", "payload": {"payload": "card"}}]


def test_run_single_product_cycle_routes_to_magic_webhook_when_phrase_matches(monkeypatch, product_config, fixed_now) -> None:
    """Magic phrase hits should route to MAGIC_TEST_WEBHOOK instead of product webhook."""  # Branch: magic route.
    monkeypatch.setenv(product_config.teams_webhook_env_var, "https://teams.example/normal-webhook")
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: True)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kwargs: {"payload": "card"})

    posted: List[Dict[str, Any]] = []

    def fake_post_to_teams(webhook_url: str, payload: Dict[str, Any]) -> None:
        posted.append({"webhook_url": webhook_url, "payload": payload})

    monkeypatch.setattr(watch_helper, "post_to_teams", fake_post_to_teams)
    _install_fake_executor(monkeypatch)

    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[_make_ticket()],
    )

    assert hits == 1
    assert changed is True
    assert posted[0]["webhook_url"] == watch_helper.MAGIC_TEST_WEBHOOK


def test_run_single_product_cycle_parse_failure_uses_fallback_created_display_and_age(monkeypatch, product_config) -> None:
    """Parse failures should fallback to raw createdTime and age -1 while still allowing alert flow."""  # Branch: parse exception.
    monkeypatch.setenv(product_config.teams_webhook_env_var, "https://teams.example/webhook")
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(
        watch_helper,
        "parse_zoho_time_assume_la",
        lambda _raw: (_ for _ in ()).throw(ValueError("bad createdTime")),
    )
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)

    card_kwargs: Dict[str, Any] = {}

    def fake_build_card(**kwargs):
        card_kwargs.update(kwargs)
        return {"payload": "card"}

    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", fake_build_card)
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda *_args, **_kwargs: None)
    _install_fake_executor(monkeypatch)

    ticket = _make_ticket(created_time="RAW_BAD_CREATED_TIME")
    hits, changed = watch_helper.run_single_product_cycle(
        config=product_config,
        token="token-123",
        compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
        last_sent={},
        pre_fetched_tickets=[ticket],
    )

    assert hits == 1
    assert changed is True
    assert card_kwargs["created_display"] == "RAW_BAD_CREATED_TIME"
    assert card_kwargs["age_minutes"] == -1


def test_run_single_product_cycle_raises_when_send_future_fails(monkeypatch, product_config, fixed_now) -> None:
    """Any exception raised by send future should propagate to caller."""  # Branch: future.result error propagation.
    monkeypatch.setenv(product_config.teams_webhook_env_var, "https://teams.example/webhook")
    monkeypatch.setattr(watch_helper, "effective_notify_cooldown_seconds", lambda _cfg: 0)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "should_alert", lambda *_args, **_kwargs: (True, "subject keyword match; age ok"))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kwargs: {"payload": "card"})
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda *_args, **_kwargs: None)
    _install_fake_executor(monkeypatch, submit_error=RuntimeError("send failed"))

    with pytest.raises(RuntimeError, match="send failed"):
        watch_helper.run_single_product_cycle(
            config=product_config,
            token="token-123",
            compiled_regex=re.compile(product_config.keyword_regex, re.IGNORECASE),
            last_sent={},
            pre_fetched_tickets=[_make_ticket()],
        )


def test_run_product_loop_once_builds_path_compiles_regex_delegates_and_saves(monkeypatch, product_config) -> None:
    """run_product_loop_once should load, compile, delegate, and save when changed=True."""  # Branch: changed save path.
    expected_path = os.path.join(os.path.dirname(os.path.abspath(watch_helper.__file__)), product_config.last_sent_filename)
    loaded_last_sent = {"1166045000005103001": datetime(2026, 1, 1, 12, 0, 0)}
    compiled_regex = object()

    load_calls: List[str] = []
    compile_calls: List[Dict[str, Any]] = []
    cycle_calls: List[Dict[str, Any]] = []
    save_calls: List[Dict[str, Any]] = []

    monkeypatch.setattr(watch_helper.os.path, "exists", lambda path: False if path == expected_path else True)

    def fake_load(path: str) -> Dict[str, datetime]:
        load_calls.append(path)
        return loaded_last_sent

    def fake_compile(pattern: str, flags: int):
        compile_calls.append({"pattern": pattern, "flags": flags})
        return compiled_regex

    def fake_run_single_product_cycle(**kwargs):
        cycle_calls.append(kwargs)
        return 2, True

    def fake_save(path: str, payload: Dict[str, datetime]) -> None:
        save_calls.append({"path": path, "payload": payload})

    monkeypatch.setattr(watch_helper, "load_last_sent", fake_load)
    monkeypatch.setattr(watch_helper.re, "compile", fake_compile)
    monkeypatch.setattr(watch_helper, "run_single_product_cycle", fake_run_single_product_cycle)
    monkeypatch.setattr(watch_helper, "save_last_sent", fake_save)

    pre_fetched = [_make_ticket()]
    watch_helper.run_product_loop_once(product_config, token="token-123", pre_fetched_tickets=pre_fetched)

    assert load_calls == [expected_path]
    assert compile_calls == [{"pattern": product_config.keyword_regex, "flags": re.IGNORECASE}]
    assert len(cycle_calls) == 1
    assert cycle_calls[0]["config"] is product_config
    assert cycle_calls[0]["token"] == "token-123"
    assert cycle_calls[0]["compiled_regex"] is compiled_regex
    assert cycle_calls[0]["last_sent"] is loaded_last_sent
    assert cycle_calls[0]["pre_fetched_tickets"] is pre_fetched
    assert save_calls == [{"path": expected_path, "payload": loaded_last_sent}]


def test_run_product_loop_once_skips_save_when_changed_false(monkeypatch, product_config) -> None:
    """run_product_loop_once should not persist when changed=False."""  # Branch: unchanged skip-save path.
    expected_path = os.path.join(os.path.dirname(os.path.abspath(watch_helper.__file__)), product_config.last_sent_filename)
    loaded_last_sent: Dict[str, datetime] = {}
    compiled_regex = object()

    save_calls: List[Dict[str, Any]] = []
    compile_calls: List[Dict[str, Any]] = []

    monkeypatch.setattr(watch_helper.os.path, "exists", lambda path: True if path == expected_path else False)
    monkeypatch.setattr(watch_helper, "load_last_sent", lambda _path: loaded_last_sent)

    def fake_compile(pattern: str, flags: int):
        compile_calls.append({"pattern": pattern, "flags": flags})
        return compiled_regex

    monkeypatch.setattr(watch_helper.re, "compile", fake_compile)
    monkeypatch.setattr(watch_helper, "run_single_product_cycle", lambda **_kwargs: (0, False))
    monkeypatch.setattr(watch_helper, "save_last_sent", lambda path, payload: save_calls.append({"path": path, "payload": payload}))

    watch_helper.run_product_loop_once(product_config, token="token-123", pre_fetched_tickets=None)

    assert compile_calls == [{"pattern": product_config.keyword_regex, "flags": re.IGNORECASE}]
    assert save_calls == []
