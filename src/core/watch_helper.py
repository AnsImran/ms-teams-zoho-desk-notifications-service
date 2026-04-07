"""Shared helpers for product-specific Zoho Desk watchers (layperson style)."""  # Short module description in plain words.

import os                                                 # Work with file paths and environment variables.
import json                                               # Read and write small JSON files.
import re                                                 # Run simple keyword matching with regular expressions.
from dataclasses import dataclass                         # Define tiny config containers.
from datetime import datetime, timedelta                   # Handle time math safely.
from typing import Any, Dict, List, Optional, Set, Tuple  # Provide friendly type hints.

import pytz                     # Keep all local time handling consistent (Los Angeles by default).
import requests                 # Talk to Zoho Desk and Microsoft Teams over HTTPS.
from dotenv import load_dotenv  # Pull settings from a .env file automatically.
from pydantic import ValidationError  # Surface schema-validation failures clearly.

from src.schema.zoho_api_schemas import (  # Validate Zoho API payloads before use.
    ZohoTicketSearchResponse,
)

# Load environment variables as soon as the module imports.
load_dotenv()  # Makes later env lookups succeed without manual loading.

# -----------------------------
# Basic configuration values
# -----------------------------

DEFAULT_TZ_NAME = os.getenv("TZ_NAME", "America/Los_Angeles")  # Time zone string for display and windows.
LA_TZ           = pytz.timezone(DEFAULT_TZ_NAME)               # Time zone object we reuse everywhere.

CHECK_EVERY_SECONDS     = int(os.getenv("CHECK_EVERY_SECONDS", "30"))                                       # Polling interval shared by all products.
MAX_AGE_HOURS_DEFAULT   = int(os.getenv("MAX_AGE_HOURS", "24"))                                             # Default search lookback window in hours.
MIN_AGE_MINUTES_DEFAULT = int(os.getenv("MIN_AGE_MINUTES", "5"))                                            # Default minimum ticket age before alerting.
PAGE_LIMIT              = int(os.getenv("PAGE_LIMIT", "50"))                                                # Hard cap on search pages to avoid endless loops.
PAGE_SIZE               = int(os.getenv("PAGE_SIZE", "100"))                                                # Page size for Zoho search calls.
NOTIFY_COOLDOWN_RAW     = os.getenv("NOTIFY_COOLDOWN_SECONDS", "").strip()                                  # Optional global cooldown override in seconds.
NOTIFY_COOLDOWN_SECONDS = int(NOTIFY_COOLDOWN_RAW) if NOTIFY_COOLDOWN_RAW else None                        # None means derive cooldown from each product's min-age setting.
ZOHO_DESK_BASE          = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")                  # Base URL for Zoho Desk.

MAGIC_TEST_WEBHOOK = "https://defaulteaa017ab544342dfa2fa8cf8760698.84.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/0914c4da9462495f94ba9c6eb21f228a/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=U6i-SXJbj5gi-GfrPtwK2WRoRAaH_55gFMOypbkRupM"  # Shared test webhook for magic phrase.
MAGIC_TRIGGER      = os.getenv("MAGIC_TEST_TRIGGER_PHRASE", "test ticket by magic ai").strip().lower()      # Magic phrase text.

TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://host.docker.internal:8000").rstrip("/")  # Centralized Zoho token service on the host.

# -----------------------------
# Simple config container
# -----------------------------

@dataclass            # Decorator that turns the class below into a lightweight data container.
class ProductConfig:  # Holds settings for one product watcher.
    """Holds the knobs for one product watcher (kept easy to read)."""  # Plain-English class docstring.
    name:                  str                                          # Friendly product label for logs.
    target_product_names:  List[str]                                    # Product names to match exactly (case-insensitive).
    active_statuses:       Set[str]                                     # Status strings considered open.
    teams_webhook_env_var: str                                          # Env var name that stores the Teams webhook for this product.
    last_sent_filename:    str                                          # File name where we remember cooldown timestamps.
    max_age_hours:         int = MAX_AGE_HOURS_DEFAULT                  # How far back to search; defaults to shared value.
    min_age_minutes:       int = MIN_AGE_MINUTES_DEFAULT                # Minimum age before alert; defaults to shared value.
    notify_cooldown_seconds: Optional[int] = None                       # Optional per-product cooldown override in seconds.
    card_banner_text:      str = ""                                     # Optional top-of-card banner text (used for product-specific instructions).


@dataclass                   # Lightweight container for scheduled pending summary settings.
class PendingSummaryConfig:  # Holds knobs used by the pending summary watcher.
    """Holds configuration for scheduled pending-ticket summaries."""  # Plain-English class docstring.
    name:                  str                                         # Friendly watcher label for logs.
    pending_status_name:   str                                         # Status text treated as pending.
    teams_webhook_env_var: str                                         # Env var that stores pending-summary Teams webhook.
    report_times_la:       List[Tuple[int, int]]                       # Scheduled local LA times as (hour, minute).
    report_window_seconds: int                                         # Send window around each scheduled time.
    last_sent_filename:    str                                         # File where we store sent slot keys.

# -----------------------------
# Tiny helper utilities
# -----------------------------

def env_required(name: str) -> str:                                 # Ensure an environment variable exists and return it.
    """Return required env value or raise with a clear message."""  # Short docstring in simple words.
    value = os.getenv(name)                                         # Grab the value from environment.
    if not value:                                                   # If nothing was set...
        raise RuntimeError(f"Missing env var: {name}")              # Stop with a friendly error.
    return value                                                    # Send back the value when present.


