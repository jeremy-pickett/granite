import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

export async function GET(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ count: 0 });

    const result = await pool.query(
      `SELECT COUNT(*) as count FROM alerts
       WHERE user_id = $1 AND last_triggered IS NOT NULL
         AND (read_at IS NULL OR last_triggered > read_at)`,
      [userId],
    );

    return NextResponse.json({ count: parseInt(result.rows[0].count, 10) });
  } catch {
    return NextResponse.json({ count: 0 });
  }
}
