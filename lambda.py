import os
import json
import re
import time
import logging
import hashlib
from urllib.parse import urlparse

import boto3
import botocore.exceptions
import requests

# ---------------------------------------------------
# Logging setup
# ---------------------------------------------------
logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# ---------------------------------------------------
# Environment / configuration
# ---------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")
TABLE_NAME = os.getenv("TABLE_NAME")

if not GOOGLE_API_KEY or not GOOGLE_CX or not TABLE_NAME:
    logger.warning(
        "One or more required environment variables are missing: "
        "GOOGLE_API_KEY, GOOGLE_CX, TABLE_NAME"
    )

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# ---------------------------------------------------
# Search definitions
# Focus: commercial work, prisons / justice, architects / engineers, bids/RFPs
# in and around New York + nearby states/cities
# ---------------------------------------------------
SEARCH_QUERIES = [
    # Core commercial low-voltage work (small jobs + general commercial)
    '"commercial low voltage contractor" "New York"',
    '"structured cabling" "office" "NYC"',
    '"network cabling contractor" "New York City"',
    '"low voltage contractor" "Philadelphia" "commercial"',
    '"low voltage contractor" "Boston" "commercial"',
    '"low voltage contractor" "Connecticut" "business"',
    '"low voltage contractor" "New Jersey" "office"',
    '"low voltage contractor" "Baltimore" "commercial"',

    # Correctional / justice facilities (prisons, jails, detention)
    '"security camera" "correctional facility" "bid"',
    '"access control" "detention center" "RFP"',
    '"surveillance" "county jail" "low voltage"',
    '"network cabling" "correctional facility" "New York"',
    '"security system" "state prison" "RFP"',

    # Architects & engineering firms (blueprint / spec writers)
    '"low voltage design" architect "New York"',
    '"security systems" "consulting engineer" "NYC"',
    '"structured cabling" "MEP engineer" "Boston"',
    '"low voltage" "electrical engineer" "Philadelphia"',
    '"security camera" "architectural firm" "New York"',
    '"access control" "architect" "specifications"',

    # Bids / RFPs / long-term contract work
    '"low voltage" "RFP" "New York"',
    '"security camera" "RFP" "New Jersey"',
    '"access control" "bid" "Connecticut"',
    '"surveillance system" "RFP" "Pennsylvania"',
]

# ---------------------------------------------------
# Size limits to avoid DynamoDB 400 KB item limit
# ---------------------------------------------------
MAX_EMAILS = 15
MAX_PHONES = 10
MAX_ADDRESSES = 10
MAX_TITLE_LEN = 300
MAX_SEARCH_SNIPPET_LEN = 500
MAX_CONTACT_SNIPPET_LEN = 800

# ---------------------------------------------------
# Limits for searches per run
# ---------------------------------------------------
# Limit depth / cost so the Lambda stays fast & cheap
MAX_RESULTS_PER_QUERY = 3  # only top 3 per query to speed things up

# NEW: cap how many search queries run per Lambda invocation
MAX_QUERIES_PER_RUN = int(os.getenv("MAX_QUERIES_PER_RUN", "8"))

# ---------------------------------------------------
# Regex patterns
# ---------------------------------------------------
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Basic North American phone number formats
PHONE_REGEX = re.compile(
    r"(\+?1[-.\s]*)?(\(?\d{3}\)?[-.\s]*)\d{3}[-.\s]*\d{4}"
)

# Very rough street-address pattern (US-style)
ADDRESS_REGEX = re.compile(
    r"\d{1,5}\s+[A-Za-z0-9.\s]+"
    r"(Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Blvd\.|Lane|Ln\.|Drive|Dr\.|Court|Ct\.|Way|Terrace|Ter\.|Place|Pl\.)"
    r"[,A-Za-z0-9\s\-]*"
)

# Domains we intentionally ignore (social, job boards, generic directories, his own site)
SKIP_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "yelp.com",
    "angi.com",
    "homeadvisor.com",
    "yellowpages.com",
    "bing.com",
    "google.com",
    "maps.google.com",
    "youtube.com",
    "pinterest.com",
    "hdcnetworks.com",  # don't treat his own site as a lead
}

# ---------------------------------------------------
# Small helpers
# ---------------------------------------------------
def truncate_string(value, max_len):
    if not value:
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def truncate_list(values, max_items, per_item_max_len=None):
    if not values:
        return []
    trimmed = list(values)[:max_items]
    if per_item_max_len is not None:
        trimmed = [truncate_string(v, per_item_max_len) for v in trimmed]
    return trimmed