def now_la() -> datetime:                                # Get current Los Angeles time right now.
    """Return current time in Los Angeles time zone."""  # Plain docstring.
    return datetime.now(LA_TZ)                           # Ask datetime for now with LA zone.


def iso_zoho(dt_any: datetime) -> str:                                 # Convert any datetime into Zoho-friendly UTC text.
    """Turn any datetime into Zoho's UTC string with .000Z suffix."""  # Docstring kept short.
    if dt_any.tzinfo is None:                                          # If the datetime has no zone...
        dt_any = LA_TZ.localize(dt_any)                                # Assume it is LA time and attach the zone.
    dt_utc = dt_any.astimezone(pytz.UTC)              # Convert to UTC time.
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")  # Format the exact string Zoho expects.


def parse_zoho_time_assume_la(text: str) -> datetime:                     # Turn Zoho timestamp text into LA datetime.
    """Parse Zoho timestamps and always return LA time."""                # Simple docstring.
    if not text:                                                          # Guard against blanks.
        raise ValueError("Empty datetime string")                         # Tell caller what went wrong.
    try:                                                                  # First attempt: handle Z suffix or standard ISO.
        if text.endswith("Z"):                                            # If UTC is marked with Z...
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Parse with explicit offset.
            return parsed.astimezone(LA_TZ)                               # Convert to LA time.
        parsed = datetime.fromisoformat(text)  # Parse regular ISO string.
        if parsed.tzinfo is None:              # If no zone is present...
            return LA_TZ.localize(parsed)                                 # Assume LA zone.
        return parsed.astimezone(LA_TZ)                                   # Convert any zone to LA.
    except Exception:                                                     # If the fast paths fail...
        fallback = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")  # Try a manual format with zone.
        return fallback.astimezone(LA_TZ)                             # Convert fallback to LA.


def created_time_range_la(hours: int) -> str:                               # Make Zoho createdTimeRange value for last N hours.
    """Build the createdTimeRange filter string in UTC for Zoho search."""  # Brief docstring.
    end_local   = now_la()                                                  # Capture current LA time.
    start_local = end_local - timedelta(hours=hours)                        # Subtract the lookback hours.
    return f"{iso_zoho(start_local)},{iso_zoho(end_local)}"                 # Join start and end with a comma.

# -----------------------------
# Zoho token handling
# -----------------------------

def get_token_from_service() -> str:                                                       # Fetch Zoho token from the internal token microservice.
    """Fetch the current Zoho access token from the internal token service."""             # Docstring summarizing goal.
    url = f"{TOKEN_SERVICE_URL}/token"                                                     # Build the token endpoint URL.
    try:                                                                                   # Wrap in try so connection errors are clear.
        response = requests.get(url, timeout=10)                                           # GET the cached token from the service.
        response.raise_for_status()                                                        # Fail loudly on HTTP error.
    except requests.RequestException as error:                                             # Catch any network or HTTP problem.
        raise RuntimeError(f"Token service unreachable at {url}: {error}") from error      # Re-raise with context.
    token = (response.json().get("access_token") or "").strip()                            # Pull and normalize token text.
    if not token:                                                                          # Protect against blank token values.
        raise RuntimeError(f"Token service returned empty access_token from {url}.")       # Clear error.
    return token                                                                           # Return the fresh token.


def desk_headers(token: str) -> Dict[str, str]:           # Build headers needed for Zoho Desk calls.
    """Return headers needed for Zoho Desk API calls."""  # Simple docstring.
    return {                                              # Build and return the headers dictionary.
        "Authorization": f"Zoho-oauthtoken {token}",          # OAuth token header.
        "orgId":         env_required("ZOHO_DESK_ORG_ID"),    # Organization id header.
        "Accept":        "application/json",                  # Ask for JSON responses.
    }                                                         # Return the header dictionary.

# -----------------------------
# Persistence helpers
# -----------------------------

def load_last_sent(path: str) -> Dict[str, datetime]:                          # Read cooldown times from disk safely.
    """Read last-sent timestamps from disk; return empty dict on problems."""  # Clear docstring.
    if not os.path.exists(path):                                               # If file does not exist yet...
        return {}                                                              # Start with empty memory.
    try:                                                                       # Try to read and parse JSON.
        with open(path, "r", encoding="utf-8") as handle:                      # Open file for reading.
            raw = json.load(handle)                                            # Parse JSON into dict.
        output: Dict[str, datetime] = {}  # Prepare typed dict.
        for key, value in raw.items():    # Walk through stored pairs.
            try:                                                               # Convert each ISO string back to datetime.
                output[key] = datetime.fromisoformat(value)                    # Parse ISO format.
            except Exception:                                                  # Ignore malformed entries.
                continue                                                       # Skip bad rows quietly.
        return output                                                          # Send back parsed map.
    except Exception:                                                          # If any IO or JSON error happens...
        return {}                                                              # Fall back to empty dict.


def save_last_sent(path: str, payload: Dict[str, datetime]) -> None:     # Write cooldown times back to disk.
    """Write last-sent timestamps to disk in a friendly JSON format."""  # Simple docstring.
    serializable = {key: dt.isoformat() for key, dt in payload.items()}  # Convert datetimes to strings.
    with open(path, "w", encoding="utf-8") as handle:                    # Open target file for writing.
        json.dump(serializable, handle, indent=2)                        # Dump pretty JSON so humans can read it.

