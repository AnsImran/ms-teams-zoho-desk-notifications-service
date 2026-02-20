import os
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

def env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def iso_z(dt: datetime) -> str:
    # Zoho format: yyyy-MM-ddThh:mm:ss.SSSZ (use UTC Z)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def get_access_token() -> str:
    r = requests.post(
        "https://accounts.zoho.com/oauth/v2/token",
        data={
            "refresh_token": env("ZOHO_REFRESH_TOKEN"),
            "client_id": env("ZOHO_CLIENT_ID"),
            "client_secret": env("ZOHO_CLIENT_SECRET"),
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    print("TOKEN STATUS:", r.status_code)
    # Print raw token response too (helpful for debugging)
    print(r.text)
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    token = get_access_token()

    base = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")
    url = f"{base}/api/v1/tickets/search"

    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=24)

    created_time_range = f"{iso_z(start_utc)},{iso_z(end_utc)}"

    params = {
        "status": "Assigned,Pending,Escalated",
        "createdTimeRange": created_time_range,
        "from": 0,
        "limit": 50,
        "sortBy": "-createdTime",  # if Zoho rejects it, you'll see it in raw payload
    }

    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "orgId": env("ZOHO_DESK_ORG_ID"),
        "Accept": "application/json",
    }

    r = requests.get(url, headers=headers, params=params, timeout=30)

    print("\n=== REQUEST URL (with params) ===")
    print(r.url)

    print("\n=== STATUS ===")
    print(r.status_code)

    print("\n=== RAW PAYLOAD (exact response.text) ===")
    print(r.text)

    out_file = "zoho_search_raw_payload.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("REQUEST URL:\n")
        f.write(r.url + "\n\n")
        f.write("STATUS:\n")
        f.write(str(r.status_code) + "\n\n")
        f.write("RAW RESPONSE TEXT:\n")
        f.write(r.text)

    print(f"\nSaved to: {out_file}")

if __name__ == "__main__":
    main()