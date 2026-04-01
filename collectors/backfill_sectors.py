"""One-time script: backfill sector/industry on securities table from yfinance."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
import db
import yfinance as yf

def main():
    securities = db.get_securities("equity")
    print(f"Backfilling sectors for {len(securities)} equities...")

    updated = 0
    errors = 0
    for i, s in enumerate(securities):
        ticker = s["ticker"]
        try:
            info = yf.Ticker(ticker).info
            sector = info.get("sector")
            industry = info.get("industry")
            if sector or industry:
                with db.get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE securities SET sector = %s, industry = %s WHERE security_id = %s",
                            (sector, industry, s["security_id"]),
                        )
                updated += 1
        except Exception as e:
            errors += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(securities)} ({updated} updated, {errors} errors)")
        time.sleep(0.3)

    print(f"Done: {updated} updated, {errors} errors out of {len(securities)}")

if __name__ == "__main__":
    main()
