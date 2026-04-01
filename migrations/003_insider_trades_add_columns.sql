-- Add price/value/title columns to raw_insider_trades for dollar-based thresholds
-- and C-suite role identification. Safe to re-run.

ALTER TABLE raw_insider_trades ADD COLUMN IF NOT EXISTS insider_title VARCHAR(100);
ALTER TABLE raw_insider_trades ADD COLUMN IF NOT EXISTS price_per_share NUMERIC(12,4);
ALTER TABLE raw_insider_trades ADD COLUMN IF NOT EXISTS total_value NUMERIC(16,2);
