import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';
import crypto from 'crypto';

const COWARD_ADJECTIVES = [
  'Craven', 'Gutless', 'Spineless', 'Lily-Livered', 'Faint-Hearted',
  'Yellow-Bellied', 'Skulking', 'Sniveling', 'Trembling', 'Cowering',
  'Pusillanimous', 'Timorous', 'Quailing', 'Shrinking', 'Feckless',
  'Dastardly', 'Recreant', 'Poltroonish', 'Milquetoast', 'Mealy-Mouthed',
];

const COWARD_ANIMALS = [
  'Jackal', 'Hyena', 'Weasel', 'Rat', 'Opossum',
  'Vulture', 'Leech', 'Tick', 'Lamprey', 'Remora',
  'Mosquito', 'Flea', 'Mite', 'Gnat', 'Maggot',
  'Slug', 'Cockroach', 'Tapeworm', 'Hagfish', 'Louse',
];

function generateAnonName(ip: string): string {
  const hash = crypto.createHash('sha256').update(ip + 'coward-salt-2026').digest('hex');
  const adjIdx = parseInt(hash.slice(0, 4), 16) % COWARD_ADJECTIVES.length;
  const animalIdx = parseInt(hash.slice(4, 8), 16) % COWARD_ANIMALS.length;
  const number = hash.slice(8, 13);
  return `${COWARD_ADJECTIVES[adjIdx]} ${COWARD_ANIMALS[animalIdx]} ${number}`;
}

function sanitize(text: string): string {
  return text
    .replace(/https?:\/\/\S+/gi, '[link removed]')
    .replace(/www\.\S+/gi, '[link removed]')
    .replace(/<[^>]*>/g, '')
    .replace(/\[.*?\]\(.*?\)/g, '[link removed]')
    .replace(/!\[.*?\]\(.*?\)/g, '[image removed]')
    .replace(/javascript:/gi, '')
    .replace(/data:/gi, '')
    .replace(/on\w+\s*=/gi, '')
    .trim();
}

// GET /api/comments?entity_type=post&entity_id=4&page=1&limit=20
// Also supports legacy ?post_id=N
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);

  // Support legacy post_id param
  let entityType = searchParams.get('entity_type');
  let entityId = searchParams.get('entity_id');
  const legacyPostId = searchParams.get('post_id');
  if (legacyPostId && !entityType) {
    entityType = 'post';
    entityId = legacyPostId;
  }

  if (!entityType || !entityId) {
    return NextResponse.json({ error: 'entity_type and entity_id required' }, { status: 400 });
  }

  const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10));
  const limit = Math.min(50, Math.max(1, parseInt(searchParams.get('limit') ?? '20', 10)));
  const offset = (page - 1) * limit;

  try {
    const countResult = await pool.query(
      'SELECT count(*) FROM comments WHERE entity_type = $1 AND entity_id = $2',
      [entityType, entityId],
    );
    const total = parseInt(countResult.rows[0].count, 10);

    const result = await pool.query(
      `SELECT c.comment_id, c.body, c.created_at,
              COALESCE(u.display_name_custom, u.display_name, c.anon_name) AS author_name,
              CASE WHEN c.user_id IS NOT NULL THEN true ELSE false END AS is_authenticated
       FROM comments c
       LEFT JOIN users u ON u.user_id = c.user_id
       WHERE c.entity_type = $1 AND c.entity_id = $2
       ORDER BY c.created_at DESC
       LIMIT $3 OFFSET $4`,
      [entityType, entityId, limit, offset],
    );

    return NextResponse.json({
      comments: result.rows,
      total,
      page,
      limit,
      has_more: offset + result.rows.length < total,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// POST /api/comments
export async function POST(request: Request) {
  try {
    const { post_id, entity_type: rawEntityType, entity_id: rawEntityId, body: rawBody } = await request.json();

    // Support legacy post_id or new entity system
    const entityType = rawEntityType || (post_id ? 'post' : null);
    const entityId = rawEntityId || (post_id ? String(post_id) : null);

    if (!entityType || !entityId || !rawBody) {
      return NextResponse.json({ error: 'entity_type, entity_id, and body required' }, { status: 400 });
    }

    const body = sanitize(rawBody);
    if (body.length === 0) {
      return NextResponse.json({ error: 'Comment is empty after sanitization' }, { status: 400 });
    }
    if (body.length > 500) {
      return NextResponse.json({ error: 'Comment must be 500 characters or fewer' }, { status: 400 });
    }

    const ip = request.headers.get('x-forwarded-for')
      ?? request.headers.get('x-real-ip')
      ?? 'unknown';
    const ipHash = crypto.createHash('sha256').update(ip).digest('hex').slice(0, 16);

    // Try to authenticate (optional)
    let userId: number | null = null;
    let authorName: string | null = null;
    let isAdmin = false;
    try {
      const user = await verifyRequest(request);
      const userRow = await pool.query(
        'SELECT user_id, role, display_name_custom, display_name FROM users WHERE firebase_uid = $1',
        [user.uid],
      );
      if (userRow.rows[0]) {
        userId = userRow.rows[0].user_id;
        authorName = userRow.rows[0].display_name_custom || userRow.rows[0].display_name;
        isAdmin = userRow.rows[0].role === 'admin';
      }
    } catch {
      // Not authenticated — coward name
    }

    // For post entities, verify post exists
    if (entityType === 'post') {
      const postCheck = await pool.query(
        isAdmin
          ? 'SELECT post_id FROM posts WHERE post_id = $1'
          : 'SELECT post_id FROM posts WHERE post_id = $1 AND published = true',
        [parseInt(entityId, 10)],
      );
      if (postCheck.rows.length === 0) {
        return NextResponse.json({ error: 'Post not found' }, { status: 404 });
      }
    }

    const anonName = userId ? null : generateAnonName(ip);
    const postIdVal = entityType === 'post' ? parseInt(entityId, 10) : null;

    // Duplicate check: same entity + author name + body
    const dupCheck = await pool.query(
      `SELECT comment_id FROM comments
       WHERE entity_type = $1 AND entity_id = $2 AND body = $3
         AND (user_id = $4 OR ($4 IS NULL AND anon_name = $5))
       LIMIT 1`,
      [entityType, entityId, body, userId, anonName],
    );
    if (dupCheck.rows.length > 0) {
      return NextResponse.json({ error: 'Duplicate comment' }, { status: 409 });
    }

    const result = await pool.query(
      `INSERT INTO comments (post_id, entity_type, entity_id, user_id, anon_name, body, ip_hash)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING comment_id, body, created_at`,
      [postIdVal, entityType, entityId, userId, anonName, body, ipHash],
    );

    const comment = result.rows[0];
    return NextResponse.json({
      ...comment,
      author_name: authorName || anonName,
      is_authenticated: !!userId,
    }, { status: 201 });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
