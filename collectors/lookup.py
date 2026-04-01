#!/usr/bin/env python3
"""
Security Lookup — drill into a security with live price, fundamentals, and signals.

Usage:
    python collectors/lookup.py AAPL
    python collectors/lookup.py AAPL MSFT BTC-USD
    python collectors/lookup.py --all          # summary of all scored securities
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

try:
    import yfinance as yf
except ImportError:
    yf = None


def _fetch_live_quote(ticker, security_type):
    """Fetch real-time price, P/E, volume from yfinance."""
    if not yf:
        return {}
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "prev_close": info.get("previousClose"),
            "day_open": info.get("regularMarketOpen"),
            "day_high": info.get("regularMarketDayHigh"),
            "day_low": info.get("regularMarketDayLow"),
            "volume": info.get("regularMarketVolume"),
            "avg_volume_10d": info.get("averageDailyVolume10Day"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap": info.get("marketCap"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "short_name": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
    except Exception as e:
        return {"error": str(e)}


def _fmt_num(n, prefix="", suffix="", decimals=2):
    if n is None:
        return "—"
    if abs(n) >= 1e12:
        return f"{prefix}{n/1e12:.{decimals}f}T{suffix}"
    if abs(n) >= 1e9:
        return f"{prefix}{n/1e9:.{decimals}f}B{suffix}"
    if abs(n) >= 1e6:
        return f"{prefix}{n/1e6:.{decimals}f}M{suffix}"
    if abs(n) >= 1e3:
        return f"{prefix}{n/1e3:.{decimals}f}K{suffix}"
    return f"{prefix}{n:.{decimals}f}{suffix}"


def _fmt_pct(n):
    if n is None:
        return "—"
    return f"{n:+.2f}%"


def lookup_security(ticker):
    """Full drill-down on a single security."""
    ticker = ticker.upper()

    # Resolve security_id
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT security_id, ticker, name, security_type FROM securities WHERE ticker = %s",
                (ticker,)
            )
            row = cur.fetchone()

    if not row:
        print(f"  Unknown ticker: {ticker}")
        return

    sid, ticker, name, sec_type = row

    print(f"\n{'═' * 70}")
    print(f"  {ticker}  —  {name or ''}  ({sec_type})")
    print(f"{'═' * 70}")

    # ── Live quote ────────────────────────────────────────────────────
    print("\n  Fetching live quote...", end="", flush=True)
    quote = _fetch_live_quote(ticker, sec_type)
    print("\r", end="")

    if quote.get("error"):
        print(f"  Quote error: {quote['error']}")
    elif quote.get("price"):
        price = quote["price"]
        prev = quote.get("prev_close")
        change = ((price - prev) / prev * 100) if prev else None

        print(f"  PRICE       {_fmt_num(price, '$')}")
        print(f"  CHANGE      {_fmt_pct(change)} from prev close ({_fmt_num(prev, '$')})")
        print(f"  DAY         {_fmt_num(quote.get('day_open'), '$')} open  |  "
              f"{_fmt_num(quote.get('day_high'), '$')} high  |  "
              f"{_fmt_num(quote.get('day_low'), '$')} low")
        print(f"  52W RANGE   {_fmt_num(quote.get('fifty_two_week_low'), '$')} — "
              f"{_fmt_num(quote.get('fifty_two_week_high'), '$')}")

        vol = quote.get("volume")
        avg_vol = quote.get("avg_volume_10d")
        velocity = (vol / avg_vol) if vol and avg_vol else None
        print(f"  VOLUME      {_fmt_num(vol, decimals=0)} "
              f"(10d avg: {_fmt_num(avg_vol, decimals=0)})"
              f"  velocity: {velocity:.2f}x" if velocity else "")

        if sec_type == "equity":
            pe = quote.get("pe_ratio")
            fpe = quote.get("forward_pe")
            print(f"  P/E         {_fmt_num(pe) if pe else '—'} trailing  |  "
                  f"{_fmt_num(fpe) if fpe else '—'} forward")
            print(f"  MARKET CAP  {_fmt_num(quote.get('market_cap'), '$')}")
            if quote.get("sector"):
                print(f"  SECTOR      {quote.get('sector')} / {quote.get('industry', '')}")
    else:
        print("  No live quote available")

    # ── IALD Score ────────────────────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT score, verdict, active_signals, score_date
                FROM iald_scores
                WHERE security_id = %s
                ORDER BY score_date DESC LIMIT 1
            """, (sid,))
            score_row = cur.fetchone()

    print(f"\n  {'─' * 40}")
    if score_row:
        score, verdict, n_signals, score_date = score_row
        bar_len = int(float(score) * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(f"  IALD SCORE  {float(score):.4f}  [{bar}]  {verdict}")
        print(f"  SIGNALS     {n_signals} active  (as of {score_date})")
    else:
        print(f"  IALD SCORE  no score recorded")

    # ── Active Signals ────────────────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=168)
            cur.execute("""
                SELECT signal_type, contribution, confidence, direction,
                       magnitude, description, detected_at
                FROM signals
                WHERE security_id = %s AND detected_at > %s
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY contribution DESC
            """, (sid, cutoff))
            signals = cur.fetchall()

    if signals:
        print(f"\n  ACTIVE SIGNALS ({len(signals)}):")
        for stype, contrib, conf, direction, mag, desc, detected in signals:
            age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - detected).total_seconds() / 3600
            dir_icon = {"bullish": "+", "bearish": "-", "neutral": "~"}.get(direction, "?")
            print(f"    [{dir_icon}] {stype:30s}  c={float(contrib):.3f}  "
                  f"conf={float(conf):.2f}  {mag or '':10s}  {age_h:.0f}h ago")
            if desc:
                print(f"        {desc[:80]}")
    else:
        print(f"\n  No active signals in last 7 days")

    # ── Score Trend ───────────────────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT avg_score_30d, min_score_30d, max_score_30d,
                       volatility_30d, score_trend, data_points
                FROM score_aggregates
                WHERE security_id = %s
            """, (sid,))
            agg = cur.fetchone()

    if agg:
        avg, mn, mx, vol, trend, pts = agg
        print(f"\n  30D TREND   avg={float(avg):.4f}  min={float(mn):.4f}  "
              f"max={float(mx):.4f}  vol={float(vol):.4f}  → {trend}  ({pts} days)")

    # ── Analyst Ratings Consensus ────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT total_analysts, mean_rating, median_rating, mode_rating, mode_label,
                       strong_buy_pct, buy_pct, hold_pct, sell_pct, strong_sell_pct,
                       mean_price_target, high_price_target, low_price_target,
                       median_price_target, snapshot_date
                FROM raw_analyst_consensus
                WHERE security_id = %s
                ORDER BY snapshot_date DESC LIMIT 1
            """, (sid,))
            consensus = cur.fetchone()

    if consensus:
        (n_analysts, mean_r, median_r, mode_r, mode_label,
         sb_pct, b_pct, h_pct, s_pct, ss_pct,
         mean_pt, high_pt, low_pt, median_pt, snap_date) = consensus

        # Rating bar visualization
        rating_labels = {5: "Strong Buy", 4: "Buy", 3: "Hold", 2: "Sell", 1: "Strong Sell"}
        mean_label = rating_labels.get(round(float(mean_r)), "")

        print(f"\n  ANALYST CONSENSUS ({int(n_analysts)} analysts, {snap_date}):")
        print(f"    Mean rating:   {float(mean_r):.2f} / 5.00  ({mean_label})")
        print(f"    Median:        {float(median_r):.2f}    Mode: {mode_label}")

        # Distribution bar
        pcts = [
            ("SBuy", float(sb_pct)), ("Buy", float(b_pct)),
            ("Hold", float(h_pct)), ("Sell", float(s_pct)), ("SSel", float(ss_pct))
        ]
        bar_parts = []
        for label, pct in pcts:
            n = max(1, round(pct / 5)) if pct > 0 else 0
            bar_parts.append("█" * n)
        total_bar = "".join(bar_parts)
        print(f"    Distribution:  [{total_bar:20s}]")
        print(f"      Strong Buy {float(sb_pct):5.1f}%  |  Buy {float(b_pct):5.1f}%  |  "
              f"Hold {float(h_pct):5.1f}%  |  Sell {float(s_pct):5.1f}%  |  Strong Sell {float(ss_pct):5.1f}%")

        if mean_pt:
            curr_price = quote.get("price")
            upside = ((float(mean_pt) - curr_price) / curr_price * 100) if curr_price else None
            print(f"    Price target:  {_fmt_num(float(mean_pt), '$')} mean  "
                  f"({_fmt_num(float(low_pt), '$')} low — {_fmt_num(float(high_pt), '$')} high)"
                  + (f"  [{_fmt_pct(upside)} upside]" if upside is not None else ""))

    # Recent individual ratings
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rating_date, company, action, from_rating, to_rating
                FROM raw_analyst_ratings
                WHERE security_id = %s
                ORDER BY rating_date DESC
                LIMIT 8
            """, (sid,))
            ind_ratings = cur.fetchall()

    if ind_ratings:
        print(f"\n  RECENT ANALYST ACTIONS:")
        for rd, company, action, from_r, to_r in ind_ratings:
            arrow = f"{from_r} → {to_r}" if from_r and to_r else to_r or from_r or ""
            print(f"    {rd}  {company[:30]:30s}  {action:12s}  {arrow}")

    # ── Recent Institutional Moves ────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT holder_name, shares_changed, change_pct, report_date
                FROM raw_institutional_moves
                WHERE security_id = %s
                ORDER BY abs(shares_changed) DESC
                LIMIT 5
            """, (sid,))
            inst = cur.fetchall()

    if inst:
        print(f"\n  INSTITUTIONAL MOVES (top 5 by size):")
        for holder, shares, pct, rdate in inst:
            pct_str = f"{float(pct):+.1f}%" if pct else ""
            print(f"    {holder[:35]:35s}  {int(shares):>+12,} shares  {pct_str:>8s}  {rdate}")

    # ── Recent Press Releases ─────────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT headline, source, published_at
                FROM raw_press_releases
                WHERE security_id = %s
                ORDER BY published_at DESC
                LIMIT 5
            """, (sid,))
            prs = cur.fetchall()

    if prs:
        print(f"\n  PRESS RELEASES (recent):")
        for headline, source, pub in prs:
            pub_str = pub.strftime("%m/%d") if pub else ""
            print(f"    {pub_str}  {headline[:65]}")
            if source:
                print(f"          via {source[:40]}")

    # ── LLM Outlook ──────────────────────────────────────────────────
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT direction, analysis, model, query_seconds, outlook_date
                    FROM raw_llm_outlooks
                    WHERE security_id = %s
                    ORDER BY outlook_date DESC LIMIT 1
                """, (sid,))
                llm = cur.fetchone()
            except Exception:
                llm = None

    if llm:
        direction, analysis, model, qsec, odate = llm
        dir_icon = {"bullish": "+", "bearish": "-", "neutral": "~"}.get(direction, "?")
        dir_color = {"bullish": "\033[92m", "bearish": "\033[91m", "neutral": "\033[90m"}.get(direction, "")
        reset = "\033[0m"
        print(f"\n  LLM OUTLOOK ({model}, {odate}, {float(qsec):.1f}s):")
        print(f"    Direction: {dir_color}[{dir_icon}] {direction.upper()}{reset}")
        # Word-wrap the analysis at 72 chars
        words = analysis.split()
        line = "    "
        for w in words:
            if len(line) + len(w) + 1 > 76:
                print(line)
                line = "    " + w
            else:
                line += " " + w if line.strip() else "    " + w
        if line.strip():
            print(line)

    print()


