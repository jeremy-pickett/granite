import { NextResponse } from 'next/server';
import pool from '@/lib/db';

async function safeQuery(sql: string, params: unknown[]) {
  const client = await pool.connect();
  try {
    const result = await client.query(sql, params);
    return result.rows;
  } catch {
    return [];
  } finally {
    client.release();
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker')?.toUpperCase() ?? '';

  if (!ticker) {
    return NextResponse.json({ error: 'ticker required' }, { status: 400 });
  }

  // Resolve security — must succeed
  let sec;
  try {
    const secRes = await pool.query(
      'SELECT security_id, ticker, name, security_type FROM securities WHERE ticker = $1',
      [ticker],
    );
    if (secRes.rows.length === 0) {
      return NextResponse.json({ error: 'unknown ticker' }, { status: 404 });
    }
    sec = secRes.rows[0];
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }

  const sid = sec.security_id;

  // All remaining queries use separate connections so one failure doesn't poison the rest
  const [signals, snapshotRows, marketFallbackRows, consensusRows, ratings, institutional, press, llmRows, debtRows, priceSparkRows] =
    await Promise.all([
      safeQuery(
        `SELECT signal_type, contribution, confidence, direction,
                magnitude, description, detected_at
         FROM signals
         WHERE security_id = $1
           AND detected_at > now() - interval '168 hours'
           AND (expires_at IS NULL OR expires_at > now())
         ORDER BY contribution DESC`,
        [sid],
      ),
      safeQuery(
        `SELECT price, bid, ask, volume_at_snap, day_open, day_high, day_low,
                prev_close, change_pct, pe_ratio, forward_pe, market_cap,
                avg_volume_10d, volume_velocity, snapshot_time, snapshot_type
         FROM raw_market_snapshots
         WHERE security_id = $1
         ORDER BY snapshot_time DESC LIMIT 1`,
        [sid],
      ),
      safeQuery(
        `SELECT close AS price, open AS day_open, high AS day_high, low AS day_low,
                volume AS volume_at_snap, trade_date AS snapshot_time,
                CASE WHEN prev_close > 0 THEN round(((close - prev_close) / prev_close * 100)::numeric, 2) ELSE NULL END AS change_pct,
                prev_close
         FROM (
           SELECT close, open, high, low, volume, trade_date,
                  lag(close) OVER (ORDER BY trade_date) AS prev_close
           FROM raw_market_data
           WHERE security_id = $1
           ORDER BY trade_date DESC LIMIT 2
         ) sub
         ORDER BY trade_date DESC LIMIT 1`,
        [sid],
      ),
      safeQuery(
        `SELECT total_analysts, mean_rating, median_rating, mode_rating, mode_label,
                strong_buy_pct, buy_pct, hold_pct, sell_pct, strong_sell_pct,
                mean_price_target, high_price_target, low_price_target,
                median_price_target, snapshot_date
         FROM raw_analyst_consensus
         WHERE security_id = $1
         ORDER BY snapshot_date DESC LIMIT 1`,
        [sid],
      ),
      safeQuery(
        `SELECT rating_date, company, action, from_rating, to_rating
         FROM raw_analyst_ratings
         WHERE security_id = $1
         ORDER BY rating_date DESC LIMIT 10`,
        [sid],
      ),
      safeQuery(
        `SELECT holder_name, shares_held, shares_changed, change_pct, portfolio_pct, report_date
         FROM raw_institutional_moves
         WHERE security_id = $1
         ORDER BY abs(shares_changed) DESC LIMIT 8`,
        [sid],
      ),
      safeQuery(
        `SELECT headline, source, published_at
         FROM raw_press_releases
         WHERE security_id = $1
         ORDER BY published_at DESC LIMIT 6`,
        [sid],
      ),
      safeQuery(
        `SELECT direction, analysis, model, query_seconds, outlook_date
         FROM raw_llm_outlooks
         WHERE security_id = $1
         ORDER BY outlook_date DESC LIMIT 1`,
        [sid],
      ),
      safeQuery(
        `SELECT period_date, total_debt, total_equity, debt_to_equity,
                interest_expense, revenue, interest_to_revenue, free_cash_flow
         FROM raw_debt_metrics
         WHERE security_id = $1
         ORDER BY period_date DESC LIMIT 1`,
        [sid],
      ),
      safeQuery(
        `SELECT trade_date AS d, close AS p
         FROM raw_market_data
         WHERE security_id = $1
         ORDER BY trade_date DESC LIMIT 14`,
        [sid],
      ),
    ]);

  // Prefer real-time snapshot; fall back to daily market data close
  const snapshot = snapshotRows[0] ?? marketFallbackRows[0] ?? null;

  return NextResponse.json({
    security: sec,
    signals,
    snapshot,
    consensus: consensusRows[0] ?? null,
    ratings,
    institutional,
    press,
    llm_outlook: llmRows[0] ?? null,
    debt: debtRows[0] ?? null,
    price_sparkline: priceSparkRows.reverse(),
  });
}
