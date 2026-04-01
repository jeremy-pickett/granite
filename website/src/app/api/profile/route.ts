import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

export async function GET(request: Request) {
  try {
    const user = await verifyRequest(request);

    const userResult = await pool.query(
      `SELECT user_id, email, display_name, display_name_custom, photo_url, role, subscription_tier, created_at, last_login
       FROM users WHERE firebase_uid = $1`,
      [user.uid],
    );
    if (!userResult.rows[0]) return NextResponse.json({ error: 'User not found' }, { status: 404 });
    const dbUser = userResult.rows[0];

    // Watchlist count
    const watchlistResult = await pool.query(
      'SELECT count(*) FROM watchlist_items WHERE user_id = $1',
      [dbUser.user_id],
    );

    // Alert count
    const alertResult = await pool.query(
      'SELECT count(*) FROM alerts WHERE user_id = $1',
      [dbUser.user_id],
    );

    // Recently interacted securities (from watchlist + alerts)
    const interactedResult = await pool.query(
      `SELECT DISTINCT s.ticker, s.name, s.security_type
       FROM securities s
       WHERE s.security_id IN (
         SELECT security_id FROM watchlist_items WHERE user_id = $1
         UNION
         SELECT security_id FROM alerts WHERE user_id = $1
       )
       ORDER BY s.ticker
       LIMIT 20`,
      [dbUser.user_id],
    );

    // Recent audit entries for this user
    const activityResult = await pool.query(
      `SELECT action, resource_type, resource_id, event_time
       FROM audit_log
       WHERE firebase_uid = $1
       ORDER BY event_time DESC LIMIT 10`,
      [user.uid],
    );

    // Injection reports
    const reportsResult = await pool.query(
      `SELECT report_id, image_name, image_hash, width, height, profile,
              layers_active, total_markers, total_sentinels,
              heatmap_path, histogram_path, report_json_path, created_at
       FROM injection_reports
       WHERE user_id = $1
       ORDER BY created_at DESC LIMIT 10`,
      [dbUser.user_id],
    );

    return NextResponse.json({
      user: {
        email: dbUser.email,
        display_name: dbUser.display_name,
        display_name_custom: dbUser.display_name_custom,
        photo_url: dbUser.photo_url,
        role: dbUser.role,
        subscription_tier: dbUser.subscription_tier,
        created_at: dbUser.created_at,
        last_login: dbUser.last_login,
      },
      stats: {
        watchlist_count: parseInt(watchlistResult.rows[0].count, 10),
        alert_count: parseInt(alertResult.rows[0].count, 10),
        report_count: reportsResult.rows.length,
      },
      linked_securities: interactedResult.rows,
      recent_activity: activityResult.rows,
      injection_reports: reportsResult.rows,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}

export async function PUT(request: Request) {
  try {
    const user = await verifyRequest(request);
    const { display_name_custom } = await request.json();

    const result = await pool.query(
      `UPDATE users SET display_name_custom = $1 WHERE firebase_uid = $2
       RETURNING user_id, display_name_custom`,
      [display_name_custom || null, user.uid],
    );

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    return NextResponse.json({ updated: true, display_name_custom: result.rows[0].display_name_custom });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}
