FROM astrocrpublic.azurecr.io/runtime:3.2-5

# Make project modules (ingestion/, loaders/, config/) importable inside tasks
ENV PYTHONPATH="/usr/local/airflow:${PYTHONPATH}"

# Non-sensitive runtime config — mirrors .env for local scripts
ENV GCP_PROJECT=sec-edgar-debt \
    BQ_DATASET_RAW=raw \
    EDGAR_USER_AGENT="Corporate Debt Research diego.kervabon@gmail.com" \
    BACKFILL_START=2022-01-01 \
    BACKFILL_END=2024-12-31

# Credentials — key must be copied to include/keys/ (see README)
ENV GOOGLE_APPLICATION_CREDENTIALS=/usr/local/airflow/include/keys/sec-edgar-debt-979e17b362f7.json
