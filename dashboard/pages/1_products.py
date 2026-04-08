"""Products management page — view, add, remove products."""  # Page purpose.

import sys                                                    # Add project root to path.
import os                                                     # Build file paths.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # Allow imports from project root.

import time                                                   # Sleep while waiting for config to be picked up.
import streamlit as st                                        # Streamlit UI framework.
from dashboard.utils.auth import require_login                # Shared auth gate.
from src.core.config_manager import (                         # JSON config read/write.
    load_products,
    add_product,
    remove_product,
    slugify,
)
from dashboard.utils.docker_ops import (                      # Docker operations.
    get_notification_service_status,
)


WAIT_SECONDS = 35                                            # Just over one polling cycle so the change is guaranteed to be picked up.

st.set_page_config(page_title="Products", page_icon="📦", layout="wide")
require_login()                                               # Block page content until authenticated.

# ---------------------------------------------------------------------------
# Full-page block while waiting for config change to be picked up
# ---------------------------------------------------------------------------

if st.session_state.get("waiting_message"):                   # A config change was just made — block the entire page.
    st.title("📦 Product Configuration")
    with st.spinner(st.session_state["waiting_message"]):
        time.sleep(WAIT_SECONDS)
    st.session_state.pop("waiting_message", None)             # Clear the flag so next rerun shows the normal page.
    st.success("Done — the notification service has picked up the change.")
    time.sleep(2)                                             # Brief pause so the user sees the success message.
    st.rerun()                                                # Rerun to show the updated product list.

# ---------------------------------------------------------------------------
# Sidebar — notification service status
# ---------------------------------------------------------------------------

status = get_notification_service_status()
status_emoji = "🟢" if status["status"] == "running" else "🔴"
st.sidebar.markdown(f"**Notification Service:** {status_emoji} {status['status']}")
st.sidebar.divider()

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("📦 Product Configuration")
st.caption("Add, view, or remove monitored products.")

# ---------------------------------------------------------------------------
# Current products
# ---------------------------------------------------------------------------

st.subheader("Current Products")

data     = load_products()
products = data.get("products", {})

if not products:
    st.info("No products configured yet. Use the form below to add one.")
else:
    for key, entry in products.items():
        with st.expander(f"**{entry.get('name', key)}** — alert after {entry.get('min_age_minutes', '?')} min", expanded=False):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Key:** `{key}`")
                st.markdown(f"**Target product names:** {', '.join(entry.get('target_product_names', []))}")
                st.markdown(f"**Active statuses:** {', '.join(entry.get('active_statuses', []))}")
                webhook = entry.get("teams_webhook_url", "")
                st.markdown(f"**Webhook:** {'✅ configured' if webhook else '❌ NOT SET'}")
                banner = entry.get("banner_text", "")
                if banner:
                    st.markdown(f"**Banner:** {banner}")
            with col2:
                if st.button("Remove", key=f"remove_{key}", type="secondary"):
                    st.session_state[f"confirm_remove_{key}"] = True

                if st.session_state.get(f"confirm_remove_{key}", False):
                    st.warning(f"Remove **{entry.get('name', key)}**?")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("Yes", key=f"confirm_yes_{key}", type="primary"):
                            remove_product(key)
                            st.session_state.pop(f"confirm_remove_{key}", None)
                            st.session_state["waiting_message"] = f"Removing '{entry.get('name', key)}'... waiting for the notification service to pick up the change."
                            st.rerun()
                    with col_no:
                        if st.button("Cancel", key=f"confirm_no_{key}"):
                            st.session_state.pop(f"confirm_remove_{key}", None)
                            st.rerun()

    st.caption(f"{len(products)} product(s) configured.")

# ---------------------------------------------------------------------------
# Add new product form
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Add New Product")

with st.form("add_product_form", clear_on_submit=True):
    product_name   = st.text_input("Product Name *", help="The Zoho Desk product name to watch (e.g., 'Super Stat').")
    webhook_url    = st.text_input("Teams Webhook URL *", help="The Microsoft Teams webhook URL for notifications.")
    use_test_wh    = st.checkbox("Use test webhook instead", help="Override with the shared test webhook for development.")
    min_age        = st.number_input("Min Age (minutes) *", min_value=1, value=5, help="Minimum ticket age before sending a notification.")
    target_names   = st.text_input("Target Product Names (comma-separated)", help="Leave blank to use the product name. Use commas for multiple names.")
    banner_text    = st.text_area("Banner Text (optional)", help="Instruction text shown at the top of the Teams card.")
    submitted      = st.form_submit_button("Add Product", type="primary")

    if submitted:
        if not product_name.strip():
            st.error("Product name is required.")
        elif not webhook_url.strip() and not use_test_wh:
            st.error("Teams webhook URL is required (or select 'Use test webhook').")
        else:
            key = slugify(product_name.strip())
            if key in products:
                st.error(f"A product with key '{key}' already exists. Remove it first or use a different name.")
            else:
                if target_names.strip():
                    parsed_targets = [n.strip() for n in target_names.split(",") if n.strip()]
                else:
                    parsed_targets = [product_name.strip()]

                if use_test_wh:
                    from src.core.watch_helper import MAGIC_TEST_WEBHOOK
                    resolved_webhook = MAGIC_TEST_WEBHOOK
                else:
                    resolved_webhook = webhook_url.strip()

                new_entry = {
                    "name":                    product_name.strip(),
                    "teams_webhook_url":       resolved_webhook,
                    "min_age_minutes":         min_age,
                    "target_product_names":    parsed_targets,
                    "active_statuses":         ["Assigned", "Pending", "Escalated"],
                    "banner_text":             banner_text.strip(),
                    "notify_cooldown_seconds": None,
                }
                add_product(key, new_entry)
                st.session_state["waiting_message"] = f"Adding '{product_name.strip()}'... waiting for the notification service to pick up the change."
                st.rerun()
