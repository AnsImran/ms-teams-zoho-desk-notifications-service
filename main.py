"""Entry point that runs all product watchers with one shared Zoho token."""  # High-level purpose in plain words.

import os                                          # Read environment variables for worker count.
import time                                        # Provide sleep between polling cycles.
from concurrent.futures import ThreadPoolExecutor  # Run product watchers in parallel threads.
from dotenv import load_dotenv                     # Load environment values from a .env file if present.

from src.core.watch_helper import (  # Import shared helpers we need here.
    CHECK_EVERY_SECONDS,                       # Shared polling interval.
    get_token_from_service,                     # Fetch Zoho token from internal token service.
    delete_cooldown_file,                      # Helper to clear cooldown files at startup.
    run_product_loop_once,                     # Generic one-cycle runner for any ProductConfig.
    search_tickets,                            # Shared Zoho ticket search to fetch once per loop.
)                                              # End of helper imports list.

from src.scripts import pending_watch                        # Pending summary watcher module (separate scheduled flow).
from src.scripts.product_registry import load_product_configs_from_env  # Declarative env-driven product configs.

PRODUCT_WORKERS_RAW = os.getenv("PRODUCT_WORKERS", "").strip()                   # Raw env value for product worker count (may be blank).
PRODUCT_WORKERS     = int(PRODUCT_WORKERS_RAW) if PRODUCT_WORKERS_RAW else None  # Worker count for product threads; None lets Python choose.
 

def run_all_products_loop() -> None:                                              # Keep the infinite loop that services every product.
    """Keep running the watchers forever, sharing one Zoho token each cycle."""   # Layperson-friendly docstring.
    load_dotenv()                                                                 # Make sure env vars from .env are available right away.

    product_configs = load_product_configs_from_env()                             # Build all reminder-product configs from one registry.
    if not product_configs:                                                       # Safety guard against empty registry.
        raise RuntimeError("No reminder products are configured in PRODUCT_REGISTRY.")
    
    for product_config in product_configs:                                        # Reset all reminder-product cooldown files once at startup.
        delete_cooldown_file(product_config)
    pending_watch.delete_pending_schedule_state_file()                            # Reset pending schedule state once at startup.

    status_union = set()                                                          # Aggregate status names across all reminder products.
    product_name_set = set()                                                      # Aggregate product names across all reminder products.
    for product_config in product_configs:
        status_union.update(product_config.active_statuses)
        product_name_set.update(product_config.target_product_names)
    shared_statuses      = sorted(status_union)                                   # Shared status filter used by one pre-fetch search call.
    shared_product_names = sorted(product_name_set)                               # All product names for Zoho productName filter.
    
    pending_executor = ThreadPoolExecutor(max_workers=1)                          # Dedicated background worker for pending summary runs.
    pending_future   = None                                                       # Track currently-running pending summary job, if any.


    try:                                                                                                 # Ensure we always close the pending executor on shutdown.
        while True:                                                                                      # Repeat forever until manually stopped.
            try:                                                                                         # Protect the loop so one failure does not kill the process.
                token = get_token_from_service()                                                          # Fetch the Zoho access token from the internal token service.
                if pending_future is not None and pending_future.done():                                 # Collect completed pending job results before launching next one.
                    try:                                                                                 # Surface pending worker exceptions without killing main loop.
                        pending_future.result()                                                          # Raise any exception thrown inside pending worker.
                    except Exception as pending_error:                                                   # Log pending worker failures clearly.
                        print("[main] ERROR in pending summary worker:", repr(pending_error))            # Pending-specific error.
                    pending_future = None                                                                # Clear completed job handle.
                if pending_future is None:                                                               # Submit only when no pending worker job is currently running.
                    pending_future = pending_executor.submit(pending_watch.run_cycle, token)             # Run pending watcher asynchronously with its own fetch path.
                tickets = search_tickets(token, statuses=shared_statuses, product_names=shared_product_names)  # Fetch tickets once for all reminder watchers.
                with ThreadPoolExecutor(max_workers=PRODUCT_WORKERS) as executor:                        # Spin up a small pool for product-level parallelism.
                    futures = [                                                                         # Submit one generic cycle job per product config.
                        executor.submit(run_product_loop_once, product_config, token, tickets)
                        for product_config in product_configs
                    ]
                    for future in futures:                                                               # Wait for all products to finish.
                        future.result()                                                                  # Raise any error that occurred inside the thread.
            except Exception as error:                                                                   # Catch any unexpected problem.
                print("ERROR in main loop:", repr(error))                                                # Log the problem in simple words.
            print(f"[main] Sleeping for {CHECK_EVERY_SECONDS} seconds...")                               # Tell the operator we are pausing.
            time.sleep(CHECK_EVERY_SECONDS)                                                              # Pause before the next combined cycle.
            print("")                                                                                    # Blank line to separate one cycle from the next.
            print("")                                                                                    # Second blank line for clearer spacing.
    finally:                                                                                             # Clean up the background pending executor when process exits.
        pending_executor.shutdown(wait=False, cancel_futures=True)                                       # Stop accepting new pending jobs and cancel queued work.


if __name__ == "__main__":   # Allow running via `python main.py`.
    run_all_products_loop()  # Start the never-ending watcher loop.
