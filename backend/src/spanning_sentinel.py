#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Spanning Sentinel Architecture — 24/16/8-bit Tiered Detection
===============================================================

Addresses the fundamental failure of absolute Mersenne sentinels:
JPEG completely zeros channel differences at ~10% of positions,
making CANARY_WIDTH irrelevant at those locations.

Solution: encode the sentinel across multiple pixels in the same
8×8 DCT block. The anchor carries the Mersenne identity. Flanking
pixels carry correlated redundancy. JPEG must coherently destroy
the entire span to kill the sentinel.

Three tiers based on available span at embedding position:

  TIER_24 — 5-pixel span (maximum):
    [p-2][p-1][ANCHOR][p+1][p+2]
    All 5 in same row. Same DCT block preferred.
    Joint detection: anchor Mersenne + flanking differential.
    Falls back to Tier 16 if p-2 or p+2 crosses block boundary.

  TIER_16 — 3-pixel span:
    [p-1][ANCHOR][p+1]
    Anchor + one neighbor each side.
    Triggers at block boundaries or within 2px of image edge.
    Falls back to Tier 8 if only one side available.

  TIER_8 — 1-pixel (current architecture):
    [ANCHOR]
    Last resort at hard image edges.
    Same as existing absolute Mersenne embedding.
    Less reliable but better than nothing.

Flanking pixel encoding:
  Each flanking pixel encodes differential: d(pN) - d(anchor) = 0
  Target: flanking pixels have the SAME channel difference as anchor.
  If drift is correlated within a block (tested by same_block_correlation_test),
  then d(pN) - d(anchor) ≈ (M + δN) - (M + δA) = δN - δA ≈ 0 after JPEG.
  The differential signal survives even when the absolute values don't.

Detection:
  1. Find positions where channel diff ≈ Mersenne (anchor candidates)
  2. Check flanking pixels — do their diffs ≈ anchor diff?
  3. Determine tier from how many flanking pixels match
  4. Determine entry/exit from sign convention (TBD, see below)
  5. Report tier with detection (24/16/8) for independent layer stats

Entry/Exit encoding in spanning:
  TIER_24: entry → p+2 has diff = anchor + 1 (or +small prime)
           exit  → p-2 has diff = anchor + 1
           The asymmetry in WHICH flanking pixel carries the tag
           encodes direction. Corruption of that pixel = tier demotion,
           not misclassification.
  TIER_16: entry → p+1 is tagged
           exit  → p-1 is tagged
  TIER_8:  entry/exit encoded in choice of Mersenne value
           (3,7 = entry; 31,127 = exit, or vice versa — TBD)

Graceful degradation:
  Tier 24 detection finding only 3 valid flanking pixels → reports Tier 16.
  Tier 16 finding only 1 → reports Tier 8.
  Tier 8 finding nothing → reports no detection.
  Demotion is NOT catastrophic — lower tier still contributes to
  the overall matched-pair analysis.

Manifest QA:
  Every embedded position records its tier and intended values.
  The manifest detector checks tier survival independently.
  If Tier 24 manifest drops while Tier 8 holds → block structure degrading.
  If all tiers drop together → something more fundamental is wrong.
