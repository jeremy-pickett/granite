import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

// List cohorts — public/system + user's own
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const type = searchParams.get('type') ?? '';

  // Try to get user ID for showing their private cohorts
  let userId: number | null = null;
  try {
    const user = await verifyRequest(request);
    userId = await getUserId(user.uid);
  } catch {}

  try {
    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (type) {
      conditions.push(`c.cohort_type = $${paramIdx}`);
      params.push(type);
      paramIdx++;
    }

    // Show public/system cohorts + user's own
    if (userId) {
      conditions.push(`(c.is_public = true OR c.user_id IS NULL OR c.user_id = $${paramIdx})`);
      params.push(userId);
      paramIdx++;
    } else {
      conditions.push('(c.is_public = true OR c.user_id IS NULL)');
    }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';

    const result = await pool.query(
      `SELECT c.cohort_id, c.cohort_type, c.cohort_name, c.description, c.user_id,
              count(cm.security_id)::int AS member_count
       FROM cohorts c
       LEFT JOIN cohort_members cm ON cm.cohort_id = c.cohort_id
       ${where}
       GROUP BY c.cohort_id
       ORDER BY c.cohort_type, c.cohort_name`,
      params,
    );

    return NextResponse.json({ cohorts: result.rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Create a new user cohort
export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { cohort_name, description, tickers } = await request.json();
    if (!cohort_name?.trim()) {
      return NextResponse.json({ error: 'cohort_name required' }, { status: 400 });
    }

    // Create cohort
    const cohortResult = await pool.query(
      `INSERT INTO cohorts (cohort_type, cohort_name, description, is_public, user_id)
       VALUES ('user', $1, $2, false, $3)
       RETURNING cohort_id`,
      [cohort_name.trim(), description ?? '', userId],
    );
    const cohortId = cohortResult.rows[0].cohort_id;

    // Add members if provided
    if (tickers && Array.isArray(tickers) && tickers.length > 0) {
      const upperTickers = tickers.map((t: string) => t.toUpperCase());
      const secResult = await pool.query(
        `SELECT security_id, ticker FROM securities WHERE ticker = ANY($1)`,
        [upperTickers],
      );

      for (const sec of secResult.rows) {
        await pool.query(
          `INSERT INTO cohort_members (cohort_id, security_id)
           VALUES ($1, $2)
           ON CONFLICT DO NOTHING`,
          [cohortId, sec.security_id],
        );
      }
    }

    return NextResponse.json({ cohort_id: cohortId, success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Delete a user cohort
export async function DELETE(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { cohort_id } = await request.json();
    if (!cohort_id) return NextResponse.json({ error: 'cohort_id required' }, { status: 400 });

    // Only allow deleting own cohorts
    const check = await pool.query(
      'SELECT cohort_id FROM cohorts WHERE cohort_id = $1 AND user_id = $2',
      [cohort_id, userId],
    );
    if (!check.rows[0]) {
      return NextResponse.json({ error: 'Cohort not found or not yours' }, { status: 403 });
    }

    await pool.query('DELETE FROM cohort_members WHERE cohort_id = $1', [cohort_id]);
    await pool.query('DELETE FROM cohorts WHERE cohort_id = $1', [cohort_id]);

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
