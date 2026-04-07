"""Unit tests for get_token_from_service (the notification-side token client)."""

from __future__ import annotations

import requests

from src.core import watch_helper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_token_from_service_happy_path(monkeypatch):
    """Should return the access_token string from a mocked 200 response."""
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **kw: _FakeResponse({"access_token": "tok-from-service"}),
    )
    assert watch_helper.get_token_from_service() == "tok-from-service"


def test_correct_url_called(monkeypatch):
    """The URL passed to requests.get should be {TOKEN_SERVICE_URL}/token."""
    captured_url = None

    def _capture(url, **kw):
        nonlocal captured_url
        captured_url = url
        return _FakeResponse({"access_token": "x"})

    monkeypatch.setattr(requests, "get", _capture)
    monkeypatch.setattr(watch_helper, "TOKEN_SERVICE_URL", "http://test-host:9000")
    watch_helper.get_token_from_service()
    assert captured_url == "http://test-host:9000/token"


def test_raises_on_connection_error(monkeypatch):
    """A network failure should raise RuntimeError mentioning 'unreachable'."""
    def _boom(*a, **kw):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", _boom)
    try:
        watch_helper.get_token_from_service()
        raise AssertionError("Expected RuntimeError.")
    except RuntimeError as error:
        assert "unreachable" in str(error).lower()


def test_raises_on_empty_token(monkeypatch):
    """An empty access_token in the response should raise RuntimeError."""
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **kw: _FakeResponse({"access_token": ""}),
    )
    try:
        watch_helper.get_token_from_service()
        raise AssertionError("Expected RuntimeError.")
    except RuntimeError as error:
        assert "empty" in str(error).lower()


def test_env_url_override(monkeypatch):
    """TOKEN_SERVICE_URL env var should override the default URL."""
    captured_url = None

    def _capture(url, **kw):
        nonlocal captured_url
        captured_url = url
        return _FakeResponse({"access_token": "x"})

    monkeypatch.setattr(requests, "get", _capture)
    monkeypatch.setattr(watch_helper, "TOKEN_SERVICE_URL", "http://custom:7777")
    watch_helper.get_token_from_service()
    assert captured_url == "http://custom:7777/token"