def summary_all():
    """Show all securities with IALD scores, sorted by score descending."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.ticker, s.name, i.score, i.verdict, i.active_signals, i.score_date
                FROM iald_scores i
                JOIN securities s ON s.security_id = i.security_id
                WHERE i.score_date = (SELECT max(score_date) FROM iald_scores)
                ORDER BY i.score DESC
            """)
            rows = cur.fetchall()

    if not rows:
        print("No scores recorded yet. Run: python collectors/collectors_run.py --score")
        return

    print(f"\n{'═' * 75}")
    print(f"  IALD SCORES — {rows[0][5]}")
    print(f"{'═' * 75}")
    print(f"  {'TICKER':8s} {'NAME':25s} {'SCORE':>8s} {'VERDICT':>10s} {'SIGNALS':>8s}")
    print(f"  {'─'*8} {'─'*25} {'─'*8} {'─'*10} {'─'*8}")
    for ticker, name, score, verdict, n_sig, _ in rows:
        name_short = (name or "")[:25]
        print(f"  {ticker:8s} {name_short:25s} {float(score):8.4f} {verdict:>10s} {n_sig:>8d}")
    print(f"\n  {len(rows)} securities scored\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python collectors/lookup.py AAPL [MSFT BTC-USD ...]")
        print("       python collectors/lookup.py --all")
        sys.exit(1)

    if args[0] == "--all":
        summary_all()
    else:
        for ticker in args:
            lookup_security(ticker)
