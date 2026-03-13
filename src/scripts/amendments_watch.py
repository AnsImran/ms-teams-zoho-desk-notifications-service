"""Product-specific watcher settings for AMENDMENTS (simple, layperson style)."""  # Describe what this file is about.

import os  # Read environment variables for product-specific overrides.

from src.core.watch_helper import (   # Pull shared helpers so we do not duplicate logic.
    ProductConfig,            # Data holder for product knobs.
    MAX_AGE_HOURS_DEFAULT,    # Shared default lookback hours.
    MIN_AGE_MINUTES_DEFAULT,  # Shared default minimum age.
    run_product_loop_once,    # Helper that runs one full cycle.
    get_access_token,         # Helper that fetches Zoho token when running this file alone.
    delete_cooldown_file,     # Helper that clears the cooldown file on startup.
)                             # End of imported helpers list.

# Build AMENDMENTS specific settings from environment with friendly defaults.
AMENDMENTS_ACTIVE_STATUSES = {status.strip() for status in os.getenv("AMENDMENTS_ACTIVE_STATUSES", os.getenv("ACTIVE_STATUSES", "Assigned,Pending,Escalated")).split(",") if status.strip()}  # Statuses we treat as open.
AMENDMENTS_TARGET_PRODUCTS = [name.strip().lower() for name in os.getenv("AMENDMENTS_TARGET_PRODUCT_NAMES", os.getenv("TARGET_PRODUCT_NAMES", "")).split(",") if name.strip()]                # Product names we match exactly.
AMENDMENTS_KEYWORD_REGEX   = os.getenv("AMENDMENTS_KEYWORD_REGEX", os.getenv("KEYWORD_REGEX",  r"\\bamendments\\b")).replace("\\\\", "\\")                                               # Regex that finds AMENDMENTS mentions, unescaped.

# Create the ProductConfig object used by the helper.
AMENDMENTS_CONFIG = ProductConfig(                                                                 # Package all AMENDMENTS settings together.
    name                  = "Amendments",                                                          # Friendly label for logs and cards.
    keyword_regex         = AMENDMENTS_KEYWORD_REGEX,                                              # Regex for keyword match.
    target_product_names  = AMENDMENTS_TARGET_PRODUCTS,                                            # Exact product names to match (lower-case).
    active_statuses       = AMENDMENTS_ACTIVE_STATUSES,                                            # Statuses considered open.
    teams_webhook_env_var = "TEAMS_WEBHOOK_AMENDMENTS",                                            # Env var that stores the Teams webhook for this product.
    last_sent_filename    = "sent_amendments_notifications.json",                                  # File where cooldown data is stored for this product.
    max_age_hours         = int(os.getenv("AMENDMENTS_MAX_AGE_HOURS",   MAX_AGE_HOURS_DEFAULT)),     # Lookback hours (override or default).
    min_age_minutes       = int(os.getenv("AMENDMENTS_MIN_AGE_MINUTES", MIN_AGE_MINUTES_DEFAULT)), # Minimum age before alert.
)                                                                                                  # Finished building AMENDMENTS config.


def run_cycle(token: str, pre_fetched_tickets=None) -> None:                                 # Run one AMENDMENTS watch cycle using a shared token and optional tickets.
    """Run one pass of the AMENDMENTS watcher with a provided Zoho token."""                 # Docstring in simple terms.
    run_product_loop_once(AMENDMENTS_CONFIG, token, pre_fetched_tickets=pre_fetched_tickets)  # Delegate all heavy lifting to the shared helper.


if __name__ == "__main__":                   # Allow this file to be run directly for quick testing.
    delete_cooldown_file(AMENDMENTS_CONFIG)  # Clear cooldown history so startup mimics old behavior.
    shared_token = get_access_token()        # Grab or reuse a Zoho token.
    run_cycle(shared_token)                  # Run a single AMENDMENTS cycle with that token.
