import os, requests, json
from dotenv import load_dotenv
load_dotenv()

def token():
    r = requests.post(
        "https://accounts.zoho.com/oauth/v2/token",
        data={
            "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
            "client_id": os.environ["ZOHO_CLIENT_ID"],
            "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def headers(t):
    return {
        "Authorization": f"Zoho-oauthtoken {t}",
        "orgId": os.environ["ZOHO_DESK_ORG_ID"],
        "Accept": "application/json",
    }

def main():
    base = os.getenv("ZOHO_DESK_BASE", "https://desk.zoho.com").rstrip("/")
    tid = os.environ.get("TEST_TICKET_ID")  # set this to the ticket id
    if not tid:
        raise SystemExit("Set TEST_TICKET_ID in env to the ticket id from the URL.")

    t = token()

    # 1) ticket details
    url1 = f"{base}/api/v1/tickets/{tid}"
    r1 = requests.get(url1, headers=headers(t), timeout=30)
    print("TICKET DETAILS STATUS:", r1.status_code)
    print("Has description:", "description" in r1.text or "descriptionText" in r1.text)

    if r1.ok:
        d = r1.json()
        desc = (d.get("description") or d.get("descriptionText") or "")
        print("\n--- DESCRIPTION FROM /tickets/{id} ---\n")
        print(desc[:1500])

    # 2) threads (conversations)
    url2 = f"{base}/api/v1/tickets/{tid}/threads"
    r2 = requests.get(url2, headers=headers(t), timeout=30)
    print("\nTHREADS STATUS:", r2.status_code)

    if r2.ok:
        data = r2.json()
        print("Threads keys:", list(data.keys()) if isinstance(data, dict) else type(data))
        print("\n--- RAW THREADS (first 1) ---\n")
        if isinstance(data, dict) and "data" in data and data["data"]:
            print(json.dumps(data["data"][0], indent=2)[:2000])
        else:
            print(json.dumps(data, indent=2)[:2000])

if __name__ == "__main__":
    main()