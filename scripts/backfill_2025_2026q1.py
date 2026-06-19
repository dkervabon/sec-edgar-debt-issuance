"""
One-time backfill: EDGAR 8-K Item 2.03 filings + FRED rates
for 2025-01-01 → 2026-03-31, then incremental document parse.

Appends to the existing raw tables — safe to run without touching
the 2022-2024 data already in BigQuery.

Usage:
    cd corporate-debt-trends
    python scripts/backfill_2025_2026q1.py
"""
import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config.settings as settings  # triggers load_dotenv + sets GOOGLE_APPLICATION_CREDENTIALS
from google.cloud import bigquery
from ingestion import edgar, fred, document_parser
from loaders import bq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BACKFILL_START = "2025-01-01"
BACKFILL_END   = "2026-03-31"


def run_edgar_backfill(client: bigquery.Client, ingested_at: str) -> int:
    rows = edgar.fetch_filings(
        start_date=BACKFILL_START,
        end_date=BACKFILL_END,
        user_agent=settings.EDGAR_USER_AGENT,
        ingested_at=ingested_at,
    )
    bq.load_rows(
        client,
        project=settings.GCP_PROJECT,
        dataset_id=settings.BQ_DATASET_RAW,
        table_id="edgar_8k_filings",
        schema=bq.EDGAR_SCHEMA,
        rows=rows,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    return len(rows)


def run_fred_backfill(client: bigquery.Client, ingested_at: str) -> int:
    rows = fred.fetch_all_series(
        series_dict=settings.FRED_SERIES,
        start_date=BACKFILL_START,
        end_date=BACKFILL_END,
        api_key=settings.FRED_API_KEY,
        ingested_at=ingested_at,
    )
    bq.load_rows(
        client,
        project=settings.GCP_PROJECT,
        dataset_id=settings.BQ_DATASET_RAW,
        table_id="fred_rate_observations",
        schema=bq.FRED_SCHEMA,
        rows=rows,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    return len(rows)


def _already_parsed(client: bigquery.Client) -> set[str]:
    try:
        return {
            row.accession_no
            for row in client.query(f"""
                SELECT accession_no
                FROM `{settings.GCP_PROJECT}.{settings.BQ_DATASET_RAW}.edgar_debt_details`
            """).result()
        }
    except Exception:
        return set()


def run_parse_backfill(client: bigquery.Client, parsed_at: str) -> int:
    # Scope to the new date window so we don't re-examine 15k existing rows
    new_filings = [
        {
            **dict(row),
            "file_date": row["file_date"].isoformat() if row["file_date"] else None,
        }
        for row in client.query(f"""
            SELECT accession_no, cik, entity_name, file_date, primary_doc
            FROM `{settings.GCP_PROJECT}.{settings.BQ_DATASET_RAW}.edgar_8k_filings`
            WHERE primary_doc IS NOT NULL
              AND file_date BETWEEN '{BACKFILL_START}' AND '{BACKFILL_END}'
        """).result()
    ]

    done = _already_parsed(client)
    to_parse = [r for r in new_filings if r["accession_no"] not in done]

    if not to_parse:
        logger.info("Document parse: nothing new to parse")
        return 0

    logger.info(
        f"Document parse: {len(to_parse):,} new filings to parse "
        f"({len(done):,} already done across all dates)"
    )

    results = document_parser.parse_all(to_parse, settings.EDGAR_USER_AGENT, parsed_at)

    bq.load_rows(
        client,
        project=settings.GCP_PROJECT,
        dataset_id=settings.BQ_DATASET_RAW,
        table_id="edgar_debt_details",
        schema=bq.DEBT_DETAILS_SCHEMA,
        rows=results,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    return len(results)


def main() -> None:
    now = datetime.now(tz=timezone.utc)
    ingested_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(
        f"Backfill {BACKFILL_START} → {BACKFILL_END} | "
        f"project={settings.GCP_PROJECT} dataset={settings.BQ_DATASET_RAW}"
    )

    client = bq.get_client(settings.GCP_PROJECT)

    # Step 1 — metadata (EDGAR + FRED in parallel, both WRITE_APPEND)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edgar_future: Future = pool.submit(run_edgar_backfill, client, ingested_at)
        fred_future:  Future = pool.submit(run_fred_backfill,  client, ingested_at)
        edgar_count = edgar_future.result()
        fred_count  = fred_future.result()

    logger.info(
        f"Metadata loaded — EDGAR: {edgar_count:,} filings | FRED: {fred_count:,} observations"
    )

    # Step 2 — document parse (new rows only)
    parse_count = run_parse_backfill(client, ingested_at)

    logger.info(
        f"Backfill complete — {edgar_count:,} filings | "
        f"{fred_count:,} rate observations | {parse_count:,} documents parsed"
    )


if __name__ == "__main__":
    main()
