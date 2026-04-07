"""Centralized product watcher registry loaded from environment variables."""  # Module purpose.

import os                                        # Read product-specific env overrides.
from typing import Any, Dict, List, Optional     # Keep type hints explicit and readable.

from src.core.watch_helper import (              # Reuse shared watch-helper contracts and defaults.
    ProductConfig,                               # Shared config object consumed by process_tickets.
    MAX_AGE_HOURS_DEFAULT,                       # Shared default lookback.
    MIN_AGE_MINUTES_DEFAULT,                     # Shared default minimum age before alerting.
)                                                # End helper imports.

# Shared default statuses used when neither global nor product-specific values are provided.
DEFAULT_ACTIVE_STATUSES = "Assigned,Pending,Escalated"

# Product registry (dictionary-of-dictionaries) so new products are added by data, not new modules.
PRODUCT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "superstat": {
        "prefix": "SUPERSTAT",
        "name": "Super-Stat",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_SUPERSTAT",
        "last_sent_filename": "sent_superstat_notifications.json",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
    },
    "code_stroke": {
        "prefix": "CODE_STROKE",
        "name": "Code Stroke",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CODE_STROKE",
        "last_sent_filename": "sent_code_stroke_notifications.json",
        "default_target_product_names": [],
        "use_global_target_fallback": False,
    },
    "critical_findings": {
        "prefix": "CRITICAL_FINDINGS",
        "name": "Critical Findings",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CRITICAL_FINDINGS",
        "last_sent_filename": "sent_critical_findings_notifications.json",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
        "banner_env_var": "CRITICAL_FINDINGS_BANNER_TEXT",
        "default_banner_text": "ONLY TAG THE TICKET AS RESOLVED WHEN THE REPORT HAS BEEN AMMENDED BY THE RADIOLOGIST AND INCLUDES THAT INFORMATION WAS ALREADY RELAYED BY THE SUPPORT TEAM",
    },
    "amendments": {
        "prefix": "AMENDMENTS",
        "name": "Amendments",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_AMENDMENTS",
        "last_sent_filename": "sent_amendments_notifications.json",
        "default_target_product_names": [],
        "use_global_target_fallback": True,
    },
    "nm_studies": {
        "prefix": "NM_STUDIES",
        "name": "NM Studies",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_NM_STUDIES",
        "last_sent_filename": "sent_nm_studies_notifications.json",
        "default_target_product_names": ["nm studies"],
        "use_global_target_fallback": False,
        "banner_env_var": "NM_STUDIES_BANNER_TEXT",
        "default_banner_text": "Please verify whether any radiologist scheduled today is able to read this study. If none are available, notify the team immediately so we can secure a radiologist who can complete the read.",
    },
    "it_system_studies": {
        "prefix": "IT_SYSTEM_STUDIES",
        "name": "IT / System Studies",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_IT_SYSTEM_STUDIES",
        "last_sent_filename": "sent_it_system_studies_notifications.json",
        "default_target_product_names": ["it / system studies"],
        "use_global_target_fallback": False,
    },
    "reading_requests": {
        "prefix": "READING_REQUESTS",
        "name": "Reading Requests",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_READING_REQUESTS",
        "last_sent_filename": "sent_reading_requests_notifications.json",
        "default_target_product_names": ["reading requests"],
        "use_global_target_fallback": False,
    },
    "password_reset": {
        "prefix": "PASSWORD_RESET",
        "name": "Password Reset",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_PASSWORD_RESET",
        "last_sent_filename": "sent_password_reset_notifications.json",
        "default_target_product_names": ["Password Reset"],
        "use_global_target_fallback": False,
    },
    "unlock_account": {
        "prefix": "UNLOCK_ACCOUNT",
        "name": "Unlock Account",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_PASSWORD_RESET",
        "last_sent_filename": "sent_unlock_account_notifications.json",
        "default_target_product_names": ["Unlock Account"],
        "use_global_target_fallback": False,
    },
    "general": {
        "prefix": "GENERAL",
        "name": "General",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_GENERAL",
        "last_sent_filename": "sent_general_notifications.json",
        "default_target_product_names": ["general"],
        "use_global_target_fallback": False,
    },
    "consults_and_physician_connection": {
        "prefix": "CONSULTS_AND_PHYSICIAN_CONNECTION",
        "name": "Consults & Physician Connection",
        "teams_webhook_env_var": "TEAMS_WEBHOOK_CONSULTS_AND_PHYSICIAN_CONNECTION",
        "last_sent_filename": "sent_consults_and_physician_connection_notifications.json",
        "default_target_product_names": ["consults & physician connection"],
        "use_global_target_fallback": False,
    },
}


