"""
Fetch SIC codes from the EDGAR submissions API for a list of CIKs,
then map SIC → GICS sector.

Endpoint: https://data.sec.gov/submissions/CIK{cik:010d}.json
Rate limit: < 10 req/s (same SEC policy as EFTS).
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:>010s}.json"
_FETCH_DELAY = 0.18   # 3 workers × (1/0.18) ≈ 16 burst, but latency keeps real rate ~5 req/s
_MAX_WORKERS = 3


# ── SIC → GICS mapping ────────────────────────────────────────────────────────

def sic_to_gics(sic: int | None) -> str:
    if sic is None:
        return "Other"
    s = int(sic)

    if   100  <= s <=  999: return "Consumer Staples"       # agriculture
    if  1000  <= s <= 1099: return "Materials"              # metal mining
    if  1200  <= s <= 1299: return "Energy"                 # coal
    if  1300  <= s <= 1399: return "Energy"                 # oil & gas extraction
    if  1400  <= s <= 1499: return "Materials"              # nonmetallic minerals
    if  1500  <= s <= 1799: return "Industrials"            # construction
    if  2000  <= s <= 2111: return "Consumer Staples"       # food & tobacco
    if  2200  <= s <= 2299: return "Consumer Discretionary" # textiles
    if  2300  <= s <= 2390: return "Consumer Discretionary" # apparel
    if  2400  <= s <= 2590: return "Consumer Discretionary" # lumber, furniture
    if  2600  <= s <= 2661: return "Materials"              # paper
    if  2670  <= s <= 2741: return "Communication Services" # publishing
    if  2750  <= s <= 2799: return "Industrials"            # commercial printing
    if  2800  <= s <= 2836: return "Health Care"            # pharma / biotech
    if  2840  <= s <= 2899: return "Materials"              # soap, cleaners, chemicals
    if  2900  <= s <= 2999: return "Energy"                 # petroleum refining
    if  3000  <= s <= 3099: return "Materials"              # rubber & plastics
    if  3100  <= s <= 3199: return "Consumer Discretionary" # leather / footwear
    if  3200  <= s <= 3299: return "Materials"              # stone, clay, glass
    if  3300  <= s <= 3399: return "Materials"              # primary metals
    if  3400  <= s <= 3499: return "Industrials"            # fabricated metals
    if  3500  <= s <= 3559: return "Industrials"            # industrial machinery
    if  3560  <= s <= 3579: return "Information Technology" # computers / office equip
    if  3580  <= s <= 3599: return "Industrials"            # misc industrial machinery
    if  3600  <= s <= 3674: return "Information Technology" # semiconductors / electronics
    if  3675  <= s <= 3699: return "Information Technology" # electronic components
    if  3700  <= s <= 3799: return "Consumer Discretionary" # transportation equipment / autos
    if  3800  <= s <= 3826: return "Information Technology" # instruments
    if  3827  <= s <= 3851: return "Health Care"            # optical / medical instruments
    if  3900  <= s <= 3999: return "Industrials"            # misc manufacturing
    if  4000  <= s <= 4499: return "Industrials"            # railroads / trucking / transport
    if  4500  <= s <= 4599: return "Industrials"            # air transportation
    if  4600  <= s <= 4699: return "Energy"                 # pipelines
    if  4700  <= s <= 4799: return "Industrials"            # transportation services
    if  4800  <= s <= 4899: return "Communication Services" # telephone / broadcasting
    if  4900  <= s <= 4999: return "Utilities"              # electric / gas / water
    if  5000  <= s <= 5199: return "Industrials"            # wholesale trade
    if  5200  <= s <= 5399: return "Consumer Discretionary" # retail — building, general
    if  5400  <= s <= 5499: return "Consumer Staples"       # food & drug stores
    if  5500  <= s <= 5799: return "Consumer Discretionary" # auto dealers, eating places
    if  5900  <= s <= 5999: return "Consumer Discretionary" # misc retail
    if  6000  <= s <= 6099: return "Financials"             # deposit institutions
    if  6100  <= s <= 6199: return "Financials"             # credit institutions
    if  6200  <= s <= 6299: return "Financials"             # securities / commodity brokers
    if  6300  <= s <= 6499: return "Financials"             # insurance
    if  6500  <= s <= 6552: return "Real Estate"            # real estate / REITs
    if  6726  <= s <= 6726: return "Real Estate"             # investment offices (mortgage REITs)
    if  6798  <= s <= 6798: return "Real Estate"             # REITs
    if  6700  <= s <= 6799: return "Financials"             # holding & investment companies
    if  7000  <= s <= 7099: return "Consumer Discretionary" # hotels & lodging
    if  7200  <= s <= 7299: return "Consumer Discretionary" # personal services
    if  7300  <= s <= 7369: return "Industrials"            # business services
    if  7370  <= s <= 7379: return "Information Technology" # computer programming / services
    if  7380  <= s <= 7389: return "Industrials"            # misc business services
    if  7510  <= s <= 7549: return "Consumer Discretionary" # auto repair
    if  7600  <= s <= 7699: return "Consumer Discretionary" # misc repair
    if  7800  <= s <= 7819: return "Communication Services" # motion picture production
    if  7820  <= s <= 7999: return "Consumer Discretionary" # amusements / recreation
    if  8000  <= s <= 8099: return "Health Care"            # health services
    if  8100  <= s <= 8199: return "Industrials"            # legal services
    if  8200  <= s <= 8299: return "Consumer Discretionary" # educational services
    if  8700  <= s <= 8742: return "Industrials"            # engineering / management consulting
    if  8900  <= s <= 8999: return "Industrials"            # misc services
    return "Other"


# ── fetch ─────────────────────────────────────────────────────────────────────

def _fetch_one(cik: str, user_agent: str) -> dict:
    url = _SUBMISSIONS_URL.format(cik=cik.zfill(10))
    _empty = {"cik": cik, "sic_code": None, "sic_description": None,
              "entity_name": None, "ticker": None, "gics_sector": "Other"}
    for attempt in range(5):
        try:
            time.sleep(_FETCH_DELAY)
            resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=20)
            if resp.status_code == 404:
                return _empty
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                logger.warning(f"CIK {cik}: 429, sleeping {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            tickers = data.get("tickers") or []
            sic_raw = data.get("sic")
            sic = int(sic_raw) if sic_raw else None
            return {
                "cik":             cik,
                "entity_name":     data.get("name"),
                "ticker":          tickers[0] if tickers else None,
                "sic_code":        str(sic) if sic else None,
                "sic_description": data.get("sicDescription"),
                "gics_sector":     sic_to_gics(sic),
            }
        except requests.exceptions.HTTPError as exc:
            logger.warning(f"CIK {cik} attempt {attempt+1}: {exc}")
            if attempt < 4:
                time.sleep(2 ** attempt)
        except Exception as exc:
            logger.warning(f"CIK {cik}: {exc}")
            return _empty
    return _empty


def fetch_all_sectors(
    ciks: list[str],
    user_agent: str,
    fetched_at: str,
) -> list[dict]:
    results: list[dict] = []
    total = len(ciks)
    done = 0

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, cik, user_agent): cik for cik in ciks}
        for future in as_completed(futures):
            row = future.result()
            row["fetched_at"] = fetched_at
            results.append(row)
            done += 1
            if done % 500 == 0:
                logger.info(f"Sectors: {done:,}/{total:,} CIKs fetched")

    logger.info(
        f"Sectors: fetched {len(results):,} CIKs — "
        f"{sum(1 for r in results if r['gics_sector'] != 'Other'):,} mapped to a GICS sector"
    )
    return results
