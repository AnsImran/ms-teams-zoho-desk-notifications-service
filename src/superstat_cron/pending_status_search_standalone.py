"""Standalone probe for Zoho Desk: search tickets with status=PENDING only.

This script has no project-module imports and no third-party dependencies.
It uses a refresh token to get an access token, then calls:
    GET /api/v1/tickets/search?status=PENDING
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


def load_dotenv_simple() -> None:
    """Load KEY=VALUE pairs from env files into os.environ if missing."""
    here = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / "current.env",
        Path.cwd() / ".env",
        here / "current.env",
        here / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception as error:
            print(f"WARNING: Could not read env file {path}: {error}", file=sys.stderr)


def env_required(name: str) -> str:
    """Return required env var value or raise."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def http_post_form(url: str, form_data: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    """POST form data and return parsed JSON."""
    payload = urllib.parse.urlencode(form_data).encode("utf-8")
    request = urllib.request.Request(url=url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_json(url: str, headers: Dict[str, str], params: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    """GET JSON response for URL + query params."""
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    request = urllib.request.Request(url=full_url, method="GET")
    for key, value in headers.items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def token_url_from_env() -> str:
    """Resolve Zoho accounts token URL from existing env naming."""
    explicit = os.getenv("ZOHO_ACCOUNTS_TOKEN_URL", "").strip()
    if explicit:
        return explicit
    accounts_base = os.getenv("ZOHO_ACCOUNTS_BASE", "").strip().rstrip("/")
    if accounts_base:
        return f"{accounts_base}/oauth/v2/token"
    return "https://accounts.zoho.com/oauth/v2/token"


def get_access_token() -> str:
    """Exchange refresh token for a fresh access token."""
    token_json = http_post_form(
        token_url_from_env(),
        form_data={
            "refresh_token": env_required("ZOHO_REFRESH_TOKEN"),
            "client_id": env_required("ZOHO_CLIENT_ID"),
            "client_secret": env_required("ZOHO_CLIENT_SECRET"),
            "grant_type": "refresh_token",
        },
    )
    token = (token_json.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Token response did not include access_token: {token_json}")
    return token


def search_pending_tickets(token: str, status: str, page_size: int, max_pages: int) -> List[Dict[str, Any]]:
    """Search ticket pages filtered only by status."""
    base = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").strip().rstrip("/")
    search_url = f"{base}/api/v1/tickets/search"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "orgId": env_required("ZOHO_DESK_ORG_ID"),
        "Accept": "application/json",
    }

    results: List[Dict[str, Any]] = []
    use_sort = True
    page_idx = 0

    while max_pages == 0 or page_idx < max_pages:
        params = {
            "status": status,
            "from": str(page_idx * page_size),
            "limit": str(page_size),
        }
        if use_sort:
            params["sortBy"] = "-createdTime"

        try:
            body = http_get_json(search_url, headers=headers, params=params)
        except urllib.error.HTTPError as error:
            error_text = error.read().decode("utf-8", errors="replace")
            if error.code == 422 and use_sort:
                use_sort = False
                continue
            raise RuntimeError(f"HTTP {error.code} for {search_url}?{urllib.parse.urlencode(params)}\n{error_text}") from error

        data = body.get("data", []) or []
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        page_idx += 1

    return results


def assignee_name(ticket: Dict[str, Any]) -> str:
    """Return assignee full name from ticket payload."""
    assignee = ticket.get("assignee")
    if isinstance(assignee, dict):
        first = str(assignee.get("firstName") or "").strip()
        last = str(assignee.get("lastName") or "").strip()
        full = " ".join(part for part in (first, last) if part)
        if full:
            return full
        fallback_name = str(assignee.get("name") or "").strip()
        if fallback_name:
            return fallback_name
    return "(unassigned)"


def main() -> int:
    load_dotenv_simple()

    parser = argparse.ArgumentParser(description="Probe Zoho Desk tickets/search with status=PENDING only.")
    parser.add_argument("--status", default="PENDING", help="Status filter value to send, default: PENDING")
    parser.add_argument("--page-size", type=int, default=100, help="Page size for search calls (1-100).")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum pages to fetch. Use 0 for no cap (default).")
    parser.add_argument("--show", type=int, default=20, help="How many ticket rows to print.")
    args = parser.parse_args()

    if args.page_size < 1 or args.page_size > 100:
        raise RuntimeError("--page-size must be between 1 and 100.")
    if args.max_pages < 0:
        raise RuntimeError("--max-pages must be >= 0.")

    token = get_access_token()
    tickets = search_pending_tickets(
        token=token,
        status=args.status,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )

    print("")
    print("Query used:")
    print(f"  /api/v1/tickets/search?status={args.status}&limit={args.page_size}&from=...")
    print(f"Fetched {len(tickets)} ticket(s) with status filter '{args.status}'.")
    print("")

    shown = 0
    for ticket in tickets:
        if shown >= args.show:
            break
        ticket_id = str(ticket.get("id") or "")
        ticket_number = str(ticket.get("ticketNumber") or "")
        status = str(ticket.get("status") or "")
        subject = str(ticket.get("subject") or "").replace("\n", " ").strip()
        ticket_url = str(ticket.get("webUrl") or "").strip() or "(no webUrl)"
        assignee = assignee_name(ticket)
        print(
            f"- id={ticket_id} ticketNumber={ticket_number} status={status} assignee={assignee} "
            f"subject={subject} url={ticket_url}"
        )
        shown += 1

    if not tickets:
        print("No tickets returned. If your portal status label is title-case, retry with --status Pending.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