# -----------------------------
# Teams helpers
# -----------------------------

def post_to_teams(webhook_url: str, payload: Dict[str, Any]) -> None:  # Push one payload to a Teams webhook.
    """Send a single Adaptive Card payload to Teams via webhook."""    # Straight docstring.
    response = requests.post(webhook_url, json=payload, timeout=30)    # POST the JSON body to Teams.
    if response.status_code >= 400:                                    # If Teams returned an error status...
        print("TEAMS WEBHOOK ERROR", response.status_code)             # Log the status code.
        print("Teams response body:", (response.text or "")[:2000])    # Log a short response snippet.
    response.raise_for_status()                                        # Raise on errors so caller can react.


def build_teams_adaptive_card(  # Build and wrap an adaptive card payload.
    *,                          # Only allow keyword arguments for clarity.
    title:           str,       # Card title text.
    summary:         str,       # Short summary text.
    banner_text:     str = "",  # Optional top banner shown above the title.
    ticket_number:   str,       # Ticket number text.
    ticket_id:       str,       # Ticket id text.
    subject_line:    str,       # Subject text.
    status:          str,       # Status text.
    status_type:     str,       # Status type text.
    created_display: str,       # Created time display string.
    age_minutes:     int,       # Age in minutes as integer.
    reason:          str,       # Why the ticket matched.
    web_url:         str,       # Link to open the ticket.
) -> Dict[str, Any]:                                                           # Return a dictionary payload ready for Teams.
    """Build the Adaptive Card body wrapped in the Teams message envelope."""  # Short docstring.
    body_blocks: List[Dict[str, Any]] = []                                     # Build card rows in order so optional banner can appear first.
    if banner_text.strip():                                                    # Add a visual instruction banner when provided.
        body_blocks.append(                                                    # Banner appears at very top of the card.
            {
                "type":   "TextBlock",
                "text":   banner_text.strip(),
                "wrap":   True,
                "weight": "Bolder",
                "color":  "Attention",
                "size":   "Medium",
            }
        )                # End banner block append.
    body_blocks.extend(  # Append normal product reminder rows.
        [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},       # Title block.
            {"type": "TextBlock", "text": summary, "wrap": True, "spacing": "Small"},                       # Summary line.
            {"type": "TextBlock", "text": f"Matched because: {reason}", "wrap": True, "spacing": "Small"},  # Reason line.
            {                                                                                               # Fact list with ticket details.
                "type": "FactSet",  # Fact list container.
                "facts": [          # Array of facts to show.
                    {"title": "Ticket Number", "value": str(ticket_number)            },  # Ticket number fact.
                    {"title": "Ticket ID",     "value": str(ticket_id)                },  # Ticket id fact.
                    {"title": "Subject",       "value": subject_line    or "(none)"   },  # Subject fact.
                    {"title": "Status",        "value": status          or "(none)"   },  # Status fact.
                    {"title": "Status Type",   "value": status_type     or "(none)"   },  # Status type fact.
                    {"title": "Created (LA)",  "value": created_display or "(unknown)"},  # Created time fact.
                    {"title": "Age (minutes)", "value": str(age_minutes)              },  # Age fact.
                ],                                                                                          # End of facts list.
            },                                                                                              # End fact set block.
        ]
    )         # End normal rows append.
    card = {  # Actual adaptive card payload.
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",                  # Schema reference.
        "type": "AdaptiveCard",                                                           # Card type identifier.
        "version": "1.4",                                                                 # Card version that Teams understands.
        "body": body_blocks,                                                              # Visible body elements list.
        "actions": [{"type": "Action.OpenUrl", "title": "Open Ticket", "url": web_url}],  # Single button action.
    }         # Close adaptive card definition.
    return {  # Wrap adaptive card inside Teams message envelope.
        "type": "message",  # Envelope type.
        "attachments": [    # Attachments list.
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}   # Adaptive card attachment.
        ],                                                                                # End attachments list.
    }                                                                                     # End envelope and return it.


