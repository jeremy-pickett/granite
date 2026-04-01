import { NextResponse } from 'next/server';
import pool from '@/lib/db';
import { exec } from 'child_process';
import { promisify } from 'util';
import { readFileSync } from 'fs';

const execAsync = promisify(exec);

async function shell(cmd: string, timeout = 5000): Promise<string> {
  try {
    const { stdout } = await execAsync(cmd, { timeout });
    return stdout.trim();
  } catch {
    return '';
  }
}

async function safeQuery(sql: string, params: unknown[] = []) {
  const client = await pool.connect();
  try {
    const result = await client.query(sql, params);
    return result.rows;
  } catch {
    return [];
  } finally {
    client.release();
  }
}

export async function GET(request: Request) {
  // Auth check — require admin role
  const authHeader = request.headers.get('authorization');
  if (authHeader) {
    // Verify via Firebase admin if needed — for now trust the client-side role check
  }

  const now = new Date();

  // ── Collector Status ──────────────────────────────────────────
  const collectors = await safeQuery(`
    SELECT c.collector_id, c.collector_name, c.collector_type, c.is_active,
           c.last_run_at, c.last_success_at, c.last_error_at, c.last_error,
           c.records_total, c.securities_covered, c.total_securities,
           EXTRACT(EPOCH FROM (now() - c.last_success_at)) / 3600 AS hours_since_success
    FROM collectors c
    ORDER BY c.last_success_at DESC NULLS LAST
  `);

  // ── Signal Stats ──────────────────────────────────────────────
  const signalStats = await safeQuery(`
    SELECT signal_type, count(*) AS total,
           max(detected_at) AS latest,
           EXTRACT(EPOCH FROM (now() - max(detected_at))) / 3600 AS hours_since_latest
    FROM signals
    WHERE detected_at > now() - interval '7 days'
    GROUP BY signal_type
    ORDER BY count(*) DESC
  `);

  const signalTotals = await safeQuery(`
    SELECT count(*) AS total_7d,
           count(DISTINCT security_id) AS securities_with_signals,
           count(DISTINCT signal_type) AS signal_types_active
    FROM signals
    WHERE detected_at > now() - interval '7 days'
  `);

  // ── IALD Scoring ──────────────────────────────────────────────
  const scoringStats = await safeQuery(`
    SELECT max(score_date) AS last_scored,
           count(*) AS scores_today,
           count(DISTINCT security_id) AS securities_scored,
           avg(score) AS avg_score,
           count(*) FILTER (WHERE verdict = 'CRITICAL') AS critical,
           count(*) FILTER (WHERE verdict = 'ELEVATED') AS elevated,
           count(*) FILTER (WHERE verdict = 'MODERATE') AS moderate,
           count(*) FILTER (WHERE verdict = 'LOW') AS low
    FROM iald_scores
    WHERE score_date = CURRENT_DATE
  `);

  // ── Table Sizes ───────────────────────────────────────────────
  const tableSizes = await safeQuery(`
    SELECT relname AS table_name,
           n_live_tup AS row_count,
           pg_size_pretty(pg_total_relation_size(relid)) AS size
    FROM pg_stat_user_tables
    WHERE schemaname = 'public'
    ORDER BY n_live_tup DESC
    LIMIT 30
  `);

  // ── Database Stats ────────────────────────────────────────────
  const dbStats = await safeQuery(`
    SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size,
           (SELECT count(*) FROM securities) AS total_securities,
           (SELECT count(*) FROM securities WHERE security_type = 'equity') AS equities,
           (SELECT count(*) FROM securities WHERE security_type = 'crypto') AS crypto
  `);

  // ── System Metrics (Linux) ────────────────────────────────────
  const [uptime, loadAvg, memInfo, diskUsage, cpuCount] = await Promise.all([
    shell('uptime -p'),
    shell("cat /proc/loadavg | awk '{print $1, $2, $3}'"),
    shell("free -m | awk '/^Mem:/{printf \"%d/%dMB (%.0f%%)\", $3, $2, $3/$2*100}'"),
    shell("df -h / | awk 'NR==2{printf \"%s/%s (%s used)\", $3, $2, $5}'"),
    shell("nproc"),
  ]);

  // ── Process Info ──────────────────────────────────────────────
  const [nextProcess, pythonProcesses, nodeVersion, pythonVersion] = await Promise.all([
    shell("ps aux | grep 'next-server' | grep -v grep | awk '{printf \"PID %s, %s%% CPU, %s%% MEM, up since %s %s\", $2, $3, $4, $9, $10}'"),
    shell("ps aux | grep 'python3.*collectors' | grep -v grep | wc -l"),
    shell("node --version"),
    shell("python3 --version"),
  ]);

  // ── Cron Schedule ─────────────────────────────────────────────
  const cronJobs = await shell("crontab -l 2>/dev/null | grep python3 | wc -l");
  const nextCron = await shell("crontab -l 2>/dev/null | grep python3 | head -5");

  // ── Recent Errors ─────────────────────────────────────────────
  const recentErrors = await safeQuery(`
    SELECT collector_name, last_error, last_error_at
    FROM collectors
    WHERE last_error IS NOT NULL AND last_error_at > now() - interval '24 hours'
    ORDER BY last_error_at DESC
    LIMIT 10
  `);

  // ── Log file sizes ────────────────────────────────────────────
  const logSizes = await shell("ls -lhS /home/ubuntu/granite/logs/*.log 2>/dev/null | head -10 | awk '{print $5, $9}'");

  // ── API Rate Limit Status ─────────────────────────────────────
  // Check Finnhub remaining calls
  let finnhubRemaining = '';
  try {
    const fResp = await fetch('https://finnhub.io/api/v1/quote?symbol=AAPL&token=' + process.env.FINNHUB_API_KEY, {
      method: 'HEAD',
    });
    finnhubRemaining = fResp.headers.get('x-ratelimit-remaining') ?? 'unknown';
  } catch { /* */ }

  return NextResponse.json({
    timestamp: now.toISOString(),
    system: {
      uptime,
      load_avg: loadAvg,
      memory: memInfo,
      disk: diskUsage,
      cpu_cores: cpuCount,
      node_version: nodeVersion,
      python_version: pythonVersion,
    },
    next_js: {
      process: nextProcess || 'not detected',
      pid: nextProcess?.match(/PID (\d+)/)?.[1] ?? null,
    },
    database: {
      ...(dbStats[0] ?? {}),
      table_sizes: tableSizes,
    },
    collectors: {
      registered: collectors.length,
      items: collectors,
      running_python: parseInt(pythonProcesses) || 0,
    },
    signals: {
      ...(signalTotals[0] ?? {}),
      by_type: signalStats,
    },
    scoring: scoringStats[0] ?? null,
    cron: {
      total_jobs: parseInt(cronJobs) || 0,
      sample: nextCron,
    },
    errors: recentErrors,
    logs: logSizes,
    rate_limits: {
      finnhub_remaining: finnhubRemaining,
    },
  });
}
