"""Zoho Desk API client for the dashboard — fetch active tickets."""  # Module purpose.

import os                                                             # Read environment variables.
import sys                                                            # Path setup for project-root imports.
import requests                                                       # HTTP calls to Zoho and token service.
from typing import Any, Dict, List                                    # Type hints.

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # Ensure project root is on path.
from src.core.logger import get_logger                                   # Centralized structured logging.

logger = get_logger(__name__)                                            # Named logger for this module.


TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://token-service:8000").rstrip("/")  # Centralized token service URL.
ZOHO_DESK_BASE    = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")        # Zoho Desk API base URL.


def get_token() -> str:                                                                      # Fetch Zoho token from centralized service.
    """Fetch the current Zoho access token from the token service."""                        # Docstring in plain words.
    url      = f"{TOKEN_SERVICE_URL}/v1/token"                                               # Versioned token endpoint URL.
    response = requests.get(url, timeout=10)                                                 # GET the cached token.
    response.raise_for_status()                                                              # Fail loudly on HTTP error.
    token = (response.json().get("access_token") or "").strip()                              # Extract token text.
    if token:
        logger.debug("Token fetched from token service")
    else:
        logger.warning("Token service returned empty token")
    return token                                                                             # Return the token text.


def desk_headers(token: str) -> Dict[str, str]:                                              # Build Zoho Desk API headers.
    """Return headers needed for Zoho Desk API calls."""                                     # Docstring in plain words.
    return {                                                                                 # Header dict.
        "Authorization": f"Zoho-oauthtoken {token}",                                        # OAuth token header.
        "orgId":         os.getenv("ZOHO_DESK_ORG_ID", ""),                                  # Organization ID header.
        "Accept":        "application/json",                                                 # JSON response.
    }                                                                                        # End headers.


def fetch_active_tickets(product_names: List[str], statuses: List[str]) -> List[Dict[str, Any]]:  # Fetch tickets from Zoho.
    """Fetch active tickets for the given products and statuses."""                               # Docstring in plain words.
    try:                                                                                          # Wrap in try so dashboard shows error, not crash.
        token = get_token()                                                                       # Get Zoho access token.
        if not token:                                                                             # If token is empty...
            logger.warning("Cannot fetch tickets — empty token")
            return []                                                                             # Return empty — can't query without token.
        url    = f"{ZOHO_DESK_BASE}/api/v1/tickets/search"                                        # Search endpoint.
        params = {                                                                                # Query parameters.
            "status":      ",".join(statuses),                                                    # Comma-separated statuses.
            "productName": ",".join(product_names),                                               # Comma-separated product names.
            "limit":       100,                                                                   # Page size.
            "sortBy":      "-createdTime",                                                        # Newest first.
        }                                                                                         # End params.
        logger.debug("Fetching active tickets — products=%d, statuses=%d", len(product_names), len(statuses))
        response = requests.get(url, headers=desk_headers(token), params=params, timeout=30)      # Fire request.
        if response.status_code == 204 or not response.text.strip():                              # No results.
            return []                                                                             # Return empty list.
        response.raise_for_status()                                                               # Fail on HTTP error.
        return response.json().get("data", [])                                                    # Return ticket list.
    except Exception as error:                                                                    # Any error.
        logger.error("Failed to fetch tickets from Zoho", exc_info=error)
        print(f"[dashboard] Error fetching tickets: {error}")                                     # Log to console.
        return []                                                                                 # Return empty — dashboard stays up.
