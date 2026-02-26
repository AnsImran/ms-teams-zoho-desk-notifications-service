"""Pending summary watcher config that delegates runtime logic to shared helpers."""  # Module purpose in one line.

import os  # Read pending watcher environment overrides.

from .watch_helper import (  # Reuse shared helper logic to keep this module thin.
    PendingSummaryConfig,  # Data holder for pending summary settings.
    delete_pending_summary_state_file,  # Shared startup cleanup helper for pending slot state.
    get_access_token,  # Token helper used for standalone runs.
    parse_hhmm_schedule,  # Shared parser for HH:MM;HH:MM LA schedule strings.
    run_pending_summary_loop_once,  # Shared one-cycle runner for pending summaries.
)  # End helper imports.

PENDING_WEBHOOK_ENV_VAR = "TEAMS_WEBHOOK_PENDING"  # Env var that stores pending-summary Teams webhook.
PENDING_STATUS_NAME = os.getenv("PENDING_STATUS_NAME", "PENDING").strip()  # Status text treated as pending.
PENDING_REPORT_WINDOW_SECONDS = int(os.getenv("PENDING_REPORT_WINDOW_SECONDS", "120"))  # Allowed window before/after each scheduled time (default: 2 minutes).
PENDING_LAST_SENT_FILENAME = "sent_pending_summary_slots.json"  # Slot-state file used for one-send-per-slot dedupe.
PENDING_REPORT_TIMES_LA_RAW = os.getenv("PENDING_REPORT_TIMES_LA", "04:00;12:00;20:00").strip()  # LA schedule in HH:MM;HH:MM 24-hour format.
PENDING_REPORT_TIMES_LA = parse_hhmm_schedule(PENDING_REPORT_TIMES_LA_RAW, env_name="PENDING_REPORT_TIMES_LA")  # Parsed and validated schedule tuples.

PENDING_CONFIG = PendingSummaryConfig(  # Bundle pending summary settings for shared helper runner.
    name="Pending Summary",  # Friendly label for logs.
    pending_status_name=PENDING_STATUS_NAME,  # Pending status filter.
    teams_webhook_env_var=PENDING_WEBHOOK_ENV_VAR,  # Webhook env var for pending channel.
    report_times_la=PENDING_REPORT_TIMES_LA,  # Parsed LA schedule times.
    report_window_seconds=PENDING_REPORT_WINDOW_SECONDS,  # Window around each schedule slot.
    last_sent_filename=PENDING_LAST_SENT_FILENAME,  # Slot-state filename.
)  # End pending config definition.


def run_cycle(token: str) -> None:  # Run one pending summary cycle with a dedicated fetch path.
    """Run one scheduled pending summary cycle using shared helper logic."""  # Brief docstring.
    run_pending_summary_loop_once(PENDING_CONFIG, token)  # Delegate to shared helper.


def delete_pending_schedule_state_file() -> None:  # Clear pending slot-state file once at startup.
    """Delete pending schedule state file so startup begins with a clean slate."""  # Brief docstring.
    delete_pending_summary_state_file(PENDING_CONFIG)  # Delegate cleanup to shared helper.


if __name__ == "__main__":  # Allow running this watcher directly for manual checks.
    shared_token = get_access_token()  # Fetch or reuse Zoho token.
    run_cycle(shared_token)  # Execute one schedule-aware pending summary cycle.
