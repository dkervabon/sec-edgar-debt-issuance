"""
Daily incremental EL pipeline for corporate debt issuance data.

Tasks:
  ingest_edgar    — 8-K Item 2.03 filings from the last 7 days → BQ WRITE_APPEND
  ingest_fred     — rate observations for the execution interval → BQ WRITE_APPEND
  parse_documents — fetch + parse all unparsed 8-K documents   → BQ WRITE_APPEND

EDGAR uses a 7-day lookback (not 1-day) because companies have up to 4 business
days to file after the triggering event. Duplicates in the raw table are resolved
by dbt models keying on accession_no / (series_id, observation_date).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

log = logging.getLogger(__name__)

sys.path.insert(0, "/usr/local/airflow")


# ── credential helpers ────────────────────────────────────────────────────────

def _ensure_credentials() -> None:
    """
    Fall back to the Docker-internal key path when the env-var path doesn't
    resolve (i.e. the local Mac path was injected by Astro but doesn't exist
    inside the container).
    """
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds or not os.path.exists(creds):
        docker_path = (
            "/usr/local/airflow/include/keys/"
            "sec-edgar-debt-979e17b362f7.json"
        )
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = docker_path


def _ensure_fred_key() -> None:
    if not os.getenv("FRED_API_KEY"):
        try:
            from airflow.models import Variable
            key = Variable.get("FRED_API_KEY", default_var="")
            if key:
                os.environ["FRED_API_KEY"] = key
        except Exception:
            pass


# ── DAG ──────────────────────────────────────────────────────────────────────

@dag(
    dag_id="debt_issuance_el",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["edgar", "fred", "el"],
    doc_md=__doc__,
)
def debt_issuance_el():

    @task(execution_timeout=timedelta(minutes=30))
    def ingest_edgar() -> int:
        _ensure_credentials()
        _ensure_fred_key()

        ctx = get_current_context()
        end_dt   = ctx["data_interval_end"]
        start_dt = end_dt - timedelta(days=7)
        start_date  = start_dt.strftime("%Y-%m-%d")
        end_date    = end_dt.strftime("%Y-%m-%d")
        ingested_at = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        import config.settings as settings
        from ingestion import edgar
        from loaders import bq

        rows = edgar.fetch_filings(
            start_date, end_date, settings.EDGAR_USER_AGENT, ingested_at
        )
        client = bq.get_client(settings.GCP_PROJECT)
        bq.load_rows(
            client, settings.GCP_PROJECT, settings.BQ_DATASET_RAW,
            "edgar_8k_filings", bq.EDGAR_SCHEMA, rows,
            write_disposition="WRITE_APPEND",
        )
        log.info("Ingested %d EDGAR filings (%s → %s)", len(rows), start_date, end_date)
        return len(rows)

    @task(execution_timeout=timedelta(minutes=10))
    def ingest_fred() -> int:
        _ensure_credentials()
        _ensure_fred_key()

        ctx = get_current_context()
        start_date  = ctx["data_interval_start"].strftime("%Y-%m-%d")
        end_date    = ctx["data_interval_end"].strftime("%Y-%m-%d")
        ingested_at = ctx["data_interval_end"].strftime("%Y-%m-%dT%H:%M:%SZ")

        import config.settings as settings
        from ingestion import fred
        from loaders import bq

        rows = fred.fetch_all_series(
            settings.FRED_SERIES, start_date, end_date,
            settings.FRED_API_KEY, ingested_at,
        )
        client = bq.get_client(settings.GCP_PROJECT)
        bq.load_rows(
            client, settings.GCP_PROJECT, settings.BQ_DATASET_RAW,
            "fred_rate_observations", bq.FRED_SCHEMA, rows,
            write_disposition="WRITE_APPEND",
        )
        log.info("Ingested %d FRED observations (%s → %s)", len(rows), start_date, end_date)
        return len(rows)

    @task(execution_timeout=timedelta(hours=2))
    def parse_documents() -> int:
        _ensure_credentials()

        ctx = get_current_context()
        parsed_at = ctx["data_interval_end"].strftime("%Y-%m-%dT%H:%M:%SZ")

        import config.settings as settings
        from ingestion import document_parser
        from loaders import bq
        from google.cloud import bigquery

        client  = bq.get_client(settings.GCP_PROJECT)
        project = settings.GCP_PROJECT
        dataset = settings.BQ_DATASET_RAW

        # Find filings that have a document URL but haven't been parsed yet.
        # LEFT JOIN handles the first-ever run gracefully if edgar_debt_details
        # doesn't exist yet — falls back to parsing all filings.
        try:
            query = f"""
                SELECT
                    f.accession_no, f.cik, f.entity_name,
                    CAST(f.file_date AS STRING) AS file_date,
                    f.primary_doc
                FROM `{project}.{dataset}.edgar_8k_filings` f
                LEFT JOIN `{project}.{dataset}.edgar_debt_details` d
                  ON f.accession_no = d.accession_no
                WHERE f.primary_doc IS NOT NULL
                  AND d.accession_no IS NULL
            """
            rows = [dict(row) for row in client.query(query).result()]
        except Exception as exc:
            log.warning("Falling back to full parse (edgar_debt_details may not exist): %s", exc)
            query = f"""
                SELECT
                    accession_no, cik, entity_name,
                    CAST(file_date AS STRING) AS file_date,
                    primary_doc
                FROM `{project}.{dataset}.edgar_8k_filings`
                WHERE primary_doc IS NOT NULL
            """
            rows = [dict(row) for row in client.query(query).result()]

        if not rows:
            log.info("No unparsed documents — skipping")
            return 0

        log.info("Parsing %d documents", len(rows))
        results = document_parser.parse_all(rows, settings.EDGAR_USER_AGENT, parsed_at)
        bq.load_rows(
            client, project, dataset,
            "edgar_debt_details", bq.DEBT_DETAILS_SCHEMA, results,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        return len(results)

    edgar_done = ingest_edgar()
    fred_done  = ingest_fred()
    parse_done = parse_documents()

    [edgar_done, fred_done] >> parse_done


debt_issuance_el()
