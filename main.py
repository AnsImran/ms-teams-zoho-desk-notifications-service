"""Entry point — single-loop architecture with one shared Zoho fetch."""  # High-level purpose in plain words.

import os                                          # Read environment variables for worker count.
import time                                        # Provide sleep between polling cycles.
from concurrent.futures import ThreadPoolExecutor  # Run pending summary in background thread.
from dotenv import load_dotenv                     # Load environment values from a .env file if present.

from src.core.watch_helper import (  # Import shared helpers we need here.
    CHECK_EVERY_SECONDS,             # Shared polling interval.
    get_token_from_service,          # Fetch Zoho token from centralized token service.
    build_config_lookup,             # Build product-name-to-config lookup dict.
    delete_cooldown_file,            # Helper to clear cooldown files at startup.
    load_last_sent,                  # Load cooldown state from disk.
    process_tickets,                 # Single-loop ticket processor.
    search_tickets,                  # Shared Zoho ticket search to fetch once per loop.
)                                    # End of helper imports list.

from src.scripts import pending_watch                                   # Pending summary watcher module (separate scheduled flow).
from src.scripts.product_registry import load_product_configs_from_env  # Declarative env-driven product configs.


def run_all_products_loop() -> None:                                                          # Main loop that drives the entire service.
    """Fetch tickets once per cycle, process each ticket through its product config."""       # Layperson-friendly docstring.
    load_dotenv()                                                                             # Make sure env vars from .env are available right away.

    product_configs = load_product_configs_from_env()                                         # Build all product configs from one registry.
    if not product_configs:                                                                   # Safety guard against empty registry.
        raise RuntimeError("No products are configured in PRODUCT_REGISTRY.")

    for product_config in product_configs:                                                    # Reset all cooldown files once at startup.
        delete_cooldown_file(product_config)
    pending_watch.delete_pending_schedule_state_file()                                        # Reset pending schedule state once at startup.

    config_lookup = build_config_lookup(product_configs)                                      # Build product-name-to-config lookup once.

    status_union     = set()                                                                  # Aggregate status names across all products.
    product_name_set = set()                                                                  # Aggregate product names across all products.
    for product_config in product_configs:                                                    # Walk every product config to build shared filter sets.
        status_union.update(product_config.active_statuses)                                   # Add this product's watched statuses.
        product_name_set.update(product_config.target_product_names)                          # Add this product's target names.
    shared_statuses      = sorted(status_union)                                               # Shared status filter used by one pre-fetch search call.
    shared_product_names = sorted(product_name_set)                                           # All product names sent to Zoho productName filter.

    cooldown_state: dict = {}                                                                 # In-memory cooldown state keyed by filename, persisted each cycle.
    for product_config in product_configs:                                                    # Pre-load any existing cooldown files (empty after startup cleanup).
        script_dir = os.path.dirname(os.path.abspath(__file__))                               # Current folder path.
        path       = os.path.join(script_dir, "src", "core", product_config.last_sent_filename)  # Build path to cooldown file.
        cooldown_state[product_config.last_sent_filename] = load_last_sent(path)              # Load cooldown data (empty dict if file missing).

    pending_executor = ThreadPoolExecutor(max_workers=1)                                      # Dedicated background worker for pending summary runs.
    pending_future   = None                                                                   # Track currently-running pending summary job, if any.

    try:                                                                                      # Ensure we always close the pending executor on shutdown.
        while True:                                                                           # Repeat forever until manually stopped.
            try:                                                                              # Protect the loop so one failure does not kill the process.
                token = get_token_from_service()                                              # Fetch the Zoho access token from the centralized token service.
                if pending_future is not None and pending_future.done():                      # Collect completed pending job results before launching next one.
                    try:                                                                      # Surface pending worker exceptions without killing main loop.
                        pending_future.result()                                               # Raise any exception thrown inside pending worker.
                    except Exception as pending_error:                                        # Log pending worker failures clearly.
                        print("[main] ERROR in pending summary worker:", repr(pending_error))  # Pending-specific error.
                    pending_future = None                                                     # Clear completed job handle.
                if pending_future is None:                                                    # Submit only when no pending worker job is currently running.
                    pending_future = pending_executor.submit(pending_watch.run_cycle, token)   # Run pending watcher asynchronously.

                tickets = search_tickets(token, statuses=shared_statuses, product_names=shared_product_names)  # Fetch tickets once for all products.
                process_tickets(                                                              # Process every ticket in one pass.
                    tickets        = tickets,                                                  # Pass the shared ticket list.
                    config_lookup  = config_lookup,                                           # Pass the product-name-to-config lookup.
                    cooldown_state = cooldown_state,                                          # Pass in-memory cooldown state.
                )                                                                             # End process_tickets call.
            except Exception as error:                                                        # Catch any unexpected problem.
                print("ERROR in main loop:", repr(error))                                     # Log the problem in simple words.
            print(f"[main] Sleeping for {CHECK_EVERY_SECONDS} seconds...")                    # Tell the operator we are pausing.
            time.sleep(CHECK_EVERY_SECONDS)                                                   # Pause before the next cycle.
            print("")                                                                         # Blank line to separate one cycle from the next.
            print("")                                                                         # Second blank line for clearer spacing.
    finally:                                                                                  # Clean up the background pending executor when process exits.
        pending_executor.shutdown(wait=False, cancel_futures=True)                             # Stop accepting new pending jobs and cancel queued work.


if __name__ == "__main__":   # Allow running via `python main.py`.
    run_all_products_loop()  # Start the never-ending watcher loop.
