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

# DynamoDB table for low-voltage leads
TABLE_NAME = os.getenv("TABLE_NAME", "low-voltage-leads-v1")

# Email to send the daily/summary report FROM and TO you
REPORT_EMAIL = os.getenv("REPORT_EMAIL")

# Extra fixed recipient (Omar). Make sure this is VERIFIED in SES.
OMAR_EMAIL = "oboyd@hdcnetworks.com"

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

ses_client = boto3.client("ses")

# ---------------------------------------------------
# Low-voltage search definitions (New York focused)
# ---------------------------------------------------
LOW_VOLTAGE_QUERIES = [
    # Your original prime phrases, tightened and with -filetype:pdf to avoid random PDFs
    '"commercial low voltage contractor" "New York" -filetype:pdf',
    '"property management" "Wi-Fi" "intercom" "CCTV" "NYC" -filetype:pdf',
    '"general contractor" "network cabling" "New York City" -filetype:pdf',
    '"IT service company" "structured cabling" "New York City" -filetype:pdf',
    '"school" "Wi-Fi" "CCTV" "Structured Cabling" "Fiber Optics" "Access Control" "security camera contractor" "New York City" -filetype:pdf',
    '"low voltage RFP" "New York City" -filetype:pdf',
    '"access control bid" "New York City" -filetype:pdf',
    '"security camera bid" "New York" -filetype:pdf',

    # Extra RFP / bid focused phrases
    '"security camera" "request for proposals" "New York" -filetype:pdf',
    '"access control" "request for proposals" "New York" -filetype:pdf',
    '"structured cabling" "RFP" "NYC" -filetype:pdf',
    '"low voltage" "invitation to bid" "New York" -filetype:pdf',
    '"CCTV" "bid notice" "New York City" -filetype:pdf',
    '"campus security" "RFP" "New York" -filetype:pdf',
    '"college campus" "structured cabling" "New York" -filetype:pdf',
    '"municipal" "security camera RFP" "NYC" -filetype:pdf',
]

# Domains we NEVER want (social, job boards, random junk)
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
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
    "glassdoor.com",
    "www.glassdoor.com",
}

# Domains (or suffixes) we ALWAYS care about even if text is weaker:
# gov, school, and official-ish things
IMPORTANT_DOMAIN_SUFFIXES = [
    ".nyc.gov",
    ".ny.gov",
    ".gov",               # catch city/municipal sites
    ".k12.ny.us",
    ".edu",               # universities, colleges
    "schools.nyc.gov",
]

# Text must look like it's tied to New York somehow (if not important domain)
LOCATION_KEYWORDS = [
    "new york",
    "nyc",
    "new york city",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
]

# Words that suggest an actual opportunity / procurement
OPPORTUNITY_KEYWORDS = [
    "rfp",
    "request for proposals",
    "request for proposal",
    "invitation to bid",
    "invitation for bid",
    "ifb",
    "bid",
    "bids",
    "bidding",
    "solicitation",
    "tender",
    "scope of work",
    "statement of work",
    "sow",
    "proposal due",
    "proposals due",
    "vendor",
    "contractor",
    "procurement",
]


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


def is_junk_domain(domain: str) -> bool:
    return domain in JUNK_DOMAINS


def is_important_domain(domain: str) -> bool:
    """
    True if this is a gov/school/official-ish domain we always want,
    even if the content isn't obviously RFP-ish.
    """
    for suffix in IMPORTANT_DOMAIN_SUFFIXES:
        if domain.endswith(suffix):
            return True
    return False


def looks_like_new_york(text: str) -> bool:
    """
    Check if title/snippet mentions New York in some form.
    """
    lowered = text.lower()
    return any(keyword in lowered for keyword in LOCATION_KEYWORDS)


def looks_like_opportunity(text: str) -> bool:
    """
    Check if title/snippet looks like an RFP/bid/procurement opportunity.
    """
    lowered = text.lower()
    return any(keyword in lowered for keyword in OPPORTUNITY_KEYWORDS)


EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)


def extract_emails(text: str):
    if not text:
        return []
    emails = set(EMAIL_REGEX.findall(text))
    # Later we could filter out obvious junk if needed
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
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=10,
        )
    except Exception as e:
        logger.error("Google search request failed: %s", e)
        return []

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


