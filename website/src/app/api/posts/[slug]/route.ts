import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

interface RouteContext {
  params: Promise<{ slug: string }>;
}

// GET /api/posts/:slug — public sees published only, admin sees all
export async function GET(request: Request, context: RouteContext) {
  const { slug } = await context.params;
  try {
    const result = await pool.query(
      'SELECT * FROM posts WHERE slug = $1',
      [slug],
    );
    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }

    const post = result.rows[0];

    // If unpublished, only admin can see it
    if (!post.published) {
      try {
        const user = await verifyRequest(request);
        const userRow = await pool.query(
          'SELECT role FROM users WHERE firebase_uid = $1',
          [user.uid],
        );
        if (!userRow.rows[0] || userRow.rows[0].role !== 'admin') {
          return NextResponse.json({ error: 'Not found' }, { status: 404 });
        }
      } catch {
        return NextResponse.json({ error: 'Not found' }, { status: 404 });
      }
    }

    return NextResponse.json(post);
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// PUT /api/posts/:slug — admin only, update post
export async function PUT(request: Request, context: RouteContext) {
  const { slug } = await context.params;
  try {
    const user = await verifyRequest(request);
    const userRow = await pool.query(
      'SELECT role FROM users WHERE firebase_uid = $1',
      [user.uid],
    );
    if (!userRow.rows[0] || userRow.rows[0].role !== 'admin') {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const { title, body, project, published } = await request.json();
    const result = await pool.query(
      `UPDATE posts SET
         title = COALESCE($1, title),
         body = COALESCE($2, body),
         project = COALESCE($3, project),
         published = COALESCE($4, published),
         updated_at = now()
       WHERE slug = $5
       RETURNING post_id, slug, title, project, published, updated_at`,
      [title || null, body || null, project, published ?? null, slug],
    );

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }
    return NextResponse.json(result.rows[0]);
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// DELETE /api/posts/:slug — admin only
export async function DELETE(request: Request, context: RouteContext) {
  const { slug } = await context.params;
  try {
    const user = await verifyRequest(request);
    const userRow = await pool.query(
      'SELECT role FROM users WHERE firebase_uid = $1',
      [user.uid],
    );
    if (!userRow.rows[0] || userRow.rows[0].role !== 'admin') {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    const result = await pool.query(
      'DELETE FROM posts WHERE slug = $1 RETURNING post_id',
      [slug],
    );
    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }
    return NextResponse.json({ deleted: true });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
