-- Fix: three raw tables referenced last_updated in ON CONFLICT but never defined the column.
-- Run once against production database. Safe to re-run (ADD COLUMN IF NOT EXISTS).

ALTER TABLE raw_news_sentiment ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT now();
ALTER TABLE raw_insider_trades ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT now();
ALTER TABLE raw_congressional_trades ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT now();
