# ------------------------------------------------------------------------------------
# OVERALL GOAL (plain English):
# ------------------------------------------------------------------------------------
# This script keeps checking Zoho Desk for support tickets that are still not resolved,
# and that look like they are about "Super-Stat" (based on product name or keyword match).
# If it finds a matching unresolved ticket that is old enough, it sends an email reminder,
# and optionally posts a message to Microsoft Teams.
#
# IMPORTANT BEHAVIOR:
# - It runs forever in a loop (because of "while True").
# - It checks every N seconds (default: 300 seconds = 5 minutes).
# - It looks back over tickets created in the last N hours (default: 24 hours).
# - It will alert EVERY time the script runs if the ticket still matches (not just once).
# - It keeps a small "seen" state file mainly so it can clean up IDs of resolved tickets.
# ------------------------------------------------------------------------------------

import os  # Lets us read environment variables and work with files/paths.
import time  # Lets us pause the program between checks (sleep).
import json  # Lets us store and read data in JSON format (the "seen tickets" file).
import re  # Lets us search for keywords using regular expressions (pattern matching).
import smtplib  # Lets us send email using an SMTP server.
import ssl  # Lets us create secure encryption settings for email connections.
from email.message import EmailMessage  # A helper class to build an email message cleanly.
from typing import List, Dict, Any, Tuple, Optional  # Type hints: make code easier to understand.
from datetime import datetime, timedelta, timezone  # Date/time handling and time differences.

import pytz  # Time zone library (so we can work in Los Angeles time reliably).
import requests  # Lets us make HTTP calls to Zoho APIs and Teams webhooks.
from dotenv import load_dotenv  # Loads variables from a .env file into environment variables.

import certifi




load_dotenv()  # Load variables from a .env file (if present) into the environment.

# -----------------------------
# Configuration (settings)
# -----------------------------

# NOTE (plain English):
# We are intentionally NOT using the "seen tickets" state mechanism at runtime anymore.
# We are keeping the original comments and functions below (verbatim) because you said:
# - Do not remove any comment at all.
# - The documentation is very necessary.
# The monitoring logic below will still alert on every run for matching unresolved tickets.

CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "300"))
# How often we check for tickets, in seconds.
# Default is 300 seconds = 5 minutes.

MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "24"))
# We only look at tickets created within the last N hours (default: 24 hours).

MIN_AGE_MINUTES = int(os.getenv("MIN_AGE_MINUTES", "5"))
# We do NOT alert on tickets that are too new.
# Default: ticket must be at least 5 minutes old before we alert.

TZ_NAME = os.getenv("TZ_NAME", "America/Los_Angeles")
# The time zone name we will treat as the "main" time zone for display and windows.
# Default is Los Angeles time.

LA_TZ = pytz.timezone(TZ_NAME)
# Convert the time zone string into an actual timezone object used by pytz.

ACTIVE_STATUSES = set(
    s.strip() for s in os.getenv("ACTIVE_STATUSES", "Assigned,Pending,Escalated").split(",") if s.strip()
)
# These are the ticket statuses that we consider "active" (not resolved yet).
# We read it from env var ACTIVE_STATUSES, or use "Assigned,Pending,Escalated".
# We split by commas, trim spaces, and store them as a set for fast lookups.

TARGET_PRODUCT_NAMES = [p.strip().lower() for p in os.getenv("TARGET_PRODUCT_NAMES", "").split(",") if p.strip()]
# If you set TARGET_PRODUCT_NAMES in the environment, we will match tickets by product name.
# We make them lowercase so we can do case-insensitive comparisons.
# If the env var is empty, this list will be empty (meaning product match is disabled).

KEYWORD_REGEX = os.getenv("KEYWORD_REGEX", r"\bsuper[\s-]?stat\b")
# This is the pattern used to detect "Super-Stat" in subject/description.
# Default pattern matches: "superstat", "super stat", "super-stat" (case-insensitive).

KEYWORD_RE = re.compile(KEYWORD_REGEX, re.IGNORECASE)
# We compile the regex once (faster than compiling every time) and make it case-insensitive.

ZOHO_ACCOUNTS_TOKEN_URL = os.getenv("ZOHO_ACCOUNTS_TOKEN_URL", "https://accounts.zoho.com/oauth/v2/token")
# URL where we request a new access token from Zoho using a refresh token.

# Simple in-memory cache so we don't refresh the Zoho access token every loop.
TOKEN_CACHE: Dict[str, Any] = {
    "token": None,         # Cached access token string.
    "created_at": None,    # When we fetched it (UTC).
    "expires_at": None,    # When it expires (UTC).
}
TOKEN_LIFETIME_SECONDS = 3600          # Zoho access tokens last for 1 hour.
TOKEN_RENEW_GRACE_SECONDS = 10 * 60    # Refresh when less than 10 minutes remain.

