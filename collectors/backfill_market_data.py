"""One-time script: backfill raw_market_data to 1 month of history."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import db
import config
import yfinance as yf
from psycopg2.extras import execute_values

def main():
    securities = db.get_securities()
    tickers = [s["ticker"] for s in securities]
    sec_lookup = {s["ticker"]: s["security_id"] for s in securities}

    print(f"Backfilling 1mo OHLCV for {len(tickers)} securities...")

    chunk_size = 50
    total_rows = 0

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        batch_num = i // chunk_size + 1
        total_batches = (len(tickers) + chunk_size - 1) // chunk_size
        print(f"  Batch {batch_num}/{total_batches} ({len(chunk)} tickers)...")

        try:
            df = yf.download(
                chunk,
                period="1mo",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if df is None or df.empty:
                continue

            rows = []
            for ticker in chunk:
                sid = sec_lookup.get(ticker)
                if not sid:
                    continue
                try:
                    if len(chunk) == 1:
                        tdf = df
                    else:
                        tdf = df[ticker]

                    for date_idx, row in tdf.iterrows():
                        dt = date_idx.date() if hasattr(date_idx, 'date') else date_idx
                        o, h, l, c, v = row.get("Open"), row.get("High"), row.get("Low"), row.get("Close"), row.get("Volume")
                        if c is None or (hasattr(c, '__float__') and c != c):
                            continue
                        rows.append((sid, dt, float(o), float(h), float(l), float(c), int(v or 0)))
                except Exception:
                    continue

            if rows:
                with db.get_conn() as conn:
                    with conn.cursor() as cur:
                        execute_values(
                            cur,
                            """INSERT INTO raw_market_data
                                   (security_id, trade_date, open, high, low, close, volume)
                               VALUES %s
                               ON CONFLICT (security_id, trade_date) DO UPDATE SET
                                   open = EXCLUDED.open, high = EXCLUDED.high,
                                   low = EXCLUDED.low, close = EXCLUDED.close,
                                   volume = EXCLUDED.volume""",
                            rows,
                            template="(%s, %s, %s, %s, %s, %s, %s)",
                            page_size=500,
                        )
                total_rows += len(rows)

        except Exception as e:
            print(f"  Batch error: {e}")

    print(f"Done: {total_rows} rows upserted")

if __name__ == "__main__":
    main()