# ---------------------------------------------------
# Google search (freshness-biased)
# ---------------------------------------------------
def google_search(query):
    """
    Call Google Programmable Search API.
    We bias toward FRESH results (last 3 months, sorted by date)
    and then only take the top MAX_RESULTS_PER_QUERY.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        logger.error("Google API key or CX is not set.")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "start": 1,
        "sort": "date",        # bias toward newer content
        "dateRestrict": "m3",  # last 3 months
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        logger.info(f"Google search for '{query}' returned {len(items)} items.")
        return items[:MAX_RESULTS_PER_QUERY]
    except requests.RequestException as e:
        logger.error(f"Error calling Google Custom Search API: {e}")
        return []


# ---------------------------------------------------
# Page fetching & text extraction (HTML + PDFs)
# ---------------------------------------------------
def strip_html(html_text):
    """
    Very simple HTML-to-text using regex (no external libs).
    """
    if not html_text:
        return ""
    # Remove script/style blocks
    html_text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html_text)
    # Remove all tags
    text = re.sub(r"<[^>]+>", " ", html_text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_page_text(url):
    """
    Fetch page content and return plain text.
    - For HTML: strip tags
    - For PDFs: decode bytes and run regex directly on text
    - For CSV and other giant data files: skip to avoid huge items
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LowVoltageAgent/1.0)"
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()

        # Skip obviously huge dataset types (CSV etc.) – they create giant items
        if "text/csv" in content_type or url.lower().endswith(".csv"):
            logger.info(f"Skipping text content for CSV-like URL: {url}")
            return ""

        if "pdf" in content_type or url.lower().endswith(".pdf"):
            # crude PDF text extraction: decode bytes and search with regex
            try:
                text = resp.content.decode("latin-1", errors="ignore")
            except Exception as e:
                logger.warning(f"Failed to decode PDF {url}: {e}")
                return ""
            return text
        else:
            html = resp.text
            return strip_html(html)
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""


# ---------------------------------------------------
# Contact info extraction
# ---------------------------------------------------
def extract_emails(text):
    if not text:
        return []
    emails = set(re.findall(EMAIL_REGEX, text))
    return list(emails)


def extract_phones(text):
    if not text:
        return []
    phones = set()
    for match in re.finditer(PHONE_REGEX, text):
        full = match.group(0)
        cleaned = re.sub(r"\s+", " ", full).strip()
        phones.add(cleaned)
    return list(phones)


def extract_addresses(text):
    if not text:
        return []
    addresses = set()
    for match in re.finditer(ADDRESS_REGEX, text):
        addr = match.group(0)
        addr = re.sub(r"\s+", " ", addr).strip()
        addresses.add(addr)
    return list(addresses)


def extract_contact_name(text):
    """
    Try to find a contact person's name based on simple patterns.
    This is heuristic and may be empty or just a business name.
    """
    if not text:
        return None

    patterns = [
        r"Contact\s*[:\-]\s*(.+)",
        r"Contacts\s*[:\-]\s*(.+)",
        r"Attn\.?\s*[:\-]?\s*(.+)",
        r"Attention\s*[:\-]\s*(.+)",
    ]

    snippet = text[:2000]  # only first part to keep it cheap

    for pat in patterns:
        m = re.search(pat, snippet, flags=re.IGNORECASE)
        if m:
            name_part = m.group(1)
            # Stop at first comma or "at" or "for"
            name_part = re.split(r"[,\n]| at | for ", name_part, maxsplit=1)[0]
            name_part = name_part.strip()
            if 2 <= len(name_part.split()) <= 5:
                return name_part

    return None


def find_contact_snippet(text):
    """
    Grab a small block of text around where 'contact' or phone/email appears.
    Helps you see address/name even if we didn't parse it perfectly.
    """
    if not text:
        return None

    lower = text.lower()
    idx = lower.find("contact")
    if idx == -1:
        for keyword in ["phone", "tel", "call", "email"]:
            idx = lower.find(keyword)
            if idx != -1:
                break

    if idx == -1:
        # Fall back to first 400 chars of the page
        return text[:400]

    start = max(0, idx - 200)
    end = min(len(text), idx + 400)
    snippet = text[start:end]
    return snippet.strip()