ZOHO_DESK_BASE = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")
# Base URL for Zoho Desk API requests.
# rstrip("/") removes a trailing slash so we don't accidentally create URLs like "//api/v1/...".

PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "50"))
# Maximum number of pages to request from Zoho search (to avoid endless pagination).

PAGE_SIZE = int(os.getenv("PAGE_SIZE", "100"))
# How many tickets to request per page from Zoho.

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
# If set, we send alerts to Microsoft Teams via an incoming webhook.
# If blank, Teams posting is skipped.

# -----------------------------
# Helpers (small utility functions)
# -----------------------------

def env(name: str) -> str:
    """
    Read a required environment variable.

    Lay-person explanation:
    - Environment variables are "settings" provided outside the script (often in a .env file).
    - If a required setting is missing, the script cannot run properly.
    - This function forces the script to fail early with a clear message.

    Args:
        name: The environment variable name (like "SMTP_HOST").

    Returns:
        The string value of that environment variable.

    Raises:
        RuntimeError: If the variable is missing or empty.
    """
    v = os.getenv(name)  # Read the environment variable value.
    if not v:  # If it doesn't exist or is empty...
        raise RuntimeError(f"Missing env var: {name}")  # Stop and explain what's missing.
    return v  # Return the value if it exists.

def iso_zoho(dt_any: datetime) -> str:
    """
    Convert a datetime into Zoho's time format for search ranges.

    Lay-person explanation:
    - Zoho wants a specific timestamp format like: 2026-02-19T10:30:00.000Z
    - The "Z" means UTC time.
    - We do the time window in Los Angeles time (for business logic),
      but we send UTC to Zoho to avoid certain Zoho errors.

    Args:
        dt_any: A datetime object (may or may not already have timezone info).

    Returns:
        A string formatted as UTC with ".000Z" at the end.
    """
    if dt_any.tzinfo is None:  # If there is no timezone info attached...
        dt_any = LA_TZ.localize(dt_any)  # Assume it's Los Angeles time and "attach" that timezone.
    dt_utc = dt_any.astimezone(pytz.UTC)  # Convert the time to UTC.
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")  # Format in Zoho-friendly UTC string.

def now_la() -> datetime:
    """
    Get the current time in Los Angeles timezone.

    Returns:
        Current datetime with LA timezone.
    """
    return datetime.now(LA_TZ)  # Get "now" in LA time.

def parse_zoho_time_assume_la(s: str) -> datetime:
    """
    Parse a Zoho datetime string, returning a datetime in Los Angeles time.

    Lay-person explanation:
    - Zoho returns createdTime as a text string.
    - Sometimes the string includes a timezone (like "...Z" for UTC),
      and sometimes it might not.
    - This function tries to interpret it safely and always returns LA time.

    Args:
        s: The datetime string from Zoho (e.g., "2026-02-19T12:34:56.000Z").

    Returns:
        A datetime object converted to Los Angeles time.

    Raises:
        ValueError: If the string is empty or in an unknown format.
    """
    if not s:  # If the string is empty...
        raise ValueError("Empty datetime string")  # Stop with a clear error.

    # Handle timestamps that end with "Z" which indicates UTC time.
    try:  # Try the most common parsing approach first.
        if s.endswith("Z"):  # If Zoho returned a UTC timestamp...
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))  # Convert "Z" into "+00:00" for Python parser.
            return dt.astimezone(LA_TZ)  # Convert from UTC into Los Angeles time.

        dt = datetime.fromisoformat(s)  # Parse normal ISO time strings.
        if dt.tzinfo is None:  # If Zoho did not include timezone info...
            return LA_TZ.localize(dt)  # Assume it is LA time and attach LA timezone.
        return dt.astimezone(LA_TZ)  # If it has timezone info, convert to LA time.
    except Exception:
        # Fallback for timestamps like "...-0800" (timezone without a colon).
        try:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")  # Parse using an explicit format.
            return dt.astimezone(LA_TZ)  # Convert into LA time.
        except Exception as e:  # If even the fallback failed...
            raise ValueError(f"Unrecognized Zoho datetime: {s!r}") from e  # Raise a clear error message.

def created_time_range_la(hours: int) -> str:
    """
    Create a Zoho search "createdTimeRange" string for the last N hours.

    Lay-person explanation:
    - We choose a start time and end time in LA time.
    - Then we format both times in UTC Z format for Zoho.
    - Zoho expects it as "start,end".

    Args:
        hours: How many hours back to look.

    Returns:
        A string like "startUTC,endUTC".
    """
    end_local =   now_la()  # End of window = current LA time.
    start_local = end_local - timedelta(hours=hours)  # Start of window = now minus N hours.
    return f"{iso_zoho(start_local)},{iso_zoho(end_local)}"  # Format both and join with comma.

