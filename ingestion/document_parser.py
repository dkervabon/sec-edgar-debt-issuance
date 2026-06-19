"""
Fetch 8-K documents from SEC EDGAR and parse the Item 2.03 section to
extract debt instrument details.

Document URL: https://www.sec.gov/Archives/edgar/data/{cik}/{clean_adsh}/{primary_doc}
The primary_doc filename comes from the EFTS _id field captured during the metadata fetch.

Rate-limit: SEC guidance is < 10 req/s.
With MAX_WORKERS=5 and FETCH_DELAY=0.6s each worker's effective rate is
  5 / (0.6 + ~0.35 network) ≈ 5.3 req/s, safely under the cap.
"""
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE = "https://www.sec.gov/Archives/edgar/data"
FETCH_DELAY = 0.6
MAX_WORKERS = 5

# ── instrument-type patterns (priority-ordered, most specific first) ──────────
_INSTRUMENTS = [
    (r"revolving credit (?:facility|agreement)",  "revolving_credit_facility"),
    (r"\brevolver\b",                             "revolving_credit_facility"),
    (r"delayed[\s-]draw term loan",               "term_loan"),
    (r"term loan [ab]\b",                         "term_loan"),
    (r"\bterm loan\b",                            "term_loan"),
    (r"senior secured notes?",                    "senior_secured_notes"),
    (r"senior unsecured notes?",                  "senior_unsecured_notes"),
    (r"convertible (?:senior )?notes?",           "convertible_notes"),
    (r"junior subordinated (?:notes?|debentures?)","junior_subordinated"),
    (r"subordinated notes?",                      "subordinated_notes"),
    (r"senior notes?",                            "senior_notes"),
    (r"guaranteed notes?",                        "guaranteed_notes"),
    (r"senior debentures?",                       "senior_debentures"),
    (r"\bdebentures?\b",                          "debentures"),
    (r"commercial paper",                         "commercial_paper"),
    (r"bridge (?:loan|facility)",                 "bridge_facility"),
    (r"accounts?\s+receivable.{0,40}(?:facility|loan)", "receivables_facility"),
    (r"securiti[sz]ation\s+facility",             "securitization_facility"),
    (r"secured\s+promissory\s+note",              "secured_promissory_note"),
    (r"promissory\s+note",                        "promissory_note"),
    (r"credit (?:agreement|facility)",            "credit_facility"),
    (r"financing\s+agreement",                    "financing_agreement"),
]

_MULT = {"billion": 1_000_000_000, "million": 1_000_000, "thousand": 1_000}

_MONTHS = (
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _doc_url(cik: str, adsh: str, primary_doc: str) -> str:
    clean = adsh.replace("-", "")
    return f"{_BASE}/{int(cik)}/{clean}/{primary_doc}"


def _fetch_text(url: str, user_agent: str) -> Optional[str]:
    time.sleep(FETCH_DELAY)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=30,
        )
        if resp.status_code == 404:
            logger.warning(f"404 {url}")
            return None
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    except Exception as exc:
        logger.warning(f"Fetch failed {url}: {exc}")
        return None


def _extract_section(text: str) -> str:
    """
    Debt terms in 8-K filings are always within the first few pages.
    We normalise whitespace and take up to 25k chars, which reliably
    captures both Items 1.01 and 2.03 without fighting inline cross-
    references that fool heading-based segmentation.
    """
    normalised = re.sub(r"\s+", " ", text)
    return normalised[:25_000]


# ── field parsers ─────────────────────────────────────────────────────────────

def _parse_instrument(text: str) -> Optional[str]:
    lower = text.lower()
    for pattern, label in _INSTRUMENTS:
        if re.search(pattern, lower):
            return label
    return None


def _parse_principal(text: str) -> tuple[Optional[float], Optional[str]]:
    # "$X.X billion/million/thousand"
    m = re.search(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)",
        text,
        re.IGNORECASE,
    )
    if m:
        amount = float(m.group(1).replace(",", "")) * _MULT[m.group(2).lower()]
        return amount, m.group(0).strip()

    # "$X,XXX,XXX" exact-dollar (skip tiny amounts like $1,000 fees)
    m = re.search(r"\$\s*([\d]{1,3}(?:,[\d]{3}){2,})", text)
    if m:
        amount = float(m.group(1).replace(",", ""))
        if amount >= 1_000_000:
            return amount, m.group(0).strip()

    return None, None


