"""Unit tests for watch_helper.search_tickets using mocked Zoho API responses."""  # Brief module purpose.

from __future__ import annotations

import json                         # Parse JSON text extracted from the raw fixture file.
from pathlib import Path            # Build stable file-system paths for fixtures.
from typing import Any, Dict        # Keep test-helper typing explicit and readable.

import requests                     # Reuse requests.HTTPError in the response stub.

from src.core import watch_helper   # Function under test lives in this module.


REPO_ROOT            = Path(__file__).resolve().parents[2]                               # Repository root from this test module location.
PAYLOAD_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "zoho_tickets_search_raw_payload.txt"
                                                                                         # Fixture holding the captured Zoho "RAW RESPONSE TEXT" payload.

class StubResponse:
    """Tiny requests-like response stub used by monkeypatched requests.get."""  # Keep monkeypatch setup simple.

    def __init__(
        self,
        *,
        status_code: int,
        payload: Dict[str, Any],
        url:     str = "https://desk.zoho.com/api/v1/tickets/search",
        text:    str = "",
    ) -> None:
        self.status_code = status_code  # Expose HTTP status for test control flow.
        self._payload    = payload      # JSON body returned by .json().
        self.url         = url          # Request URL for debug/error messages.
        self.text        = text         # Raw response text for HTTP error logging paths.

    def json(self) -> Dict[str, Any]:
        return self._payload            # Mimic requests.Response.json().

    def raise_for_status(self) -> None:
        if self.status_code >= 400:                                              # Match requests behavior for error statuses.
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)  # Include self as response object.



def _load_zoho_search_payload_from_fixture() -> Dict[str, Any]:
    """Load raw Zoho search payload from fixture text file."""  # Extract JSON from a captured raw-output artifact.

    fixture_text = PAYLOAD_FIXTURE_PATH.read_text(encoding="utf-8")  # Read complete raw fixture text.
    marker       = "RAW RESPONSE TEXT:"                              # JSON begins after this literal marker.
    marker_index = fixture_text.find(marker)                         # Locate marker offset.
    if marker_index == -1:                                           # Guard against malformed fixture content.
        raise AssertionError(f"Could not find '{marker}' marker in {PAYLOAD_FIXTURE_PATH}.")
    raw_json_text = fixture_text[marker_index + len(marker) :].strip()   # Slice JSON payload portion.
    return json.loads(raw_json_text)                                     # Parse JSON into dict for the stub.


def test_search_tickets_uses_fixture_payload_and_returns_validated_rows(monkeypatch) -> None:
    """search_tickets should parse fixture payload and pass expected request params."""  # Happy-path contract.

    payload = _load_zoho_search_payload_from_fixture()     # Realistic mocked API body.
    monkeypatch.setenv("ZOHO_DESK_ORG_ID", "test-org-id")  # Required by desk_headers().

    captured_call: Dict[str, Any] = {}  # Capture outbound request details for assertions.

    def fake_get(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int) -> StubResponse:
        captured_call["url"]     = url      # Called endpoint.
        captured_call["headers"] = headers  # Authorization/org headers.
        captured_call["params"]  = params   # Query parameters built by search_tickets().
        captured_call["timeout"] = timeout  # Timeout configured by function.
        return StubResponse(status_code=200, payload=payload, url=f"{url}?mock=true", text=json.dumps(payload))  # One successful page.

    monkeypatch.setattr(watch_helper.requests, "get", fake_get)  # Replace network call with local stub.

    result = watch_helper.search_tickets(                   # Execute function under test.
        token      = "token-123",                           # Synthetic token.
        statuses   = ["Assigned", "Pending"],               # Two statuses -> comma-joined query param.
        hours      = 24,                                    # Ensures createdTimeRange is included.
        page_limit = 3,                                     # Any positive cap works for this single-page fixture.
    )                                                       # End test call.

    assert len(result) == len(payload["data"])  # Same number of tickets as fixture.
    assert {row["id"] for row in result} == {row["id"] for row in payload["data"]}   # IDs preserved through validation+dump.
    assert captured_call["url"] == "https://desk.zoho.com/api/v1/tickets/search"     # Correct endpoint.
    assert captured_call["headers"]["Authorization"] == "Zoho-oauthtoken token-123"  # Auth header format.
    assert captured_call["headers"]["orgId"]         == "test-org-id"                # Org header wiring.
    assert captured_call["params"]["status"]         == "Assigned,Pending"           # Status join behavior.
    assert "createdTimeRange" in captured_call["params"]                             # Time window added when hours is provided.
    assert captured_call["params"]["sortBy"]         == "-createdTime"               # Sort requested initially.
    assert captured_call["timeout"]                  == 30                           # Function timeout contract.