def get_access_token() -> str:
    """
    Get a Zoho access token using a refresh token, with caching.

    Lay-person explanation:
    - Zoho uses OAuth tokens.
    - A refresh token is long-lived and can be exchanged for a short-lived access token.
    - We need an access token to call Zoho Desk APIs.
    - We cache the short-lived token and reuse it until ~10 minutes before expiry.

    Returns:
        Access token string.

    Raises:
        requests.HTTPError: If Zoho returns an error.
        KeyError: If the response does not contain "access_token".
    """
    now_utc = datetime.now(timezone.utc)  # Use timezone-aware UTC to avoid deprecation warnings.

    # Reuse the cached token if it is still safely valid.
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expires_at"]:
        # Renew when less than TOKEN_RENEW_GRACE_SECONDS remain.
        remaining = TOKEN_CACHE["expires_at"] - now_utc
        if remaining > timedelta(seconds=TOKEN_RENEW_GRACE_SECONDS):
            # Log how long the cached token remains valid.
            print(
                f"Reusing cached Zoho access token (expires in {remaining.total_seconds() / 60:.1f} minutes)."
            )
            return TOKEN_CACHE["token"]

    # Otherwise, fetch a fresh token using the long-lived refresh token.
    r = requests.post(
        ZOHO_ACCOUNTS_TOKEN_URL,  # The token endpoint URL.
        data={
            "refresh_token": env("ZOHO_REFRESH_TOKEN"),  # Required: the refresh token.
            "client_id":     env("ZOHO_CLIENT_ID"),      # Required: your Zoho client ID.
            "client_secret": env("ZOHO_CLIENT_SECRET"),  # Required: your Zoho client secret.
            "grant_type":        "refresh_token",        # Tells Zoho we are refreshing.
        },
        timeout=30,  # Safety: don't hang forever if network is stuck.
    )
    r.raise_for_status()  # If HTTP status is 4xx/5xx, raise an exception.
    token = r.json()["access_token"]  # Extract the access token from the JSON response.

    # Store token metadata so we can reuse it until close to expiry.
    created_at = now_utc
    expires_at = created_at + timedelta(seconds=TOKEN_LIFETIME_SECONDS)
    TOKEN_CACHE.update({"token": token, "created_at": created_at, "expires_at": expires_at})

    # Log the new token lifetime for visibility.
    print(
        f"Fetched new Zoho access token (valid for {(TOKEN_LIFETIME_SECONDS / 60):.0f} minutes)."
    )

    return token

def desk_headers(token: str) -> Dict[str, str]:
    """
    Build the HTTP headers needed for Zoho Desk API calls.

    Lay-person explanation:
    - APIs often require special headers for authentication and identification.
    - We provide the access token and the organization ID.

    Args:
        token: The Zoho OAuth access token.

    Returns:
        Dictionary of HTTP headers.
    """
    return {
        "Authorization": f"Zoho-oauthtoken {token}",  # Auth header Zoho expects.
        "orgId":         env("ZOHO_DESK_ORG_ID"),  # Organization ID in Zoho Desk.
        "Accept":        "application/json",  # Ask for JSON responses.
    }

# # -----------------------------
# # "Seen tickets" state functions (kept for documentation; not used in runtime flow)
# # -----------------------------

# STATE_FILE = os.getenv("STATE_FILE", "seen_superstat_ticket_ids.json")
# # The filename where we store ticket IDs we've "seen" before.
# # If the environment variable STATE_FILE is not set, we use the default file name shown above.

# def load_seen() -> set:
#     """
#     Load the "seen tickets" set from disk.

#     Lay-person explanation:
#     - We store ticket IDs in a JSON file so we can remember them between runs.
#     - If the file doesn't exist or is broken, we fall back to an empty set.

#     Returns:
#         A set of ticket IDs (strings).
#     """
#     if not os.path.exists(STATE_FILE):  # If the file doesn't exist...
#         return set()  # Return an empty set (meaning we haven't seen anything).
#     try:
#         with open(STATE_FILE, "r", encoding="utf-8") as f:  # Open the file for reading.
#             data = json.load(f)  # Load JSON from file.
#         return set(data) if isinstance(data, list) else set()  # Convert list -> set; otherwise empty set.
#     except Exception:
#         return set()  # If file is corrupted or unreadable, ignore and start fresh.

# def save_seen(seen: set) -> None:
#     """
#     Save the "seen tickets" set to disk.

#     Lay-person explanation:
#     - Sets are not directly JSON serializable in the way we want, so we convert to a list.
#     - We sort it so the file stays stable and readable.

#     Args:
#         seen: Set of ticket IDs to store.
#     """
#     with open(STATE_FILE, "w", encoding="utf-8") as f:  # Open the file for writing (overwrites existing file).
#         json.dump(sorted(list(seen)), f, indent=2)  # Save sorted IDs in pretty JSON format.

