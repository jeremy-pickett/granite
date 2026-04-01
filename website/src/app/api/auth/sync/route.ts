import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import { audit } from '@/lib/audit';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const ip = request.headers.get('x-forwarded-for') ?? request.headers.get('x-real-ip');
    const ua = request.headers.get('user-agent');

    // Upsert user record
    const result = await pool.query(
      `INSERT INTO users (firebase_uid, email, display_name, last_login)
       VALUES ($1, $2, $3, NOW())
       ON CONFLICT (firebase_uid)
       DO UPDATE SET
         email = EXCLUDED.email,
         display_name = EXCLUDED.display_name,
         last_login = NOW()
       RETURNING user_id, role, subscription_tier, display_name_custom, created_at`,
      [user.uid, user.email ?? null, user.name ?? null]
    );

    const dbUser = result.rows[0];

    // Audit the login
    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      user_display_name: user.name,
      action: 'login',
      resource_type: 'session',
      ip_address: ip,
      user_agent: ua,
      request_method: 'POST',
      request_path: '/api/auth/sync',
      response_status: 200,
      detail: {
        user_id: dbUser.user_id,
        role: dbUser.role,
        subscription_tier: dbUser.subscription_tier,
      },
    });

    return NextResponse.json({
      user_id: dbUser.user_id,
      role: dbUser.role,
      subscription_tier: dbUser.subscription_tier,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}
