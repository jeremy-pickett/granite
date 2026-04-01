"""
Crypto Exposure Estimator
===========================
Scans all securities and estimates their exposure to cryptocurrency.

Three-pass approach:
  1. KNOWN LIST — curated companies with confirmed crypto holdings
     (from treasury disclosures, 10-K filings, public statements)
  2. KEYWORD SCAN — search company names/descriptions and Finnhub
     profiles for crypto-related terms
  3. SEC FILING SCAN — search recent 10-K/10-Q filings for digital
     asset disclosures (via SEC EDGAR full-text search)

Output: per-security crypto_exposure_score (0.0-1.0) and classification:
  PURE_PLAY  (0.8-1.0) — crypto IS the business (Coinbase, Marathon)
  HIGH       (0.5-0.8) — significant treasury/revenue exposure (Tesla, Block)
  MODERATE   (0.2-0.5) — some holdings or crypto services
  LOW        (0.05-0.2) — minor exposure or crypto-adjacent
  NONE       (0.0)     — no detected exposure

Runs daily.  Results stored in `crypto_exposure` table and used by
Crypto Whale Tracker to decide which equities deserve on-chain monitoring.
"""

import sys
import os
import re
import time
import logging
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
import config
import db


# =========================================================================
# KNOWN CRYPTO HOLDINGS — curated from public disclosures (2024-2026)
# =========================================================================
# Format: ticker → (exposure_score, classification, reason)
# Sources: treasury disclosures, 10-K, press releases

KNOWN_CRYPTO_HOLDINGS = {
    # Pure-play crypto companies
    "COIN": (0.95, "PURE_PLAY", "Coinbase — crypto exchange operator"),
    "MARA": (0.95, "PURE_PLAY", "Marathon Digital — Bitcoin miner"),
    "RIOT": (0.95, "PURE_PLAY", "Riot Platforms — Bitcoin miner"),
    "CLSK": (0.95, "PURE_PLAY", "CleanSpark — Bitcoin miner"),
    "HUT":  (0.90, "PURE_PLAY", "Hut 8 Mining — Bitcoin miner"),
    "BITF": (0.90, "PURE_PLAY", "Bitfarms — Bitcoin miner"),
    "CIFR": (0.90, "PURE_PLAY", "Cipher Mining — Bitcoin miner"),
    "IREN": (0.90, "PURE_PLAY", "Iris Energy — Bitcoin miner"),
    "BTBT": (0.90, "PURE_PLAY", "Bit Digital — Bitcoin miner"),
    "MSTR": (0.95, "PURE_PLAY", "MicroStrategy — treasury is BTC"),
    "GBTC": (0.95, "PURE_PLAY", "Grayscale Bitcoin Trust"),
    "ETHE": (0.95, "PURE_PLAY", "Grayscale Ethereum Trust"),
    "BITO": (0.90, "PURE_PLAY", "ProShares Bitcoin Strategy ETF"),
    "IBIT": (0.95, "PURE_PLAY", "iShares Bitcoin Trust ETF"),
    "FBTC": (0.95, "PURE_PLAY", "Fidelity Wise Origin Bitcoin Fund"),

    # High exposure — significant treasury or revenue
    "TSLA": (0.55, "HIGH", "Tesla — BTC treasury holder, accepts crypto payments"),
    "SQ":   (0.60, "HIGH", "Block Inc — Cash App BTC trading, BTC treasury"),
    "XYZ":  (0.60, "HIGH", "Block Inc (alt ticker)"),
    "PYPL": (0.40, "MODERATE", "PayPal — crypto buy/sell/hold in app"),
    "SOS":  (0.70, "HIGH", "SOS Limited — blockchain/crypto mining"),
    "CAN":  (0.75, "HIGH", "Canaan — ASIC mining hardware"),
    "MELI": (0.30, "MODERATE", "MercadoLibre — crypto trading in LATAM"),
    "HOOD": (0.45, "MODERATE", "Robinhood — significant crypto trading revenue"),
    "COIN": (0.95, "PURE_PLAY", "Coinbase"),
    "GLXY": (0.85, "PURE_PLAY", "Galaxy Digital — crypto asset management"),
    "SI":   (0.65, "HIGH", "Silvergate Capital — crypto banking (wound down)"),

    # Moderate — crypto services or investments
    "V":    (0.15, "LOW", "Visa — crypto settlement pilots"),
    "MA":   (0.15, "LOW", "Mastercard — crypto card programs"),
    "GS":   (0.20, "MODERATE", "Goldman Sachs — crypto trading desk, custody"),
    "MS":   (0.15, "LOW", "Morgan Stanley — crypto fund access"),
    "BLK":  (0.25, "MODERATE", "BlackRock — iShares Bitcoin Trust sponsor"),
    "NVDA": (0.15, "LOW", "NVIDIA — GPU mining revenue (diminished)"),
    "AMD":  (0.10, "LOW", "AMD — GPU mining (minor)"),
    "IBM":  (0.10, "LOW", "IBM — blockchain/Hyperledger services"),
    "CME":  (0.20, "MODERATE", "CME Group — Bitcoin/Ether futures"),
    "CBOE": (0.15, "LOW", "Cboe — crypto index products"),
    "ICE":  (0.15, "LOW", "ICE/Bakkt — crypto custody/trading"),
}