def parse_smtp_to(raw: str) -> List[str]:
    """
    Convert a string of email recipients into a list.

    Lay-person explanation:
    - Some people write multiple emails separated by commas or semicolons.
    - This function splits by comma or semicolon and cleans whitespace.

    Args:
        raw: A string like "a@x.com, b@y.com; c@z.com"

    Returns:
        List of email addresses.
    """
    parts = re.split(r"[;,]\s*", raw.strip())  # Split by comma/semicolon with optional spaces.
    return [p.strip() for p in parts if p.strip()]  # Remove blanks and trim spaces.

def send_email(subject: str, body: str) -> None:
    """
    Send a plain-text email using SMTP.

    Lay-person explanation:
    - SMTP is a standard way to send email programmatically.
    - We connect to an email server (SMTP_HOST/SMTP_PORT),
      authenticate (username/password),
      and then send the message.

    Args:
        subject: The email subject line.
        body: The email body content (plain text).

    Raises:
        RuntimeError: If required env vars are missing (via env()).
        smtplib.SMTPException: If sending fails.
    """
    smtp_host = env("SMTP_HOST")  # Read SMTP server hostname.
    smtp_port = int(env("SMTP_PORT"))  # Read SMTP server port and convert to int.
    smtp_user = env("SMTP_USERNAME")  # Read SMTP login username.
    smtp_pass = env("SMTP_PASSWORD")  # Read SMTP login password.

    to_list   = parse_smtp_to(env("SMTP_TO"))  # Read recipients and parse into a list.
    from_addr = env("SMTP_FROM")  # Read sender email address.

    msg = EmailMessage()  # Create an email object.
    msg["Subject"] = subject  # Set email subject.
    msg["From"] = from_addr  # Set sender.
    msg["To"] = ", ".join(to_list)  # Set recipients as a comma-separated string.
    msg.set_content(body)  # Set the email body as plain text.

    context = ssl.create_default_context(cafile=certifi.where())

    if smtp_port == 465:  # Port 465 usually means "implicit SSL" (connect already encrypted).
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as s:  # Open encrypted SMTP connection.
            s.login(smtp_user, smtp_pass)  # Log in to the SMTP server.
            s.send_message(msg)  # Send the email message.
    else:  # Other ports often use STARTTLS (upgrade to TLS after connecting).
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:  # Open normal SMTP connection.
            s.ehlo()  # Say hello to server (negotiation step).
            s.starttls(context=context)  # Upgrade the connection to encrypted TLS.
            s.ehlo()  # Say hello again after TLS (best practice).
            s.login(smtp_user, smtp_pass)  # Log in.
            s.send_message(msg)  # Send the email message.

def post_to_teams(webhook_url: str, payload: Dict[str, Any]) -> None:
    """
    Post an Adaptive Card payload to a Teams Incoming Webhook.

    Lay-person explanation:
    - Microsoft Teams can accept messages via a special URL called a "webhook".
    - We send a JSON payload that defines a rich card (Adaptive Card).

    Args:
        webhook_url: The Teams incoming webhook URL.
        payload: A dictionary that will be sent as JSON.

    Raises:
        requests.HTTPError: If Teams responds with an error status.
    """
    r = requests.post(webhook_url, json=payload, timeout=30)  # Send a POST request with JSON body.
    if r.status_code >= 400:                                  # If Teams returned an error...
        print("TEAMS WEBHOOK ERROR", r.status_code)           # Print the status code for debugging.
        print("Teams response body:", (r.text or "")[:2000])  # Print up to 2000 chars of response for debugging.
    r.raise_for_status()                                      # Raise an exception for non-success status codes.

def format_email_body(
    *,
    ticket_id: str,
    ticket_number: str,
    subject_line: str,
    status: str,
    status_type: str,
    created_display: str,
    age_minutes: int,
    web_url: str,
    reason: str,
) -> str:
    """
    Build a neat, readable plain-text email body.

    Lay-person explanation:
    - We create a consistent, easy-to-scan email message.
    - We show key details (number, status, age, URL, etc.).
    - The "reason" explains why this ticket triggered the alert.

    Returns:
        A single plain-text string to use as the email body.
    """
    lines = []  # Start with an empty list of text lines (we'll join them at the end).
    lines.append("SUPER-STAT REMINDER (Automated, sent from dev script)")  # Add title line.
    lines.append("-" * 72)  # Add a divider line.
    lines.append("This ticket is still NOT resolved and matched the alert rules.")  # Explain why email exists.
    lines.append(f"Matched because: {reason}")  # Explain which rule was matched.
    lines.append("")  # Blank line for readability.
    lines.append("Ticket Details")  # Section header.
    lines.append("-" * 72)  # Divider line under header.

    fields = [
        ("Ticket Number", ticket_number),
        ("Ticket ID", ticket_id),
        ("Subject", subject_line),
        ("Status", status),
        ("Status Type", status_type),
        ("Created (LA)", created_display),
        ("Age (minutes)", str(age_minutes)),
        ("URL", web_url),
    ]
    # This list holds the "label" and "value" pairs we want to print in the email.

    label_width = max(len(k) for k, _ in fields)  # Find the longest label length for alignment.
    for k, v in fields:  # Loop over each label/value pair...
        lines.append(f"{k:<{label_width}} : {v}")  # Add an aligned line like "Status : Pending".

    lines.append("")  # Add blank line at end of details.
    lines.append("-" * 72)  # Final divider line.
    lines.append("If you believe you received this in error, please ignore.")  # Closing note.
    return "\n".join(lines)  # Join all lines with newline characters into one string.

