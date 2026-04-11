"""Read and write the products.json configuration file with file locking."""  # Module purpose in plain words.

import json                  # Parse and write JSON files.
import os                    # Read environment variables and file paths.
import re                    # Slugify product names with regex.
from pathlib import Path     # Build file paths cleanly.
from typing import Any, Dict # Keep type hints explicit and readable.
from filelock import FileLock # Prevent concurrent writes from corrupting the file.

from src.core.logger import get_logger  # Centralized structured logging.

logger = get_logger(__name__)  # Named logger for this module.


PRODUCTS_JSON_PATH = os.getenv("PRODUCTS_JSON_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "products.json"))  # Default path to products.json.
LOCK_PATH          = PRODUCTS_JSON_PATH + ".lock"                                                                                                      # Lock file path next to the JSON.


def slugify(name: str) -> str:                                                   # Convert a product name into a safe dict key.
    """Turn 'Super-Stat' into 'super_stat' for use as a JSON key."""            # Docstring in plain words.
    slug = name.lower().strip()                                                  # Lowercase and trim whitespace.
    slug = re.sub(r"[^a-z0-9\s]", "", slug)                                      # Remove special characters.
    slug = re.sub(r"\s+", "_", slug)                                             # Replace spaces with underscores.
    return slug                                                                  # Return the clean slug.


def load_products() -> Dict[str, Any]:                                           # Read products.json from disk.
    """Load the products config from JSON; return empty structure if missing.""" # Docstring in plain words.
    path = Path(PRODUCTS_JSON_PATH)                                              # Build a Path object.
    if not path.exists():                                                        # If file does not exist...
        logger.debug("Products config file not found — path=%s", PRODUCTS_JSON_PATH)
        return {"products": {}}                                                  # Return empty structure.
    with FileLock(LOCK_PATH):                                                    # Acquire file lock for safe reading.
        data = json.loads(path.read_text(encoding="utf-8"))                      # Parse and return JSON content.
    logger.debug("Products config loaded from disk")
    return data


def save_products(data: Dict[str, Any]) -> None:                                # Write products.json to disk.
    """Save the products config to JSON with pretty formatting."""              # Docstring in plain words.
    path = Path(PRODUCTS_JSON_PATH)                                              # Build a Path object.
    path.parent.mkdir(parents=True, exist_ok=True)                               # Create parent directories if needed.
    with FileLock(LOCK_PATH):                                                    # Acquire file lock for safe writing.
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")  # Write formatted JSON.
    logger.info("Products config saved to disk — path=%s", PRODUCTS_JSON_PATH)


def add_product(key: str, product: Dict[str, Any]) -> None:                     # Add one product to the config file.
    """Add a product entry to products.json."""                                 # Docstring in plain words.
    data = load_products()                                                       # Load current config.
    data["products"][key] = product                                              # Insert or overwrite the product entry.
    save_products(data)                                                          # Persist to disk.
    logger.info("Product added to config — key=%s", key)


def remove_product(key: str) -> None:                                            # Remove one product from the config file.
    """Remove a product entry from products.json."""                            # Docstring in plain words.
    data = load_products()                                                       # Load current config.
    data["products"].pop(key, None)                                              # Remove the product entry if it exists.
    save_products(data)                                                          # Persist to disk.
    logger.info("Product removed from config — key=%s", key)
