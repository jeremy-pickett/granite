import { NextResponse } from 'next/server';
import { verifyRequest } from '@/lib/firebase-admin';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    await verifyRequest(request);

    const { ticker, filing_text, filing_type } = await request.json();
    if (!ticker || !filing_text) {
      return NextResponse.json({ error: 'ticker and filing_text required' }, { status: 400 });
    }

    const secRes = await pool.query(
      'SELECT name, security_type FROM securities WHERE ticker = $1',
      [ticker.toUpperCase()],
    );
    const companyName = secRes.rows[0]?.name ?? ticker;

    const systemPrompt = `You are a forensic financial analyst. Analyze SEC filings with extreme skepticism. You are looking for what management is trying to hide, not what they are promoting. Return valid JSON only, no markdown.`;

    const userPrompt = `Analyze this ${filing_type || 'SEC filing'} for ${companyName} (${ticker}).

Filing text (truncated):
${filing_text.slice(0, 15000)}

Return a JSON object with these exact keys:
{
  "green_flags": ["up to 5 genuinely positive findings about the company"],
  "red_flags": ["up to 5 concerning findings — financial stress, risk factors, declining metrics"],
  "suspect_sections": ["sections that look unusual compared to industry peers — vague language, missing data, changed methodology"],
  "weasel_words": ["specific phrases that use hedging, obfuscation, or minimizing language to hide bad news — quote the actual text"],
  "overall_risk": "low | medium | high | critical",
  "summary": "2-3 sentence assessment"
}`;

    let analysis = null;

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
            max_tokens: 2000,
            system: systemPrompt,
            messages: [{ role: 'user', content: userPrompt }],
          }),
        });
        if (resp.ok) {
          const result = await resp.json();
          const text = result.content?.[0]?.text ?? '';
          const jsonMatch = text.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            analysis = JSON.parse(jsonMatch[0]);
          }
        }
      } catch {}
    }

    if (!analysis) {
      analysis = {
        green_flags: [],
        red_flags: [],
        suspect_sections: [],
        weasel_words: [],
        overall_risk: 'unknown',
        summary: 'Analysis unavailable — API key not configured or rate limited.',
      };
    }

    return NextResponse.json({ analysis });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
