"""Unit tests for the single-loop process_tickets architecture."""  # Module purpose.

from __future__ import annotations

from datetime import datetime, timedelta  # Drive deterministic time branches.
from typing import Any, Dict, List        # Keep helper typing explicit and readable.

import pytest  # Test runner and assertions.

from src.core import watch_helper  # Module under test.


def _make_ticket(
    *,
    ticket_id:     str = "1166045000005103001",
    ticket_number: str = "4679",
    status:        str = "Assigned",
    status_type:   str = "Open",
    subject:       str = "Test subject",
    description:   str = "Test description",
    created_time:  str = "2026-01-01T11:00:00.000Z",
    web_url:       str = "https://desk.zoho.com/ticket/1",
    product_name:  str = "Super Stat",
) -> Dict[str, Any]:
    """Build one baseline ticket payload with per-test overrides."""  # Keep test setup concise.
    return {
        "id":           ticket_id,
        "ticketNumber": ticket_number,
        "status":       status,
        "statusType":   status_type,
        "subject":      subject,
        "description":  description,
        "createdTime":  created_time,
        "webUrl":       web_url,
        "productName":  product_name,
    }


@pytest.fixture
def fixed_now() -> datetime:
    """Deterministic 'current time' used across tests."""  # Avoid clock flakiness.
    return datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def config() -> watch_helper.ProductConfig:
    """Reusable ProductConfig fixture."""  # Shared config reduces duplication.
    return watch_helper.ProductConfig(
        name                  = "Super-Stat",
        target_product_names  = ["Super Stat"],
        active_statuses       = {"Assigned", "Pending"},
        teams_webhook_url     = "https://teams.example/wh",
        last_sent_filename    = "sent_superstat_notifications.json",
        min_age_minutes       = 5,
    )


@pytest.fixture
def lookup(config) -> Dict[str, watch_helper.ProductConfig]:
    """Build a config lookup from the fixture config."""  # Shared lookup.
    return watch_helper.build_config_lookup([config])


def _run(monkeypatch, tickets, lookup, cooldown_state=None, fixed_now=None, webhook="https://teams.example/wh"):
    """Helper to run process_tickets with common monkeypatches."""  # Reduce test boilerplate.
    if fixed_now:                                                   # Pin time when provided.
        monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
        monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    if cooldown_state is None:                                      # Default to empty cooldown state.
        cooldown_state = {}
    return watch_helper.process_tickets(                            # Run the single-loop processor.
        tickets        = tickets,
        config_lookup  = lookup,
        cooldown_state = cooldown_state,
    ), cooldown_state


# ---------------------------------------------------------------------------
# Ticket skipping tests
# ---------------------------------------------------------------------------

def test_skips_ticket_without_id(monkeypatch, lookup, fixed_now) -> None:
    """Tickets missing an id should be skipped entirely."""  # Missing id guard.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    total, _ = _run(monkeypatch, [_make_ticket(ticket_id=None)], lookup, fixed_now=fixed_now)
    assert total == 0
    assert posted == []


def test_skips_ticket_without_product_name(monkeypatch, lookup, fixed_now) -> None:
    """Tickets with no product name should be skipped."""  # No product guard.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    ticket = _make_ticket()
    ticket.pop("productName")
    total, _ = _run(monkeypatch, [ticket], lookup, fixed_now=fixed_now)
    assert total == 0


def test_skips_ticket_with_unknown_product(monkeypatch, lookup, fixed_now) -> None:
    """Tickets for products not in the lookup should be skipped."""  # Unknown product guard.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    total, _ = _run(monkeypatch, [_make_ticket(product_name="Unknown Product")], lookup, fixed_now=fixed_now)
    assert total == 0


def test_skips_ticket_with_inactive_status(monkeypatch, lookup, fixed_now) -> None:
    """Tickets with a status outside the product's active set should be skipped."""  # Status guard.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    total, _ = _run(monkeypatch, [_make_ticket(status="Closed")], lookup, fixed_now=fixed_now)
    assert total == 0


def test_skips_ticket_too_new(monkeypatch, config, lookup) -> None:
    """Tickets younger than min_age_minutes should be skipped."""  # Age guard.
    fixed = datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed)
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed - timedelta(minutes=2))  # 2 min old, min_age is 5.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    total, _ = _run(monkeypatch, [_make_ticket()], lookup)
    assert total == 0


def test_skips_ticket_in_cooldown(monkeypatch, config, lookup, fixed_now) -> None:
    """Tickets still in cooldown should be skipped."""  # Cooldown guard.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    cooldown_state = {config.last_sent_filename: {"1166045000005103001": datetime.now()}}  # Just sent.
    total, _ = _run(monkeypatch, [_make_ticket()], lookup, cooldown_state=cooldown_state, fixed_now=fixed_now)
    assert total == 0
    assert posted == []


# ---------------------------------------------------------------------------
# Successful alert tests
# ---------------------------------------------------------------------------

def test_sends_alert_for_matching_ticket(monkeypatch, config, lookup, fixed_now) -> None:
    """A matching ticket that passes all checks should trigger a Teams POST."""  # Happy path.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append({"url": url, "payload": payload}))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kw: {"card": "test"})
    total, state = _run(monkeypatch, [_make_ticket()], lookup, fixed_now=fixed_now)
    assert total == 1
    assert len(posted) == 1
    assert posted[0]["url"] == "https://teams.example/wh"
    assert "1166045000005103001" in state[config.last_sent_filename]  # Cooldown recorded.


