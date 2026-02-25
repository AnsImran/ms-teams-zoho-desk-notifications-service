"""
Send a tiny Teams Adaptive Card to a webhook to verify which channel/group it maps to.

Usage:
    python src/superstat_cron/test_teams_webhook.py \
        --title "Webhook Smoke Test" \
        --note "This is only a test from test_teams_webhook.py"

Configuration:
    - TEAMS_WEBHOOK_URL must be set (dotenv is loaded if present).
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv


def build_test_card(title: str, note: str) -> dict:
    """Create a compact Adaptive Card payload similar to superstat_watch.py."""
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "text": note, "wrap": True, "spacing": "Small"},
        ],
    }
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }


def send_card(webhook_url: str, payload: dict) -> None:
    """POST the payload to the webhook and raise on HTTP errors."""
    r = requests.post(webhook_url, json=payload, timeout=15)
    if r.status_code >= 400:
        print("Teams webhook returned", r.status_code, file=sys.stderr)
        print(r.text[:2000], file=sys.stderr)
    r.raise_for_status()


def main(argv: list[str]) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Send a test Teams Adaptive Card via webhook.")
    parser.add_argument("--title", default="Webhook Smoke Test", help="Card title text.")
    parser.add_argument("--note", default="This is a test message to identify this webhook's destination.", help="Body text.")
    args = parser.parse_args(argv)

    webhook = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
    if not webhook:
        print("Missing TEAMS_WEBHOOK_URL environment variable.", file=sys.stderr)
        return 1

    payload = build_test_card(args.title, args.note)
    send_card(webhook, payload)
    print("Sent test card to Teams webhook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
