import logging

from google.api_core.exceptions import Conflict
from google.cloud import bigquery

logger = logging.getLogger(__name__)

EDGAR_SCHEMA = [
    bigquery.SchemaField("accession_no",     "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("cik",              "STRING"),
    bigquery.SchemaField("entity_name",      "STRING"),
    bigquery.SchemaField("form_type",        "STRING"),
    bigquery.SchemaField("file_date",        "DATE"),
    bigquery.SchemaField("period_of_report", "DATE"),
    bigquery.SchemaField("items",            "STRING"),
    bigquery.SchemaField("file_url",         "STRING"),
    bigquery.SchemaField("primary_doc",      "STRING"),
    bigquery.SchemaField("ingested_at",      "TIMESTAMP"),
]

DEBT_DETAILS_SCHEMA = [
    bigquery.SchemaField("accession_no",          "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("cik",                   "STRING"),
    bigquery.SchemaField("entity_name",           "STRING"),
    bigquery.SchemaField("file_date",             "DATE"),
    bigquery.SchemaField("instrument_type",       "STRING"),
    bigquery.SchemaField("principal_amount_usd",  "FLOAT64"),
    bigquery.SchemaField("principal_raw",         "STRING"),
    bigquery.SchemaField("interest_rate_type",    "STRING"),
    bigquery.SchemaField("interest_rate_raw",     "STRING"),
    bigquery.SchemaField("maturity_raw",          "STRING"),
    bigquery.SchemaField("item_203_text",         "STRING"),
    bigquery.SchemaField("parse_success",         "BOOL"),
    bigquery.SchemaField("parsed_at",             "TIMESTAMP"),
]

FRED_SCHEMA = [
    bigquery.SchemaField("series_id",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("observation_date", "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("value",            "FLOAT64"),
    bigquery.SchemaField("ingested_at",      "TIMESTAMP"),
]


CIK_SECTORS_SCHEMA = [
    bigquery.SchemaField("cik",              "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("entity_name",      "STRING"),
    bigquery.SchemaField("ticker",           "STRING"),
    bigquery.SchemaField("sic_code",         "STRING"),
    bigquery.SchemaField("sic_description",  "STRING"),
    bigquery.SchemaField("gics_sector",      "STRING"),
    bigquery.SchemaField("fetched_at",       "TIMESTAMP"),
]


def get_client(project: str) -> bigquery.Client:
    return bigquery.Client(project=project)


def ensure_dataset(client: bigquery.Client, project: str, dataset_id: str) -> None:
    dataset = bigquery.Dataset(f"{project}.{dataset_id}")
    dataset.location = "US"
    try:
        client.create_dataset(dataset)
        logger.info(f"Created dataset {project}.{dataset_id}")
    except Conflict:
        pass


def load_rows(
    client: bigquery.Client,
    project: str,
    dataset_id: str,
    table_id: str,
    schema: list,
    rows: list[dict],
    write_disposition: str = bigquery.WriteDisposition.WRITE_TRUNCATE,
) -> None:
    if not rows:
        logger.warning(f"No rows to load into {dataset_id}.{table_id}, skipping")
        return

    table_ref = f"{project}.{dataset_id}.{table_id}"
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=write_disposition,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()
    logger.info(f"Loaded {len(rows):,} rows into {table_ref}")
