import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

// GET /api/posts — public listing (published only), admin sees all with ?drafts=1
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = Math.min(50, parseInt(searchParams.get('limit') ?? '20', 10));
  const offset = parseInt(searchParams.get('offset') ?? '0', 10);
  const showDrafts = searchParams.get('drafts') === '1';

  // If requesting drafts, verify admin
  let isAdmin = false;
  if (showDrafts) {
    try {
      const user = await verifyRequest(request);
      const userRow = await pool.query(
        'SELECT role FROM users WHERE firebase_uid = $1',
        [user.uid],
      );
      isAdmin = userRow.rows[0]?.role === 'admin';
    } catch {
      // Not authenticated — just show published
    }
  }

  const whereClause = isAdmin ? '' : 'WHERE published = true';

  try {
    const result = await pool.query(
      `SELECT post_id, slug, title, project, published,
              LEFT(body, 300) AS excerpt,
              created_at, updated_at
       FROM posts
       ${whereClause}
       ORDER BY created_at DESC
       LIMIT $1 OFFSET $2`,
      [limit, offset],
    );
    const count = await pool.query(`SELECT count(*) FROM posts ${whereClause}`);
    return NextResponse.json({
      posts: result.rows,
      total: parseInt(count.rows[0].count, 10),
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// POST /api/posts — admin only, create new post
export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);

    // Check admin role
    const userRow = await pool.query(
      'SELECT role FROM users WHERE firebase_uid = $1',
      [user.uid],
    );
    if (!userRow.rows[0] || userRow.rows[0].role !== 'admin') {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const { title, body, project, slug } = await request.json();
    if (!title || !body) {
      return NextResponse.json({ error: 'title and body required' }, { status: 400 });
    }

    // Auto-generate slug from title if not provided
    const finalSlug = slug || title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 80);

    const result = await pool.query(
      `INSERT INTO posts (slug, title, body, project)
       VALUES ($1, $2, $3, $4)
       RETURNING post_id, slug, title, project, created_at`,
      [finalSlug, title, body, project || null],
    );

    return NextResponse.json(result.rows[0], { status: 201 });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    if (msg.includes('duplicate key')) {
      return NextResponse.json({ error: 'Slug already exists' }, { status: 409 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