def test_routes_magic_ticket_to_magic_webhook(monkeypatch, config, lookup, fixed_now) -> None:
    """Magic phrase tickets should use the shared magic test webhook."""  # Magic route.
    monkeypatch.setattr(watch_helper, "MAGIC_TEST_WEBHOOK", "https://magic.example/test")  # Ensure magic webhook is set.
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: True)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kw: {"card": "test"})
    total, _ = _run(monkeypatch, [_make_ticket()], lookup, fixed_now=fixed_now)
    assert total == 1
    assert posted[0] == "https://magic.example/test"


def test_skips_send_when_webhook_missing(monkeypatch, fixed_now) -> None:
    """If no webhook is configured and no magic phrase, ticket should be skipped."""  # No webhook.
    empty_webhook_config = watch_helper.ProductConfig(                            # Config with empty webhook URL.
        name="Super-Stat", target_product_names=["Super Stat"],
        active_statuses={"Assigned", "Pending"}, teams_webhook_url="",
        last_sent_filename="sent_superstat_notifications.json", min_age_minutes=5,
    )
    empty_lookup = watch_helper.build_config_lookup([empty_webhook_config])
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kw: {"card": "test"})
    total, _ = _run(monkeypatch, [_make_ticket()], empty_lookup, fixed_now=fixed_now)
    assert total == 0
    assert posted == []


def test_parse_failure_uses_fallback_display(monkeypatch, config, lookup) -> None:
    """Parse failures should use fallback created display and age -1."""  # Parse failure branch.
    monkeypatch.setattr(
        watch_helper, "parse_zoho_time_assume_la",
        lambda _raw: (_ for _ in ()).throw(ValueError("bad")),
    )
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)

    card_kwargs = {}
    def fake_build(**kwargs):
        card_kwargs.update(kwargs)
        return {"card": "test"}

    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", fake_build)
    posted = []
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: posted.append(url))
    total, _ = _run(monkeypatch, [_make_ticket(created_time="BAD_TIME")], lookup)
    assert total == 1                                    # Age -1 does not block (unknown age passes).
    assert card_kwargs["created_display"] == "BAD_TIME"  # Fallback display.
    assert card_kwargs["age_minutes"]     == -1          # Unknown age marker.


# ---------------------------------------------------------------------------
# Cooldown persistence tests
# ---------------------------------------------------------------------------

def test_cooldown_file_saved_only_when_alerts_sent(monkeypatch, config, lookup, fixed_now) -> None:
    """Cooldown file should only be saved when at least one alert was sent."""  # Persistence contract.
    saved = []
    monkeypatch.setattr(watch_helper, "save_last_sent", lambda path, data: saved.append(path))
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: None)
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kw: {"card": "test"})

    # No tickets → no save.
    _run(monkeypatch, [], lookup, fixed_now=fixed_now)
    assert saved == []

    # One matching ticket → save.
    _run(monkeypatch, [_make_ticket()], lookup, fixed_now=fixed_now)
    assert len(saved) == 1
    assert config.last_sent_filename in saved[0]


def test_multiple_products_independent_cooldowns(monkeypatch, fixed_now) -> None:
    """Each product should have its own independent cooldown map."""  # Independence contract.
    config_a = watch_helper.ProductConfig(
        name="Super-Stat", target_product_names=["Super Stat"],
        active_statuses={"Assigned"}, teams_webhook_url="https://a.example",
        last_sent_filename="a.json", min_age_minutes=1,
    )
    config_b = watch_helper.ProductConfig(
        name="Amendments", target_product_names=["Amendments"],
        active_statuses={"Assigned"}, teams_webhook_url="https://b.example",
        last_sent_filename="b.json", min_age_minutes=1,
    )
    lookup = watch_helper.build_config_lookup([config_a, config_b])
    monkeypatch.setattr(watch_helper, "parse_zoho_time_assume_la", lambda _raw: fixed_now - timedelta(hours=1))
    monkeypatch.setattr(watch_helper, "now_la", lambda: fixed_now)
    monkeypatch.setattr(watch_helper, "post_to_teams", lambda url, payload: None)
    monkeypatch.setattr(watch_helper, "contains_magic_phrase", lambda *_texts: False)
    monkeypatch.setattr(watch_helper, "build_teams_adaptive_card", lambda **_kw: {"card": "test"})

    cooldown_state: dict = {}
    tickets = [
        _make_ticket(ticket_id="t1", product_name="Super Stat"),
        _make_ticket(ticket_id="t2", product_name="Amendments"),
    ]
    total = watch_helper.process_tickets(tickets=tickets, config_lookup=lookup, cooldown_state=cooldown_state)

    assert total == 2
    assert "t1" in cooldown_state["a.json"]  # Super-Stat's cooldown file.
    assert "t2" in cooldown_state["b.json"]  # Amendments' cooldown file.
    assert "t1" not in cooldown_state.get("b.json", {})  # No cross-contamination.
    assert "t2" not in cooldown_state.get("a.json", {})  # No cross-contamination.
