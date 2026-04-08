"""Shared authentication gate used by every dashboard page."""  # Module purpose.

import streamlit as st                                        # Streamlit UI framework.
import streamlit_authenticator as stauth                      # Login/logout with session management.


def require_login() -> None:                                                     # Enforce authentication on the current page.
    """Show login form if not authenticated; call st.stop() to block page content."""  # Docstring in plain words.

    auth_config = {                                                              # Build auth config from secrets.
        "credentials": {                                                         # User credentials section.
            "usernames": {                                                       # Username-to-details mapping.
                st.secrets["auth"]["username"]: {                                # Single admin user.
                    "name":     st.secrets["auth"]["name"],                      # Display name.
                    "password": st.secrets["auth"]["password_hash"],             # Bcrypt hash.
                }
            }
        },
        "cookie": {                                                              # Session cookie config.
            "name":        "dashboard_auth",                                     # Cookie name.
            "key":         st.secrets["auth"]["cookie_key"],                     # Cookie encryption key.
            "expiry_days": 7,                                                    # Cookie lifetime.
        },
    }

    authenticator = stauth.Authenticate(                                         # Create authenticator instance.
        credentials        = auth_config["credentials"],                         # Pass credentials.
        cookie_name        = auth_config["cookie"]["name"],                      # Pass cookie name.
        cookie_key         = auth_config["cookie"]["key"],                       # Pass cookie key.
        cookie_expiry_days = auth_config["cookie"]["expiry_days"],               # Pass cookie lifetime.
    )

    authenticator.login(location="main")                                         # Render login form (v0.4+ stores result in session_state).

    if st.session_state.get("authentication_status") is False:                   # Wrong credentials entered.
        st.error("Incorrect username or password.")                              # Show error.
        st.stop()                                                                # Block page content.

    if not st.session_state.get("authentication_status"):                        # Not logged in yet.
        st.info("Please log in to access the dashboard.")                        # Show prompt.
        st.stop()                                                                # Block page content.

    st.sidebar.title(f"Welcome, {st.session_state.get('name', 'User')}")         # Greet the user.
    authenticator.logout("Logout", "sidebar")                                    # Add logout button.
