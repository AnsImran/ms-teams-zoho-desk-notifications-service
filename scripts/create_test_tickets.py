"""Create one test ticket per configured product for end-to-end testing.

Each ticket has:
  subject:     "test ticket by magic ai"
  description: "test ticket by magic ai"
  product:     one of the configured products from the registry + env vars

Usage (from repo root):
  uv run python scripts/create_test_tickets.py

The script uses the centralized token service for authentication.
The token must have Desk.tickets.CREATE (or Desk.tickets.ALL) scope.
"""  # Module-level docstring explaining purpose and usage.

import sys                      # Exit with non-zero code on failure.
import requests                 # Talk to Zoho Desk over HTTPS.
from dotenv import load_dotenv  # Pull settings from a .env file automatically.

load_dotenv()  # Makes later env lookups succeed without manual loading.

from src.core.watch_helper import (  # Import shared helpers we need here.
    ZOHO_DESK_BASE,                  # Base URL for Zoho Desk API calls.
    desk_headers,                    # Build authorization headers for Zoho.
    get_token_from_service,          # Fetch Zoho token from centralized token service.
)                                    # End of helper imports list.
from src.scripts.product_registry import load_product_configs_from_env  # Declarative env-driven product configs.


SUBJECT     = "test ticket by magic ai"  # Ticket subject line (matches magic test phrase).
DESCRIPTION = "test ticket by magic ai"  # Ticket description body (matches magic test phrase).


def discover_product_id(token: str, product_name: str) -> str | None:                                    # Find a Zoho product ID by searching for one existing ticket.
    """Find a product's Zoho ID by searching for one existing ticket with that productName."""            # Docstring in plain words.
    url      = f"{ZOHO_DESK_BASE}/api/v1/tickets/search"                                                 # Build search URL.
    response = requests.get(url, headers=desk_headers(token), params={"productName": product_name, "limit": 1}, timeout=30)  # Search for one ticket with this product.
    if response.status_code == 200:                                                                       # If search returned results...
        tickets = response.json().get("data", [])                                                         # Pull the ticket list from the response.
        if tickets:                                                                                       # If at least one ticket found...
            return tickets[0].get("productId")                                                            # Return its product ID.
    return None                                                                                           # No ticket found for this product name.


DEPARTMENT_ID = "1166045000000006907"                                                                    # Webzter Support department (required by Zoho create API).
CONTACT_ID    = "1166045000005076012"                                                                    # Shared test contact (required by Zoho create API).


def create_ticket(token: str, product_id: str) -> dict:                                                  # Create one test ticket with a specific product.
    """Create one test ticket with the given product ID; returns the API response dict."""                # Docstring in plain words.
    url     = f"{ZOHO_DESK_BASE}/api/v1/tickets"                                                         # Build ticket creation URL.
    headers = desk_headers(token)                                                                        # Start with standard Zoho headers.
    headers["Content-Type"] = "application/json"                                                         # Tell Zoho we are sending JSON.
    payload = {                                                                                          # Build the ticket payload.
        "subject":      SUBJECT,                                                                         # Ticket subject line.
        "description":  DESCRIPTION,                                                                     # Ticket description body.
        "productId":    product_id,                                                                      # Link ticket to the correct product.
        "departmentId": DEPARTMENT_ID,                                                                   # Required department field.
        "contactId":    CONTACT_ID,                                                                      # Required contact field.
    }                                                                                                    # End of payload.
    response = requests.post(url, headers=headers, json=payload, timeout=30)                             # POST to create the ticket.
    response.raise_for_status()                                                                          # Fail loudly on HTTP error.
    return response.json()                                                                               # Return the created ticket data.


def main():                                                                                              # Script entry point.
    """Discover product IDs and create one test ticket for each configured product."""                   # Docstring in plain words.
    token   = get_token_from_service()                                                                   # Fetch Zoho token from centralized service.
    configs = load_product_configs_from_env()                                                             # Build all product configs from registry and env vars.

    seen: set[str]           = set()                                                                     # Track product names we have already collected.
    product_names: list[str] = []                                                                        # Ordered list of unique product names to create tickets for.
    for cfg in configs:                                                                                  # Walk every product config.
        for name in cfg.target_product_names:                                                            # Walk every target product name.
            if name not in seen:                                                                         # If we have not seen this name yet...
                seen.add(name)                                                                           # Mark as seen.
                product_names.append(name)                                                               # Add to the ordered list.

    print(f"Found {len(product_names)} unique product name(s) across {len(configs)} config(s).")         # Log discovery count.
    print()                                                                                              # Blank line for readability.

    product_map: dict[str, str] = {}                                                                     # Map product name to Zoho product ID.
    for name in product_names:                                                                           # Walk every unique product name.
        pid = discover_product_id(token, name)                                                           # Search Zoho for the product ID.
        if pid:                                                                                          # If we found an ID...
            product_map[name] = pid                                                                      # Save the mapping.
            print(f"  {name:40s} -> {pid}")                                                              # Log the discovered ID.
        else:                                                                                            # If no ticket exists for this product...
            print(f"  {name:40s} -> NOT FOUND (no existing tickets; skipping)")                          # Log that we will skip it.
    print()                                                                                              # Blank line for readability.

    created = 0                                                                                          # Count of successfully created tickets.
    failed  = 0                                                                                          # Count of failed ticket creations.
    for name, pid in product_map.items():                                                                # Walk every discovered product.
        try:                                                                                             # Wrap in try so one failure does not stop the rest.
            result        = create_ticket(token, pid)                                                    # Create the test ticket.
            ticket_number = result.get("ticketNumber", "?")                                              # Pull the ticket number from the response.
            ticket_id     = result.get("id", "?")                                                        # Pull the ticket ID from the response.
            print(f"  CREATED #{ticket_number} (id={ticket_id}) for product '{name}'")                   # Log success.
            created += 1                                                                                 # Increment success count.
        except requests.HTTPError as error:                                                              # Catch HTTP errors from Zoho.
            print(f"  FAILED for product '{name}': {error}")                                             # Log the failure.
            if hasattr(error, "response") and error.response is not None:                                # If there is a response body...
                print(f"    Response: {error.response.text[:300]}")                                       # Log the first 300 chars of the error body.
            failed += 1                                                                                  # Increment failure count.

    print()                                                                                              # Blank line for readability.
    print(f"Done. Created: {created}, Failed: {failed}, Skipped: {len(product_names) - len(product_map)}")  # Final summary.

    if failed > 0:                                                                                       # If any tickets failed to create...
        print()                                                                                          # Blank line before help text.
        print("If you see 401 errors, the token likely lacks write scope.")                              # Hint about scope issues.
        print("Ensure the Zoho OAuth app has Desk.tickets.CREATE or Desk.tickets.ALL scope.")            # Tell the user what to fix.
        sys.exit(1)                                                                                      # Exit with error code.


if __name__ == "__main__":  # Allow running via `python scripts/create_test_tickets.py`.
    main()                  # Run the test ticket creation flow.
