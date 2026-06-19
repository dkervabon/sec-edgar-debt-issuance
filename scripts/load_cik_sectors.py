"""
One-time (and refreshable) load: fetch SIC codes from EDGAR submissions API
for every distinct CIK in raw.edgar_8k_filings, map to GICS sector, and
write to raw.cik_sectors (WRITE_TRUNCATE — safe to re-run).

Usage:
    cd corporate-debt-trends
    python scripts/load_cik_sectors.py
"""
import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config.settings as settings
from ingestion.sec_sectors import fetch_all_sectors
from loaders import bq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    fetched_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client = bq.get_client(settings.GCP_PROJECT)

    # Get all distinct CIKs from the raw filings table
    logger.info("Querying distinct CIKs from edgar_8k_filings …")
    ciks = [
        row.cik
        for row in client.query(f"""
            SELECT DISTINCT cik
            FROM `{settings.GCP_PROJECT}.{settings.BQ_DATASET_RAW}.edgar_8k_filings`
            WHERE cik IS NOT NULL
        """).result()
    ]
    logger.info(f"Found {len(ciks):,} unique CIKs — fetching EDGAR submissions …")

    rows = fetch_all_sectors(ciks, settings.EDGAR_USER_AGENT, fetched_at)

    bq.load_rows(
        client,
        project=settings.GCP_PROJECT,
        dataset_id=settings.BQ_DATASET_RAW,
        table_id="cik_sectors",
        schema=bq.CIK_SECTORS_SCHEMA,
        rows=rows,
        # WRITE_TRUNCATE: full refresh — safe to re-run as CIK universe grows
    )
    logger.info(f"Done — {len(rows):,} rows in raw.cik_sectors")


if __name__ == "__main__":
    main()
