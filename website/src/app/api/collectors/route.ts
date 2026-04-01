import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const type = searchParams.get('type') ?? '';
  const ticker = searchParams.get('ticker') ?? '';

  try {
    if (ticker) {
      // Per-security collector coverage
      const result = await pool.query(
        `SELECT c.collector_id, c.collector_name, c.collector_type, c.description,
                c.is_active, c.last_run_at, c.last_success_at,
                c.run_interval_minutes,
                cc.records_count, cc.last_data_at
         FROM collectors c
         LEFT JOIN collector_coverage cc ON cc.collector_id = c.collector_id
           AND cc.security_id = (SELECT security_id FROM securities WHERE ticker = $1)
         WHERE c.is_active = true
         ORDER BY c.collector_type, c.collector_name`,
        [ticker.toUpperCase()],
      );

      return NextResponse.json({ collectors: result.rows, ticker: ticker.toUpperCase() });
    }

    // Global collector status
    const conditions: string[] = [];
    const params: string[] = [];
    let paramIdx = 1;

    if (type) {
      conditions.push(`c.collector_type = $${paramIdx}`);
      params.push(type);
      paramIdx++;
    }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';

    const result = await pool.query(
      `SELECT c.collector_id, c.collector_name, c.collector_type, c.description,
              c.is_active, c.run_interval_minutes,
              c.last_run_at, c.last_success_at, c.last_error,
              c.records_total, c.securities_covered, c.total_securities,
              c.coverage_pct
       FROM collectors c
       ${where}
       ORDER BY c.collector_type, c.collector_name`,
      params,
    );

    return NextResponse.json({ collectors: result.rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