def build_teams_adaptive_card(
    *,
    title:           str,
    summary:         str,
    ticket_number:   str,
    ticket_id:       str,
    subject_line:    str,
    status:          str,
    status_type:     str,
    created_display: str,
    age_minutes:     int,
    reason:          str,
    web_url:         str,
) -> Dict[str, Any]:
    """
    Build the JSON payload for a Microsoft Teams Adaptive Card message.

    Lay-person explanation:
    - An Adaptive Card is a structured message format used by Teams.
    - We include text blocks and a fact list (key/value details).
    - We also add a button that opens the ticket URL.

    Returns:
        A dict ready to send as JSON to Teams webhook.
    """
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",  # Card schema reference.
        "type":    "AdaptiveCard",  # Tells Teams: this is an adaptive card.
        "version": "1.4",  # Card version.
        "body": [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},  # Main title.
            {"type": "TextBlock", "text": summary, "wrap": True, "spacing": "Small"},  # Short summary.
            {"type": "TextBlock", "text": f"Matched because: {reason}", "wrap": True, "spacing": "Small"},  # Match reason.
            {
                "type": "FactSet",  # A neat list of facts (label/value pairs).
                "facts": [
                    {"title": "Ticket Number", "value": str(ticket_number)},  # Ticket number.
                    {"title": "Ticket ID", "value": str(ticket_id)},  # Ticket ID.
                    {"title": "Subject", "value": subject_line or "(none)"},  # Subject (or placeholder).
                    {"title": "Status", "value": status or "(none)"},  # Status (or placeholder).
                    {"title": "Status Type", "value": status_type or "(none)"},  # Status type (or placeholder).
                    {"title": "Created (LA)", "value": created_display or "(unknown)"},  # Created time.
                    {"title": "Age (minutes)", "value": str(age_minutes)},  # Age in minutes.
                ],
            },
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "Open Ticket", "url": web_url}  # Button to open ticket.
        ],
    }

    return {
        "type": "message",  # Message wrapper used by Teams webhook.
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",  # Tells Teams what's attached.
                "content": card,  # The actual card content.
            }
        ],
    }

# -----------------------------
# Zoho Desk calls (talking to Zoho)
# -----------------------------

def search_tickets(token: str, statuses: List[str], hours: int) -> List[Dict[str, Any]]:
    """
    Search Zoho Desk tickets using server-side filters.

    Lay-person explanation:
    - Instead of downloading every ticket, we ask Zoho to only return:
      1) Tickets with certain statuses (active statuses),
      2) Tickets created in the last N hours.
    - We also try to sort newest-first.
    - Some Zoho data centers reject sortBy for this endpoint, so we retry without it.

    Args:
        token:    Access token for Zoho Desk API.
        statuses: List of statuses we want (e.g., ["Assigned", "Pending"]).
        hours:    How many hours back to search.

    Returns:
        A list of ticket "rows" from the search endpoint.
    """
    url            =  f"{ZOHO_DESK_BASE}/api/v1/tickets/search"  # Build the search endpoint URL.
    statuses_param =  ",".join(statuses)                         # Zoho expects statuses as a comma-separated string.

    out: List[Dict[str, Any]] = []    # This list will hold all tickets we collect across pages.
    use_sort                  = True  # We'll try using sortBy first; if Zoho rejects it we will disable it.

    for page_idx in range(PAGE_LIMIT):  # Loop over pages up to a maximum count.
        start = page_idx * PAGE_SIZE    # Compute the offset for pagination.
        params = {
            "status":           statuses_param,                # Filter by active statuses.
            "createdTimeRange": created_time_range_la(hours),  # Filter by created time window.
            "from":  start,                                    # Pagination start index.
            "limit": PAGE_SIZE,                                # How many items in one page.
        }
        if use_sort:  # If sorting is enabled...
            params["sortBy"] = "-createdTime"  # Ask for descending sort (newest first).

        r = requests.get(url, headers=desk_headers(token), params=params, timeout=30)  # Call Zoho search API.

        if r.status_code == 422 and use_sort:  # If Zoho says "unprocessable entity" because of sortBy...
            use_sort = False  # Turn off sortBy.
            continue  # Try again on the same page without sortBy.

        if r.status_code >= 400:  # If any other HTTP error happened...
            print("HTTP ERROR",     r.status_code,        "for",  r.url)  # Print error details.
            print("Response body:", (r.text or "")[:2000])  # Print response body snippet for debugging.
        r.raise_for_status()  # Stop the program if the request failed.

        data = r.json().get("data", []) or []  # Pull "data" field from JSON (list of tickets).
        if not data:  # If Zoho returned no tickets...
            break  # Stop pagination.

        out.extend(data)  # Add this page's tickets to our output list.

        if len(data) < PAGE_SIZE:  # If Zoho returned less than a full page...
            break  # Then there are no more pages.

    out.sort(key=lambda t: t.get("createdTime") or "", reverse=True)  # Sort tickets newest-first as a safety step.
    return out  # Return the list of tickets.


