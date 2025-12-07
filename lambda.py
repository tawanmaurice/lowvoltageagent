import os
import json
import re
import time
import hashlib
import logging
from urllib.parse import urlparse

import boto3
import botocore.exceptions
import requests

# ---------------------------------------------------
# Logging setup
# ---------------------------------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------
# Environment / configuration
# ---------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")
TABLE_NAME = os.getenv("TABLE_NAME", "travel-agent-leads-v1")

# Email to send the daily/summary report *to you*, not to leads
REPORT_EMAIL = os.getenv("REPORT_EMAIL")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

ses_client = boto3.client("ses")

# ---------------------------------------------------
# Travel search definitions
# ---------------------------------------------------
TRAVEL_QUERIES = [
    '"short term rental" "1 month" "Mexico" -airbnb',
    '"furnished apartment" "monthly rental" "Mexico" -airbnb',
    '"long term rental" "apartment" "Mexico" -airbnb',
]

# Domains we never want (pure social/junk for this use case)
JUNK_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "youtube.com",
    "www.youtube.com",
}

# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def normalize_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)


def extract_emails(text: str):
    if not text:
        return []
    emails = set(EMAIL_REGEX.findall(text))
    # Filter obvious garbage if needed later
    return sorted(emails)


def google_search(query: str):
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        logger.error("Missing GOOGLE_API_KEY or GOOGLE_CX.")
        return []

    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "num": 10,
    }
    resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
    if resp.status_code != 200:
        logger.error("Google search failed (%s): %s", resp.status_code, resp.text)
        return []

    data = resp.json()
    return data.get("items", [])


def make_lead_id(url: str, query: str) -> str:
    h = hashlib.sha256()
    h.update(url.encode("utf-8"))
    h.update(query.encode("utf-8"))
    return h.hexdigest()


def upsert_lead(item, query: str, agent_name: str = "travel_agent_v1"):
    url = item.get("link")
    title = item.get("title", "")
    snippet = item.get("snippet", "")

    if not url:
        return None

    domain = normalize_domain(url)
    if not domain:
        logger.info("Skipping item with invalid domain: %s", url)
        return None

    if domain in JUNK_DOMAINS:
        logger.info("Skipping junk/social domain: %s", domain)
        return None

    # Extract potential emails from snippet only (we're being conservative)
    emails = extract_emails(snippet)

    lead_id = make_lead_id(url, query)
    now_ts = int(time.time())

    item_to_save = {
        "id": lead_id,
        "url": url,
        "title": title,
        "snippet": snippet,
        "domain": domain,
        "source_query": query,
        "agent_name": agent_name,
        "emails": emails,
        "created_at": now_ts,
    }

    table.put_item(Item=item_to_save)
    logger.info(
        "Upserted lead %s for URL=%s",
        lead_id,
        url,
    )
    return item_to_save


def send_summary_email(leads, total_saved: int):
    """
    Send a simple summary email to REPORT_EMAIL using SES.
    We ONLY email you, not the leads.
    """
    if not REPORT_EMAIL:
        logger.warning("REPORT_EMAIL not set; skipping SES summary email.")
        return

    if not leads:
        logger.info("No leads collected; skipping summary email.")
        return

    # Build a short text summary (cap at 20 URLs so email isn't huge)
    lines = []
    lines.append(f"Travel agent just completed a run.")
    lines.append(f"Total records saved this run: {total_saved}")
    lines.append("")
    lines.append("Sample URLs from this run:")

    for lead in leads[:20]:
        url = lead.get("url", "N/A")
        title = lead.get("title", "").strip()
        lines.append(f"- {title[:80]} ({url})")

    body_text = "\n".join(lines)

    subject = "Travel Agent Report - New Leads Collected"

    try:
        response = ses_client.send_email(
            Source=REPORT_EMAIL,
            Destination={"ToAddresses": [REPORT_EMAIL]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                },
            },
        )
        logger.info("SES summary email sent. MessageId=%s", response["MessageId"])
    except botocore.exceptions.ClientError as e:
        logger.error("Failed to send SES email: %s", e)
    except Exception as e:
        logger.error("Unexpected error sending SES email: %s", e)


# ---------------------------------------------------
# Lambda handler
# ---------------------------------------------------
def lambda_handler(event, context):
    logger.info("Travel agent scanning started.")
    total_saved = 0
    leads_this_run = []

    for query in TRAVEL_QUERIES:
        items = google_search(query)
        logger.info(
            'Google search for "%s" returned %d items.',
            query,
            len(items),
        )
        for item in items:
            lead = upsert_lead(item, query, agent_name="travel_agent_v1")
            if lead:
                total_saved += 1
                leads_this_run.append(lead)

    logger.info(
        "Travel agent completed. Saved %d records.",
        total_saved,
    )

    # Send SES summary to you (if configured)
    send_summary_email(leads_this_run, total_saved)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Travel agent completed.",
                "saved": total_saved,
            }
        ),
    }
