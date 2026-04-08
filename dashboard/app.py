"""Dashboard entry point with authentication gate."""  # Module purpose.

import streamlit as st                                    # Streamlit UI framework.
import streamlit_authenticator as stauth                  # Login/logout with session management.
import yaml                                               # Read auth config (inline for simplicity).


# Page config must be the first Streamlit command.
st.set_page_config(
    page_title  = "Teams Notifications Dashboard",
    page_icon   = "🔔",
    layout      = "wide",
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

# Auth config loaded from Streamlit secrets (dashboard/.streamlit/secrets.toml).
# Expected secrets.toml format:
#
# [auth]
# username = "admin"
# name = "Admin"
# password_hash = "$2b$12$..."    # bcrypt hash of your password
# cookie_key = "some-random-key"
#
# Generate a hash with:  python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"

auth_config = {
    "credentials": {
        "usernames": {
            st.secrets["auth"]["username"]: {
                "name":     st.secrets["auth"]["name"],
                "password": st.secrets["auth"]["password_hash"],
            }
        }
    },
    "cookie": {
        "name":       "dashboard_auth",
        "key":        st.secrets["auth"]["cookie_key"],
        "expiry_days": 7,
    },
}

authenticator = stauth.Authenticate(
    credentials  = auth_config["credentials"],
    cookie_name  = auth_config["cookie"]["name"],
    cookie_key   = auth_config["cookie"]["key"],
    cookie_expiry_days = auth_config["cookie"]["expiry_days"],
)

name, authentication_status, username = authenticator.login(location="main")

if authentication_status is False:
    st.error("Incorrect username or password.")
    st.stop()

if authentication_status is None:
    st.info("Please log in to access the dashboard.")
    st.stop()

# ---------------------------------------------------------------------------
# Authenticated content
# ---------------------------------------------------------------------------

st.sidebar.title(f"Welcome, {name}")
authenticator.logout("Logout", "sidebar")

st.title("Teams Notifications Dashboard")
st.markdown("Manage product notifications and view active Zoho Desk tickets.")
st.markdown("Use the sidebar to navigate between pages.")