# ---------------------------------------------------
# Helpers for DynamoDB + domain filtering
# ---------------------------------------------------
def make_lead_id(url, email=None):
    base = (url or "") + "|" + (email or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def save_lead_to_dynamo(item):
    if not table:
        logger.error("DynamoDB table is not configured (TABLE_NAME missing).")
        return False
    try:
        table.put_item(Item=item)
        return True
    except botocore.exceptions.ClientError as e:
        # Specifically catch size issues and log/skip the item
        if e.response.get("Error", {}).get("Code") == "ValidationException":
            logger.error(
                f"Skipping item due to DynamoDB ValidationException (likely size): "
                f"{e.response.get('Error', {}).get('Message')}"
            )
            return False
        logger.error(f"Error writing to DynamoDB: {e}")
        return False
    except botocore.exceptions.BotoCoreError as e:
        logger.error(f"Error writing to DynamoDB (BotoCoreError): {e}")
        return False


def build_lead_item(
    result,
    page_text,
    emails,
    phones,
    addresses,
    contact_name,
    contact_snippet,
    chosen_email=None,
    source_query=None,
):
    url = result.get("link")
    title = result.get("title") or ""
    snippet = result.get("snippet") or ""
    parsed = urlparse(url) if url else None
    domain = parsed.netloc if parsed else None

    # Apply caps to lists and text fields to avoid giant items
    emails_capped = truncate_list(emails or [], MAX_EMAILS, per_item_max_len=254)
    phones_capped = truncate_list(phones or [], MAX_PHONES, per_item_max_len=64)
    addresses_capped = truncate_list(addresses or [], MAX_ADDRESSES, per_item_max_len=512)
    contact_snippet_capped = truncate_string(
        contact_snippet or "", MAX_CONTACT_SNIPPET_LEN
    )

    lead_id = make_lead_id(url, chosen_email)

    item = {
        "id": lead_id,
        "url": truncate_string(url or "", 1000),
        "title": truncate_string(title, MAX_TITLE_LEN),
        "snippet": truncate_string(snippet, MAX_SEARCH_SNIPPET_LEN),
        "domain": truncate_string(domain or "", 255),
        "source_query": truncate_string(source_query or "", 500),
        "created_at": int(time.time()),
        # Contact info (best-effort, capped)
        "emails": emails_capped,
        "phones": phones_capped,
        "addresses": addresses_capped,
    }

    if chosen_email:
        item["primary_email"] = truncate_string(chosen_email, 254)

    if contact_name:
        item["contact_name"] = truncate_string(contact_name, 255)

    if contact_snippet_capped:
        item["contact_snippet"] = contact_snippet_capped

    return item


def is_high_quality_lead(emails, phones, addresses):
    """
    SAFEGUARD: Only keep leads where there is at least
    one way to reach them (email, phone, or address).
    """
    return bool(emails or phones or addresses)


def should_skip_domain(url):
    """
    SAFEGUARD: Skip social sites, job boards, giant directories,
    and his own site.
    """
    if not url:
        return True
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for bad in SKIP_DOMAINS:
        if domain == bad or domain.endswith("." + bad):
            return True
    return False


def try_contact_pages(base_url, max_pages=2):
    """
    Go a little deeper: try common contact URLs on the same domain.
    This is how we "go deep" without going crazy.
    """
    if not base_url:
        return []

    try:
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return []

    candidates = [
        f"{base}/contact",
        f"{base}/contact-us",
    ]

    texts = []
    for url in candidates[:max_pages]:
        text = fetch_page_text(url)
        if text:
            texts.append(text)
    return texts


# ---------------------------------------------------
# Core processing
# ---------------------------------------------------
def process_search_results(query):
    """
    For a given query:
    - call Google Custom Search (fresh results only)
    - for each result, skip junk domains
    - fetch main page (+ contact pages) as text (including PDFs)
    - extract: emails, phones, addresses, contact name, snippet
    - write high-quality leads to DynamoDB
    """
    saved_count = 0
    items = google_search(query)

    for result in items:
        url = result.get("link")
        if not url:
            continue

        if should_skip_domain(url):
            logger.info(f"Skipping domain (low quality or social): {url}")
            continue

        logger.info(f"Processing search result URL: {url}")

        # Main page
        page_text = fetch_page_text(url)
        # Try 1–2 obvious contact URLs on same domain
        extra_texts = try_contact_pages(url, max_pages=2)

        combined_text = page_text + " " + " ".join(extra_texts)

        emails_found = extract_emails(combined_text)
        phones_found = extract_phones(combined_text)
        addresses_found = extract_addresses(combined_text)
        contact_name = extract_contact_name(combined_text)
        contact_snippet = find_contact_snippet(combined_text)

        # SAFEGUARD: only keep leads with at least a phone/email/address
        if not is_high_quality_lead(emails_found, phones_found, addresses_found):
            logger.info(f"Skipping low-quality lead (no contact methods) for URL: {url}")
            continue

        # If there are emails, store multiple entries so you can filter on primary_email
        if emails_found:
            for email in emails_found:
                item = build_lead_item(
                    result=result,
                    page_text=combined_text,
                    emails=emails_found,
                    phones=phones_found,
                    addresses=addresses_found,
                    contact_name=contact_name,
                    contact_snippet=contact_snippet,
                    chosen_email=email,
                    source_query=query,
                )
                if save_lead_to_dynamo(item):
                    saved_count += 1
        else:
            # No email but still have phones / addresses/etc → still valuable
            item = build_lead_item(
                result=result,
                page_text=combined_text,
                emails=[],
                phones=phones_found,
                addresses=addresses_found,
                contact_name=contact_name,
                contact_snippet=contact_snippet,
                chosen_email=None,
                source_query=query,
            )
            if save_lead_to_dynamo(item):
                saved_count += 1

    logger.info(f"Query '{query}' saved {saved_count} items to DynamoDB.")
    return saved_count


# ---------------------------------------------------
# Lambda handler
# ---------------------------------------------------
def lambda_handler(event, context):
    logger.info("Starting low-voltage lead agent run...")
    total_saved = 0

    # Only run up to MAX_QUERIES_PER_RUN each time so it doesn't take forever
    for q in SEARCH_QUERIES[:MAX_QUERIES_PER_RUN]:
        logger.info(f"Running search for query: {q}")
        saved_for_query = process_search_results(q)
        total_saved += saved_for_query

    logger.info(f"Low-voltage lead agent completed. Total items saved: {total_saved}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Low-voltage agent ran successfully.",
            "saved": total_saved
        })
    }
