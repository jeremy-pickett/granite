import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';
import path from 'path';
import fs from 'fs';

const LOCKERS_ROOT = path.resolve(process.cwd(), '..', 'lockers');

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

export async function GET(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { searchParams } = new URL(request.url);
    const fileId = searchParams.get('file_id');

    if (!fileId) {
      return NextResponse.json({ error: 'file_id parameter required' }, { status: 400 });
    }

    // Fetch file record — MUST belong to this user
    const result = await pool.query(
      `SELECT file_id, file_name, file_path, mime_type
       FROM locker_files
       WHERE file_id = $1 AND user_id = $2`,
      [fileId, userId],
    );

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'File not found' }, { status: 404 });
    }

    const fileRecord = result.rows[0];
    const fullPath = path.join(LOCKERS_ROOT, fileRecord.file_path);

    // Prevent path traversal
    const resolved = path.resolve(fullPath);
    if (!resolved.startsWith(path.resolve(LOCKERS_ROOT))) {
      return NextResponse.json({ error: 'Invalid file path' }, { status: 403 });
    }

    if (!fs.existsSync(resolved)) {
      return NextResponse.json({ error: 'File not found on disk' }, { status: 404 });
    }

    const fileBuffer = fs.readFileSync(resolved);
    const mimeType = fileRecord.mime_type || 'application/octet-stream';

    return new NextResponse(fileBuffer, {
      headers: {
        'Content-Type': mimeType,
        'Content-Disposition': `attachment; filename="${fileRecord.file_name}"`,
        'Content-Length': String(fileBuffer.length),
        'Cache-Control': 'private, no-cache',
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}