# -----------------------------
# Matching logic (deciding if a ticket should alert)
# -----------------------------

def is_unresolved(ticket: Dict[str, Any]) -> bool:
    """
    Decide if a ticket is still unresolved/open.

    Lay-person explanation:
    - A ticket can be considered "done" if status == "Resolved" or statusType == "Closed".
    - Anything else is considered still open for the purposes of alerts.

    Args:
        ticket: Ticket details dictionary.

    Returns:
        True if ticket is NOT resolved/closed, otherwise False.
    """
    status      = (ticket.get("status") or "").strip()  # Read status string safely and remove extra spaces.
    status_type = (ticket.get("statusType") or "").strip().lower()  # Read statusType safely and normalize to lowercase.
    if status.lower() == "resolved":  # If status literally says resolved...
        return False  # Treat it as resolved.
    if status_type == "closed":  # If statusType indicates closed...
        return False  # Treat it as resolved/closed.
    return True  # Otherwise treat it as unresolved.

def subject_matches(ticket: Dict[str, Any]) -> bool:
    """
    Check whether a ticket subject contains the keyword pattern.

    Lay-person explanation:
    - We look for the KEYWORD_REGEX pattern in the subject line.

    Args:
        ticket: Ticket dictionary (can be search row or details).

    Returns:
        True if regex matches subject, else False.
    """
    subj = ticket.get("subject") or ""  # Get subject; if missing, use empty string.
    return bool(KEYWORD_RE.search(subj))  # True if keyword pattern is found.

def description_matches(details: Dict[str, Any]) -> bool:
    """
    Check whether a ticket description contains the keyword pattern.

    Lay-person explanation:
    - Some tickets include the main text in "lesp    cription" or "descriptionText".
    - We check both, then search for the keyword regex.

    Args:
        details: Full ticket details.

    Returns:
        True if regex matches description, else False.
    """
    desc = details.get("description") or details.get("descriptionText") or ""  # Pick first available description field.
    return bool(KEYWORD_RE.search(desc))  # Return True if keyword pattern is found.

def product_matches(details: Dict[str, Any]) -> bool:
    """
    Check whether a ticket's product name matches any target product names.

    Lay-person explanation:
    - If TARGET_PRODUCT_NAMES is empty, product matching is disabled.
    - Otherwise, we look for product fields in the ticket details and compare them.
    - Comparison is case-insensitive.

    Args:
        details: Full ticket details.

    Returns:
        True if ticket product matches one of TARGET_PRODUCT_NAMES.
    """
    if not TARGET_PRODUCT_NAMES:  # If no target products were configured...
        return False  # We cannot match by product.

    candidates: List[str] = []  # We'll store possible product name strings here.

    for k in ("productName", "product"):  # Check both common keys.
        v = details.get(k)  # Read the value under this key.
        if isinstance(v, str) and v.strip():  # If it's a non-empty string...
            candidates.append(v.strip())  # Add it as a candidate.
        elif isinstance(v, dict):  # If it's a dictionary object...
            for kk in ("name", "productName"):  # Try common sub-keys inside it.
                vv = v.get(kk)  # Read the nested value.
                if isinstance(vv, str) and vv.strip():  # If it is a non-empty string...
                    candidates.append(vv.strip())  # Add it as a candidate.

    for name in candidates:  # Go through all candidate product names...
        if name.lower() in TARGET_PRODUCT_NAMES:  # Compare lowercase for case-insensitive match...
            return True  # Found a match.
    return False  # No match found.

