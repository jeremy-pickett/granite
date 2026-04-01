import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    await verifyRequest(request);

    const { cohort_name } = await request.json();
    if (!cohort_name?.trim()) {
      return NextResponse.json({ error: 'cohort_name required' }, { status: 400 });
    }

    // Fetch all securities with their latest scores for context
    const secResult = await pool.query(
      `SELECT s.ticker, s.name, s.security_type,
              sc.score AS iald, sc.verdict
       FROM securities s
       LEFT JOIN LATERAL (
         SELECT score, verdict FROM iald_scores
         WHERE security_id = s.security_id
         ORDER BY score_date DESC LIMIT 1
       ) sc ON true
       ORDER BY s.ticker`,
    );

    const secList = secResult.rows
      .map((r: { ticker: string; name: string; security_type: string; iald: number | null; verdict: string | null }) =>
        `${r.ticker} — ${r.name} (${r.security_type}${r.iald ? `, IALD: ${Number(r.iald).toFixed(2)} ${r.verdict}` : ''})`)
      .join('\n');

    const systemPrompt = `You are a financial classification assistant. Given a cohort name/description, select which securities from the provided list belong in that cohort. Return ONLY a JSON array of ticker symbols, nothing else. No explanation, no markdown, just the JSON array. Example: ["AAPL","MSFT","GOOG"]. Be thoughtful about the cohort concept — consider industry, sector, theme, risk profile, or whatever the name implies. Include 5-20 securities when reasonable.`;

    const userPrompt = `Cohort name: "${cohort_name.trim()}"\n\nAvailable securities:\n${secList}`;

    let tickers: string[] = [];

    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (anthropicKey) {
      try {
        const resp = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': anthropicKey,
            'anthropic-version': '2023-06-01',
          },
          body: JSON.stringify({
            model: 'claude-haiku-4-5-20251001',
            max_tokens: 1000,
            system: systemPrompt,
            messages: [{ role: 'user', content: userPrompt }],
          }),
        });
        if (resp.ok) {
          const result = await resp.json();
          const text = result.content?.[0]?.text ?? '[]';
          // Extract JSON array from response
          const match = text.match(/\[[\s\S]*\]/);
          if (match) {
            tickers = JSON.parse(match[0]);
          }
        }
      } catch {}
    }

    // Fallback: OpenAI
    if (tickers.length === 0) {
      const openaiKey = process.env.OPENAI_API_KEY;
      if (openaiKey) {
        try {
          const resp = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${openaiKey}`,
            },
            body: JSON.stringify({
              model: 'gpt-4o-mini',
              max_tokens: 1000,
              messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: userPrompt },
              ],
            }),
          });
          if (resp.ok) {
            const result = await resp.json();
            const text = result.choices?.[0]?.message?.content ?? '[]';
            const match = text.match(/\[[\s\S]*\]/);
            if (match) {
              tickers = JSON.parse(match[0]);
            }
          }
        } catch {}
      }
    }

    // Validate tickers exist in our DB
    if (tickers.length > 0) {
      const valid = await pool.query(
        'SELECT ticker FROM securities WHERE ticker = ANY($1)',
        [tickers.map((t: string) => t.toUpperCase())],
      );
      tickers = valid.rows.map((r: { ticker: string }) => r.ticker);
    }

    return NextResponse.json({ tickers });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