def build_pending_tickets_adaptive_card(                                                                      # Build a Teams card that lists pending tickets with clickable links.
    *,                                             # Only allow keyword arguments for readability.
    title:                  str,                   # Card title text.
    summary:                str,                   # Summary line under the title.
    pending_ticket_entries: List[Dict[str, str]],  # One structured entry per pending ticket.
) -> Dict[str, Any]:                                                                                          # Return a Teams message payload.
    """Build a compact Adaptive Card for scheduled pending-ticket summaries."""  # Plain docstring.
    body_blocks: List[Dict[str, Any]] = [                                        # Start with static title + summary rows.
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},  # Card title.
        {"type": "TextBlock", "text": summary, "wrap": True, "spacing": "Small"},                  # Summary text.
    ]                               # End initial body rows.
    if not pending_ticket_entries:  # Render a fallback row when there are no tickets.
        body_blocks.append({"type": "TextBlock", "text": "(no pending tickets in this window)", "wrap": True, "spacing": "Small"})  # Simple fallback line.
    else:                                                                                                     # Render each ticket with a FactSet so labels are aligned like product reminder cards.
        for ticket_index, entry in enumerate(pending_ticket_entries):                                         # Walk through each pending ticket entry.
            if ticket_index > 0:                                                                              # Add one spacer row between tickets.
                body_blocks.append({"type": "TextBlock", "text": "\u00A0", "wrap": True, "spacing": "None"})  # Extra blank line between tickets.
            body_blocks.append(                                                                               # Add one aligned fact table per ticket.
                {
                    "type": "FactSet",  # Aligned label-value rows.
                    "facts": [
                        {"title": "Ticket Number", "value": entry.get("ticket_number", "(none)")},
                        {"title": "Ticket ID", "value": entry.get("ticket_id_value", "(none)")},
                        {"title": "Subject", "value": entry.get("subject", "(no subject)")},
                        {"title": "Assignee", "value": entry.get("assignee", "(unassigned)")},
                        {"title": "Created (LA)", "value": entry.get("created_display", "(unknown)")},
                        {"title": "Age (minutes)", "value": entry.get("age_minutes", "-1")},
                    ],
                    "spacing": "Small",
                }
            )                                                                            # End FactSet append.
    card = {                                                                             # Adaptive Card content.
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",  # Schema reference.
        "type": "AdaptiveCard",                                           # Card type.
        "version": "1.4",                                                 # Card version supported by Teams.
        "body": body_blocks,                                              # Body elements rendered in strict explicit-line order.
    }         # End card dictionary.
    return {  # Wrap the adaptive card in a Teams webhook envelope.
        "type": "message",  # Message envelope type.
        "attachments": [    # Attachments array with one adaptive card.
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}  # Teams card attachment.
        ],                                                                               # End attachments array.
    }                                                                                    # End message envelope.


def contains_magic_phrase(*texts: Any) -> bool:                            # Look for the shared magic phrase in any text.
    """Return True if any provided text holds the shared magic phrase."""  # Docstring in clear words.
    if not MAGIC_TRIGGER:                                                  # If no trigger configured...
        return False                                                       # Always say no.
    for text in texts:                                                     # Inspect each provided value.
        if not isinstance(text, str):                                      # Ignore non-string inputs.
            continue                                                       # Skip to next item.
        normalized = re.sub(r"\\s+", " ", text).lower()  # Collapse whitespace and lowercase.
        if MAGIC_TRIGGER in normalized:                  # If phrase appears anywhere...
            return True                                                    # Signal a match.
    return False                                                           # No matches found.

# -----------------------------
# Ticket helpers
# -----------------------------

def extract_product_name(ticket: Dict[str, Any]) -> Optional[str]:                           # Pull the product name from a ticket payload.
    """Extract product name from ticket, checking common Zoho field shapes."""               # Docstring in plain words.
    for key in ("productName", "product"):                                                   # Check common product keys.
        value = ticket.get(key)                                                              # Read the value.
        if isinstance(value, str) and value.strip():                                         # If it is a non-empty string...
            return value.strip()                                                             # Return it directly.
        elif isinstance(value, dict):                                                        # If value is a nested dict...
            for sub_key in ("name", "productName"):                                          # Check nested name fields.
                nested = value.get(sub_key)                                                  # Read nested value.
                if isinstance(nested, str) and nested.strip():                               # If usable string...
                    return nested.strip()                                                    # Return the nested name.
    return None                                                                              # No product name found.


def build_config_lookup(configs: List[ProductConfig]) -> Dict[str, ProductConfig]:           # Build product-name-to-config lookup dict.
    """Map each target product name (lower-case) to its ProductConfig."""                    # Docstring in plain words.
    lookup: Dict[str, ProductConfig] = {}                                                    # Empty lookup dict to populate.
    for config in configs:                                                                   # Walk every product config.
        for name in config.target_product_names:                                             # Walk every target name for this product.
            lookup[name.lower()] = config                                                    # Map lower-case name to its config.
    return lookup                                                                            # Return the completed lookup dict.


def effective_notify_cooldown_seconds(config: ProductConfig) -> int:                         # Compute cooldown seconds used for repeat alerts.
    """Return cooldown seconds with clear precedence and safe defaults."""                   # Brief docstring.
    if config.notify_cooldown_seconds is not None:                                           # Product-specific override wins first.
        return max(0, int(config.notify_cooldown_seconds))                                   # Clamp to non-negative seconds.
    if NOTIFY_COOLDOWN_SECONDS is not None:                                                  # Fall back to global env override when provided.
        return max(0, int(NOTIFY_COOLDOWN_SECONDS))                                          # Clamp to non-negative seconds.
    return max(0, int(config.min_age_minutes) * 60)                                          # Default to product min-age minutes.

# -----------------------------
# Zoho search
# -----------------------------

