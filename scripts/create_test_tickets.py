"""Create one test ticket per configured product for end-to-end testing.

Each ticket has:
  subject:     "test ticket by magic ai"
  description: "test ticket by magic ai"
  product:     one of the configured products from the registry + env vars

Usage (from repo root):
  uv run python scripts/create_test_tickets.py

The script uses the centralized token service for authentication.
The token must have Desk.tickets.CREATE (or Desk.tickets.ALL) scope.
"""

import sys
import requests
from dotenv import load_dotenv

load_dotenv()

from src.core.watch_helper import (
    ZOHO_DESK_BASE,
    TOKEN_SERVICE_URL,
    desk_headers,
    get_token_from_service,
)
from src.scripts.product_registry import load_product_configs_from_env


SUBJECT     = "test ticket by magic ai"
DESCRIPTION = "test ticket by magic ai"


def discover_product_id(token: str, product_name: str) -> str | None:
    """Find a product's Zoho ID by searching for one existing ticket with that productName."""
    url = f"{ZOHO_DESK_BASE}/api/v1/tickets/search"
    r = requests.get(
        url,
        headers=desk_headers(token),
        params={"productName": product_name, "limit": 1},
        timeout=30,
    )
    if r.status_code == 200:
        tickets = r.json().get("data", [])
        if tickets:
            return tickets[0].get("productId")
    return None


def create_ticket(token: str, product_id: str) -> dict:
    """Create one test ticket with the given product ID. Returns the API response dict."""
    url = f"{ZOHO_DESK_BASE}/api/v1/tickets"
    headers = desk_headers(token)
    headers["Content-Type"] = "application/json"
    payload = {
        "subject":     SUBJECT,
        "description": DESCRIPTION,
        "productId":   product_id,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    token   = get_token_from_service()
    configs = load_product_configs_from_env()

    # Collect unique product names across all configs (preserving the original casing from env).
    seen = set()
    product_names: list[str] = []
    for cfg in configs:
        for name in cfg.target_product_names:
            if name not in seen:
                seen.add(name)
                product_names.append(name)

    print(f"Found {len(product_names)} unique product name(s) across {len(configs)} config(s).")
    print()

    # Discover product IDs by searching for existing tickets.
    product_map: dict[str, str] = {}
    for name in product_names:
        pid = discover_product_id(token, name)
        if pid:
            product_map[name] = pid
            print(f"  {name:40s} -> {pid}")
        else:
            print(f"  {name:40s} -> NOT FOUND (no existing tickets; skipping)")
    print()

    # Create one ticket per product.
    created = 0
    failed  = 0
    for name, pid in product_map.items():
        try:
            result = create_ticket(token, pid)
            ticket_number = result.get("ticketNumber", "?")
            ticket_id     = result.get("id", "?")
            print(f"  CREATED #{ticket_number} (id={ticket_id}) for product '{name}'")
            created += 1
        except requests.HTTPError as e:
            print(f"  FAILED for product '{name}': {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"    Response: {e.response.text[:300]}")
            failed += 1

    print()
    print(f"Done. Created: {created}, Failed: {failed}, Skipped: {len(product_names) - len(product_map)}")

    if failed > 0:
        print("\nIf you see 401 errors, the token likely lacks write scope.")
        print("Ensure the Zoho OAuth app has Desk.tickets.CREATE or Desk.tickets.ALL scope.")
        sys.exit(1)


if __name__ == "__main__":
    main()
