"""Dashboard entry point with authentication gate."""  # Module purpose.

import sys                                                    # Add project root to path.
import os                                                     # Build file paths.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # Allow imports from project root.

import streamlit as st                                        # Streamlit UI framework.
from dashboard.utils.auth import require_login                # Shared auth gate.


# Page config must be the first Streamlit command.
st.set_page_config(
    page_title  = "Teams Notifications Dashboard",
    page_icon   = "🔔",
    layout      = "wide",
)

require_login()                                               # Block page content until authenticated.

st.title("Teams Notifications Dashboard")
st.markdown("Manage product notifications and view active Zoho Desk tickets.")
st.markdown("Use the sidebar to navigate between pages.")