def search_tickets(token: str, statuses: List[str], hours: Optional[int] = None, product_names: Optional[List[str]] = None, page_limit: Optional[int] = PAGE_LIMIT) -> List[Dict[str, Any]]:  # Pull tickets from Zoho with optional filters.
    """Search Zoho Desk for tickets by status and optionally by product names."""  # Docstring.
    url                           = f"{ZOHO_DESK_BASE}/api/v1/tickets/search"                     # Build search URL.
    statuses_param                = ",".join(statuses)                                            # Join statuses for Zoho parameter.
    results: List[Dict[str, Any]] = []                                                            # Aggregate list for pages.
    use_sort                      = True                                                          # Start with sort enabled.
    page_idx                      = 0                                                             # Track current page index for pagination.
    while True:                                                                                   # Continue until Zoho returns no more rows or we hit optional page cap.
        if page_limit is not None and page_idx >= page_limit:                                                 # Stop when configured cap is reached.
            break                                                                                             # Exit pagination loop.
        start  = page_idx * PAGE_SIZE    # Calculate offset.
        params = {                       # Build query parameters.
            "status": statuses_param,    # Status filter.
            "from":   start,             # Pagination start.
            "limit":  PAGE_SIZE,         # Page size.
        }                      # Finished building params dictionary.
        if product_names:                                                                                     # Add product name filter when provided.
            params["productName"] = ",".join(product_names)                                                   # Comma-separated product names for Zoho server-side filtering.
        if hours is not None:  # Add lookback filter only when caller requests one.
            params["createdTimeRange"] = created_time_range_la(hours)                                         # Time window filter.
        if use_sort:                                                                                          # Only include sort when allowed.
            params["sortBy"] = "-createdTime"                                                                 # Ask for newest first.
        print(f"[search] GET {url} params={params}")                                                         # Log the full query for debugging.
        response = requests.get(url, headers=desk_headers(token), params=params, timeout=30)  # Fire request.
        if response.status_code == 422 and use_sort:                                          # If sort is not supported here...
            use_sort = False  # Disable sort and retry same page.
            continue          # Skip to next loop iteration.
        if response.status_code >= 400:                                                                       # For any other error...
            print("HTTP ERROR", response.status_code, "for", response.url)  # Log details.
            print("Response body:", (response.text or "")[:2000])           # Log short body snippet.
        response.raise_for_status()  # Raise on HTTP error.
        if not response.text.strip():                                                                         # Zoho returns empty body when search has no results.
            break                                                                                             # Treat empty body as zero results and stop paginating.
        try:                         # Validate Zoho search payload before processing ticket rows.
            search_payload = ZohoTicketSearchResponse.model_validate(response.json())  # Parse top-level payload.
        except ValidationError as error:                                                # Raise clear validation failure.
            raise RuntimeError(f"Zoho search response failed schema validation: {error}") from error
        data = [ticket.model_dump(mode="python") for ticket in (search_payload.data or [])]  # Convert validated models back to dictionaries for existing code paths.
        if not data:                                  # If page empty...
            break                                                                                             # Stop paginating.
        results.extend(data)       # Add page items to results.
        if len(data) < PAGE_SIZE:  # If fewer than a full page...
            break                                                                                             # End pagination.
        page_idx += 1                                                                                         # Move to the next page.
    results.sort(key=lambda item: item.get("createdTime") or "", reverse=True)  # Sort newest first just in case.
    return results                                                              # Hand back all collected tickets.

# -----------------------------
# Single-loop ticket processor
# -----------------------------

