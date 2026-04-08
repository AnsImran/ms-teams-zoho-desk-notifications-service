"""One-time migration: generate products.json from the old hardcoded PRODUCT_REGISTRY + .env values.

Reads the old product definitions and resolved env vars, then writes
config/products.json in the new schema. Run once from repo root:

  uv run python scripts/migrate_to_json.py

After verifying the output, the old PRODUCT_REGISTRY dict can be removed.
"""  # Module-level docstring explaining purpose and usage.

import json                      # Write JSON output.
import os                        # Read environment variables.
from pathlib import Path         # Build file paths cleanly.
from dotenv import load_dotenv   # Pull settings from a .env file automatically.

load_dotenv()  # Makes env lookups succeed without manual loading.


# The old hardcoded registry (copied from the original product_registry.py before refactor).
OLD_REGISTRY = {
    "superstat": {
        "prefix": "SUPERSTAT",
        "name": "Super-Stat",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_SUPERSTAT",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
        "default_banner_text": "",
    },
    "code_stroke": {
        "prefix": "CODE_STROKE",
        "name": "Code Stroke",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CODE_STROKE",
        "default_target_product_names": [],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "critical_findings": {
        "prefix": "CRITICAL_FINDINGS",
        "name": "Critical Findings",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CRITICAL_FINDINGS",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
        "banner_env_var": "CRITICAL_FINDINGS_BANNER_TEXT",
        "default_banner_text": "ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM",
    },
    "amendments": {
        "prefix": "AMENDMENTS",
        "name": "Amendments",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_AMENDMENTS",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
        "default_banner_text": "",
    },
    "nm_studies": {
        "prefix": "NM_STUDIES",
        "name": "NM Studies",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_NM_STUDIES",
        "default_target_product_names": ["nm studies"],
        "use_global_target_fallback": False,
        "banner_env_var": "NM_STUDIES_BANNER_TEXT",
        "default_banner_text": "Please verify whether any radiologist scheduled today is able to read this study. If none are available, notify the team immediately so we can secure a radiologist who can complete the read.",
    },
    "it_system_studies": {
        "prefix": "IT_SYSTEM_STUDIES",
        "name": "IT / System Studies",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_IT_SYSTEM_STUDIES",
        "default_target_product_names": ["it / system studies"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "reading_requests": {
        "prefix": "READING_REQUESTS",
        "name": "Reading Requests",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_READING_REQUESTS",
        "default_target_product_names": ["reading requests"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "password_reset": {
        "prefix": "PASSWORD_RESET",
        "name": "Password Reset",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_PASSWORD_RESET",
        "default_target_product_names": ["Password Reset"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "unlock_account": {
        "prefix": "UNLOCK_ACCOUNT",
        "name": "Unlock Account",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_PASSWORD_RESET",
        "default_target_product_names": ["Unlock Account"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "general": {
        "prefix": "GENERAL",
        "name": "General",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_GENERAL",
        "default_target_product_names": ["general"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
    "consults_and_physician_connection": {
        "prefix": "CONSULTS_AND_PHYSICIAN_CONNECTION",
        "name": "Consults & Physician Connection",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CONSULTS_AND_PHYSICIAN_CONNECTION",
        "default_target_product_names": ["consults & physician connection"],
        "use_global_target_fallback": False,
        "default_banner_text": "",
    },
}

DEFAULT_ACTIVE_STATUSES = ["Assigned", "Pending", "Escalated"]                   # Shared default from old code.


def resolve_product(key: str, spec: dict) -> dict:                               # Resolve one product entry from old registry + env vars.
    """Resolve one old-style product entry into the new JSON schema."""          # Docstring in plain words.
    prefix = spec["prefix"]                                                      # Env var prefix (e.g., SUPERSTAT).

    # Resolve target product names (env var → global fallback → registry default).
    target_raw = os.getenv(f"{prefix}_TARGET_PRODUCT_NAMES", "").strip()         # Product-specific env var first.
    if not target_raw and spec.get("use_global_target_fallback"):                 # If empty and fallback enabled...
        target_raw = os.getenv("TARGET_PRODUCT_NAMES", "").strip()               # Try global env var.
    if not target_raw:                                                           # If still empty...
        target_names = spec.get("default_target_product_names", [])              # Use registry default.
    else:                                                                        # Otherwise parse the comma-separated text.
        target_names = [n.strip() for n in target_raw.split(",") if n.strip()]   # Split and trim.

    # Resolve active statuses.
    statuses_raw = os.getenv(f"{prefix}_ACTIVE_STATUSES", "").strip()            # Product-specific env var first.
    if not statuses_raw:                                                         # If empty...
        statuses_raw = os.getenv("ACTIVE_STATUSES", "").strip()                  # Try global env var.
    if statuses_raw:                                                             # If we have a value...
        active_statuses = [s.strip() for s in statuses_raw.split(",") if s.strip()]  # Parse comma-separated.
    else:                                                                        # Otherwise use default.
        active_statuses = DEFAULT_ACTIVE_STATUSES                                # Default statuses.

    # Resolve webhook URL from env var.
    webhook_url = os.getenv(spec["teams_webhook_env_var"], "").strip()            # Read actual webhook URL from env.

    # Resolve banner text.
    banner_env_var = spec.get("banner_env_var")                                  # Optional banner env var key.
    banner_default = spec.get("default_banner_text", "")                         # Default banner text.
    banner_text    = os.getenv(banner_env_var, banner_default).strip() if banner_env_var else banner_default  # Resolve banner.

    # Resolve numeric settings.
    min_age = int(os.getenv(f"{prefix}_MIN_AGE_MINUTES", os.getenv("MIN_AGE_MINUTES", "5")))     # Min age minutes.
    cooldown_raw = os.getenv(f"{prefix}_NOTIFY_COOLDOWN_SECONDS", "").strip()                    # Optional cooldown.
    cooldown_sec = int(cooldown_raw) if cooldown_raw else None                                   # Parse or None.

    return {                                                                     # Return the new-schema product entry.
        "name":                    spec["name"],                                 # Friendly product label.
        "teams_webhook_url":       webhook_url,                                  # Resolved webhook URL.
        "min_age_minutes":         min_age,                                      # Minimum age before alerting.
        "target_product_names":    target_names,                                 # Product names to match.
        "active_statuses":         active_statuses,                              # Status strings considered open.
        "banner_text":             banner_text,                                  # Optional instruction banner.
        "notify_cooldown_seconds": cooldown_sec,                                 # Optional per-product cooldown.
    }                                                                            # End product entry.


def main():                                                                      # Script entry point.
    """Migrate all old-style products to products.json."""                       # Docstring in plain words.
    products = {}                                                                # Collect resolved product entries.
    for key, spec in OLD_REGISTRY.items():                                       # Walk each old product.
        products[key] = resolve_product(key, spec)                               # Resolve and store.
        print(f"  {key:45s} -> {products[key]['name']}")                         # Log each product.

    output = {"products": products}                                              # Wrap in top-level structure.
    output_path = Path("config/products.json")                                   # Output file path.
    output_path.parent.mkdir(parents=True, exist_ok=True)                        # Create directory if needed.
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")  # Write formatted JSON.
    print(f"\nWrote {len(products)} products to {output_path}")                  # Final summary.


if __name__ == "__main__":  # Allow running via `python scripts/migrate_to_json.py`.
    main()                  # Run the migration.