def older_than_min_age(details: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Check if a ticket is old enough to alert (not too new).

    Lay-person explanation:
    - We don't want to alert immediately when a ticket is just created.
    - So we check the created time and ensure it is at least MIN_AGE_MINUTES old.

    Args:
        details: Full ticket details (must contain createdTime).

    Returns:
        (ok, reason)
        - ok: True if ticket is old enough, False otherwise.
        - reason: Explanation string for logs/emails.
    """

    created_raw = details.get("createdTime") or ""  # Read createdTime safely.
    if not created_raw:  # If createdTime is missing...
        return False, "missing createdTime"  # Cannot verify age.

    created_la = parse_zoho_time_assume_la(created_raw)  # Parse created time and convert to LA time.
    age = now_la() - created_la  # Compute how old the ticket is.

    if age < timedelta(minutes=MIN_AGE_MINUTES):  # If ticket age is less than minimum threshold...
        mins = max(0, int(age.total_seconds() // 60))  # Compute age in minutes (floor), never negative.
        return False, f"too new ({mins}m old)"  # Not old enough to alert.

    return True, f"age ok ({int(age.total_seconds() // 60)}m old)"  # Old enough; return a helpful message.

def should_alert(search_row: Dict[str, Any], details: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Decide whether we should send an alert for a ticket.

    Lay-person explanation:
    - First, we confirm the ticket is still unresolved.
    - Then we check the matching rules in order:
      1) Product match (if enabled)
      2) Subject keyword match
      3) Description keyword match
    - For any match, we also check that the ticket is older than MIN_AGE_MINUTES.

    Args:
        search_row: The ticket object from the search API results.
        details: The full ticket details fetched by ID.

    Returns:
        (should_alert, reason)
        - should_alert: True if we should send an alert.
        - reason: Human-readable explanation of why/why not.
    """
    if not is_unresolved(details):  # If ticket is resolved/closed...
        return False, "resolved/closed"  # Do not alert.

    if product_matches(details):  # If product matches the target list...
        ok_age, age_reason = older_than_min_age(details)  # Check minimum age.
        return ok_age, f"product match; {age_reason}"  # Alert only if age is ok.

    if subject_matches(search_row) or subject_matches(details):  # Check keyword in subject (search or details)...
        ok_age, age_reason = older_than_min_age(details)  # Check minimum age.
        return ok_age, f"subject keyword match; {age_reason}"  # Alert only if age is ok.

    if description_matches(details):  # Check keyword in description...
        ok_age, age_reason = older_than_min_age(details)  # Check minimum age.
        return ok_age, f"description keyword match; {age_reason}"  # Alert only if age is ok.

    return False, "no match"  # Nothing matched, so do not alert.

# -----------------------------
# Main loop (the program that runs forever)
# -----------------------------

def main_loop() -> None:
    """
    Run the monitoring loop forever.

    Lay-person explanation:
    - This function prints the configuration.
    - Then it enters an infinite loop:
      1) Get Zoho access token
      2) Search tickets in active statuses and recent time window
      3) For each ticket, fetch details and decide whether to alert
      4) Send email (and Teams message if enabled)
      5) Clean up the "seen" list so it doesn't grow forever
      6) Sleep until next run
    """
    print(f"Timezone: {TZ_NAME}")  # Print timezone setting.
    print(f"Watching statuses: {', '.join(sorted(ACTIVE_STATUSES))}")  # Print active statuses being watched.
    print(f"Search window: last {MAX_AGE_HOURS} hours via createdTimeRange (LA window -> UTC Z for Zoho)")  # Print age window.
    print(f"Minimum age before alert: {MIN_AGE_MINUTES} minutes")  # Print min age threshold.
    print(f"Keyword regex: {KEYWORD_REGEX}")  # Print keyword regex.
    print(f"Target products: {', '.join(TARGET_PRODUCT_NAMES) if TARGET_PRODUCT_NAMES else '(none)'}")  # Print product list.
    print(f"Interval: {CHECK_EVERY_SECONDS} seconds")  # Print polling interval.
    # print(f"State file: {STATE_FILE}")  # Print state file path.
    print(f"Teams webhook: {'enabled' if TEAMS_WEBHOOK_URL else 'disabled'}\n")  # Print whether Teams is enabled.

    # NOTE (plain English):
    # We are NOT using the seen-state file mechanism in the runtime loop right now.
    # We are keeping all original comments and documentation, but we are removing the
    # runtime dependency on "seen", "still_open", "cleared", and CLEAN_SEEN cleanup.

    while True:  # Infinite loop: script will run until you stop it.
        try:  # Catch errors so one failure doesn't kill the loop.
            loop_started_at = datetime.now(timezone.utc)  # Track loop start time for debugging.
            print(f"[loop] Starting cycle at {loop_started_at.isoformat()}")

            token = get_access_token()  # Get a fresh Zoho access token.

            tickets = search_tickets(token, statuses=sorted(ACTIVE_STATUSES), hours=MAX_AGE_HOURS)  # Search recent active tickets.
            print(f"Fetched {len(tickets)} ticket(s) from search endpoint.")  # Log how many were found.
            # DEBUG: Save raw search response locally for inspection. Comment out when not needed.
            debug_dump_path = f"search_results_{int(time.time())}.json"
            with open(debug_dump_path, "w", encoding="utf-8") as f:
                json.dump(tickets, f, indent=2)
            print(f"Saved raw search results to {debug_dump_path}")

            hits = 0  # Count how many alerts we send in this run.

            for row in tickets:  # Process each ticket returned by the search.
                tid = row.get("id")  # Extract ticket ID.
                if not tid:  # If ticket has no ID for some reason...
                    continue  # Skip it because we cannot fetch details without an ID.

                row_status = (row.get("status") or "").strip()  # Read the status from search row.
                if row_status and row_status not in ACTIVE_STATUSES:  # If status isn't one we care about...
                    continue  # Skip it.

                # We already have all needed fields from the search payload, so avoid an extra API call.
                details = row  # Use search row as "details" to keep downstream logic unchanged.

                should, reason = should_alert(row, details)  # Decide if we should alert and why.
                if not should:  # If we should NOT alert...
                    continue  # Move on to next ticket.

                # CHANGE (explained in plain English):
                # We do NOT skip tickets that are already in "seen".
                # That means if the ticket is still matching, we will alert EVERY run.

                hits += 1  # Increase the count of alerts we are sending.

                ticket_number = str(details.get("ticketNumber", "") or "")  # Get ticket number for display.
                web_url = details.get("webUrl", "") or row.get("webUrl", "") or ""  # Try details first, then search row.
                subject_line = details.get("subject", "") or row.get("subject", "") or ""  # Try details first, then search row.

                created_raw = details.get("createdTime", "")  # Get ticket created time as raw string.
                try:
                    created_la = parse_zoho_time_assume_la(created_raw)  # Parse created time, convert to LA.
                    age_minutes = int((now_la() - created_la).total_seconds() // 60)  # Compute age in minutes.
                    created_display = created_la.strftime("%Y-%m-%d %H:%M:%S %Z")  # Format time nicely for display.
                except Exception:
                    age_minutes = -1  # Use -1 to indicate unknown age.
                    created_display = created_raw or "(unknown)"  # Fall back to raw string or placeholder.

                email_subject = f"[Super-STAT REMINDER] Ticket {ticket_number} still NOT resolved"
                # Create a clear subject line for the email reminder.

                email_body = format_email_body(
                    ticket_id=str(tid),  # Ticket ID.
                    ticket_number=ticket_number,  # Ticket number.
                    subject_line=subject_line,  # Ticket subject.
                    status=str(details.get("status", "") or ""),  # Ticket status.
                    status_type=str(details.get("statusType", "") or ""),  # Ticket status type.
                    created_display=created_display,  # Created time in LA format.
                    age_minutes=age_minutes,  # Age in minutes.
                    web_url=web_url,  # Link to the ticket.
                    reason=reason,  # Explanation of match.
                )
                # The above block builds the entire email body in a neat format.

                print(f"ALERT: Ticket {ticket_number} ({tid}) -> emailing... reason={reason}")  # Log alert action.
                send_email(email_subject, email_body)  # Send the email reminder.

                if TEAMS_WEBHOOK_URL:  # Only do Teams posting if webhook URL is configured.
                    title = "SUPER-STAT REMINDER (Automated, sent from dev script)"  # Card title.
                    summary = f"Ticket {ticket_number} is still NOT resolved."  # Short summary line.
                    teams_payload = build_teams_adaptive_card(
                        title=title,  # Card title.
                        summary=summary,  # Card summary.
                        ticket_number=ticket_number,  # Ticket number.
                        ticket_id=str(tid),  # Ticket ID.
                        subject_line=subject_line,  # Subject line.
                        status=str(details.get("status", "") or ""),  # Status.
                        status_type=str(details.get("statusType", "") or ""),  # Status type.
                        created_display=created_display,  # Created time display.
                        age_minutes=age_minutes,  # Age.
                        reason=reason,  # Why this matched.
                        web_url=web_url,  # Link to ticket.
                    )
                    # The above builds the Teams Adaptive Card JSON.

                    print(f"ALERT: Ticket {ticket_number} ({tid}) -> posting to Teams...")  # Log Teams action.
                    post_to_teams(TEAMS_WEBHOOK_URL, teams_payload)  # Post card to Teams.

            # Cleanup seen list so it doesn't grow forever (keep only still-open tickets from this run)
            if os.getenv("CLEAN_SEEN", "1").strip() == "1":  # If CLEAN_SEEN is enabled (default yes)...
                before = 0  # Count IDs before cleanup.
                after = 0  # Count IDs after cleanup.
                if after != before:  # If something changed...
                    print(f"Cleaned seen set: {before} -> {after}")  # Log the cleanup.

            # save_seen(set())  # Save the updated seen set to disk.

            if hits == 0:  # If we did not alert on any tickets this run...
                print("No NEW matching unresolved tickets found.")  # Note: wording says "NEW" but alerts can repeat.
            else:
                print(f"Sent {hits} reminder email(s) (+ Teams if enabled).")  # Log alert count.

        except Exception as e:  # Catch any error from the entire loop iteration...
            print("ERROR:", repr(e))  # Print the error so we know what went wrong.

        print(f"[loop] Sleeping for {CHECK_EVERY_SECONDS} seconds...\n")
        time.sleep(CHECK_EVERY_SECONDS)  # Wait before checking again.

if __name__ == "__main__":
    # This means: "If this file is being run directly (not imported), start the main loop."
    main_loop()  # Start the monitoring script.