def process_tickets(                                                                                          # Process all tickets in one pass using a config lookup.
    *,                                                                                                        # Force keyword arguments for clarity.
    tickets:        List[Dict[str, Any]],                                                                     # Pre-fetched ticket list from Zoho search.
    config_lookup:  Dict[str, ProductConfig],                                                                 # Product-name-to-config lookup built by build_config_lookup.
    cooldown_state: Dict[str, Dict[str, datetime]],                                                           # Per-product cooldown maps keyed by last_sent_filename.
) -> int:                                                                                                     # Return total number of alerts sent.
    """Walk every ticket once, look up its product config, check age and cooldown, send to Teams."""          # Docstring in plain words.
    script_dir  = os.path.dirname(os.path.abspath(__file__))                                                  # Folder that holds cooldown JSON files.
    total_sent  = 0                                                                                           # Count alerts across all products.
    changed_set: Set[str] = set()                                                                             # Track which cooldown files need saving.

    for ticket in tickets:                                                                                    # One pass through every ticket.
        ticket_id = ticket.get("id")                                                                          # Pull ticket id.
        if not ticket_id:                                                                                     # If missing id...
            continue                                                                                          # Skip this ticket.

        product_name = extract_product_name(ticket)                                                           # Pull product name from ticket payload.
        if not product_name:                                                                                  # If no product name found...
            continue                                                                                          # Skip — cannot match any config.
        config = config_lookup.get(product_name.lower())                                                      # Look up the matching product config.
        if not config:                                                                                        # If no config owns this product name...
            continue                                                                                          # Skip — not one of our watched products.

        status = (ticket.get("status") or "").strip()                                                         # Read status text.
        if status and status not in config.active_statuses:                                                   # If status not in this product's watched set...
            continue                                                                                          # Skip.

        created_raw = ticket.get("createdTime", "")                                                           # Raw created timestamp.
        try:                                                                                                  # Try to parse created time.
            created_la      = parse_zoho_time_assume_la(created_raw)                                          # Parse into LA time.
            age_minutes     = int((now_la() - created_la).total_seconds() // 60)                              # Age in minutes.
            created_display = created_la.strftime("%Y-%m-%d %H:%M:%S %Z")                                    # Nice display string.
        except Exception:                                                                                     # If parsing fails...
            created_la      = None                                                                            # Mark as unknown time.
            age_minutes     = -1                                                                              # Unknown age marker.
            created_display = created_raw or "(unknown)"                                                      # Fallback display.

        if age_minutes >= 0 and age_minutes < config.min_age_minutes:                                         # If ticket is too new for this product...
            continue                                                                                          # Skip — not old enough to alert.

        last_sent        = cooldown_state.setdefault(config.last_sent_filename, {})                            # Get or create this product's cooldown map.
        cooldown_seconds = effective_notify_cooldown_seconds(config)                                           # Resolve cooldown seconds for this product.
        now_local        = datetime.now()                                                                     # Current local time for cooldown math.
        last_time        = last_sent.get(ticket_id)                                                           # Previous send time for this ticket.
        if last_time:                                                                                         # If we sent before...
            elapsed = (now_local - last_time).total_seconds()                                                 # Seconds since last send.
            if cooldown_seconds > 0 and elapsed < cooldown_seconds:                                           # If still in cooldown...
                wait_minutes = (cooldown_seconds - elapsed) / 60.0                                            # Minutes remaining.
                print(f"[{config.name}] Skip ticket {ticket_id} - cooldown {wait_minutes:.1f} min left.")     # Log skip.
                continue                                                                                      # Move on.

        ticket_number    = str(ticket.get("ticketNumber", "") or "")                                          # For logs and card.
        subject_line     = ticket.get("subject", "") or ""                                                    # Read subject.
        description_text = ticket.get("description") or ticket.get("descriptionText") or ""                   # Read description text.
        web_url          = ticket.get("webUrl", "") or ""                                                     # Read web URL for button.
        reason           = f"age ok ({age_minutes}m old)" if age_minutes >= 0 else "age unknown"              # Build reason text.
        print(f"[{config.name}] ALERT: Ticket {ticket_number} ({ticket_id}) reason={reason}")                 # Log alert intent.

        teams_payload = build_teams_adaptive_card(                                                            # Build Teams payload.
            title           = f"{config.name.upper()} REMINDER (Automated)",                                  # Title with product name.
            summary         = f"Ticket {ticket_number} is still NOT resolved.",                               # Short summary.
            banner_text     = config.card_banner_text,                                                        # Optional top banner.
            ticket_number   = ticket_number,                                                                  # Ticket number.
            ticket_id       = str(ticket_id),                                                                 # Ticket id.
            subject_line    = subject_line,                                                                   # Subject line.
            status          = str(ticket.get("status", "") or ""),                                            # Status text.
            status_type     = str(ticket.get("statusType", "") or ""),                                        # Status type text.
            created_display = created_display,                                                                # Created display text.
            age_minutes     = age_minutes,                                                                    # Age minutes.
            reason          = reason,                                                                         # Match reason.
            web_url         = web_url,                                                                        # Ticket link.
        )                                                                                                     # Finish payload build.

        magic_hit      = contains_magic_phrase(subject_line, description_text)                                 # Check magic phrase.
        target_webhook = MAGIC_TEST_WEBHOOK if magic_hit else os.getenv(config.teams_webhook_env_var, "").strip()  # Pick webhook URL.
        if not target_webhook:                                                                                # If no webhook configured...
            print(f"[{config.name}] Skip ticket {ticket_number} ({ticket_id}) - no webhook configured.")      # Log skip.
            continue                                                                                          # Skip sending.

        post_to_teams(target_webhook, teams_payload)                                                          # Send card to Teams sequentially.
        last_sent[ticket_id] = now_local                                                                      # Record send time for cooldowns.
        changed_set.add(config.last_sent_filename)                                                            # Mark this product's cooldown file as dirty.
        total_sent += 1                                                                                       # Increment total alert count.

    for filename in changed_set:                                                                              # Save only the cooldown files that changed.
        path = os.path.join(script_dir, filename)                                                             # Build full path to cooldown file.
        save_last_sent(path, cooldown_state[filename])                                                        # Persist updates to disk.
        print(f"[cooldown] Saved {filename}")                                                                 # Log save.

    if total_sent == 0:                                                                                       # If nothing sent this cycle...
        print("[main] No matching tickets found this cycle.")                                                  # Log quiet cycle.
    else:                                                                                                     # If we sent something...
        print(f"[main] Sent {total_sent} reminder notification(s) to Teams.")                                 # Log total count.
    return total_sent                                                                                         # Hand back the total.

# -----------------------------
# Pending summary helpers
# -----------------------------

def parse_hhmm_schedule(raw_text: str, env_name: str = "PENDING_REPORT_TIMES_LA") -> List[Tuple[int, int]]:   # Parse semicolon-separated 24-hour HH:MM strings.
    """Parse env text like '04:00;12:00;20:00' into unique (hour, minute) tuples."""  # Docstring in plain language.
    entries = [entry.strip() for entry in raw_text.split(";") if entry.strip()]       # Split on semicolons and drop blanks.
    if not entries:                                                                   # Guard against empty schedule configs.
        raise RuntimeError(f"{env_name} is empty. Use HH:MM;HH:MM in 24-hour format.")                        # Raise clear config error.
    parsed: List[Tuple[int, int]] = []     # Output list preserving input order.
    seen: set[Tuple[int, int]]    = set()  # Track duplicates.
    for entry in entries:                  # Parse each HH:MM token.
        parts = entry.split(":")                                                 # Expected shape is exactly hour:minute.
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():  # Validate basic token structure.
            raise RuntimeError(f"Invalid time '{entry}' in {env_name}. Expected HH:MM in 24-hour format.")    # Raise parse error.
        hour   = int(parts[0])                                  # Hour component as int.
        minute = int(parts[1])                                  # Minute component as int.
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:  # Validate allowed ranges.
            raise RuntimeError(f"Invalid time '{entry}' in {env_name}. Hour must be 00-23 and minute 00-59.") # Raise range error.
        value = (hour, minute)  # Canonical tuple form.
        if value in seen:       # Ignore duplicate entries.
            continue                                                                                          # Skip duplicate.
        seen.add(value)       # Mark tuple as seen.
        parsed.append(value)  # Keep tuple in the parsed output.
    return parsed                                                                                             # Return parsed schedule list.


def _scheduled_slot_if_due(now_local: datetime, report_times_la: List[Tuple[int, int]], window_seconds: int) -> Optional[Tuple[str, datetime]]:  # Detect whether now is inside any scheduled window.
    """Return (slot_key, slot_time) when now falls within +/- window of a scheduled LA time."""  # Docstring.
    for hour, minute in report_times_la:                                                         # Check all configured times for today.
        slot_time = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)  # Build today's scheduled timestamp.
        if abs((now_local - slot_time).total_seconds()) <= window_seconds:                # Accept times just before or after slot.
            return slot_time.strftime("%Y-%m-%d %H:%M"), slot_time                                            # Stable key used for slot de-dup.
    return None                                                                                               # Not currently in any configured send window.