def _parse_rate(text: str) -> tuple[Optional[str], Optional[str]]:
    # Floating: SOFR/LIBOR + spread
    m = re.search(
        r"((?:Term\s+)?SOFR|(?:CME\s+)?Term\s+SOFR|LIBOR|EURIBOR)"
        r"\s*(?:\+|plus)\s*([\d.]+)\s*(?:%|basis\s+points?|bps?)",
        text,
        re.IGNORECASE,
    )
    if m:
        return "floating", m.group(0).strip()

    if re.search(r"\b(SOFR|LIBOR|EURIBOR)\b", text, re.IGNORECASE):
        return "floating", "floating (reference rate detected)"

    # Fixed: X.XXX% (sanity-check range 0.1–25)
    for pattern in (
        r"(\d+(?:\.\d+)?)\s*%\s+(?:per\s+annum|senior\s+notes?|notes?|annual|coupon)",
        r"(?:interest\s+(?:rate\s+)?(?:of\s+)?)(\d+(?:\.\d+)?)%",
        r"(?:bears?\s+interest\s+(?:at\s+)?(?:a\s+rate\s+of\s+)?)(\d+(?:\.\d+)?)%",
        r"(\d+(?:\.\d+)?)\s*%",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                pct = float(m.group(1))
            except (IndexError, ValueError):
                continue
            if 0.1 <= pct <= 25:
                return "fixed", m.group(0).strip()

    return None, None


def _parse_maturity(text: str) -> Optional[str]:
    # Full date: "mature on March 15, 2030"
    m = re.search(
        rf"(?:matur(?:e[sd]?|ity)|due\s+(?:on\b|in\b)?)\s+(?:on\s+)?"
        rf"((?:{_MONTHS})[a-z]*\.?\s+\d{{1,2}},?\s+\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Just a year: "mature in 2030"
    m = re.search(
        r"(?:matur(?:e[sd]?|ity)|due)\s+(?:in\s+)?(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m and 2020 <= int(m.group(1)) <= 2060:
        return m.group(1)

    return None


# ── per-filing orchestration ──────────────────────────────────────────────────

def parse_filing(row: dict, user_agent: str, parsed_at: str) -> dict:
    accession_no = row["accession_no"]
    cik          = row.get("cik") or ""
    primary_doc  = row.get("primary_doc") or ""

    base = {
        "accession_no":         accession_no,
        "cik":                  cik or None,
        "entity_name":          row.get("entity_name"),
        "file_date":            row.get("file_date"),
        "instrument_type":      None,
        "principal_amount_usd": None,
        "principal_raw":        None,
        "interest_rate_type":   None,
        "interest_rate_raw":    None,
        "maturity_raw":         None,
        "item_203_text":        None,
        "parse_success":        False,
        "parsed_at":            parsed_at,
    }

    if not (cik and primary_doc):
        return base

    url  = _doc_url(cik, accession_no, primary_doc)
    text = _fetch_text(url, user_agent)
    if not text:
        return base

    section = _extract_section(text)

    instrument          = _parse_instrument(section)
    principal, p_raw    = _parse_principal(section)
    rate_type, rate_raw = _parse_rate(section)
    maturity            = _parse_maturity(section)

    return {
        **base,
        "instrument_type":      instrument,
        "principal_amount_usd": principal,
        "principal_raw":        p_raw,
        "interest_rate_type":   rate_type,
        "interest_rate_raw":    rate_raw,
        "maturity_raw":         maturity,
        "item_203_text":        section[:10_000],
        "parse_success":        bool(instrument or principal),
    }


def parse_all(rows: list[dict], user_agent: str, parsed_at: str) -> list[dict]:
    total   = len(rows)
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(parse_filing, row, user_agent, parsed_at): row["accession_no"]
            for row in rows
        }
        for done, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if done % 250 == 0 or done == total:
                successes = sum(1 for r in results if r["parse_success"])
                logger.info(f"Parsed {done}/{total} | {successes} succeeded so far")

    successes = sum(1 for r in results if r["parse_success"])
    logger.info(f"Document parsing complete: {successes}/{total} with extractable fields")
    return results
