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
      `SELECT a.alert_id, a.alert_type, a.condition_value, a.status,
              a.triggered_count, a.created_at, a.last_triggered, a.read_at,
              s.ticker, s.name
       FROM alerts a
       JOIN securities s ON s.security_id = a.security_id
       WHERE a.user_id = $1
       ORDER BY a.created_at DESC`,
      [userId],
    );

    const unreadCount = result.rows.filter(
      (a: { read_at: string | null; last_triggered: string | null }) =>
        a.last_triggered && (!a.read_at || new Date(a.last_triggered) > new Date(a.read_at))
    ).length;

    // Mark all as read when the user views the alerts page
    await pool.query(
      'UPDATE alerts SET read_at = NOW() WHERE user_id = $1 AND (read_at IS NULL OR last_triggered > read_at)',
      [userId],
    );

    return NextResponse.json({ alerts: result.rows, unread_count: unreadCount });
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

    const { ticker, alert_type, condition_value } = await request.json();
    if (!ticker || !alert_type) {
      return NextResponse.json({ error: 'ticker and alert_type required' }, { status: 400 });
    }

    const validTypes = ['score_threshold', 'score_change', 'verdict_change', 'price_change'];
    if (!validTypes.includes(alert_type)) {
      return NextResponse.json({ error: 'Invalid alert_type' }, { status: 400 });
    }

    const sec = await pool.query('SELECT security_id FROM securities WHERE ticker = $1', [ticker.toUpperCase()]);
    if (!sec.rows[0]) return NextResponse.json({ error: 'Security not found' }, { status: 404 });

    const result = await pool.query(
      `INSERT INTO alerts (user_id, security_id, alert_type, condition_value)
       VALUES ($1, $2, $3, $4) RETURNING alert_id`,
      [userId, sec.rows[0].security_id, alert_type, condition_value ?? null],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'alert_create',
      resource_type: 'alert',
      resource_id: String(result.rows[0].alert_id),
      request_method: 'POST',
      request_path: '/api/alerts',
      response_status: 200,
      detail: { ticker: ticker.toUpperCase(), alert_type, condition_value },
    });

    return NextResponse.json({ alert_id: result.rows[0].alert_id });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PATCH(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { alert_id, status } = await request.json();
    if (!alert_id || !status) {
      return NextResponse.json({ error: 'alert_id and status required' }, { status: 400 });
    }

    if (!['active', 'paused'].includes(status)) {
      return NextResponse.json({ error: 'Invalid status' }, { status: 400 });
    }

    await pool.query(
      'UPDATE alerts SET status = $1 WHERE alert_id = $2 AND user_id = $3',
      [status, alert_id, userId],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: `alert_${status}`,
      resource_type: 'alert',
      resource_id: String(alert_id),
      request_method: 'PATCH',
      request_path: '/api/alerts',
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

    const { alert_id } = await request.json();
    if (!alert_id) return NextResponse.json({ error: 'alert_id required' }, { status: 400 });

    await pool.query(
      'DELETE FROM alerts WHERE alert_id = $1 AND user_id = $2',
      [alert_id, userId],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'alert_delete',
      resource_type: 'alert',
      resource_id: String(alert_id),
      request_method: 'DELETE',
      request_path: '/api/alerts',
      response_status: 200,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