def pending_summary_state_path(config: PendingSummaryConfig) -> str:           # Compute absolute path for pending summary slot-state file.
    """Return path to the pending summary slot-state file for this config."""  # Brief docstring.
    script_dir = os.path.dirname(os.path.abspath(__file__))                    # Locate directory containing this helper module.
    return os.path.join(script_dir, config.last_sent_filename)                 # Build full path to slot-state JSON.


def delete_pending_summary_state_file(config: PendingSummaryConfig) -> None:                 # Delete pending schedule state file at startup.
    """Remove pending summary state file so slot tracking starts fresh for this process."""  # Docstring in simple words.
    path = pending_summary_state_path(config)                                                # Resolve file path from config.
    if os.path.exists(path):                                                                 # Delete only when file already exists.
        try:                                                                                 # Attempt safe file removal.
            os.remove(path)                                            # Delete slot-state file.
            print(f"[{config.name}] Startup cleanup: removed {path}")  # Log success for visibility.
        except Exception as error:                                                           # Catch deletion failures without crashing the app.
            print(f"[{config.name}] WARNING: Could not delete state file {path}: {error}")   # Log warning message.


def one_line_text(value: Any, fallback: str = "(no subject)") -> str:                 # Convert input text into a single compact line.
    """Collapse whitespace into one line and provide fallback for missing values."""  # Brief docstring.
    if not isinstance(value, str):                                                    # Non-string values cannot be normalized directly.
        return fallback                                                               # Return fallback text.
    normalized = re.sub(r"\s+", " ", value).strip()  # Collapse multiple whitespace and trim edges.
    return normalized or fallback                    # Return fallback when normalized text is empty.


def pending_ticket_assignee_name(ticket: Dict[str, Any]) -> str:                  # Extract assignee name from ticket payload.
    """Return assignee full name from ticket data, or a clear fallback."""  # Brief docstring.
    assignee = ticket.get("assignee")                                       # Read assignee object.
    if isinstance(assignee, dict):                                          # Handle the expected object shape.
        first     = one_line_text(assignee.get("firstName"), fallback="").strip()  # Assignee first name.
        last      = one_line_text(assignee.get("lastName"), fallback="").strip()   # Assignee last name.
        full_name = " ".join(part for part in (first, last) if part)               # Join non-empty name parts.
        if full_name:                                                              # Prefer full name when available.
            return full_name                                                      # Return readable full name.
        fallback_name = one_line_text(assignee.get("name"), fallback="").strip()  # Some payloads include a single name field.
        if fallback_name:                                                         # Use fallback name if present.
            return fallback_name                                                  # Return fallback name.
    return "(unassigned)"                                                         # Final fallback when no assignee name is available.


