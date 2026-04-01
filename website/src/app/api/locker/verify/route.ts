import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import { audit } from '@/lib/audit';
import pool from '@/lib/db';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';

const execAsync = promisify(exec);

const LOCKERS_ROOT = path.resolve(process.cwd(), '..', 'lockers');
const VALID_MIME_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif']);
const VALID_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.gif']);
const MAX_FILE_SIZE = 50 * 1024 * 1024;

async function getUserId(firebaseUid: string): Promise<number | null> {
  const r = await pool.query('SELECT user_id FROM users WHERE firebase_uid = $1', [firebaseUid]);
  return r.rows[0]?.user_id ?? null;
}

export async function POST(request: Request) {
  try {
    const user = await verifyRequest(request);
    const userId = await getUserId(user.uid);
    if (!userId) return NextResponse.json({ error: 'User not found' }, { status: 404 });

    const formData = await request.formData();
    const file = formData.get('image') as File | null;

    if (!file) {
      return NextResponse.json({ error: 'Image file required' }, { status: 400 });
    }

    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ error: 'File too large (max 50 MB)' }, { status: 400 });
    }

    if (!VALID_MIME_TYPES.has(file.type)) {
      return NextResponse.json(
        { error: 'Invalid file type. Accepted: JPEG, PNG, GIF' },
        { status: 400 },
      );
    }

    const ext = path.extname(file.name).toLowerCase();
    if (!VALID_EXTENSIONS.has(ext)) {
      return NextResponse.json(
        { error: 'Invalid file extension. Accepted: .jpg, .jpeg, .png, .gif' },
        { status: 400 },
      );
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    if (!isValidImageHeader(buffer)) {
      return NextResponse.json(
        { error: 'File content does not match a valid image format' },
        { status: 400 },
      );
    }

    // Create user locker directory
    const userDir = path.join(LOCKERS_ROOT, String(userId), 'uploads');
    fs.mkdirSync(userDir, { recursive: true });

    const uploadGroup = crypto.randomBytes(12).toString('hex');

    // Save uploaded file temporarily
    const tmpDir = '/tmp/granite_uploads';
    fs.mkdirSync(tmpDir, { recursive: true });
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
    const tmpPath = path.join(tmpDir, `${uploadGroup}_${safeName}`);
    fs.writeFileSync(tmpPath, buffer);

    // Run verification scanner
    const scriptPath = path.resolve(process.cwd(), '..', 'backend', 'src', 'verify_image.py');
    const { stdout, stderr } = await execAsync(
      `python3 "${scriptPath}" "${tmpPath}" -o "${userDir}"`,
      { timeout: 120000 },
    );

    // Clean up temp file
    try { fs.unlinkSync(tmpPath); } catch {}

    // Find the generated verify report JSON
    const reportFiles = fs.readdirSync(userDir)
      .filter(f => f.endsWith('_verify.json'))
      .map(f => ({ name: f, time: fs.statSync(path.join(userDir, f)).mtimeMs }))
      .sort((a, b) => b.time - a.time);

    if (reportFiles.length === 0) {
      return NextResponse.json({ error: 'Verification failed — no report generated' }, { status: 500 });
    }

    const reportJson = JSON.parse(
      fs.readFileSync(path.join(userDir, reportFiles[0].name), 'utf-8'),
    );

    // Store verify report in locker
    const relPath = path.join(String(userId), 'uploads', reportFiles[0].name);
    const stat = fs.statSync(path.join(userDir, reportFiles[0].name));

    await pool.query(
      `INSERT INTO locker_files
        (user_id, upload_group, file_type, file_name, file_path, mime_type, file_size, image_hash, profile)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [userId, uploadGroup, 'verify_report', reportFiles[0].name, relPath,
       'application/json', stat.size, reportJson.image_hash, null],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'locker_verify',
      resource_type: 'locker',
      resource_id: uploadGroup,
      request_method: 'POST',
      request_path: '/api/locker/verify',
      response_status: 200,
      detail: {
        image_name: reportJson.image_name,
        verdict: reportJson.verdict,
        signal_count: reportJson.signal_count,
      },
    });

    return NextResponse.json(reportJson);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Locker verify error:', message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

function isValidImageHeader(buf: Buffer): boolean {
  if (buf.length < 4) return false;
  if (buf[0] === 0xFF && buf[1] === 0xD8 && buf[2] === 0xFF) return true;
  if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4E && buf[3] === 0x47) return true;
  if (buf[0] === 0x47 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x38) return true;
  return false;
}
