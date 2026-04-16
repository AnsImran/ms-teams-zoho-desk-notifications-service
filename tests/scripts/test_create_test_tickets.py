"""Tests for scripts/create_test_tickets.py — ticket creation via microservice."""  # Module purpose.

from __future__ import annotations

import json                              # Parse mock response bodies.
from unittest.mock import patch, MagicMock  # Mock HTTP calls and registry.

import pytest                            # Test runner and assertions.
import requests                          # For HTTPError exception class.

from scripts import create_test_tickets  # Module under test.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PRODUCT_CONFIGS = []  # Populated by helper below.


def _make_fake_configs(names: list[str]):
    """Build lightweight ProductConfig-like objects with target_product_names."""
    configs = []
    for name in names:
        cfg = MagicMock()
        cfg.target_product_names = [name]
        configs.append(cfg)
    return configs


# ---------------------------------------------------------------------------
# create_ticket_via_service tests
# ---------------------------------------------------------------------------

class TestCreateTicketViaService:
    """Tests for the create_ticket_via_service helper function."""

    @patch("scripts.create_test_tickets.requests.post")
    def test_posts_to_microservice_with_product_name(self, mock_post) -> None:
        """Should POST to /v1/tickets with productName, not productId."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "123", "ticketNumber": "100"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = create_test_tickets.create_ticket_via_service("Super Stat")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert payload["productName"] == "Super Stat"                            # Product name sent, not ID.
        assert payload["subject"] == create_test_tickets.SUBJECT                 # Magic test phrase.
        assert payload["description"] == create_test_tickets.DESCRIPTION         # Magic test phrase.
        assert "contact" in payload                                              # Contact is required.
        assert payload["contact"]["lastName"]                                    # lastName is mandatory.
        assert "productId" not in payload                                        # No productId — microservice resolves it.
        assert result == {"id": "123", "ticketNumber": "100"}

    @patch("scripts.create_test_tickets.requests.post")
    def test_uses_configured_service_url(self, mock_post) -> None:
        """Should build the URL from TICKET_SERVICE_URL."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1", "ticketNumber": "1"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        create_test_tickets.create_ticket_via_service("Test Product")

        call_args = mock_post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", call_args[0][0])
        assert url.endswith("/v1/tickets")                                       # Correct endpoint path.

    @patch("scripts.create_test_tickets.requests.post")
    def test_raises_on_http_error(self, mock_post) -> None:
        """Should propagate HTTPError when microservice returns an error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("422 Client Error")
        mock_post.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            create_test_tickets.create_ticket_via_service("Bogus Product")


# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------

class TestMain:
    """Tests for the main() orchestration function."""

    @patch("scripts.create_test_tickets.create_ticket_via_service")
    @patch("scripts.create_test_tickets.load_product_configs_from_env")
    def test_creates_one_ticket_per_unique_product(self, mock_load, mock_create) -> None:
        """Should call the microservice once per unique product name."""
        mock_load.return_value = _make_fake_configs(["Super Stat", "Amendments"])
        mock_create.return_value = {"id": "1", "ticketNumber": "100"}

        create_test_tickets.main()

        assert mock_create.call_count == 2
        product_names_called = [call.args[0] for call in mock_create.call_args_list]
        assert product_names_called == ["Super Stat", "Amendments"]

    @patch("scripts.create_test_tickets.create_ticket_via_service")
    @patch("scripts.create_test_tickets.load_product_configs_from_env")
    def test_deduplicates_product_names(self, mock_load, mock_create) -> None:
        """If two configs share the same product name, only one ticket is created."""
        configs = _make_fake_configs(["Super Stat", "Super Stat"])
        mock_load.return_value = configs
        mock_create.return_value = {"id": "1", "ticketNumber": "100"}

        create_test_tickets.main()

        assert mock_create.call_count == 1                                       # Deduplicated.

    @patch("scripts.create_test_tickets.create_ticket_via_service")
    @patch("scripts.create_test_tickets.load_product_configs_from_env")
    def test_continues_after_single_failure(self, mock_load, mock_create) -> None:
        """One failed product should not prevent the others from being created."""
        mock_load.return_value = _make_fake_configs(["Fail Product", "Good Product"])
        mock_create.side_effect = [
            requests.HTTPError(response=MagicMock(text="error")),                # First fails.
            {"id": "2", "ticketNumber": "200"},                                  # Second succeeds.
        ]

        with pytest.raises(SystemExit) as exc_info:                              # Exits with code 1 due to failure.
            create_test_tickets.main()

        assert exc_info.value.code == 1
        assert mock_create.call_count == 2                                       # Both attempted.

    @patch("scripts.create_test_tickets.create_ticket_via_service")
    @patch("scripts.create_test_tickets.load_product_configs_from_env")
    def test_exits_zero_when_all_succeed(self, mock_load, mock_create) -> None:
        """Should not call sys.exit when all tickets are created successfully."""
        mock_load.return_value = _make_fake_configs(["Product A"])
        mock_create.return_value = {"id": "1", "ticketNumber": "100"}

        create_test_tickets.main()                                               # Should not raise SystemExit.
