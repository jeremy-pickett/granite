import { NextResponse } from 'next/server';
import pool from '@/lib/db';

// Get filings for a security + optional Claude analysis
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker')?.toUpperCase() ?? '';

  if (!ticker) {
    return NextResponse.json({ error: 'ticker required' }, { status: 400 });
  }

  try {
    const secRes = await pool.query(
      'SELECT security_id, name FROM securities WHERE ticker = $1',
      [ticker],
    );
    if (!secRes.rows[0]) {
      return NextResponse.json({ error: 'unknown ticker' }, { status: 404 });
    }
    const sid = secRes.rows[0].security_id;
    const companyName = secRes.rows[0].name;

    // Get SEC filings from raw_sec_filings if it exists, otherwise return empty
    let filings: unknown[] = [];
    try {
      const result = await pool.query(
        `SELECT filing_type, filing_date, description, filing_url, accession_number
         FROM raw_sec_filings
         WHERE security_id = $1
         ORDER BY filing_date DESC
         LIMIT 50`,
        [sid],
      );
      filings = result.rows;
    } catch {
      // Table may not exist yet — that's OK
    }

    // Get corporate records (loans, liens, judgments, etc.)
    let records: unknown[] = [];
    try {
      const result = await pool.query(
        `SELECT record_type, description, source_filing, filing_date, amount, collected_at
         FROM raw_corporate_records
         WHERE security_id = $1
         ORDER BY filing_date DESC
         LIMIT 50`,
        [sid],
      );
      records = result.rows;
    } catch {}

    // Get related entities (LLCs, subsidiaries)
    let entities: unknown[] = [];
    try {
      const result = await pool.query(
        `SELECT entity_name, entity_type, relationship, first_seen, last_seen
         FROM raw_related_entities
         WHERE security_id = $1
         ORDER BY entity_name`,
        [sid],
      );
      entities = result.rows;
    } catch {}

    // Get executives
    let executives: unknown[] = [];
    try {
      const result = await pool.query(
        `SELECT name, title, role_type, age, since, compensation, headshot_url
         FROM raw_executives
         WHERE security_id = $1
         ORDER BY
           CASE role_type
             WHEN 'c-suite' THEN 1
             WHEN 'director' THEN 2
             WHEN 'vp' THEN 3
             ELSE 4
           END, name`,
        [sid],
      );
      executives = result.rows;
    } catch {}

    // Get background check findings
    let backgrounds: unknown[] = [];
    try {
      const result = await pool.query(
        `SELECT executive_name, check_type, finding, severity, source, source_url, case_date
         FROM raw_executive_background
         WHERE security_id = $1
         ORDER BY severity DESC, case_date DESC`,
        [sid],
      );
      backgrounds = result.rows;
    } catch {}

    return NextResponse.json({
      ticker,
      company_name: companyName,
      filings,
      records,
      entities,
      executives,
      backgrounds,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