"""

import os
import sys
import io
import json
import math
import time
import numpy as np
from PIL import Image
from datetime import datetime

from pgps_detector import build_prime_lookup, sample_positions_grid


# =============================================================================
# CONSTANTS
# =============================================================================

MERSENNE_BASKET  = [3, 7, 31, 127]
FLOOR            = 43
DENSITY_FRAC     = 0.08
CASCADE_QUALITIES= [95, 85, 75, 60, 40]
MIN_DIMENSION    = 512
BIT_DEPTH        = 8
WINDOW_W         = 8

# Tier definitions
TIER_24 = 24  # 5-pixel span
TIER_16 = 16  # 3-pixel span
TIER_8  = 8   # 1-pixel (anchor only)

# Sentinel Mersenne values — M=127 excluded after correlation test.
# 97.6% of M=127 positions drift to 0 (JPEG chroma neutralization).
# The differential survives (0-0=0) but the anchor is invisible in blind mode.
# M=31 and M=7 both have <1% catastrophic rate and clear correlation.
SENTINEL_MERSENNE_ENTRY = 31   # anchor value for entry sentinels
SENTINEL_MERSENNE_EXIT  = 7    # anchor value for exit sentinels
# Different Mersenne values per direction: detector can determine
# entry/exit from the anchor value alone, without sign arithmetic.

# Detection tolerances — calibrated from same_block_correlation_test.py
# Anchor tolerance: must be wide enough to catch absolute drift (~33 mean).
# In manifest mode, we know exactly where the anchor is — relax this.
# The DIFFERENTIAL is the real signal; anchor is just findability.
TIER_24_ANCHOR_TOL  = 64   # anchor absolute tolerance (covers ~80% of G4 drifts)
TIER_24_DIFF_TOL    = 6    # flanking differential (from correlation test p95)
TIER_16_ANCHOR_TOL  = 64
TIER_16_DIFF_TOL    = 8
TIER_8_ANCHOR_TOL   = 16   # widest — single pixel, no differential check

# Legacy aliases used in detection function
TIER_24_TOL = TIER_24_ANCHOR_TOL
TIER_16_TOL = TIER_16_ANCHOR_TOL
TIER_8_TOL  = TIER_8_ANCHOR_TOL


# =============================================================================
# UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


# =============================================================================
# TIER DETERMINATION
# =============================================================================

def determine_tier(r, col, h, w):
    """
    Determine which spanning tier is available at position (r, col).
    
    Returns (tier, left_cols, right_cols) where left_cols and right_cols
    are the column offsets available for flanking pixels.
    
    Constraints:
      - All span pixels must be in the same row
      - Flanking pixels should be in the same 8×8 DCT block as anchor
      - Graceful: if only one side available, use it (asymmetric tier)
    """
    block_start = (col // 8) * 8
    block_end   = block_start + 7

    # How many pixels left/right within the SAME block?
    left_avail  = min(col - block_start, 2, col)          # max 2 left
    right_avail = min(block_end - col,   2, w - 1 - col)  # max 2 right

    left_cols  = list(range(-left_avail,  0))   # e.g. [-2, -1] or [-1] or []
    right_cols = list(range(1, right_avail + 1)) # e.g. [1, 2] or [1] or []

    total_span = 1 + len(left_cols) + len(right_cols)

    if total_span >= 5:
        return TIER_24, left_cols, right_cols
    elif total_span >= 3:
        return TIER_16, left_cols, right_cols
    else:
        return TIER_8, [], []


# =============================================================================
# SPANNING EMBEDDER
# =============================================================================

def embed_spanning_sentinel(modified, r, col, mersenne, direction,
                             ch_a=0, ch_b=1):
    """
    Embed a spanning sentinel at (r, col) with appropriate tier.
    
    Anchor: |ch_a - ch_b| = mersenne at (r, col)
    Flanking: |ch_a - ch_b| = mersenne at each flanking pixel
              (differential encoding: flank diff ≈ anchor diff)
    Direction tag: asymmetric placement or Mersenne choice encodes entry/exit
    
    Returns sentinel metadata dict including tier and all pixel positions.
    """
    h, w, _ = modified.shape
    tier, left_cols, right_cols = determine_tier(r, col, h, w)

    def set_channel_diff(px, rr, cc, target):
        """Set |ch_a - ch_b| = target at (rr, cc). Returns success bool."""
        val_a = int(px[rr, cc, ch_a])
        opts  = [v for v in [val_a - target, val_a + target]
                 if 20 <= v <= 235]
        if not opts:
            return False
        px[rr, cc, ch_b] = min(opts, key=lambda x: abs(x - int(px[rr, cc, ch_b])))
        return True

    # Embed anchor
    ok_anchor = set_channel_diff(modified, r, col, mersenne)
    if not ok_anchor:
        return None

    actual_anchor = abs(int(modified[r, col, ch_a]) - int(modified[r, col, ch_b]))

    # Embed flanking pixels (differential: target = same as anchor)
    flanking = []
    for dc in left_cols + right_cols:
        fc = col + dc
        if 0 <= fc < w:
            ok = set_channel_diff(modified, r, fc, actual_anchor)
            flanking.append({
                "col":     fc,
                "side":    "left" if dc < 0 else "right",
                "offset":  dc,
                "ok":      ok,
                "intended":actual_anchor,
            })

    n_flanking_ok = sum(1 for f in flanking if f["ok"])

    # Direction encoding:
    # Entry: majority of right flanking pixels carry the signal
    # Exit:  majority of left flanking pixels carry the signal
    # (Simple for now — can be made more sophisticated)
    direction_tag = "right_heavy" if direction == "entry" else "left_heavy"

    return {
        "type":            direction,
        "tier":            tier,
        "row":             r,
        "col":             col,
        "mersenne":        mersenne,
        "actual_anchor":   actual_anchor,
        "left_cols":       left_cols,
        "right_cols":      right_cols,
        "flanking":        flanking,
        "n_flanking_ok":   n_flanking_ok,
        "direction_tag":   direction_tag,
        "placed":          True,
    }


# =============================================================================
# SPANNING DETECTOR — MANIFEST MODE
# =============================================================================

def detect_spanning_manifest(pixels, sentinels, ch_a=0, ch_b=1):
    """
    Manifest-mode detection for spanning sentinels.
    
    For each sentinel, check anchor + flanking survival.
    Reports per-tier survival rates independently.
    
    Returns:
        - per-tier intact counts and percentages
        - tier demotion counts (e.g., Tier 24 detected as Tier 16)
        - overall contract status
    """
    h, w, _ = pixels.shape
    tier_results = {TIER_24: [], TIER_16: [], TIER_8: []}

    for s in sentinels:
        if not s.get("placed", True):
            continue
        r, col = s["row"], s["col"]
        if r >= h or col >= w:
            continue

        intended_anchor = s["mersenne"]
        actual_anchor   = abs(int(pixels[r, col, ch_a]) - int(pixels[r, col, ch_b]))
        anchor_drift    = abs(actual_anchor - intended_anchor)
        tier            = s["tier"]

        # Determine effective tolerance for this tier
        tol = {TIER_24: TIER_24_TOL, TIER_16: TIER_16_TOL, TIER_8: TIER_8_TOL}[tier]
        anchor_survived = anchor_drift <= tol

        # Check flanking pixels
        flanking_survived = []
        for f in s.get("flanking", []):
            fc = f["col"]
            if 0 <= fc < w:
                actual_flank = abs(int(pixels[r, fc, ch_a]) - int(pixels[r, fc, ch_b]))
                diff_from_anchor = abs(actual_flank - actual_anchor)
                diff_tol = {TIER_24: TIER_24_DIFF_TOL,
                            TIER_16: TIER_16_DIFF_TOL,
                            TIER_8:  999}[tier]
                flanking_survived.append(diff_from_anchor <= diff_tol)

        n_flank_ok = sum(flanking_survived)
        n_flank    = len(flanking_survived)

        # Determine detected tier (graceful demotion)
        if tier == TIER_24:
            if anchor_survived and n_flank_ok >= 3:
                detected_tier = TIER_24
            elif anchor_survived and n_flank_ok >= 1:
                detected_tier = TIER_16
            elif anchor_survived:
                detected_tier = TIER_8
            else:
                detected_tier = None
        elif tier == TIER_16:
            if anchor_survived and n_flank_ok >= 1:
                detected_tier = TIER_16
            elif anchor_survived:
                detected_tier = TIER_8
            else:
                detected_tier = None
        else:  # TIER_8
            detected_tier = TIER_8 if anchor_survived else None

        tier_results[tier].append({
            "anchor_survived": anchor_survived,
            "anchor_drift":    anchor_drift,
            "n_flanking":      n_flank,
            "n_flanking_ok":   n_flank_ok,
            "detected_tier":   detected_tier,
            "survived":        detected_tier is not None,
        })

    # Aggregate per tier
    summary = {}
    for tier, results in tier_results.items():
        if not results:
            summary[tier] = {"n": 0, "n_intact": 0, "intact_pct": 0.0,
                             "n_demoted": 0, "demoted_pct": 0.0, "mean_drift": 0.0}
            continue
        n_intact   = sum(1 for r in results if r["survived"])
        n_demoted  = sum(1 for r in results
                         if r["survived"] and r["detected_tier"] != tier)
        summary[tier] = {
            "n":              len(results),
            "n_intact":       n_intact,
            "intact_pct":     round(n_intact / len(results) * 100, 1),
            "n_demoted":      n_demoted,
            "demoted_pct":    round(n_demoted / len(results) * 100, 1),
            "mean_drift":     round(float(np.mean([r["anchor_drift"] for r in results])), 2),
        }

    overall_n     = sum(len(v) for v in tier_results.values())
    overall_intact= sum(s["n_intact"] for s in summary.values())

    return {
        "tier_24": summary[TIER_24],
        "tier_16": summary[TIER_16],
        "tier_8":  summary[TIER_8],
        "overall_intact_pct": round(overall_intact / max(overall_n, 1) * 100, 1),
        "n_total": overall_n,
    }


# =============================================================================
# SPANNING DETECTOR — BLIND MODE
# =============================================================================

def detect_spanning_blind(pixels, floor=FLOOR, ch_a=0, ch_b=1, prime_tol=2):
    """
    Blind spanning sentinel scanner — no manifest required.
    
    Strategy:
      1. Find anchor candidates: positions where |ch_a-ch_b| ≈ Mersenne
      2. For each anchor, check flanking pixels for differential match
      3. Classify tier from number of matching flanking pixels
      4. Match entry+exit pairs at expected spatial separation
    
    Returns per-tier matched pair counts + FP estimates.
    """
    h, w, _ = pixels.shape
    prime_lookup = build_prime_lookup(BIT_DEPTH)
    all_pos      = sample_positions_grid(h, w, WINDOW_W)

    # Find anchor candidates
    anchors_24, anchors_16, anchors_8 = [], [], []

    for pos in all_pos:
        r   = int(pos[0]) + 3
        col = int(pos[1]) + 3
        if r >= h or col >= w:
            continue

        d_anchor = abs(int(pixels[r, col, ch_a]) - int(pixels[r, col, ch_b]))

        # Is it a fuzzy Mersenne?
        is_mersenne = any(abs(d_anchor - m) <= TIER_8_TOL for m in MERSENNE_BASKET)
        if not is_mersenne:
            continue

        # Check flanking pixels
        tier, left_cols, right_cols = determine_tier(r, col, h, w)
        flank_diffs = []
        for dc in left_cols + right_cols:
            fc = col + dc
            if 0 <= fc < w:
                d_flank = abs(int(pixels[r, fc, ch_a]) - int(pixels[r, fc, ch_b]))
                flank_diffs.append(abs(d_flank - d_anchor))

        n_flank_match_24 = sum(1 for d in flank_diffs if d <= TIER_24_DIFF_TOL)
        n_flank_match_16 = sum(1 for d in flank_diffs if d <= TIER_16_DIFF_TOL)

        # Classify into tier based on what we can detect
        entry_or_exit = "unknown"  # direction detection TBD

        if tier == TIER_24 and n_flank_match_24 >= 3:
            anchors_24.append({"r": r, "col": col, "d": d_anchor})
        elif n_flank_match_16 >= 1 or tier == TIER_16:
            anchors_16.append({"r": r, "col": col, "d": d_anchor})
        else:
            anchors_8.append({"r": r, "col": col, "d": d_anchor})

    return {
        "n_anchors_24":  len(anchors_24),
        "n_anchors_16":  len(anchors_16),
        "n_anchors_8":   len(anchors_8),
        "n_total":       len(anchors_24) + len(anchors_16) + len(anchors_8),
        "anchors_24":    anchors_24,
        "anchors_16":    anchors_16,
        "anchors_8":     anchors_8,
        # Note: matched-pair analysis from detect_sentinels_blind() applies here too
        # anchors need to be matched as entry+exit pairs at expected separation
        # That logic is shared with compound_markers.detect_sentinels_blind()
        # Full integration pending after same_block_correlation_test results
    }


# =============================================================================
# CORPUS TEST
# =============================================================================

def run_test(input_dir, output_dir, max_images=0):
    """
    Test spanning sentinel embedding and manifest detection across cascade.
    Compare per-tier survival rates.
    """
    os.makedirs(output_dir, exist_ok=True)

    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    all_files  = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])
    if max_images > 0:
        all_files = all_files[:max_images]
    n_total = len(all_files)

    print(f"{'='*80}")
    print(f"SPANNING SENTINEL TEST — 24/16/8-bit Tiered Detection")
    print(f"{'='*80}")
    print(f"Images:   {n_total}")
    print(f"Floor:    {FLOOR}")
    print(f"Density:  {int(DENSITY_FRAC*100)}%")
    print(f"Tiers:    24-bit (5px span)  16-bit (3px span)  8-bit (1px anchor)")
    print(f"Mersennes: entry=M{SENTINEL_MERSENNE_ENTRY}  exit=M{SENTINEL_MERSENNE_EXIT}  (M=127 excluded — JPEG chroma gravity)")
    print(f"Tolerances: anchor T24/T16={TIER_24_ANCHOR_TOL}  diff T24={TIER_24_DIFF_TOL} T16={TIER_16_DIFF_TOL}  T8={TIER_8_ANCHOR_TOL}")
    print(f"  anchor tol is wide (absolute drift ~33 mean) — differential is the real signal")
    print(f"{'='*80}\n")

    # Import here to avoid circular imports if used standalone
    from compound_markers import MarkerConfig, embed_compound
    import math

    all_results = []
    t_start     = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>3d}/{n_total}] {fname}  ", end="", flush=True)

        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print("SKIP"); continue
        if max(h, w) > 1024:
            scale  = 1024 / max(h, w)
            img    = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)
            h, w   = pixels.shape[:2]

        n_req   = max(10, math.ceil(len(sample_positions_grid(h, w, 8)) * DENSITY_FRAC))
        rng     = np.random.default_rng(42)
        config  = MarkerConfig(
            name="span_test",
            description="Spanning sentinel test",
            min_prime=FLOOR,
            use_twins=True,
            use_rare_basket=True,
            use_magic=False,
            detection_prime_tolerance=2,
            n_markers=n_req,
        )

        marked_px, markers, _ = embed_compound(pixels.copy(), config, variable_offset=42)

        # Place spanning sentinels at section boundaries
        n_sections   = max(1, len(markers) // 8)  # SENTINEL_CANARY_RATIO
        section_size = len(markers) // n_sections
        mod_int      = marked_px.astype(np.int16)
        span_sentinels = []

        for sec_idx in range(n_sections):
            start = sec_idx * section_size
            end   = start + section_size if sec_idx < n_sections - 1 else len(markers)
            for role, pos_idx in [("entry", start), ("exit", end - 1)]:
                if pos_idx >= len(markers):
                    continue
                m_pos    = markers[pos_idx]
                # Use fixed Mersennes per direction — M=127 excluded.
                mersenne = SENTINEL_MERSENNE_ENTRY if role == "entry" else SENTINEL_MERSENNE_EXIT
                span_s   = embed_spanning_sentinel(
                    mod_int, m_pos["row"], m_pos["col"],
                    mersenne, role
                )
                if span_s:
                    span_s["section"] = sec_idx
                    span_sentinels.append(span_s)

        span_px = np.clip(mod_int, 0, 255).astype(np.uint8)

        # Tier distribution
        tier_counts = {TIER_24: 0, TIER_16: 0, TIER_8: 0}
        for s in span_sentinels:
            tier_counts[s["tier"]] += 1

        gen0_jpeg   = io.BytesIO()
        Image.fromarray(span_px).save(gen0_jpeg, format='JPEG', quality=95)
        current     = gen0_jpeg.getvalue()
        cascade     = []

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            if gen_idx > 0:
                buf = io.BytesIO()
                Image.fromarray(decode_jpeg(current)).save(buf, format='JPEG', quality=q)
                current = buf.getvalue()

            compressed = decode_jpeg(current)
            manifest   = detect_spanning_manifest(compressed, span_sentinels)

            cascade.append({
                "generation": gen_idx,
                "quality":    q,
                "t24_intact": manifest["tier_24"]["intact_pct"],
                "t16_intact": manifest["tier_16"]["intact_pct"],
                "t8_intact":  manifest["tier_8"]["intact_pct"],
                "overall":    manifest["overall_intact_pct"],
                "t24_demoted":manifest["tier_24"]["demoted_pct"],
            })

        elapsed = time.time() - t_img
        g4      = cascade[4] if len(cascade) > 4 else {}
        t24n    = tier_counts[TIER_24]
        t16n    = tier_counts[TIER_16]
        t8n     = tier_counts[TIER_8]
        print(f"T24={t24n} T16={t16n} T8={t8n}  "
              f"G4: t24={g4.get('t24_intact',0):.1f}%  "
              f"t16={g4.get('t16_intact',0):.1f}%  "
              f"t8={g4.get('t8_intact',0):.1f}%  "
              f"[{elapsed:.1f}s]")

        all_results.append({
            "image":       fname,
            "tier_counts": tier_counts,
            "cascade":     cascade,
        })

    total_time = time.time() - t_start
    n_good     = len(all_results)

    print(f"\n\n{'='*80}")
    print(f"SPANNING SENTINEL AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if not all_results:
        print("No valid results."); return

    print(f"{'Gen':>4}  {'Q':>3}  {'T24%':>7}  {'T16%':>7}  {'T8%':>7}  "
          f"{'Overall%':>9}  {'T24_demoted%':>13}")
    print("─" * 65)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        def gmean(key):
            vals = [r["cascade"][gen_idx].get(key, 0)
                    for r in all_results if len(r["cascade"]) > gen_idx]
            return sum(vals) / len(vals) if vals else 0

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {gmean('t24_intact'):>6.1f}%"
              f"  {gmean('t16_intact'):>6.1f}%"
              f"  {gmean('t8_intact'):>6.1f}%"
              f"  {gmean('overall'):>8.1f}%"
              f"  {gmean('t24_demoted'):>12.1f}%")

    # Save
    agg = {
        "n_images":    n_good,
        "tier_24_tol": TIER_24_TOL,
        "tier_16_tol": TIER_16_TOL,
        "tier_8_tol":  TIER_8_TOL,
        "gen4": {
            "t24_intact": np.mean([r["cascade"][4].get("t24_intact", 0)
                                   for r in all_results if len(r["cascade"]) > 4]),
            "t16_intact": np.mean([r["cascade"][4].get("t16_intact", 0)
                                   for r in all_results if len(r["cascade"]) > 4]),
            "t8_intact":  np.mean([r["cascade"][4].get("t8_intact",  0)
                                   for r in all_results if len(r["cascade"]) > 4]),
        }
    }
    with open(os.path.join(output_dir, "spanning_aggregate.json"), "w") as f:
        json.dump(agg, f, indent=2, default=float)

    print(f"\nResults: {output_dir}/")
    return agg


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Spanning Sentinel Test — 24/16/8-bit Tiered"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="spanning_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_test(args.input, args.output, max_images=args.max_images)
