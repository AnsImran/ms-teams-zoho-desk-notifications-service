import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def env(name, default=None, required=True):
    v = os.getenv(name, default)
    if required and (v is None or str(v).strip() == ""):
        raise RuntimeError(f"Missing env var: {name}")
    return str(v).strip()

def get_access_token():
    accounts = env("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.com", required=False).rstrip("/")
    r = requests.post(
        f"{accounts}/oauth/v2/token",
        data={
            "refresh_token": env("ZOHO_REFRESH_TOKEN"),
            "client_id": env("ZOHO_CLIENT_ID"),
            "client_secret": env("ZOHO_CLIENT_SECRET"),
            "grant_type": "refresh_token",
        },
        timeout=30
    )
    print("TOKEN STATUS:", r.status_code)
    print("TOKEN BODY:", r.text)
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    desk_base = env("ZOHO_DESK_BASE", "https://desk.zoho.com", required=False).rstrip("/")
    org_id = env("ZOHO_DESK_ORG_ID")  # you have: 898106677

    access_token = get_access_token()

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "orgId": org_id,
        "Accept": "application/json",
    }

    # ✅ simplest Desk API call
    url = f"{desk_base}/api/v1/tickets"
    params = {"limit": "5"}  # keep it small

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    print("\nTICKETS URL:", resp.url)
    print("TICKETS STATUS:", resp.status_code)
    print("TICKETS BODY (raw):")
    print(resp.text)

    try:
        data = resp.json()
        print("\nTICKETS BODY (pretty JSON):")
        print(json.dumps(data, indent=2))
    except Exception:
        pass

if __name__ == "__main__":
    main()