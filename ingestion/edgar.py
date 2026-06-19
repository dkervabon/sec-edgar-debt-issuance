"""
Fetch 8-K Item 2.03 (Creation of a Direct Financial Obligation) filings
from the SEC EDGAR full-text search API (EFTS).

Chunked by month to stay under Elasticsearch's 10k-hit-per-query limit.
SEC rate-limit guidance: < 10 req/s; we sleep 0.15 s between pages.
"""
import time
import logging
from datetime import date, timedelta
from typing import Generator

import requests

logger = logging.getLogger(__name__)

_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_REQ_DELAY = 0.15  # seconds between paginated requests


def _month_ranges(start: str, end: str) -> Generator[tuple[str, str], None, None]:
    cur = date.fromisoformat(start).replace(day=1)
    end_date = date.fromisoformat(end)
    while cur <= end_date:
        if cur.month == 12:
            next_month = cur.replace(year=cur.year + 1, month=1)
        else:
            next_month = cur.replace(month=cur.month + 1)
        chunk_end = min(next_month - timedelta(days=1), end_date)
        yield cur.isoformat(), chunk_end.isoformat()
        cur = next_month


def _get_page(start: str, end: str, offset: int, user_agent: str) -> dict:
    params = {
        "q":         '"Item 2.03"',
        "forms":     "8-K",
        "dateRange": "custom",
        "startdt":   start,
        "enddt":     end,
        "from":      offset,
    }
    for attempt in range(4):
        resp = requests.get(
            _EFTS_URL,
            params=params,
            headers={"User-Agent": user_agent},
            timeout=30,
        )
        if resp.status_code < 500:
            resp.raise_for_status()
            return resp.json()
        wait = 2 ** attempt
        logger.warning(f"EDGAR 5xx on {start}–{end} offset={offset}, retry in {wait}s")
        time.sleep(wait)
    resp.raise_for_status()  # raise after exhausting retries
    return resp.json()


def _filing_url(cik: str, adsh: str) -> str:
    clean = adsh.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{clean}/{adsh}-index.htm"
    )


def _entity_name(display_names: list) -> str | None:
    if not display_names:
        return None
    # e.g. "FUELCELL ENERGY INC  (FCEL, FCELB)  (CIK 0000886128)"
    return display_names[0].split("(")[0].strip() or None


def _parse_hit(hit: dict, ingested_at: str) -> dict:
    src   = hit.get("_source", {})
    ciks  = src.get("ciks") or []
    cik   = ciks[0] if ciks else ""
    adsh  = src.get("adsh", "") or ""
    items = src.get("items") or []

    # _id format: "{adsh}:{primary_document_filename}"
    hit_id      = hit.get("_id", "")
    primary_doc = hit_id.split(":")[-1] if ":" in hit_id else None

    return {
        "accession_no":     adsh or None,
        "cik":              cik.lstrip("0") or None,
        "entity_name":      _entity_name(src.get("display_names")),
        "form_type":        src.get("form", "8-K"),
        "file_date":        src.get("file_date") or None,
        "period_of_report": src.get("period_ending") or None,
        "items":            ",".join(items) if items else None,
        "file_url":         _filing_url(cik, adsh) if cik and adsh else None,
        "primary_doc":      primary_doc,
        "ingested_at":      ingested_at,
    }


def fetch_filings(
    start_date: str,
    end_date: str,
    user_agent: str,
    ingested_at: str,
) -> list[dict]:
    records: list[dict] = []

    for chunk_start, chunk_end in _month_ranges(start_date, end_date):
        logger.info(f"EDGAR: fetching {chunk_start} → {chunk_end}")
        offset = 0

        while True:
            if offset > 0:
                time.sleep(_REQ_DELAY)

            page = _get_page(chunk_start, chunk_end, offset, user_agent)
            hits = page.get("hits", {})
            total = hits.get("total", {}).get("value", 0)
            page_hits = hits.get("hits", [])

            if not page_hits:
                break

            for hit in page_hits:
                record = _parse_hit(hit, ingested_at)
                if record["accession_no"]:
                    records.append(record)

            offset += len(page_hits)
            logger.debug(f"  {offset}/{total}")

            if offset >= total or offset >= 10_000:
                break

    logger.info(f"EDGAR: collected {len(records)} filings")
    return records
