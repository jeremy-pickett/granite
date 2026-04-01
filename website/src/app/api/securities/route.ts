import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10));
  const limit = Math.min(100, Math.max(1, parseInt(searchParams.get('limit') ?? '24', 10)));
  const search = searchParams.get('q')?.trim() ?? '';
  const type = searchParams.get('type') ?? 'all';
  const sort = searchParams.get('sort') ?? 'ticker';
  const cohortId = searchParams.get('cohort') ?? '';
  const offset = (page - 1) * limit;

  const conditions: string[] = [];
  const params: (string | number)[] = [];
  let paramIdx = 1;

  if (search) {
    conditions.push(`(s.ticker ILIKE $${paramIdx} OR s.name ILIKE $${paramIdx})`);
    params.push(`%${search}%`);
    paramIdx++;
  }

  if (type !== 'all') {
    conditions.push(`s.security_type = $${paramIdx}`);
    params.push(type);
    paramIdx++;
  }

  if (cohortId) {
    conditions.push(`s.security_id IN (SELECT security_id FROM cohort_members WHERE cohort_id = $${paramIdx})`);
    params.push(parseInt(cohortId, 10));
    paramIdx++;
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';

  let orderBy = 'ORDER BY s.ticker ASC';
  switch (sort) {
    case 'iald_desc': orderBy = 'ORDER BY COALESCE(sc.score, 0) DESC, s.ticker ASC'; break;
    case 'iald_asc': orderBy = 'ORDER BY COALESCE(sc.score, 0) ASC, s.ticker ASC'; break;
    case 'name': orderBy = 'ORDER BY s.name ASC'; break;
    case 'ticker': orderBy = 'ORDER BY s.ticker ASC'; break;
  }

  try {
    const countResult = await pool.query(
      `SELECT count(*) FROM securities s ${where}`,
      params,
    );
    const total = parseInt(countResult.rows[0].count, 10);

    const dataParams = [...params, limit, offset];
    const result = await pool.query(
      `SELECT s.security_id, s.ticker, s.name, s.security_type,
              sc.score AS iald, sc.verdict, sc.active_signals,
              sa.avg_score_30d, sa.volatility_30d, sa.score_trend,
              spark.points AS sparkline
       FROM securities s
       LEFT JOIN LATERAL (
         SELECT score, verdict, active_signals
         FROM iald_scores
         WHERE security_id = s.security_id
         ORDER BY score_date DESC LIMIT 1
       ) sc ON true
       LEFT JOIN score_aggregates sa ON sa.security_id = s.security_id
       LEFT JOIN LATERAL (
         SELECT coalesce(json_agg(json_build_object('d', sub.score_date, 's', sub.score) ORDER BY sub.score_date), '[]'::json) AS points
         FROM (
           SELECT score_date, score
           FROM iald_scores
           WHERE security_id = s.security_id
           ORDER BY score_date DESC LIMIT 14
         ) sub
       ) spark ON true
       ${where}
       ${orderBy}
       LIMIT $${paramIdx} OFFSET $${paramIdx + 1}`,
      dataParams,
    );

    return NextResponse.json({
      securities: result.rows,
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
