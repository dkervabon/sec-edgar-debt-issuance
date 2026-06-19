"""
Fetch interest rate series from the FRED API (St. Louis Fed).
Returns observations as flat dicts ready for BigQuery load.
FRED uses "." to indicate a missing value; those rows are dropped.
"""
import logging

import requests

logger = logging.getLogger(__name__)

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(
    series_id: str,
    start_date: str,
    end_date: str,
    api_key: str,
    ingested_at: str,
) -> list[dict]:
    resp = requests.get(
        _FRED_URL,
        params={
            "series_id":         series_id,
            "observation_start": start_date,
            "observation_end":   end_date,
            "api_key":           api_key,
            "file_type":         "json",
        },
        timeout=30,
    )
    resp.raise_for_status()

    observations = resp.json().get("observations", [])
    records = []
    for obs in observations:
        raw_value = obs.get("value", ".")
        if raw_value == ".":
            continue
        records.append({
            "series_id":        series_id,
            "observation_date": obs["date"],
            "value":            float(raw_value),
            "ingested_at":      ingested_at,
        })

    logger.info(f"FRED {series_id}: {len(records)} observations")
    return records


def fetch_all_series(
    series_dict: dict,
    start_date: str,
    end_date: str,
    api_key: str,
    ingested_at: str,
) -> list[dict]:
    all_records: list[dict] = []
    for series_id in series_dict:
        records = fetch_series(series_id, start_date, end_date, api_key, ingested_at)
        all_records.extend(records)
    logger.info(f"FRED total: {len(all_records)} observations across {len(series_dict)} series")
    return all_records
