import { NextResponse } from 'next/server';
import pool from '@/lib/db';

async function safeQuery(sql: string, params: unknown[]) {
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

async function getSecurityDetail(ticker: string) {
  const secRes = await pool.query(
    'SELECT security_id, ticker, name, security_type FROM securities WHERE ticker = $1',
    [ticker.toUpperCase()],
  );
  if (secRes.rows.length === 0) return null;
  const sec = secRes.rows[0];
  const sid = sec.security_id;

  const [signals, snapshot, consensus, agg, debt, llm] = await Promise.all([
    safeQuery(
      `SELECT signal_type, contribution, confidence, direction, magnitude, description
       FROM signals WHERE security_id = $1
         AND detected_at > now() - interval '168 hours'
         AND (expires_at IS NULL OR expires_at > now())
       ORDER BY contribution DESC LIMIT 10`,
      [sid],
    ),
    safeQuery(
      `SELECT price, change_pct, pe_ratio, forward_pe, market_cap, volume_at_snap,
              volume_velocity, avg_volume_10d
       FROM raw_market_snapshots WHERE security_id = $1
       ORDER BY snapshot_time DESC LIMIT 1`,
      [sid],
    ),
    safeQuery(
      `SELECT total_analysts, mean_rating, mode_label,
              strong_buy_pct, buy_pct, hold_pct, sell_pct, strong_sell_pct,
              mean_price_target, high_price_target, low_price_target
       FROM raw_analyst_consensus WHERE security_id = $1
       ORDER BY snapshot_date DESC LIMIT 1`,
      [sid],
    ),
    safeQuery(
      `SELECT avg_score_30d, min_score_30d, max_score_30d, volatility_30d, score_trend
       FROM score_aggregates WHERE security_id = $1`,
      [sid],
    ),
    safeQuery(
      `SELECT debt_to_equity, interest_to_revenue, free_cash_flow
       FROM raw_debt_metrics WHERE security_id = $1
       ORDER BY period_date DESC LIMIT 1`,
      [sid],
    ),
    safeQuery(
      `SELECT direction, analysis, model, outlook_date
       FROM raw_llm_outlooks WHERE security_id = $1
       ORDER BY outlook_date DESC LIMIT 1`,
      [sid],
    ),
  ]);

  // Compute signal summary
  const bullish = signals.filter((s: Record<string, unknown>) => s.direction === 'bullish').length;
  const bearish = signals.filter((s: Record<string, unknown>) => s.direction === 'bearish').length;
  const totalContrib = signals.reduce((sum: number, s: Record<string, unknown>) => sum + Number(s.contribution), 0);

  // Get latest IALD score
  const scoreRes = await safeQuery(
    `SELECT score, verdict, active_signals FROM iald_scores
     WHERE security_id = $1 ORDER BY score_date DESC LIMIT 1`,
    [sid],
  );

  return {
    ...sec,
    iald: scoreRes[0]?.score ?? null,
    verdict: scoreRes[0]?.verdict ?? null,
    active_signals: scoreRes[0]?.active_signals ?? 0,
    signals,
    signal_summary: { bullish, bearish, neutral: signals.length - bullish - bearish, total_contribution: totalContrib },
    snapshot: snapshot[0] ?? null,
    consensus: consensus[0] ?? null,
    aggregates: agg[0] ?? null,
    debt: debt[0] ?? null,
    llm_outlook: llm[0] ?? null,
  };
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const left = searchParams.get('left')?.toUpperCase();
  const right = searchParams.get('right')?.toUpperCase();

  if (!left || !right) {
    return NextResponse.json({ error: 'left and right tickers required' }, { status: 400 });
  }

  try {
    const [leftData, rightData] = await Promise.all([
      getSecurityDetail(left),
      getSecurityDetail(right),
    ]);

    if (!leftData || !rightData) {
      return NextResponse.json({ error: 'one or both tickers not found' }, { status: 404 });
    }

    return NextResponse.json({ left: leftData, right: rightData });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  // POST version that calls Haiku for the "$1000 opinion"
  const body = await request.json();
  const { left, right } = body;

  if (!left || !right) {
    return NextResponse.json({ error: 'left and right tickers required' }, { status: 400 });
  }

  try {
    const [leftData, rightData] = await Promise.all([
      getSecurityDetail(left),
      getSecurityDetail(right),
    ]);

    if (!leftData || !rightData) {
      return NextResponse.json({ error: 'one or both tickers not found' }, { status: 404 });
    }

    // Build context for Haiku
    const buildContext = (d: Record<string, unknown>) => {
      const snap = d.snapshot as Record<string, unknown> | null;
      const cons = d.consensus as Record<string, unknown> | null;
      const debt = d.debt as Record<string, unknown> | null;
      const sig = d.signal_summary as Record<string, unknown>;
      const agg = d.aggregates as Record<string, unknown> | null;
      const llm = d.llm_outlook as Record<string, unknown> | null;

      let ctx = `${d.ticker} (${d.name}, ${d.security_type}):\n`;
      ctx += `  IALD Score: ${d.iald ?? 'N/A'} (${d.verdict ?? 'N/A'}), ${d.active_signals} active signals\n`;
      ctx += `  Signal balance: ${sig.bullish} bullish, ${sig.bearish} bearish\n`;
      if (agg) ctx += `  30d avg: ${agg.avg_score_30d}, volatility: ${agg.volatility_30d}, trend: ${agg.score_trend}\n`;
      if (snap) {
        ctx += `  Price: $${snap.price}, change: ${snap.change_pct}%\n`;
        if (snap.pe_ratio) ctx += `  P/E: ${snap.pe_ratio} trailing, ${snap.forward_pe} forward\n`;
        if (snap.market_cap) ctx += `  Market cap: $${snap.market_cap}\n`;
        if (snap.volume_velocity) ctx += `  Volume velocity: ${snap.volume_velocity}x avg\n`;
      }
      if (cons) {
        ctx += `  Analyst consensus: ${cons.mean_rating}/5 (${cons.mode_label}), ${cons.total_analysts} analysts\n`;
        if (cons.mean_price_target) ctx += `  Price target: $${cons.mean_price_target} mean ($${cons.low_price_target}-$${cons.high_price_target})\n`;
      }
      if (debt) {
        ctx += `  Debt/equity: ${debt.debt_to_equity}, interest/revenue: ${debt.interest_to_revenue}\n`;
        if (debt.free_cash_flow) ctx += `  Free cash flow: $${debt.free_cash_flow}\n`;
      }
      if (llm) ctx += `  AI outlook: ${llm.direction} — ${(llm.analysis as string)?.substring(0, 100)}\n`;
      return ctx;
    };

    const leftCtx = buildContext(leftData as Record<string, unknown>);
    const rightCtx = buildContext(rightData as Record<string, unknown>);

    // Call LLM — try Anthropic first, fall back to OpenAI
    const systemPrompt = 'You are a bartender who happens to know a lot about markets. Charming, a little witty, but never hyperbolic. You tell people what you would do with your own money, not what they should do. Plain text only, no markdown, no bullet points, no formatting characters. Never end with a question. Never say things like "could skyrocket" or "massive upside." You are honest about what you do not know. Keep it to 3-4 sentences.';
    const userPrompt = `A regular just slid two napkins across the bar — ${left} and ${right}. They have $1000 and want to know which one you would put it in, and why. Give them the edge in both absolute and percentage terms if the data supports it. Here is what the house knows:\n\n${leftCtx}\n${rightCtx}`;

    let haiku_opinion = null;

    // Try Anthropic (Claude Haiku)
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (anthropicKey && !haiku_opinion) {
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
            max_tokens: 400,
            system: systemPrompt,
            messages: [{ role: 'user', content: userPrompt }],
          }),
        });
        if (resp.ok) {
          const result = await resp.json();
          haiku_opinion = result.content?.[0]?.text?.replace(/[*_`#~\[\]|>]/g, '') ?? null;
        }
      } catch {
        // Fall through to OpenAI
      }
    }

    // Fallback: OpenAI (gpt-4o-mini)
    const openaiKey = process.env.OPENAI_API_KEY;
    if (!haiku_opinion && openaiKey) {
      try {
        const resp = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${openaiKey}`,
          },
          body: JSON.stringify({
            model: 'gpt-4o-mini',
            max_tokens: 400,
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: userPrompt },
            ],
          }),
        });
        if (resp.ok) {
          const result = await resp.json();
          haiku_opinion = result.choices?.[0]?.message?.content?.replace(/[*_`#~\[\]|>]/g, '') ?? null;
        } else {
          const errBody = await resp.text();
          console.error('OpenAI API error:', resp.status, errBody.substring(0, 200));
        }
      } catch (e) {
        console.error('OpenAI call failed:', e);
      }
    }

    if (!haiku_opinion) {
      haiku_opinion = 'Both AI providers are currently unavailable. The data comparison above still reflects all available metrics.';
    }

    return NextResponse.json({
      left: leftData,
      right: rightData,
      haiku_opinion,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
