"""Products management page — view, add, remove products."""  # Page purpose.

import sys                                                    # Add project root to path.
import os                                                     # Build file paths.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # Allow imports from project root.

import streamlit as st                                        # Streamlit UI framework.
from dashboard.utils.auth import require_login                # Shared auth gate.
from src.core.config_manager import (                         # JSON config read/write.
    load_products,
    save_products,
    add_product,
    remove_product,
    slugify,
)
from dashboard.utils.docker_ops import (                      # Docker operations.
    restart_notification_service,
    get_notification_service_status,
)


st.set_page_config(page_title="Products", page_icon="📦", layout="wide")
require_login()                                               # Block page content until authenticated.
st.title("Product Configuration")

# ---------------------------------------------------------------------------
# Notification service status
# ---------------------------------------------------------------------------

status = get_notification_service_status()
status_emoji = "🟢" if status["status"] == "running" else "🔴"
st.sidebar.markdown(f"**Notification Service:** {status_emoji} {status['status']}")

# ---------------------------------------------------------------------------
# Current products table
# ---------------------------------------------------------------------------

st.subheader("Current Products")

data     = load_products()
products = data.get("products", {})

if not products:
    st.info("No products configured. Add one below.")
else:
    for key, entry in products.items():
        with st.expander(f"**{entry.get('name', key)}** — min age: {entry.get('min_age_minutes', '?')} min", expanded=False):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Key:** `{key}`")
                st.markdown(f"**Target product names:** {', '.join(entry.get('target_product_names', []))}")
                st.markdown(f"**Active statuses:** {', '.join(entry.get('active_statuses', []))}")
                st.markdown(f"**Max age hours:** {entry.get('max_age_hours', 24)}")
                webhook = entry.get("teams_webhook_url", "")
                st.markdown(f"**Webhook:** {'configured' if webhook else 'NOT SET'}")
                banner = entry.get("banner_text", "")
                if banner:
                    st.markdown(f"**Banner:** {banner}")
            with col2:
                if st.button(f"Remove", key=f"remove_{key}", type="secondary"):
                    st.session_state[f"confirm_remove_{key}"] = True

                if st.session_state.get(f"confirm_remove_{key}", False):
                    st.warning(f"Are you sure you want to remove **{entry.get('name', key)}**?")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("Yes, remove", key=f"confirm_yes_{key}", type="primary"):
                            remove_product(key)
                            result = restart_notification_service()
                            st.success(f"Removed '{entry.get('name', key)}'. {result}")
                            st.session_state.pop(f"confirm_remove_{key}", None)
                            st.rerun()
                    with col_no:
                        if st.button("Cancel", key=f"confirm_no_{key}"):
                            st.session_state.pop(f"confirm_remove_{key}", None)
                            st.rerun()

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
    max_age        = st.number_input("Max Age (hours)", min_value=1, value=24, help="Search lookback window in hours.")
    target_names   = st.text_input("Target Product Names (comma-separated)", help="Leave blank to use the product name. Use commas for multiple names.")
    banner_text    = st.text_area("Banner Text (optional)", help="Instruction text shown at the top of the Teams card.")
    submitted      = st.form_submit_button("Add Product")

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
                # Resolve target product names.
                if target_names.strip():
                    parsed_targets = [n.strip() for n in target_names.split(",") if n.strip()]
                else:
                    parsed_targets = [product_name.strip()]

                # Resolve webhook URL.
                if use_test_wh:
                    from src.core.watch_helper import MAGIC_TEST_WEBHOOK
                    resolved_webhook = MAGIC_TEST_WEBHOOK
                else:
                    resolved_webhook = webhook_url.strip()

                new_entry = {
                    "name":                    product_name.strip(),
                    "teams_webhook_url":       resolved_webhook,
                    "min_age_minutes":         min_age,
                    "max_age_hours":           max_age,
                    "target_product_names":    parsed_targets,
                    "active_statuses":         ["Assigned", "Pending", "Escalated"],
                    "banner_text":             banner_text.strip(),
                    "notify_cooldown_seconds": None,
                }
                add_product(key, new_entry)
                result = restart_notification_service()
                st.success(f"Added '{product_name.strip()}' (key: {key}). {result}")
                st.rerun()
