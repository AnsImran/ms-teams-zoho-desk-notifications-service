"""Shared pytest setup for test discovery/import path behavior."""  # Pytest auto-loads this module.

from __future__ import annotations

import sys               # Adjust module search path for local package imports.
from pathlib import Path  # Resolve repository root from this file path.


REPO_ROOT = Path(__file__).resolve().parents[1]  # Repo root (parent of tests/).
if str(REPO_ROOT) not in sys.path:               # Insert once to avoid duplicates.
    sys.path.insert(0, str(REPO_ROOT))           # Allow imports like `from src.core import watch_helper`.
