import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT = os.environ["GCP_PROJECT"]
BQ_DATASET_RAW = os.getenv("BQ_DATASET_RAW", "raw")
GOOGLE_APPLICATION_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

# Propagate to google-auth library before any BQ client is instantiated
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

FRED_API_KEY = os.environ["FRED_API_KEY"]
FRED_SERIES = {
    "DFF":        "Federal Funds Effective Rate",
    "DGS2":       "2-Year Treasury Constant Maturity",
    "DGS5":       "5-Year Treasury Constant Maturity",
    "DGS10":      "10-Year Treasury Constant Maturity",
    "BAMLC0A0CM": "ICE BofA US Corporate Bond OAS",
}

EDGAR_USER_AGENT = os.getenv(
    "EDGAR_USER_AGENT",
    "Corporate Debt Research diego.kervabon@gmail.com",
)

BACKFILL_START = os.getenv("BACKFILL_START", "2022-01-01")
BACKFILL_END   = os.getenv("BACKFILL_END",   "2024-12-31")
