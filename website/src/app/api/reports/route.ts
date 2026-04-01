import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import { audit } from '@/lib/audit';
import pool from '@/lib/db';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = promisify(exec);

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
      `SELECT report_id, image_name, image_hash, width, height, profile,
              layers_active, total_markers, total_sentinels,
              mean_adjustment, max_adjustment,
              heatmap_path, histogram_path, report_json_path, created_at
       FROM injection_reports
       WHERE user_id = $1
       ORDER BY created_at DESC`,
      [userId],
    );

    return NextResponse.json({ reports: result.rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 401 });
  }
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

    if (!file) return NextResponse.json({ error: 'image file required' }, { status: 400 });

    const validProfiles = ['single_basic', 'single_rare', 'twin', 'magic', 'compound'];
    if (!validProfiles.includes(profile)) {
      return NextResponse.json({ error: 'Invalid profile' }, { status: 400 });
    }

    // Save uploaded file temporarily
    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    const tmpDir = '/tmp/granite_uploads';
    fs.mkdirSync(tmpDir, { recursive: true });
    const tmpPath = path.join(tmpDir, `upload_${Date.now()}_${file.name}`);
    fs.writeFileSync(tmpPath, buffer);

    // Run the injection report generator
    const reportDir = path.resolve(process.cwd(), 'public', 'reports');
    const scriptPath = path.resolve(process.cwd(), '..', 'backend', 'src', 'injection_report.py');

    const { stdout, stderr } = await execAsync(
      `python3 ${scriptPath} "${tmpPath}" -o "${reportDir}" -p ${profile} -s ${seed}`,
      { timeout: 60000 },
    );

    // Clean up temp file
    fs.unlinkSync(tmpPath);

    // Parse the output to get report details
    // Read the most recent report JSON from the output dir
    const files = fs.readdirSync(reportDir)
      .filter(f => f.endsWith('_report.json'))
      .map(f => ({ name: f, time: fs.statSync(path.join(reportDir, f)).mtimeMs }))
      .sort((a, b) => b.time - a.time);

    if (files.length === 0) {
      return NextResponse.json({ error: 'Report generation failed' }, { status: 500 });
    }

    const reportJson = JSON.parse(
      fs.readFileSync(path.join(reportDir, files[0].name), 'utf-8'),
    );

    // Store in database
    const result = await pool.query(
      `INSERT INTO injection_reports (
        user_id, image_name, image_hash, width, height, profile,
        layers_active, total_markers, total_sentinels,
        mean_adjustment, max_adjustment,
        heatmap_path, histogram_path, report_json_path
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
      RETURNING report_id`,
      [
        userId,
        reportJson.image_name,
        reportJson.image_hash,
        reportJson.width,
        reportJson.height,
        reportJson.profile,
        reportJson.layers_active,
        reportJson.total_markers,
        reportJson.total_sentinels,
        reportJson.mean_adjustment,
        reportJson.max_adjustment,
        reportJson.heatmap_path,
        reportJson.histogram_path,
        reportJson.report_json_path,
      ],
    );

    await audit({
      firebase_uid: user.uid,
      user_email: user.email,
      action: 'injection_report',
      resource_type: 'report',
      resource_id: String(result.rows[0].report_id),
      request_method: 'POST',
      request_path: '/api/reports',
      response_status: 200,
      detail: {
        image_name: reportJson.image_name,
        profile,
        total_markers: reportJson.total_markers,
      },
    });

    return NextResponse.json({
      report_id: result.rows[0].report_id,
      heatmap_path: reportJson.heatmap_path,
      histogram_path: reportJson.histogram_path,
      report_json_path: reportJson.report_json_path,
      total_markers: reportJson.total_markers,
      total_sentinels: reportJson.total_sentinels,
      layers_active: reportJson.layers_active,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Report generation error:', message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
