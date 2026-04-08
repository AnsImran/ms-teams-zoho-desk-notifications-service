"""Load product configurations from products.json."""  # Module purpose.

from typing import Any, Dict, List               # Keep type hints explicit and readable.

from src.core.watch_helper import (              # Reuse shared watch-helper contracts and defaults.
    ProductConfig,                               # Shared config object consumed by process_tickets.
    MIN_AGE_MINUTES_DEFAULT,                     # Shared default minimum age before alerting.
)                                                # End helper imports.
from src.core.config_manager import load_products  # Read products.json from disk.


DEFAULT_ACTIVE_STATUSES = ["Assigned", "Pending", "Escalated"]  # Default statuses when not specified in JSON.


def build_product_config_from_json(key: str, entry: Dict[str, Any]) -> ProductConfig:  # Build one ProductConfig from a JSON entry.
    """Build one product config from a products.json entry."""                         # Docstring in plain words.
    name             = str(entry.get("name", key))                                     # Friendly product label.
    webhook_url      = str(entry.get("teams_webhook_url", ""))                         # Teams webhook URL (stored directly).
    min_age          = int(entry.get("min_age_minutes", MIN_AGE_MINUTES_DEFAULT))      # Minimum age before alerting.
    target_names     = list(entry.get("target_product_names", [name]))                 # Product names to match; defaults to [name].
    active_statuses  = set(entry.get("active_statuses", DEFAULT_ACTIVE_STATUSES))      # Status strings considered open.
    banner_text      = str(entry.get("banner_text", ""))                               # Optional instruction banner.
    cooldown_raw     = entry.get("notify_cooldown_seconds")                            # Optional per-product cooldown override.
    cooldown_sec     = int(cooldown_raw) if cooldown_raw is not None else None         # Parse cooldown to int or keep None.
    last_sent_file   = f"sent_{key}_notifications.json"                                # Auto-generated cooldown filename from key.

    return ProductConfig(                                                              # Build the dataclass object.
        name                    = name,                                                # Friendly product label for logs.
        target_product_names    = target_names,                                        # Product names to match (case-insensitive).
        active_statuses         = active_statuses,                                     # Status strings considered open.
        teams_webhook_url       = webhook_url,                                         # Teams webhook URL (direct, not env var).
        last_sent_filename      = last_sent_file,                                      # Auto-generated cooldown file name.
        min_age_minutes         = min_age,                                             # Minimum age before alerting.
        notify_cooldown_seconds = cooldown_sec,                                        # Optional per-product cooldown override.
        card_banner_text        = banner_text,                                         # Optional top-of-card banner text.
    )                                                                                  # End ProductConfig construction.


def load_product_configs_from_env() -> List[ProductConfig]:                            # Load all product configs from products.json.
    """Load product configs from products.json and return them as a list."""           # Docstring in plain words.
    data     = load_products()                                                         # Read products.json from disk.
    products = data.get("products", {})                                                # Pull the products dict.
    configs  = []                                                                      # Collect ProductConfig objects.
    for key, entry in products.items():                                                # Walk each product entry.
        configs.append(build_product_config_from_json(key, entry))                     # Build config and add to list.
    return configs                                                                     # Return all product configs.
