"""Dashboard entry point with authentication gate."""  # Module purpose.

import sys                                                    # Add project root to path.
import os                                                     # Build file paths.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # Allow imports from project root.

import streamlit as st                                        # Streamlit UI framework.
from dashboard.utils.auth import require_login                # Shared auth gate.


# Page config must be the first Streamlit command.
st.set_page_config(
    page_title  = "Dashboard",
    page_icon   = "🔔",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

require_login()                                               # Block page content until authenticated.

# ---------------------------------------------------------------------------
# Home page content
# ---------------------------------------------------------------------------

st.title("🔔 Teams Notifications Dashboard")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📦 Products")
    st.markdown(
        "View, add, or remove the Zoho Desk products being monitored. "
        "Changes take effect immediately — the notification service restarts automatically."
    )
    st.page_link("pages/1_products.py", label="Go to Products", icon="📦")

with col2:
    st.markdown("### 🎫 Active Tickets")
    st.markdown(
        "View the current open tickets in Zoho Desk "
        "that match your configured products and statuses."
    )
    st.page_link("pages/2_active_tickets.py", label="Go to Active Tickets", icon="🎫")

st.markdown("---")
st.caption("Zoho Desk → Microsoft Teams notification service. Managed via products.json.")
