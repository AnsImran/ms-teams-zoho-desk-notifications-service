"""Product-specific watcher settings for Code Stroke (kept simple and clear)."""  # Explain the file in one line.

import os  # Read product-specific environment overrides.

from src.core.watch_helper import (   # Import shared helpers so logic stays in one place.
    ProductConfig,            # Data holder for product options.
    MAX_AGE_HOURS_DEFAULT,    # Shared default lookback hours.
    MIN_AGE_MINUTES_DEFAULT,  # Shared default minimum age.
    run_product_loop_once,    # Helper that executes one cycle.
    get_access_token,         # Helper to fetch Zoho token when running directly.
    delete_cooldown_file,     # Helper that clears the cooldown file on startup.
)                             # End helper imports.

# Build Code Stroke settings, falling back to shared defaults when needed.
CODE_STROKE_ACTIVE_STATUSES = {status.strip() for status in os.getenv("CODE_STROKE_ACTIVE_STATUSES", os.getenv("ACTIVE_STATUSES", "Assigned,Pending,Escalated")).split(",") if status.strip()}  # Statuses treated as open.
CODE_STROKE_TARGET_PRODUCTS = [name.strip().lower() for name in os.getenv("CODE_STROKE_TARGET_PRODUCT_NAMES", "").split(",") if name.strip()]  # Product names to match (lower-case).
CODE_STROKE_KEYWORD_REGEX   = os.getenv("CODE_STROKE_KEYWORD_REGEX", r"\\bcode[\\s-]?stroke\\b").replace("\\\\", "\\")    # Regex that spots Code Stroke wording, unescaped.

# Create the ProductConfig object for Code Stroke.
CODE_STROKE_CONFIG = ProductConfig(                                                                    # Bundle all Code Stroke settings together.
    name="Code Stroke",                                                                                # Friendly name for logs and cards.
    keyword_regex         = CODE_STROKE_KEYWORD_REGEX,                                                 # Regex pattern for this product.
    target_product_names  = CODE_STROKE_TARGET_PRODUCTS,                                               # Exact product names list.
    active_statuses       = CODE_STROKE_ACTIVE_STATUSES,                                               # Open statuses to watch.
    teams_webhook_env_var = "TEAMS_WEBHOOK_CODE_STROKE",                                               # Env var holding the Teams webhook URL.
    last_sent_filename    = "sent_code_stroke_notifications.json",                                     # Cooldown file name for this product.
    max_age_hours         = int(os.getenv("CODE_STROKE_MAX_AGE_HOURS", MAX_AGE_HOURS_DEFAULT)),        # Lookback window in hours.
    min_age_minutes       = int(os.getenv("CODE_STROKE_MIN_AGE_MINUTES", MIN_AGE_MINUTES_DEFAULT)),    # Minimum age before alert.
)                                                                                                      # Finished building Code Stroke config.


def run_cycle(token: str, pre_fetched_tickets=None) -> None:                                   # Run one Code Stroke watch cycle.
    """Run one pass of the Code Stroke watcher using the provided Zoho token."""               # Docstring in clear language.
    run_product_loop_once(CODE_STROKE_CONFIG, token, pre_fetched_tickets=pre_fetched_tickets)  # Delegate to the shared helper.


if __name__ == "__main__":                    # Let this module run directly for quick checks.
    delete_cooldown_file(CODE_STROKE_CONFIG)  # Clear cooldown history so startup mimics old behavior.
    shared_token = get_access_token()         # Fetch or reuse Zoho token.
    run_cycle(shared_token)                   # Execute one Code Stroke cycle.
