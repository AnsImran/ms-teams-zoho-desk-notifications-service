"""Entry point that runs all product watchers with one shared Zoho token."""  # High-level purpose in plain words.

import os                                          # Read environment variables for worker count.
import time                                        # Provide sleep between polling cycles.
from concurrent.futures import ThreadPoolExecutor  # Run product watchers in parallel threads.
from dotenv import load_dotenv                     # Load environment values from a .env file if present.

from src.superstat_cron.watch_helper import (  # Import shared helpers we need here.
    CHECK_EVERY_SECONDS,                       # Shared polling interval.
    get_access_token,                          # Shared Zoho token fetcher.
    delete_cooldown_file,                      # Helper to clear cooldown files at startup.
    search_tickets,                            # Shared Zoho ticket search to fetch once per loop.
)                                              # End of helper imports list.

from src.superstat_cron import (               # Product-specific watcher modules.
    superstat_watch,
    code_stroke_watch,
    critical_findings_watch,
    pending_watch
    )

PRODUCT_WORKERS_RAW = os.getenv("PRODUCT_WORKERS", "").strip()                   # Raw env value for product worker count (may be blank).
PRODUCT_WORKERS     = int(PRODUCT_WORKERS_RAW) if PRODUCT_WORKERS_RAW else None  # Worker count for product threads; None lets Python choose.
 

def run_all_products_loop() -> None:                                              # Keep the infinite loop that services every product.
    """Keep running the watchers forever, sharing one Zoho token each cycle."""   # Layperson-friendly docstring.
    load_dotenv()                                                                 # Make sure env vars from .env are available right away.
    
    delete_cooldown_file(superstat_watch.SUPERSTAT_CONFIG)                        # Reset Super-Stat cooldown file once at startup.
    delete_cooldown_file(code_stroke_watch.CODE_STROKE_CONFIG)                    # Reset Code Stroke cooldown file once at startup.
    delete_cooldown_file(critical_findings_watch.CRITICAL_FINDINGS_CONFIG)        # Reset Critical Findings cooldown file once at startup.
    pending_watch.delete_pending_schedule_state_file()                            # Reset pending schedule state once at startup.

    shared_statuses = sorted(                                                     # Combine statuses watched by product-specific reminder watchers.
        superstat_watch.SUPERSTAT_CONFIG.active_statuses                          # Super-Stat statuses.
        .union(code_stroke_watch.CODE_STROKE_CONFIG.active_statuses)              # Code Stroke statuses.
        .union(critical_findings_watch.CRITICAL_FINDINGS_CONFIG.active_statuses)  # Critical Findings statuses.
    )                                                                             # End shared statuses computation.

    shared_hours = max(                                                           # Use one lookback that satisfies all watchers.
        superstat_watch.SUPERSTAT_CONFIG.max_age_hours,                           # Super-Stat lookback.
        code_stroke_watch.CODE_STROKE_CONFIG.max_age_hours,                       # Code Stroke lookback.
        critical_findings_watch.CRITICAL_FINDINGS_CONFIG.max_age_hours,           # Critical Findings lookback.
    )                                                                             # End shared lookback computation.
    
    pending_executor = ThreadPoolExecutor(max_workers=1)                          # Dedicated background worker for pending summary runs.
    pending_future   = None                                                       # Track currently-running pending summary job, if any.


    try:                                                                                                 # Ensure we always close the pending executor on shutdown.
        while True:                                                                                      # Repeat forever until manually stopped.
            try:                                                                                         # Protect the loop so one failure does not kill the process.
                token = get_access_token()                                                               # Fetch or reuse the Zoho access token (good for about an hour).
                if pending_future is not None and pending_future.done():                                 # Collect completed pending job results before launching next one.
                    try:                                                                                 # Surface pending worker exceptions without killing main loop.
                        pending_future.result()                                                          # Raise any exception thrown inside pending worker.
                    except Exception as pending_error:                                                   # Log pending worker failures clearly.
                        print("[main] ERROR in pending summary worker:", repr(pending_error))            # Pending-specific error.
                    pending_future = None                                                                # Clear completed job handle.
                if pending_future is None:                                                               # Submit only when no pending worker job is currently running.
                    pending_future = pending_executor.submit(pending_watch.run_cycle, token)             # Run pending watcher asynchronously with its own fetch path.
                tickets = search_tickets(token, statuses=shared_statuses, hours=shared_hours)            # Fetch tickets once for Super-Stat and Code Stroke only.
                with ThreadPoolExecutor(max_workers=PRODUCT_WORKERS) as executor:                        # Spin up a small pool for product-level parallelism.
                    futures = []                                                                         # Collect futures for all product watchers.
                    futures.append(executor.submit(superstat_watch.run_cycle, token, tickets))           # Submit Super-Stat cycle to pool.
                    futures.append(executor.submit(code_stroke_watch.run_cycle, token, tickets))         # Submit Code Stroke cycle to pool.
                    futures.append(executor.submit(critical_findings_watch.run_cycle, token, tickets))   # Submit Critical Findings cycle to pool.
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