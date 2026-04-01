import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

// Get cohort members
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const cohortId = searchParams.get('cohort_id');

  if (!cohortId) {
    return NextResponse.json({ error: 'cohort_id required' }, { status: 400 });
  }

  try {
    const cohortResult = await pool.query(
      `SELECT cohort_id, cohort_type, cohort_name, description, user_id
       FROM cohorts WHERE cohort_id = $1`,
      [cohortId],
    );
    if (!cohortResult.rows[0]) {
      return NextResponse.json({ error: 'Cohort not found' }, { status: 404 });
    }

    const members = await pool.query(
      `SELECT s.security_id, s.ticker, s.name, s.security_type,
              sc.score AS iald, sc.verdict,
              sa.avg_score_30d, sa.volatility_30d, sa.score_trend
       FROM cohort_members cm
       JOIN securities s ON s.security_id = cm.security_id
       LEFT JOIN LATERAL (
         SELECT score, verdict FROM iald_scores
         WHERE security_id = s.security_id
         ORDER BY score_date DESC LIMIT 1
       ) sc ON true
       LEFT JOIN score_aggregates sa ON sa.security_id = s.security_id
       WHERE cm.cohort_id = $1
       ORDER BY s.ticker`,
      [cohortId],
    );

    return NextResponse.json({
      cohort: cohortResult.rows[0],
      members: members.rows,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Add a member to a cohort
export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { cohort_id, ticker } = await request.json();
    if (!cohort_id || !ticker) {
      return NextResponse.json({ error: 'cohort_id and ticker required' }, { status: 400 });
    }

    // Verify ownership
    const check = await pool.query(
      'SELECT cohort_id FROM cohorts WHERE cohort_id = $1 AND user_id = $2',
      [cohort_id, userId],
    );
    if (!check.rows[0]) {
      return NextResponse.json({ error: 'Cohort not found or not yours' }, { status: 403 });
    }

    const sec = await pool.query(
      'SELECT security_id FROM securities WHERE ticker = $1',
      [ticker.toUpperCase()],
    );
    if (!sec.rows[0]) {
      return NextResponse.json({ error: 'Security not found' }, { status: 404 });
    }

    await pool.query(
      `INSERT INTO cohort_members (cohort_id, security_id)
       VALUES ($1, $2) ON CONFLICT DO NOTHING`,
      [cohort_id, sec.rows[0].security_id],
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Remove a member from a cohort
export async function DELETE(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { cohort_id, ticker } = await request.json();
    if (!cohort_id || !ticker) {
      return NextResponse.json({ error: 'cohort_id and ticker required' }, { status: 400 });
    }

    const check = await pool.query(
      'SELECT cohort_id FROM cohorts WHERE cohort_id = $1 AND user_id = $2',
      [cohort_id, userId],
    );
    if (!check.rows[0]) {
      return NextResponse.json({ error: 'Cohort not found or not yours' }, { status: 403 });
    }

    const sec = await pool.query(
      'SELECT security_id FROM securities WHERE ticker = $1',
      [ticker.toUpperCase()],
    );
    if (!sec.rows[0]) {
      return NextResponse.json({ error: 'Security not found' }, { status: 404 });
    }

    await pool.query(
      'DELETE FROM cohort_members WHERE cohort_id = $1 AND security_id = $2',
      [cohort_id, sec.rows[0].security_id],
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
