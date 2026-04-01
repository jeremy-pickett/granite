import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS user_notes (
      note_id     SERIAL PRIMARY KEY,
      user_id     INT NOT NULL REFERENCES users(user_id),
      title       TEXT NOT NULL,
      body        TEXT NOT NULL DEFAULT '',
      source      TEXT,
      tickers     TEXT[] DEFAULT '{}',
      created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `);
}

// List user notes
export async function GET(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    await ensureTable();
    const result = await pool.query(
      `SELECT note_id, title, body, source, tickers, created_at, updated_at
       FROM user_notes WHERE user_id = $1 ORDER BY updated_at DESC`,
      [userId],
    );
    return NextResponse.json({ notes: result.rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Create a note
export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { title, body, source, tickers } = await request.json();
    if (!title?.trim()) return NextResponse.json({ error: 'title required' }, { status: 400 });

    await ensureTable();

    // Duplicate check: same user + title + body
    const dup = await pool.query(
      `SELECT note_id FROM user_notes WHERE user_id = $1 AND title = $2 AND body = $3 LIMIT 1`,
      [userId, title.trim(), body ?? ''],
    );
    if (dup.rows.length > 0) {
      return NextResponse.json({ error: 'Duplicate note', duplicate: true }, { status: 409 });
    }

    const result = await pool.query(
      `INSERT INTO user_notes (user_id, title, body, source, tickers)
       VALUES ($1, $2, $3, $4, $5) RETURNING note_id`,
      [userId, title.trim(), body ?? '', source ?? null, tickers ?? []],
    );
    return NextResponse.json({ note_id: result.rows[0].note_id, success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Update a note
export async function PUT(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { note_id, title, body } = await request.json();
    if (!note_id) return NextResponse.json({ error: 'note_id required' }, { status: 400 });

    await pool.query(
      `UPDATE user_notes SET title = COALESCE($1, title), body = COALESCE($2, body), updated_at = now()
       WHERE note_id = $3 AND user_id = $4`,
      [title, body, note_id, userId],
    );
    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

// Delete a note
export async function DELETE(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { note_id } = await request.json();
    if (!note_id) return NextResponse.json({ error: 'note_id required' }, { status: 400 });

    await pool.query('DELETE FROM user_notes WHERE note_id = $1 AND user_id = $2', [note_id, userId]);
    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
