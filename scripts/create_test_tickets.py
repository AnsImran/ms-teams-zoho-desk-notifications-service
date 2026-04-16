"""Create one test ticket per configured product via the ticket microservice.

Each ticket has:
  subject:     "test ticket by magic ai"
  description: "test ticket by magic ai"
  product:     one of the configured products from products.json

Usage (from repo root):
  uv run python scripts/create_test_tickets.py
  uv run python -m scripts.create_test_tickets

The script calls the ticket-creation microservice which handles
Zoho authentication, product ID resolution, and ticket creation.
"""  # Module-level docstring explaining purpose and usage.

import os                       # Read environment variables.
import sys                      # Exit with non-zero code on failure.
from pathlib import Path        # Resolve repository root from this file path.

# Ensure repo root is on sys.path so `from src.*` imports work when
# the script is invoked directly (e.g. `python scripts/create_test_tickets.py`).
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import requests                 # Talk to the ticket microservice over HTTP.
from dotenv import load_dotenv  # Pull settings from a .env file automatically.

load_dotenv()  # Makes later env lookups succeed without manual loading.

from src.scripts.product_registry import load_product_configs_from_env  # Declarative env-driven product configs.


SUBJECT     = "test ticket by magic ai"  # Ticket subject line (matches magic test phrase).
DESCRIPTION = "test ticket by magic ai"  # Ticket description body (matches magic test phrase).

# Microservice base URL — on the host machine use localhost:8200,
# inside Docker use the service name or host.docker.internal.
TICKET_SERVICE_URL = os.getenv(
    "TICKET_SERVICE_URL", "http://localhost:8200"
).strip().rstrip("/")

# Contact info for test tickets (required by the microservice schema).
TEST_CONTACT = {"lastName": "Test", "firstName": "Magic AI"}


def create_ticket_via_service(product_name: str) -> dict:                       # Create one test ticket by POSTing to the microservice.
    """Create one test ticket by POSTing to the ticket microservice."""          # Docstring in plain words.
    url     = f"{TICKET_SERVICE_URL}/v1/tickets"                                # Build the ticket creation URL.
    payload = {                                                                 # Build the ticket payload.
        "subject":     SUBJECT,                                                 # Ticket subject line.
        "description": DESCRIPTION,                                             # Ticket description body.
        "productName": product_name,                                            # Product name — microservice resolves to ID.
        "contact":     TEST_CONTACT,                                            # Required contact info.
    }                                                                           # End of payload.
    response = requests.post(url, json=payload, timeout=30)                     # POST to the microservice.
    response.raise_for_status()                                                 # Fail loudly on HTTP error.
    return response.json()                                                      # Return the created ticket data.


def main():                                                                                              # Script entry point.
    """Create one test ticket for each unique product name across all configs."""                        # Docstring in plain words.
    configs = load_product_configs_from_env()                                                             # Build all product configs from registry and env vars.

    seen: set[str]           = set()                                                                     # Track product names we have already collected.
    product_names: list[str] = []                                                                        # Ordered list of unique product names to create tickets for.
    for cfg in configs:                                                                                  # Walk every product config.
        for name in cfg.target_product_names:                                                            # Walk every target product name.
            if name not in seen:                                                                         # If we have not seen this name yet...
                seen.add(name)                                                                           # Mark as seen.
                product_names.append(name)                                                               # Add to the ordered list.

    print(f"Found {len(product_names)} unique product name(s) across {len(configs)} config(s).")         # Log discovery count.
    print(f"Using ticket service at: {TICKET_SERVICE_URL}")                                              # Log microservice URL.
    print()                                                                                              # Blank line for readability.

    created = 0                                                                                          # Count of successfully created tickets.
    failed  = 0                                                                                          # Count of failed ticket creations.
    for name in product_names:                                                                           # Walk every unique product name.
        try:                                                                                             # Wrap in try so one failure does not stop the rest.
            result        = create_ticket_via_service(name)                                              # Create the test ticket via microservice.
            ticket_number = result.get("ticketNumber", "?")                                              # Pull the ticket number from the response.
            ticket_id     = result.get("id", "?")                                                        # Pull the ticket ID from the response.
            print(f"  CREATED #{ticket_number} (id={ticket_id}) for product '{name}'")                   # Log success.
            created += 1                                                                                 # Increment success count.
        except requests.HTTPError as error:                                                              # Catch HTTP errors from the microservice.
            print(f"  FAILED for product '{name}': {error}")                                             # Log the failure.
            if hasattr(error, "response") and error.response is not None:                                # If there is a response body...
                print(f"    Response: {error.response.text[:300]}")                                       # Log the first 300 chars of the error body.
            failed += 1                                                                                  # Increment failure count.

    print()                                                                                              # Blank line for readability.
    print(f"Done. Created: {created}, Failed: {failed}")                                                 # Final summary.

    if failed > 0:                                                                                       # If any tickets failed to create...
        sys.exit(1)                                                                                      # Exit with error code.


if __name__ == "__main__":  # Allow running via `python scripts/create_test_tickets.py`.
    main()                  # Run the test ticket creation flow.