def pending_ticket_created_and_age(ticket: Dict[str, Any]) -> Tuple[str, int]:  # Compute created-time display and age in minutes, matching product-card behavior.
    """Return (created_display, age_minutes) for pending ticket cards."""  # Brief docstring.
    created_raw = str(ticket.get("createdTime") or "").strip()             # Raw created timestamp text.
    try:                                                                   # Try to parse and compute values exactly like product watchers.
        created_la      = parse_zoho_time_assume_la(created_raw)              # Parse into LA time.
        age_minutes     = int((now_la() - created_la).total_seconds() // 60)  # Compute age in minutes.
        created_display = created_la.strftime("%Y-%m-%d %H:%M:%S %Z")         # Friendly created-time display.
        return created_display, age_minutes                                   # Return parsed values.
    except Exception:                                                           # If parse fails, keep safe fallbacks.
        fallback_display = created_raw or "(unknown)"  # Reuse raw value when available.
        return fallback_display, -1                    # Unknown age marker.


def build_pending_ticket_entries(tickets: List[Dict[str, Any]]) -> List[Dict[str, str]]:  # Build structured entries for pending summary cards.
    """Build one structured entry per ticket for aligned FactSet card rendering."""  # Docstring.
    entries: List[Dict[str, str]] = []                                               # Collect one structured entry per ticket.
    for ticket in tickets:                                                           # Transform each ticket into a structured dictionary.
        ticket_id = str(ticket.get("id") or "").strip()  # Read full ticket id.
        if not ticket_id:                                # Skip malformed entries without IDs.
            continue                                                                      # Skip this row.
        ticket_number                = str(ticket.get("ticketNumber") or "").strip()                  # Read ticket number when present.
        web_url                      = str(ticket.get("webUrl") or "").strip()                        # Read ticket URL when present.
        assignee_name                = pending_ticket_assignee_name(ticket)                           # Extract assignee first/last name.
        subject_text                 = one_line_text(ticket.get("subject"), fallback="(no subject)")  # Build compact one-line subject text.
        created_display, age_minutes = pending_ticket_created_and_age(ticket)                         # Compute created display and age fields.
        ticket_id_value              = f"[{ticket_id}]({web_url})" if web_url else ticket_id          # Keep ticket id clickable when URL exists.
        entries.append(                                                                               # Store one ticket as aligned label-value data.
            {
                "ticket_number": ticket_number or "(none)",
                "ticket_id_value": ticket_id_value,
                "subject": subject_text,
                "assignee": assignee_name,
                "created_display": created_display,
                "age_minutes": str(age_minutes),
            }
        )           # End of one ticket entry.
    return entries  # Return all prepared ticket entries.


def run_pending_summary_loop_once(config: PendingSummaryConfig, token: str) -> None:                      # Run one pending summary cycle with its own ticket fetch.
    """Run one pending summary cycle and send one card per due schedule slot."""                          # Docstring.
    now_local  = now_la()                                                                                 # Capture LA time once for this cycle.
    slot_match = _scheduled_slot_if_due(now_local, config.report_times_la, config.report_window_seconds)  # Determine if now is inside any slot window.
    if not slot_match:                                                                                    # Most polling loops are outside configured schedule windows.
        return                                                                                            # Exit quietly.

    slot_key, slot_time = slot_match                          # Slot key used for de-dup and display timestamp.
    state_path          = pending_summary_state_path(config)  # Path to slot-state JSON file.
    sent_slots          = load_last_sent(state_path)          # Read previously processed slot keys.
    if slot_key in sent_slots:                                # Skip repeated sends within the same scheduled slot.
        return                                       # Slot already processed.

    webhook_url = os.getenv(config.teams_webhook_env_var, "").strip()  # Read pending summary webhook from env.
    if not webhook_url:                                                # Without webhook we cannot send the card.
        print(f"[{config.name}] Skip slot {slot_key} - missing {config.teams_webhook_env_var}.")  # Log clear config issue.
        return                                                                                    # Exit without crashing main loop.

    query_status    = (config.pending_status_name or "PENDING").strip().upper()                    # Use API-level status filtering to fetch only pending tickets.
    tickets         = search_tickets(token, statuses=[query_status], hours=None, page_limit=None)  # Fetch only pending tickets from Zoho across all available history.
    pending_entries = build_pending_ticket_entries(tickets)                                        # Build aligned ticket entries for card body.

    if not pending_entries:                                                                      # No pending tickets to report in this snapshot.
        print(f"[{config.name}] Slot {slot_key}: no pending tickets in the shared result set.")  # Helpful no-op log.
        sent_slots[slot_key] = now_local                                                         # Mark slot as processed to avoid duplicate checks this window.
        save_last_sent(state_path, sent_slots)                                                   # Persist processed slot.
        return                                                                                   # Nothing to send.

    slot_display = slot_time.strftime("%Y-%m-%d %H:%M:%S %Z")  # Friendly display of the scheduled LA slot.
    payload      = build_pending_tickets_adaptive_card(        # Build adaptive card with pending ticket list.
        title="Pending Tickets Snapshot (Automated)",                                                   # Card title line.
        summary=f"LA slot {slot_display}. Found {len(pending_entries)} pending ticket(s) still open.",  # Summary text.
        pending_ticket_entries=pending_entries,                                                         # Structured entries for aligned FactSet rendering.
    )                                                                                             # Finish payload definition.
    post_to_teams(webhook_url, payload)                                                           # Send pending summary card to Teams webhook.
    sent_slots[slot_key] = now_local                                                              # Mark this slot as sent.
    save_last_sent(state_path, sent_slots)                                                        # Persist slot-state updates.
    print(f"[{config.name}] Sent {len(pending_entries)} pending ticket(s) for slot {slot_key}.")  # Success log.

# -----------------------------
# One-time startup cleanup helper
# -----------------------------

def delete_cooldown_file(config: ProductConfig) -> None:                                       # Delete the cooldown file for a product at startup.
    """Remove the product's cooldown file so alerts start fresh on launch."""  # Docstring in everyday language.
    script_dir = os.path.dirname(os.path.abspath(__file__))                    # Find the folder that holds this script.
    path       = os.path.join(script_dir, config.last_sent_filename)           # Build full path to the cooldown JSON file.
    if os.path.exists(path):                                                   # Only try to delete if the file is present.
        try:                                                                                   # Attempt the deletion safely.
            os.remove(path)                                            # Delete the file to clear cooldown history.
            print(f"[{config.name}] Startup cleanup: removed {path}")  # Log success for visibility.
        except Exception as error:                                                             # Catch any deletion problem.
            print(f"[{config.name}] WARNING: Could not delete cooldown file {path}: {error}")  # Log the warning clearly.
