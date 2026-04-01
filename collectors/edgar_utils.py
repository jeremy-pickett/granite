"""
Shared EDGAR utilities — CIK lookup, constants, and rate-limit helpers.

Used by all SEC/EDGAR-based collectors. Loads the SEC company_tickers.json
once per process, caches in module-level dict.
"""

import logging
import requests

try:
    import config
    HTTP_TIMEOUT = config.HTTP_TIMEOUT
except Exception:
    HTTP_TIMEOUT = 15

log = logging.getLogger("edgar_utils")

EDGAR_UA = "Alidade/1.0 (contact@signaldelta.io)"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_EFTS = "https://efts.sec.gov/LATEST/search-index"

# Module-level CIK cache — loaded once, shared across all collectors in same process
_CIK_CACHE: dict[str, str | None] = {}
_LOADED = False


def load_cik_map() -> dict[str, str | None]:
    """Bulk-load all ticker→CIK mappings from SEC company_tickers.json.

    Idempotent: returns immediately if already loaded. Safe to call from
    multiple collectors — the SEC API is hit at most once per process.
    """
    global _LOADED
    if _LOADED:
        return _CIK_CACHE

    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": EDGAR_UA},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            for entry in resp.json().values():
                t = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                _CIK_CACHE[t] = cik
            log.info("CIK cache loaded: %d tickers", len(_CIK_CACHE))
    except requests.RequestException as e:
        log.warning("Failed to load CIK map: %s", e)

    _LOADED = True
    return _CIK_CACHE


def get_cik(ticker: str) -> str | None:
    """Look up a single ticker's CIK. Loads full cache on first call."""
    if not _LOADED:
        load_cik_map()
    return _CIK_CACHE.get(ticker.upper())
