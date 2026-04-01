import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker') ?? '';
  const days = Math.min(90, Math.max(1, parseInt(searchParams.get('days') ?? '30', 10)));

  if (!ticker) {
    return NextResponse.json({ error: 'ticker required' }, { status: 400 });
  }

  try {
    // Score history
    const history = await pool.query(
      `SELECT sc.score_date, sc.score, sc.verdict, sc.confidence, sc.active_signals
       FROM iald_scores sc
       JOIN securities s ON s.security_id = sc.security_id
       WHERE s.ticker = $1
         AND sc.score_date >= CURRENT_DATE - $2::int
       ORDER BY sc.score_date DESC`,
      [ticker.toUpperCase(), days],
    );

    // Aggregates
    const agg = await pool.query(
      `SELECT sa.*
       FROM score_aggregates sa
       JOIN securities s ON s.security_id = sa.security_id
       WHERE s.ticker = $1`,
      [ticker.toUpperCase()],
    );

    return NextResponse.json({
      ticker: ticker.toUpperCase(),
      history: history.rows,
      aggregates: agg.rows[0] ?? null,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