def _coalesce_env(*, primary: str, secondary: Optional[str], fallback: str) -> str:  # Resolve env text with deterministic precedence.
    """Return first non-empty env value from primary/secondary, else fallback."""      # Brief helper docstring.
    primary_value = os.getenv(primary, "").strip()                                      # Product-specific value first.
    if primary_value:
        return primary_value
    if secondary:
        secondary_value = os.getenv(secondary, "").strip()                              # Optional global fallback.
        if secondary_value:
            return secondary_value
    return fallback                                                                      # Finally use hardcoded default.


def _csv_set(raw_text: str) -> set[str]:  # Convert comma text into a set of trimmed values.
    """Parse comma-separated text into a set of non-empty values."""  # Brief docstring.
    return {entry.strip() for entry in raw_text.split(",") if entry.strip()}


def _csv_list(raw_text: str) -> List[str]:  # Convert comma text into a list preserving original casing.
    """Parse comma-separated text into a list of non-empty values with original casing."""  # Brief docstring.
    return [entry.strip() for entry in raw_text.split(",") if entry.strip()]


def build_product_config(product_id: str, spec: Dict[str, Any]) -> ProductConfig:  # Build one ProductConfig from registry + env values.
    """Build one product configuration object from declarative registry metadata."""  # Brief docstring.
    prefix = str(spec["prefix"])                                                      # Product env prefix (e.g., SUPERSTAT).

    active_raw = _coalesce_env(                                                       # Active statuses always allow global fallback.
        primary   = f"{prefix}_ACTIVE_STATUSES",
        secondary = "ACTIVE_STATUSES",
        fallback  = DEFAULT_ACTIVE_STATUSES,
    )
    target_default = ",".join(spec.get("default_target_product_names", []))          # Comma text default from registry list.
    target_raw = _coalesce_env(
        primary   = f"{prefix}_TARGET_PRODUCT_NAMES",
        secondary = "TARGET_PRODUCT_NAMES" if spec.get("use_global_target_fallback", False) else None,
        fallback  = target_default,
    )

    banner_default = str(spec.get("default_banner_text", ""))                         # Optional product banner default.
    banner_env_var = spec.get("banner_env_var")                                       # Optional banner env var key.
    banner_text    = os.getenv(banner_env_var, banner_default).strip() if banner_env_var else banner_default

    cooldown_raw = os.getenv(f"{prefix}_NOTIFY_COOLDOWN_SECONDS", "").strip()        # Optional per-product cooldown override.
    cooldown_sec = int(cooldown_raw) if cooldown_raw else None

    return ProductConfig(
        name                    = str(spec["name"]),
        target_product_names    = _csv_list(target_raw),
        active_statuses         = _csv_set(active_raw),
        teams_webhook_env_var   = str(spec["teams_webhook_env_var"]),
        last_sent_filename      = str(spec["last_sent_filename"]),
        max_age_hours           = int(os.getenv(f"{prefix}_MAX_AGE_HOURS",   MAX_AGE_HOURS_DEFAULT)),
        min_age_minutes         = int(os.getenv(f"{prefix}_MIN_AGE_MINUTES", MIN_AGE_MINUTES_DEFAULT)),
        notify_cooldown_seconds = cooldown_sec,
        card_banner_text        = banner_text,
    )


def load_product_configs_from_env() -> List[ProductConfig]:  # Build all product configs in deterministic registry order.
    """Load and return all product configs declared in PRODUCT_REGISTRY."""  # Brief docstring.
    return [build_product_config(product_id, spec) for product_id, spec in PRODUCT_REGISTRY.items()]
