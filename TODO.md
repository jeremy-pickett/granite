# TODO

## Layer S — Signal Blocks (Prototype Working, Needs Hardening)

**Status**: Proof of concept validated 2026-03-31. Lossless: perfect. Q95: 4/4 blocks found, 2 bit errors in payload. Zero false positives on clean images.

**What it does**: Inserts 8-pixel-wide controlled columns into the image at 8-aligned positions, padded with black to maintain JPEG grid alignment. Each column is a native JPEG 8x8 block carrying 32 bits: 4-bit signature + 4-bit block ID + 4-bit next-pointer + 20-bit payload. Blocks chain together via ID/next pointers. Payload encodes a short URL path (e.g., `signaldelta.com/p/xK9mR2vL4n`). Tiles vote vertically for error correction.

**What needs work**:
- [ ] Widen the pixel gap (currently 96 vs 160 on R channel) — Q95 JPEG shifts values ~8 counts, sometimes flipping bits. Try 64 vs 192 or 48 vs 208.
- [ ] Add forward error correction (Reed-Solomon or simple repetition coding) on the payload bits so 2-3 bit errors don't corrupt the URL.
- [ ] Q85+ survival: the 64-count gap isn't enough. Investigate using ALL THREE channels (R, G, B) each carrying the same bits (3x redundancy) or using luma-domain encoding which JPEG preserves better than individual RGB channels.
- [ ] Wire into `verify_image.py` and `injection_report.py` behind `--experimental-sigblock` flag (same pattern as DCT and thermo layers).
- [ ] Visual blending: the gray stripes are visible. Investigate making the non-data pixels (rows 4-7) match neighbor colors while keeping data pixels (rows 0-3) at fixed levels.
- [ ] Test with real-world social media pipelines (Twitter/X re-encodes at Q85, Instagram at Q75-ish).

**Files**: `backend/src/signal_block.py`

---

## Adaptive Chain Threshold (Integrated)

**Status**: Integrated as default 2026-03-31.

Formula: `ceil(log(n_gated) / log(1/prime_rate)) + 2`, detection requires chain > threshold (strictly greater). Adapts to image content — smooth images get lower thresholds, heavily textured images get higher ones. Eliminated all chain false positives on clean DIV2K images (was 3/5 FP with fixed threshold=6).

**Trade-off**: Some embedded images at Q85+ now fall below the adaptive threshold because the signal isn't strong enough relative to natural noise. This is honest — the old threshold was lying by calling natural chains "detected."

---

## Bidirectional Chain Following (Integrated)

**Status**: Integrated as default 2026-03-31. +6 detections on the adversarial harness, zero new false positives.

---

## Experimental Layers (Behind Flags)

### Layer DCT (`--experimental-dct`)
DCT-domain prime embedding. Concept: encode primes into mid-frequency AC coefficients. **Current status: does not differentiate from natural.** The target coefficient position (zigzag 10) has ~20% natural prime rate in both phases. Needs a fundamentally different coefficient selection strategy or modular encoding approach.

### Layer T (`--experimental-thermo`)
Thermodynamic consensus. Concept: embed 10K+ minimal prime nudges, detect via binomial test. **Current status: works perfectly on lossless (+30% elevation, zero FP). Completely dead at Q95+.** The ±2 pixel nudge is smaller than JPEG quantization noise. Needs either larger nudges (hurts PSNR) or compression-resistant embedding domain.

---

## Alidade / IALD — Open Items

### Backtesting (Critical — accumulating data now)
- [ ] After 7 days of Coinglass funding data: validate contrarian signal — when funding was extreme negative, did price rise in next 1-7 days?
- [ ] After 14 days: run full backtest.py across all 33 signal types. Validate tier assignments against actual hit rates.
- [ ] After 30 days: cross-layer divergence analysis — when Fear & Greed, funding rates, and DeFi TVL disagree, which layer was right?
- [ ] Compute per-signal Sharpe ratio and information coefficient. Recalibrate tier weights from data, not intuition.
- [ ] Crypto death spiral phase validation: backtest the 5-phase classifier against known historical rug pulls and collapses.

### Pending Collectors
- [ ] Dune Analytics collector (API key configured, not yet built) — on-chain SQL queries for DEX volume, whale concentration, stablecoin flows
- [ ] Binance funding rates (direct API, supplement Coinglass with per-trade granularity)
- [ ] Deribit crypto options (IV surface, put/call ratios, max pain)
- [ ] Betfair Exchange odds (politics, economics events)

### Data Quality
- [ ] Coinglass: 39 outliers with |funding rate| > 10% — most are single-exchange micro-tokens. Monitor over time.
- [ ] Analyst ratings: Finnhub upgrade-downgrade endpoint requires paid tier. Currently building consensus from aggregate data only.
- [ ] Market snapshot: crypto price field returns null from yfinance .info — needs alternate field for crypto tickers.

---

## Granite / Provenance — Open Items (Carried Forward)
- [ ] 4096px embedding fix (large images)
- [ ] Prime-step (17px) resize test
- [ ] nginx + Let's Encrypt TLS for signaldelta.com
