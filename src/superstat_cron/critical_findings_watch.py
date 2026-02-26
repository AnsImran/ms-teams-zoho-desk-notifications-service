"""Product-specific watcher settings for Critical Findings (same pattern as other products)."""  # Explain this file in one line.

import os  # Read product-specific environment overrides.

from .watch_helper import (  # Import shared helpers so logic stays centralized.
    ProductConfig,  # Data holder for product options.
    MAX_AGE_HOURS_DEFAULT,  # Shared default lookback hours.
    MIN_AGE_MINUTES_DEFAULT,  # Shared default minimum age.
    run_product_loop_once,  # Helper that executes one cycle.
    get_access_token,  # Helper to fetch Zoho token when running directly.
    delete_cooldown_file,  # Helper that clears the cooldown file on startup.
)  # End helper imports.

# Build Critical Findings settings with environment overrides.
CRITICAL_FINDINGS_ACTIVE_STATUSES = {status.strip() for status in os.getenv("CRITICAL_FINDINGS_ACTIVE_STATUSES", os.getenv("ACTIVE_STATUSES", "Assigned,Pending,Escalated")).split(",") if status.strip()}  # Statuses treated as open.
CRITICAL_FINDINGS_TARGET_PRODUCTS = [name.strip().lower() for name in os.getenv("CRITICAL_FINDINGS_TARGET_PRODUCT_NAMES", os.getenv("TARGET_PRODUCT_NAMES", "")).split(",") if name.strip()]  # Product names to match (lower-case).
CRITICAL_FINDINGS_KEYWORD_REGEX = os.getenv("CRITICAL_FINDINGS_KEYWORD_REGEX", r"\\bcritical[\\s-]?findings?\\b").replace("\\\\", "\\")  # Regex that spots Critical Findings wording, unescaped.
CRITICAL_FINDINGS_BANNER_TEXT = os.getenv("CRITICAL_FINDINGS_BANNER_TEXT", "ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM").strip()  # Critical-only top banner text.

# Create the ProductConfig object for Critical Findings.
CRITICAL_FINDINGS_CONFIG = ProductConfig(  # Bundle all Critical Findings settings together.
    name="Critical Findings",  # Friendly name for logs and cards.
    keyword_regex=CRITICAL_FINDINGS_KEYWORD_REGEX,  # Regex pattern for this product.
    target_product_names=CRITICAL_FINDINGS_TARGET_PRODUCTS,  # Exact product names list.
    active_statuses=CRITICAL_FINDINGS_ACTIVE_STATUSES,  # Open statuses to watch.
    teams_webhook_env_var="TEAMS_WEBHOOK_CRITICAL_FINDINGS",  # Env var holding the Teams webhook URL.
    last_sent_filename="sent_critical_findings_notifications.json",  # Cooldown file name for this product.
    max_age_hours=int(os.getenv("CRITICAL_FINDINGS_MAX_AGE_HOURS", MAX_AGE_HOURS_DEFAULT)),  # Lookback window in hours.
    min_age_minutes=int(os.getenv("CRITICAL_FINDINGS_MIN_AGE_MINUTES", MIN_AGE_MINUTES_DEFAULT)),  # Minimum age before alert.
    card_banner_text=CRITICAL_FINDINGS_BANNER_TEXT,  # Banner shown only on Critical Findings cards.
)  # Finished building Critical Findings config.


def run_cycle(token: str, pre_fetched_tickets=None) -> None:  # Run one Critical Findings watch cycle.
    """Run one pass of the Critical Findings watcher using the provided Zoho token."""  # Docstring in clear language.
    run_product_loop_once(CRITICAL_FINDINGS_CONFIG, token, pre_fetched_tickets=pre_fetched_tickets)  # Delegate to the shared helper.


if __name__ == "__main__":  # Let this module run directly for quick checks.
    delete_cooldown_file(CRITICAL_FINDINGS_CONFIG)  # Clear cooldown history so startup mimics old behavior.
    shared_token = get_access_token()  # Fetch or reuse Zoho token.
    run_cycle(shared_token)  # Execute one Critical Findings cycle.