def test_search_tickets_paginates_across_multiple_pages(monkeypatch) -> None:
    """search_tickets should fetch all pages and combine them into one list."""  # Pagination contract.

    monkeypatch.setenv("ZOHO_DESK_ORG_ID", "test-org-id")                      # Required by header builder.
    monkeypatch.setattr(watch_helper, "PAGE_SIZE", 2)                          # Shrink page size so we can test with few tickets.

    page_1_tickets = [                                                         # First page: full (2 tickets = PAGE_SIZE).
        {"id": "t1", "ticketNumber": "001", "status": "Assigned", "statusType": "Open", "subject": "First",  "createdTime": "2026-01-01T10:00:00.000Z", "webUrl": "https://desk.zoho.com/1"},
        {"id": "t2", "ticketNumber": "002", "status": "Assigned", "statusType": "Open", "subject": "Second", "createdTime": "2026-01-01T09:00:00.000Z", "webUrl": "https://desk.zoho.com/2"},
    ]
    page_2_tickets = [                                                         # Second page: partial (1 ticket < PAGE_SIZE = last page).
        {"id": "t3", "ticketNumber": "003", "status": "Pending",  "statusType": "Open", "subject": "Third",  "createdTime": "2026-01-01T08:00:00.000Z", "webUrl": "https://desk.zoho.com/3"},
    ]

    calls = []                                                                 # Track requests to verify pagination offsets.

    def fake_get(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int) -> StubResponse:
        calls.append(dict(params))                                             # Snapshot params for each call.
        page_idx = params["from"] // 2                                         # Derive which page was requested.
        if page_idx == 0:                                                      # First page.
            return StubResponse(status_code=200, payload={"data": page_1_tickets, "count": 3}, text="ok")
        else:                                                                  # Second page.
            return StubResponse(status_code=200, payload={"data": page_2_tickets, "count": 3}, text="ok")

    monkeypatch.setattr(watch_helper.requests, "get", fake_get)                # Patch network I/O.

    result = watch_helper.search_tickets(                                      # Exercise pagination.
        token    = "token-123",                                                # Synthetic token.
        statuses = ["Assigned", "Pending"],                                    # Two statuses.
    )                                                                          # End call.

    assert len(result)          == 3                                           # All three tickets from both pages.
    result_ids                  = [r["id"] for r in result]                    # Collect IDs in returned order.
    assert "t1" in result_ids                                                  # Page 1 ticket present.
    assert "t2" in result_ids                                                  # Page 1 ticket present.
    assert "t3" in result_ids                                                  # Page 2 ticket present.
    assert len(calls)           == 2                                           # Exactly two requests made.
    assert calls[0]["from"]     == 0                                           # First request starts at offset 0.
    assert calls[1]["from"]     == 2                                           # Second request starts at offset 2 (PAGE_SIZE).


def test_search_tickets_stops_at_page_limit(monkeypatch) -> None:
    """search_tickets should stop fetching when page_limit is reached."""       # Page cap contract.

    monkeypatch.setenv("ZOHO_DESK_ORG_ID", "test-org-id")                      # Required by header builder.
    monkeypatch.setattr(watch_helper, "PAGE_SIZE", 2)                          # Small page size.

    full_page = [                                                              # Always return a full page (so pagination would continue without cap).
        {"id": "t1", "ticketNumber": "001", "status": "Assigned", "statusType": "Open", "subject": "First",  "createdTime": "2026-01-01T10:00:00.000Z", "webUrl": "https://desk.zoho.com/1"},
        {"id": "t2", "ticketNumber": "002", "status": "Assigned", "statusType": "Open", "subject": "Second", "createdTime": "2026-01-01T09:00:00.000Z", "webUrl": "https://desk.zoho.com/2"},
    ]

    calls = []                                                                 # Track request count.

    def fake_get(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int) -> StubResponse:
        calls.append(dict(params))                                             # Record each call.
        return StubResponse(status_code=200, payload={"data": full_page, "count": 100}, text="ok")

    monkeypatch.setattr(watch_helper.requests, "get", fake_get)                # Patch network I/O.

    result = watch_helper.search_tickets(                                      # Exercise page limit.
        token      = "token-123",                                              # Synthetic token.
        statuses   = ["Assigned"],                                             # Single status.
        page_limit = 3,                                                        # Stop after 3 pages.
    )                                                                          # End call.

    assert len(calls)  == 3                                                    # Exactly 3 requests (page_limit).
    assert len(result) == 6                                                    # 3 pages x 2 tickets = 6 total.
    assert calls[0]["from"] == 0                                               # First page offset.
    assert calls[1]["from"] == 2                                               # Second page offset.
    assert calls[2]["from"] == 4                                               # Third page offset.


def test_search_tickets_retries_without_sort_when_zoho_returns_422(monkeypatch) -> None:
    """search_tickets should retry once without sortBy when Zoho returns HTTP 422."""  # Zoho compatibility branch.

    monkeypatch.setenv("ZOHO_DESK_ORG_ID", "test-org-id")  # Required by header builder.

    calls     = []  # Capture sequence of request params across retries.
    responses = [   # First call fails with 422, second succeeds.
        StubResponse(
            status_code = 422,
            payload     = {"data": []},
            url         = "https://desk.zoho.com/api/v1/tickets/search?sortBy=-createdTime",
            text        = '{"code":"INVALID_DATA"}',
        ),
        StubResponse(status_code=200, payload={"data": [], "count": 0}),
    ]

    def fake_get(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int) -> StubResponse:
        calls.append({"url": url, "headers": headers, "params": dict(params), "timeout": timeout})     # Snapshot params per call.
        return responses.pop(0)                                                                        # Return next staged response.

    monkeypatch.setattr(watch_helper.requests, "get", fake_get)  # Patch network I/O.

    result = watch_helper.search_tickets(  # Exercise retry branch.
        token      = "token-123",                # Synthetic token.
        statuses   = ["Assigned"],               # Single status.
        hours      = None,                       # No createdTimeRange param expected.
        page_limit = 1,                          # Keep loop bounded for test determinism.
    )                                            # End call.

    assert result                             == []              # Empty response stays empty.
    assert len(calls)                         == 2               # Exactly one retry expected.
    assert calls[0]["params"]["sortBy"]       == "-createdTime"  # First call includes sortBy.
    assert "sortBy" not in calls[1]["params"]                    # Retry removes sortBy after 422.
    assert calls[1]["params"]["from"]         == 0               # Retry repeats same page offset.
