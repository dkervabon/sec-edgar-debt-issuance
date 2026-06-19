"""
EL entry point.

Steps (in order):
  1. EDGAR + FRED metadata fetch  (parallel)
  2. Document parse & enrich      (incremental — skips already-parsed rows)

Usage:
    cd corporate-debt-trends
    python scripts/run_el.py
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


def run_edgar(client, ingested_at: str) -> int:
    rows = edgar.fetch_filings(
        start_date=settings.BACKFILL_START,
        end_date=settings.BACKFILL_END,
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
    )
    return len(rows)


def run_fred(client, ingested_at: str) -> int:
    rows = fred.fetch_all_series(
        series_dict=settings.FRED_SERIES,
        start_date=settings.BACKFILL_START,
        end_date=settings.BACKFILL_END,
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
    )
    return len(rows)


def _already_parsed(client) -> set[str]:
    query = f"""
        SELECT accession_no
        FROM `{settings.GCP_PROJECT}.{settings.BQ_DATASET_RAW}.edgar_debt_details`
    """
    try:
        return {row.accession_no for row in client.query(query).result()}
    except Exception:
        return set()


def run_parse(client, parsed_at: str) -> int:
    query = f"""
        SELECT accession_no, cik, entity_name, file_date, primary_doc
        FROM `{settings.GCP_PROJECT}.{settings.BQ_DATASET_RAW}.edgar_8k_filings`
        WHERE primary_doc IS NOT NULL
    """
    all_rows = [
        {
            **dict(row),
            "file_date": row["file_date"].isoformat() if row["file_date"] else None,
        }
        for row in client.query(query).result()
    ]

    done = _already_parsed(client)
    to_parse = [r for r in all_rows if r["accession_no"] not in done]

    if not to_parse:
        logger.info("Document parse: nothing new to parse")
        return 0

    logger.info(
        f"Document parse: {len(to_parse):,} new filings "
        f"({len(done):,} already done)"
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
    now         = datetime.now(tz=timezone.utc)
    ingested_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(
        f"Starting EL: {settings.BACKFILL_START} → {settings.BACKFILL_END}  "
        f"| project={settings.GCP_PROJECT} dataset={settings.BQ_DATASET_RAW}"
    )

    client = bq.get_client(settings.GCP_PROJECT)
    bq.ensure_dataset(client, settings.GCP_PROJECT, settings.BQ_DATASET_RAW)

    # Step 1 — metadata (parallel)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edgar_future: Future = pool.submit(run_edgar, client, ingested_at)
        fred_future:  Future = pool.submit(run_fred,  client, ingested_at)
        edgar_count = edgar_future.result()
        fred_count  = fred_future.result()

    logger.info(
        f"Metadata loaded — EDGAR: {edgar_count:,} filings | FRED: {fred_count:,} observations"
    )

    # Step 2 — document parse (incremental)
    parse_count = run_parse(client, ingested_at)

    logger.info(
        f"EL complete — parsed {parse_count:,} documents "
        f"({edgar_count:,} filings | {fred_count:,} rate observations)"
    )


if __name__ == "__main__":
    main()
