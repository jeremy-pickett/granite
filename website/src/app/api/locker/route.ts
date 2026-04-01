import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import { audit } from '@/lib/audit';
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

    const result = await pool.query(
      `SELECT file_id, upload_group, file_type, file_name, file_path,
              mime_type, file_size, image_hash, profile, created_at
       FROM locker_files
       WHERE user_id = $1
       ORDER BY created_at DESC`,
      [userId],
    );

    // Group files by upload_group for display
    const groups: Record<string, {
      upload_group: string;
      image_hash: string | null;
      profile: string | null;
      created_at: string;
      files: typeof result.rows;
    }> = {};

    for (const row of result.rows) {
      if (!groups[row.upload_group]) {
        groups[row.upload_group] = {
          upload_group: row.upload_group,
          image_hash: row.image_hash,
          profile: row.profile,
          created_at: row.created_at,
          files: [],
        };
      }
      groups[row.upload_group].files.push(row);
    }

    return NextResponse.json({
      total_files: result.rows.length,
      groups: Object.values(groups),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
}

export async function DELETE(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const { upload_group } = await request.json();
    if (!upload_group) return NextResponse.json({ error: 'upload_group required' }, { status: 400 });

    // Fetch files belonging to this user and upload group
    const result = await pool.query(
      'SELECT file_id, file_path FROM locker_files WHERE user_id = $1 AND upload_group = $2',
      [userId, upload_group],
    );

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Upload group not found' }, { status: 404 });
    }

    // Delete files from disk
    for (const row of result.rows) {
      const fullPath = path.join(LOCKERS_ROOT, row.file_path);
      const resolved = path.resolve(fullPath);
      if (resolved.startsWith(path.resolve(LOCKERS_ROOT))) {
        try { fs.unlinkSync(resolved); } catch {}
      }
    }

    // Delete DB records
    await pool.query(
      'DELETE FROM locker_files WHERE user_id = $1 AND upload_group = $2',
      [userId, upload_group],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'locker_delete',
      resource_type: 'locker',
      resource_id: upload_group,
      request_method: 'DELETE',
      request_path: '/api/locker',
      response_status: 200,
      detail: { files_deleted: result.rows.length },
    });

    return NextResponse.json({ success: true, files_deleted: result.rows.length });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
