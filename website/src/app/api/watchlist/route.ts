import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import { audit } from '@/lib/audit';
import pool from '@/lib/db';

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

export async function GET(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const result = await pool.query(
      `SELECT w.watchlist_id, w.added_at,
              s.security_id, s.ticker, s.name, s.security_type,
              sc.score AS iald, sc.verdict, sc.active_signals,
              sa.avg_score_30d, sa.volatility_30d, sa.score_trend,
              spark.points AS sparkline
       FROM watchlist_items w
       JOIN securities s ON s.security_id = w.security_id
       LEFT JOIN LATERAL (
         SELECT score, verdict, active_signals
         FROM iald_scores
         WHERE security_id = s.security_id
         ORDER BY score_date DESC LIMIT 1
       ) sc ON true
       LEFT JOIN score_aggregates sa ON sa.security_id = s.security_id
       LEFT JOIN LATERAL (
         SELECT coalesce(json_agg(json_build_object('d', sub.score_date, 's', sub.score) ORDER BY sub.score_date), '[]'::json) AS points
         FROM (
           SELECT score_date, score
           FROM iald_scores
           WHERE security_id = s.security_id
           ORDER BY score_date DESC LIMIT 14
         ) sub
       ) spark ON true
       WHERE w.user_id = $1
       ORDER BY w.added_at DESC`,
      [userId],
    );

    return NextResponse.json({ watchlist: result.rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}

export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { ticker } = await request.json();
    if (!ticker) return NextResponse.json({ error: 'ticker required' }, { status: 400 });

    const sec = await pool.query('SELECT security_id FROM securities WHERE ticker = $1', [ticker.toUpperCase()]);
    if (!sec.rows[0]) return NextResponse.json({ error: 'Security not found' }, { status: 404 });

    const securityId = sec.rows[0].security_id;

    await pool.query(
      `INSERT INTO watchlist_items (user_id, security_id) VALUES ($1, $2)
       ON CONFLICT (user_id, security_id) DO NOTHING`,
      [userId, securityId],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'watchlist_add',
      resource_type: 'security',
      resource_id: ticker.toUpperCase(),
      request_method: 'POST',
      request_path: '/api/watchlist',
      response_status: 200,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { ticker } = await request.json();
    if (!ticker) return NextResponse.json({ error: 'ticker required' }, { status: 400 });

    const sec = await pool.query('SELECT security_id FROM securities WHERE ticker = $1', [ticker.toUpperCase()]);
    if (!sec.rows[0]) return NextResponse.json({ error: 'Security not found' }, { status: 404 });

    await pool.query(
      'DELETE FROM watchlist_items WHERE user_id = $1 AND security_id = $2',
      [userId, sec.rows[0].security_id],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'watchlist_remove',
      resource_type: 'security',
      resource_id: ticker.toUpperCase(),
      request_method: 'DELETE',
      request_path: '/api/watchlist',
      response_status: 200,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
