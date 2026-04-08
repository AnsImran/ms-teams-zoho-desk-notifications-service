"""Zoho Desk API client for the dashboard — fetch active tickets."""  # Module purpose.

import os                                                             # Read environment variables.
import requests                                                       # HTTP calls to Zoho and token service.
from typing import Any, Dict, List                                    # Type hints.


TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://token-service:8000").rstrip("/")  # Centralized token service URL.
ZOHO_DESK_BASE    = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")        # Zoho Desk API base URL.


def get_token() -> str:                                                                      # Fetch Zoho token from centralized service.
    """Fetch the current Zoho access token from the token service."""                        # Docstring in plain words.
    url      = f"{TOKEN_SERVICE_URL}/token"                                                  # Token endpoint URL.
    response = requests.get(url, timeout=10)                                                 # GET the cached token.
    response.raise_for_status()                                                              # Fail loudly on HTTP error.
    return (response.json().get("access_token") or "").strip()                               # Return the token text.


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
            return []                                                                             # Return empty — can't query without token.
        url    = f"{ZOHO_DESK_BASE}/api/v1/tickets/search"                                        # Search endpoint.
        params = {                                                                                # Query parameters.
            "status":      ",".join(statuses),                                                    # Comma-separated statuses.
            "productName": ",".join(product_names),                                               # Comma-separated product names.
            "limit":       100,                                                                   # Page size.
            "sortBy":      "-createdTime",                                                        # Newest first.
        }                                                                                         # End params.
        response = requests.get(url, headers=desk_headers(token), params=params, timeout=30)      # Fire request.
        if response.status_code == 204 or not response.text.strip():                              # No results.
            return []                                                                             # Return empty list.
        response.raise_for_status()                                                               # Fail on HTTP error.
        return response.json().get("data", [])                                                    # Return ticket list.
    except Exception as error:                                                                    # Any error.
        print(f"[dashboard] Error fetching tickets: {error}")                                     # Log to console.
        return []                                                                                 # Return empty — dashboard stays up.