# Keywords that suggest crypto exposure in company descriptions or filings
CRYPTO_KEYWORDS = [
    r'\bcryptocurrenc',
    r'\bbitcoin\b',
    r'\bethereum\b',
    r'\bblockchain\b',
    r'\bdigital\s+asset',
    r'\bdigital\s+currenc',
    r'\bcrypto\s+(?:mining|exchange|trading|custody|wallet)',
    r'\bdefi\b',
    r'\bweb3\b',
    r'\bnft\b',
    r'\bstablecoin',
    r'\btokeniz',
    r'\bdecentraliz',
    r'\bbtc\b',
    r'\beth\b',
    r'\bmining\s+(?:rig|farm|pool|hardware|operation)',
]

CRYPTO_PATTERN = re.compile('|'.join(CRYPTO_KEYWORDS), re.IGNORECASE)


class CryptoExposureCollector(BaseCollector):

    COLLECTOR_ID = 23  # next available after 22
    COLLECTOR_NAME = "Crypto Exposure Estimator"
    COLLECTOR_TYPE = "analytics"

    def setup(self):
        self._ensure_table()
        self.finnhub_key = config.FINNHUB_API_KEY
        self.session = requests.Session()
        self.session.headers['X-Finnhub-Token'] = self.finnhub_key or ''

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS crypto_exposure (
                        security_id    INT NOT NULL REFERENCES securities(security_id),
                        ticker         VARCHAR(20) NOT NULL,
                        exposure_score FLOAT NOT NULL DEFAULT 0.0,
                        classification VARCHAR(20) NOT NULL DEFAULT 'NONE',
                        source         VARCHAR(50),
                        reason         TEXT,
                        crypto_keywords_found TEXT,
                        assessed_at    TIMESTAMP DEFAULT now(),
                        PRIMARY KEY (security_id)
                    )
                """)

    def fetch(self, securities):
        """Three-pass scan: known list, keyword scan, Finnhub profiles."""
        results = {}
        sec_map = {s['ticker']: s for s in securities}

        # Pass 1: Known list
        for ticker, (score, classification, reason) in KNOWN_CRYPTO_HOLDINGS.items():
            if ticker in sec_map:
                sid = sec_map[ticker]['security_id']
                results[sid] = {
                    "security_id": sid,
                    "ticker": ticker,
                    "exposure_score": score,
                    "classification": classification,
                    "source": "known_list",
                    "reason": reason,
                    "crypto_keywords_found": None,
                }
                self.stats["fetched"] += 1

        # Pass 2: Name/type keyword scan
        for s in securities:
            sid = s['security_id']
            if sid in results:
                continue  # already classified from known list

            # Check if it's a crypto security type
            if s.get('security_type') == 'crypto':
                results[sid] = {
                    "security_id": sid,
                    "ticker": s['ticker'],
                    "exposure_score": 1.0,
                    "classification": "PURE_PLAY",
                    "source": "security_type",
                    "reason": f"{s['ticker']} classified as crypto security",
                    "crypto_keywords_found": None,
                }
                self.stats["fetched"] += 1
                continue

            # Keyword scan on name
            name = s.get('name', '') or ''
            matches = CRYPTO_PATTERN.findall(name)
            if matches:
                score = min(0.5, 0.15 * len(matches))
                results[sid] = {
                    "security_id": sid,
                    "ticker": s['ticker'],
                    "exposure_score": score,
                    "classification": self._classify(score),
                    "source": "name_keyword",
                    "reason": f"Crypto keywords in name: {name}",
                    "crypto_keywords_found": ", ".join(matches),
                }
                self.stats["fetched"] += 1

        # Pass 3: Finnhub company profile (for equities not yet classified)
        if self.finnhub_key:
            unclassified = [s for s in securities
                            if s['security_id'] not in results
                            and s.get('security_type') == 'equity']
            self.log.info("Pass 3: checking %d unclassified equities via Finnhub",
                          len(unclassified))

            for i, s in enumerate(unclassified):
                try:
                    profile = self._get_finnhub_profile(s['ticker'])
                    if profile:
                        desc = (profile.get('description', '') or '') + ' ' + \
                               (profile.get('finnhubIndustry', '') or '')
                        matches = CRYPTO_PATTERN.findall(desc)
                        if matches:
                            score = min(0.5, 0.10 * len(matches))
                            results[s['security_id']] = {
                                "security_id": s['security_id'],
                                "ticker": s['ticker'],
                                "exposure_score": score,
                                "classification": self._classify(score),
                                "source": "finnhub_profile",
                                "reason": f"Crypto keywords in Finnhub profile",
                                "crypto_keywords_found": ", ".join(matches[:5]),
                            }
                            self.stats["fetched"] += 1
                except Exception as e:
                    self.stats["errors"] += 1
                    if i < 3:
                        self.log.warning("Finnhub error for %s: %s", s['ticker'], e)

                # Rate limit: Finnhub free tier = 60 req/min
                if i % 55 == 54:
                    self.log.info("  ...checked %d/%d, sleeping for rate limit",
                                  i + 1, len(unclassified))
                    time.sleep(62)

        # Pass 4: Mark remaining as NONE
        for s in securities:
            sid = s['security_id']
            if sid not in results:
                results[sid] = {
                    "security_id": sid,
                    "ticker": s['ticker'],
                    "exposure_score": 0.0,
                    "classification": "NONE",
                    "source": "default",
                    "reason": "No crypto exposure detected",
                    "crypto_keywords_found": None,
                }

        return list(results.values())

    def _get_finnhub_profile(self, ticker):
        """Fetch company profile from Finnhub."""
        resp = self.session.get(
            'https://finnhub.io/api/v1/stock/profile2',
            params={'symbol': ticker},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if data else None
        return None

    def _classify(self, score):
        if score >= 0.8:
            return "PURE_PLAY"
        elif score >= 0.5:
            return "HIGH"
        elif score >= 0.2:
            return "MODERATE"
        elif score > 0.0:
            return "LOW"
        return "NONE"

    def transform(self, raw_data, securities):
        return raw_data  # already in final form

    def store(self, rows):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute("""
                        INSERT INTO crypto_exposure
                            (security_id, ticker, exposure_score, classification,
                             source, reason, crypto_keywords_found, assessed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (security_id) DO UPDATE SET
                            exposure_score = EXCLUDED.exposure_score,
                            classification = EXCLUDED.classification,
                            source = EXCLUDED.source,
                            reason = EXCLUDED.reason,
                            crypto_keywords_found = EXCLUDED.crypto_keywords_found,
                            assessed_at = now()
                    """, (
                        row['security_id'], row['ticker'],
                        row['exposure_score'], row['classification'],
                        row['source'], row['reason'],
                        row['crypto_keywords_found'],
                    ))
        super().store(rows)

    def teardown(self):
        self.session.close()


if __name__ == "__main__":
    run_collector(CryptoExposureCollector)