def upsert_lead(item, query: str, agent_name: str = "low_voltage_agent_v2_noheadless"):
    url = item.get("link")
    title = item.get("title", "") or ""
    snippet = item.get("snippet", "") or ""

    if not url:
        return None

    domain = normalize_domain(url)
    if not domain:
        logger.info("Skipping item with invalid domain: %s", url)
        return None

    if is_junk_domain(domain):
        logger.info("Skipping junk/social/job/academic domain: %s (url=%s)", domain, url)
        return None

    combined_text = f"{title}\n{snippet}"

    important = is_important_domain(domain)
    has_location = looks_like_new_york(combined_text)
    has_opportunity = looks_like_opportunity(combined_text)

    # Filtering logic:
    # - If it's an important domain (gov/school/etc.), we keep it as long as it's NY-ish OR opportunity-ish.
    # - If it's not important, we want BOTH:
    #       (NY location) AND (RFP/bid/procurement signal)
    if important:
        if not (has_location or has_opportunity):
            logger.info(
                "Skipping official domain without NY or opportunity signal: %s (url=%s)",
                domain,
                url,
            )
            return None
    else:
        if not has_location or not has_opportunity:
            logger.info(
                "Skipping non-official domain without both NY and opportunity signal: %s (url=%s)",
                domain,
                url,
            )
            return None

    # Extract potential emails from title + snippet
    emails = extract_emails(title + " " + snippet)

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
        "has_location_ny": has_location,
        "has_opportunity_signal": has_opportunity,
        "is_important_domain": important,
        "created_at": now_ts,
    }

    table.put_item(Item=item_to_save)
    logger.info(
        "Upserted low-voltage lead %s for URL=%s (important=%s, ny=%s, opp=%s)",
        lead_id,
        url,
        important,
        has_location,
        has_opportunity,
    )
    return item_to_save


def get_report_recipients():
    """
    Build the list of report recipients.
    - Always includes REPORT_EMAIL (from env) if set.
    - Always includes Omar's email.
    - De-duplicates and filters empties.
    NOTE: All recipients must be verified in SES if your account is in sandbox.
    """
    candidates = [REPORT_EMAIL, OMAR_EMAIL]
    recipients = sorted({addr for addr in candidates if addr})
    if not recipients:
        logger.warning("No report recipients configured (REPORT_EMAIL/OMAR_EMAIL empty).")
    return recipients


def send_summary_email(leads, total_saved: int):
    """
    Send a summary email using SES.
    We ONLY email you + Omar, not the leads themselves.
    """
    recipients = get_report_recipients()
    if not recipients:
        logger.warning("No report recipients configured; skipping SES summary email.")
        return

    if not leads:
        logger.info("No leads collected; skipping summary email.")
        return

    if not REPORT_EMAIL:
        # We use REPORT_EMAIL as the SES Source, so we must have it.
        logger.warning("REPORT_EMAIL is not set; cannot send SES email (Source missing).")
        return

    # Build a short text summary (cap at 30 URLs so email isn't huge)
    lines = []
    lines.append("Low Voltage Agent (NYC) just completed a run.")
    lines.append(f"Total records saved this run: {total_saved}")
    lines.append("")
    lines.append("Sample URLs from this run:")
    lines.append("(Flags: [NY?] [Opportunity?] [Important domain?])")
    lines.append("")

    for lead in leads[:30]:
        url = lead.get("url", "N/A")
        title = (lead.get("title") or "").strip()
        has_loc = lead.get("has_location_ny")
        has_opp = lead.get("has_opportunity_signal")
        important = lead.get("is_important_domain")

        flags = []
        flags.append("NY" if has_loc else "no-NY")
        flags.append("RFP" if has_opp else "no-RFP")
        flags.append("official" if important else "regular")

        flags_str = ", ".join(flags)
        lines.append(f"- [{flags_str}] {title[:80]} ({url})")

    body_text = "\n".join(lines)

    subject = "Low Voltage Agent Report - NYC RFP / Bid Leads"

    try:
        response = ses_client.send_email(
            Source=REPORT_EMAIL,
            Destination={"ToAddresses": recipients},
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
    logger.info("Low Voltage Agent v2 (no headless, New York) scanning started.")

    total_saved = 0
    leads_this_run = []
    seen_urls = set()  # de-duplicate within a run

    for query in LOW_VOLTAGE_QUERIES:
        items = google_search(query)
        logger.info(
            'Google search for "%s" returned %d items.',
            query,
            len(items),
        )

        for item in items:
            url = item.get("link")
            if not url:
                continue

            if url in seen_urls:
                logger.info("Skipping duplicate URL in this run: %s", url)
                continue

            seen_urls.add(url)

            lead = upsert_lead(item, query, agent_name="low_voltage_agent_v2_noheadless")
            if lead:
                total_saved += 1
                leads_this_run.append(lead)

    logger.info(
        "Low Voltage Agent v2 (no headless, New York) completed. Saved %d records.",
        total_saved,
    )

    # Send SES summary to you + Omar (if configured)
    send_summary_email(leads_this_run, total_saved)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Low Voltage Agent v2 (no headless, New York) completed.",
                "saved": total_saved,
            }
        ),
    }
