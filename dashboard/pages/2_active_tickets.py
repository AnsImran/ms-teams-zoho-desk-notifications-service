"""Active tickets page — view current Zoho Desk tickets matching configured products."""  # Page purpose.

import sys                                                    # Add project root to path.
import os                                                     # Build file paths.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # Allow imports from project root.

import streamlit as st                                        # Streamlit UI framework.
from src.core.config_manager import load_products             # Read current product config.
from dashboard.utils.zoho_client import fetch_active_tickets  # Fetch tickets from Zoho.


st.set_page_config(page_title="Active Tickets", page_icon="🎫", layout="wide")
st.title("Active Tickets")

# ---------------------------------------------------------------------------
# Load current product config to build query
# ---------------------------------------------------------------------------

data     = load_products()
products = data.get("products", {})

if not products:
    st.warning("No products configured. Add products first on the Products page.")
    st.stop()

# Collect all product names and statuses from config.
all_product_names = []
all_statuses      = set()
for entry in products.values():
    all_product_names.extend(entry.get("target_product_names", [entry.get("name", "")]))
    all_statuses.update(entry.get("active_statuses", ["Assigned", "Pending", "Escalated"]))
all_product_names = sorted(set(all_product_names))
all_statuses      = sorted(all_statuses)

# ---------------------------------------------------------------------------
# Fetch and display tickets
# ---------------------------------------------------------------------------

st.markdown(f"**Querying:** {len(all_product_names)} product(s) with statuses: {', '.join(all_statuses)}")

if st.button("Refresh", type="primary"):
    st.rerun()

with st.spinner("Fetching tickets from Zoho Desk..."):
    tickets = fetch_active_tickets(all_product_names, all_statuses)

if not tickets:
    st.info("No active tickets found for the configured products.")
else:
    st.markdown(f"**Found {len(tickets)} active ticket(s).**")

    rows = []
    for ticket in tickets:
        # Extract product name from ticket payload.
        product_name = ""
        for key in ("productName", "product"):
            value = ticket.get(key)
            if isinstance(value, str) and value.strip():
                product_name = value.strip()
                break
            elif isinstance(value, dict):
                for sub_key in ("name", "productName"):
                    nested = value.get(sub_key)
                    if isinstance(nested, str) and nested.strip():
                        product_name = nested.strip()
                        break
            if product_name:
                break

        # Extract assignee name.
        assignee = ticket.get("assignee")
        assignee_name = ""
        if isinstance(assignee, dict):
            first = (assignee.get("firstName") or "").strip()
            last  = (assignee.get("lastName") or "").strip()
            assignee_name = " ".join(part for part in (first, last) if part)

        rows.append({
            "Ticket #":  ticket.get("ticketNumber", ""),
            "Subject":   (ticket.get("subject") or "")[:80],
            "Product":   product_name,
            "Status":    ticket.get("status", ""),
            "Assignee":  assignee_name or "(unassigned)",
            "Created":   (ticket.get("createdTime") or "")[:19].replace("T", " "),
            "Link":      ticket.get("webUrl", ""),
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)
