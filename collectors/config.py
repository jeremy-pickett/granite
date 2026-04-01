"""
Shared configuration for all collectors.
Loads API keys from collectors/.env, falls back to environment variables.
"""

import os
from pathlib import Path

# ---------- load .env file ----------
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _key(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------- database ----------
DATABASE_URL = _key("DATABASE_URL", "postgresql://alidade:alidade_dev_2026@localhost:5432/alidade")

# ---------- API keys ----------
ETHERSCAN_API_KEY = _key("ETHERSCAN_API_KEY")
FINNHUB_API_KEY = _key("FINNHUB_API_KEY")
POLYGON_API_KEY = _key("POLYGON_API_KEY")
TIINGO_API_KEY = _key("TIINGO_API_KEY")
NASDAQ_DATA_LINK_API_KEY = _key("NASDAQ_DATA_LINK_API_KEY")
NEWSAPI_API_KEY = _key("NEWSAPI_API_KEY")
LUNARCRUSH_API_KEY = _key("LUNARCRUSH_API_KEY")
SANTIMENT_API_KEY = _key("SANTIMENT_API_KEY")
QUIVERQUANT_API_KEY = _key("QUIVERQUANT_API_KEY")
KALSHI_API_KEY = _key("KALSHI_API_KEY")
FMP_API_KEY = _key("FMP_API_KEY")
CRYPTOPANIC_API_KEY = _key("CRYPTOPANIC_API_KEY")
METACULUS_API_KEY = _key("METACULUS_API_KEY")
DEFI_API_KEY = _key("DEFI_API_KEY")
TWITTER_API_KEY = _key("TWITTER_API_KEY")
TWITTER_API_SECRET = _key("TWITTER_API_SECRET")
ANTHROPIC_API_KEY = _key("ANTHROPIC_API_KEY")
COINGLASS_API_KEY = _key("COINGLASS_API_KEY")
DUNE_API_KEY = _key("DUNE_API_KEY")

# ---------- http ----------
HTTP_TIMEOUT = 30          # seconds per request
HTTP_RETRIES = 3           # retry on transient failure
HTTP_BACKOFF = 2.0         # exponential backoff base

# ---------- batching ----------
BATCH_SIZE = 50            # securities per API call where supported
DB_BATCH_SIZE = 200        # rows per INSERT batch

# ---------- logging ----------
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
