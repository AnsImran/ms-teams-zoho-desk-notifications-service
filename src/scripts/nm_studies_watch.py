"""Product-specific watcher settings for NM Studies (simple, layperson style)."""  # Describe what this file is about.

import os  # Read environment variables for product-specific overrides.

from src.core.watch_helper import (   # Pull shared helpers so we do not duplicate logic.
    ProductConfig,            # Data holder for product knobs.
    MAX_AGE_HOURS_DEFAULT,    # Shared default lookback hours.
    MIN_AGE_MINUTES_DEFAULT,  # Shared default minimum age.
    run_product_loop_once,    # Helper that runs one full cycle.
    get_access_token,         # Helper that fetches Zoho token when running this file alone.
    delete_cooldown_file,     # Helper that clears the cooldown file on startup.
)                             # End of imported helpers list.

# Build NM Studies specific settings from environment with friendly defaults.
NM_STUDIES_ACTIVE_STATUSES = {status.strip() for status in os.getenv("NM_STUDIES_ACTIVE_STATUSES", os.getenv("ACTIVE_STATUSES", "Assigned,Pending,Escalated")).split(",") if status.strip()}  # Statuses we treat as open.
NM_STUDIES_TARGET_PRODUCTS = [name.strip().lower() for name in os.getenv("NM_STUDIES_TARGET_PRODUCT_NAMES", "NM Studies").split(",") if name.strip()]                                                # Product names we match exactly.
NM_STUDIES_KEYWORD_REGEX   = os.getenv("NM_STUDIES_KEYWORD_REGEX", r"\\bnm[\\s/-]*studies\\b").replace("\\\\", "\\")                                                                                 # Regex that finds NM Studies mentions, unescaped.
NM_STUDIES_BANNER_TEXT     = os.getenv("NM_STUDIES_BANNER_TEXT", "Please verify whether any radiologist scheduled today is able to read this study. If none are available, notify the team immediately so we can secure a radiologist who can complete the read.").strip()  # top banner text.

 
# Create the ProductConfig object used by the helper.

NM_STUDIES_CONFIG = ProductConfig(                                                               # Package all NM Studies settings together.
    name                  = "NM Studies",                                                        # Friendly label for logs and cards.
    keyword_regex         = NM_STUDIES_KEYWORD_REGEX,                                            # Regex for keyword match.
    target_product_names  = NM_STUDIES_TARGET_PRODUCTS,                                          # Exact product names to match (lower-case).
    active_statuses       = NM_STUDIES_ACTIVE_STATUSES,                                          # Statuses considered open.
    teams_webhook_env_var = "TEAMS_WEBHOOK_NM_STUDIES",                                          # Env var that stores the Teams webhook for this product.
    last_sent_filename    = "sent_nm_studies_notifications.json",                                # File where cooldown data is stored for this product.
    max_age_hours         = int(os.getenv("NM_STUDIES_MAX_AGE_HOURS",   MAX_AGE_HOURS_DEFAULT)),    # Lookback hours (override or default).
    min_age_minutes       = int(os.getenv("NM_STUDIES_MIN_AGE_MINUTES", MIN_AGE_MINUTES_DEFAULT)),  # Minimum age before alert.
    card_banner_text      = NM_STUDIES_BANNER_TEXT,                                                 # Banner shown on NM STUDIES cards.
)                                                                                                 # Finished building NM Studies config.


def run_cycle(token: str, pre_fetched_tickets=None) -> None:                                   # Run one NM Studies watch cycle using a shared token and optional tickets.
    """Run one pass of the NM Studies watcher with a provided Zoho token."""                   # Docstring in simple terms.
    run_product_loop_once(NM_STUDIES_CONFIG, token, pre_fetched_tickets=pre_fetched_tickets)  # Delegate all heavy lifting to the shared helper.


if __name__ == "__main__":                   # Allow this file to be run directly for quick testing.
    delete_cooldown_file(NM_STUDIES_CONFIG)  # Clear cooldown history so startup mimics old behavior.
    shared_token = get_access_token()        # Grab or reuse a Zoho token.
    run_cycle(shared_token)                  # Run a single NM Studies cycle with that token.
