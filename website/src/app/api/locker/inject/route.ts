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
const VALID_MIME_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/gif',
]);
const VALID_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.gif']);
const VALID_PROFILES = ['single_basic', 'single_rare', 'twin', 'magic', 'compound'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

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
    const profile = (formData.get('profile') as string) || 'compound';
    const seed = parseInt((formData.get('seed') as string) || '42', 10);

    if (!file) {
      return NextResponse.json({ error: 'Image file required' }, { status: 400 });
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ error: 'File too large (max 50 MB)' }, { status: 400 });
    }

    // Validate MIME type
    if (!VALID_MIME_TYPES.has(file.type)) {
      return NextResponse.json(
        { error: 'Invalid file type. Accepted: JPEG, PNG, GIF' },
        { status: 400 },
      );
    }

    // Validate extension
    const ext = path.extname(file.name).toLowerCase();
    if (!VALID_EXTENSIONS.has(ext)) {
      return NextResponse.json(
        { error: 'Invalid file extension. Accepted: .jpg, .jpeg, .png, .gif' },
        { status: 400 },
      );
    }

    // Validate profile
    if (!VALID_PROFILES.includes(profile)) {
      return NextResponse.json({ error: 'Invalid profile' }, { status: 400 });
    }

    // Read file bytes and validate image header (magic bytes)
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

    // Generate upload group ID
    const uploadGroup = crypto.randomBytes(12).toString('hex');

    // Save uploaded file temporarily
    const tmpDir = '/tmp/granite_uploads';
    fs.mkdirSync(tmpDir, { recursive: true });
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
    const tmpPath = path.join(tmpDir, `${uploadGroup}_${safeName}`);
    fs.writeFileSync(tmpPath, buffer);

    // Run injection report generator — outputs to user's locker
    const scriptPath = path.resolve(process.cwd(), '..', 'backend', 'src', 'injection_report.py');
    const { stdout, stderr } = await execAsync(
      `python3 "${scriptPath}" "${tmpPath}" -o "${userDir}" -p ${profile} -s ${seed}`,
      { timeout: 120000 },
    );

    // Clean up temp file
    try { fs.unlinkSync(tmpPath); } catch {}

    // Find the generated report JSON
    const reportFiles = fs.readdirSync(userDir)
      .filter(f => f.endsWith('_report.json'))
      .map(f => ({ name: f, time: fs.statSync(path.join(userDir, f)).mtimeMs }))
      .sort((a, b) => b.time - a.time);

    if (reportFiles.length === 0) {
      return NextResponse.json({ error: 'Injection failed — no report generated' }, { status: 500 });
    }

    const reportJson = JSON.parse(
      fs.readFileSync(path.join(userDir, reportFiles[0].name), 'utf-8'),
    );

    const slug = reportFiles[0].name.replace('_report.json', '');
    const relBase = path.join(String(userId), 'uploads');

    // Identify generated files — JPEG is the primary (carries DQT Layer 1),
    // PNG is the lossless archival copy
    const generatedFiles = [
      { type: 'injected',      fileName: `${slug}_embedded.jpg`,   mimeType: 'image/jpeg' },
      { type: 'injected_png',  fileName: `${slug}_embedded.png`,   mimeType: 'image/png' },
      { type: 'heatmap',       fileName: `${slug}_heatmap.png`,    mimeType: 'image/png' },
      { type: 'manifest',      fileName: `${slug}_report.json`,    mimeType: 'application/json' },
      { type: 'histogram',     fileName: `${slug}_histogram.png`,  mimeType: 'image/png' },
    ];

    // Record each file in DB
    const fileRecords = [];
    for (const gf of generatedFiles) {
      const fullPath = path.join(userDir, gf.fileName);
      if (!fs.existsSync(fullPath)) continue;

      const stat = fs.statSync(fullPath);
      const relPath = path.join(relBase, gf.fileName);

      const result = await pool.query(
        `INSERT INTO locker_files
          (user_id, upload_group, file_type, file_name, file_path, mime_type, file_size, image_hash, profile)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
         RETURNING file_id`,
        [userId, uploadGroup, gf.type, gf.fileName, relPath, gf.mimeType,
         stat.size, reportJson.image_hash, profile],
      );

      fileRecords.push({
        file_id: result.rows[0].file_id,
        file_type: gf.type,
        file_name: gf.fileName,
        file_size: stat.size,
      });
    }

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'locker_inject',
      resource_type: 'locker',
      resource_id: uploadGroup,
      request_method: 'POST',
      request_path: '/api/locker/inject',
      response_status: 200,
      detail: {
        image_name: reportJson.image_name,
        profile,
        total_markers: reportJson.total_markers,
        files_created: fileRecords.length,
      },
    });

    return NextResponse.json({
      upload_group: uploadGroup,
      image_hash: reportJson.image_hash,
      profile,
      total_markers: reportJson.total_markers,
      total_sentinels: reportJson.total_sentinels,
      layers_active: reportJson.layers_active,
      mean_adjustment: reportJson.mean_adjustment,
      max_adjustment: reportJson.max_adjustment,
      files: fileRecords,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Locker inject error:', message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

/** Validate image magic bytes */
function isValidImageHeader(buf: Buffer): boolean {
  if (buf.length < 4) return false;
  // JPEG: FF D8 FF
  if (buf[0] === 0xFF && buf[1] === 0xD8 && buf[2] === 0xFF) return true;
  // PNG: 89 50 4E 47
  if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4E && buf[3] === 0x47) return true;
  // GIF: 47 49 46 38
  if (buf[0] === 0x47 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x38) return true;
  return false;
}
