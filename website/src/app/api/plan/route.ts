import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

// GET /api/plan — public, returns plan entries (posts where project = 'plan')
export async function GET() {
  try {
    const result = await pool.query(
      `SELECT post_id, slug, title, body, created_at
       FROM posts
       WHERE project = 'plan'
       ORDER BY created_at DESC
       LIMIT 100`,
    );
    return NextResponse.json({ entries: result.rows });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// POST /api/plan — admin only, add a plan entry
export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);

    const userRow = await pool.query(
      'SELECT user_id, role, display_name FROM users WHERE firebase_uid = $1',
      [user.uid],
    );
    if (!userRow.rows[0] || userRow.rows[0].role !== 'admin') {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const { body } = await request.json();
    if (!body?.trim()) {
      return NextResponse.json({ error: 'body required' }, { status: 400 });
    }

    // Generate a date-based slug
    const now = new Date();
    const dateSlug = now.toISOString().slice(0, 10);
    const timeSlug = now.toISOString().slice(11, 16).replace(':', '');
    const slug = `plan-${dateSlug}-${timeSlug}`;

    // Title is the date
    const title = now.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });

    const result = await pool.query(
      `INSERT INTO posts (slug, title, body, project)
       VALUES ($1, $2, $3, 'plan')
       RETURNING post_id, slug, title, body, created_at`,
      [slug, title, body.trim()],
    );

    const entry = result.rows[0];
    entry.author_name = userRow.rows[0].display_name || user.name || user.email;

    return NextResponse.json(entry, { status: 201 });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    if (msg.includes('duplicate key')) {
      return NextResponse.json({ error: 'Entry already exists for this timestamp' }, { status: 409 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
