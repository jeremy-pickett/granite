#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Sentinel Drift Characterizer
=============================

Answers the question that should have been asked first:
  What is the ACTUAL distribution of |embedded_value - actual_value|
  at sentinel positions after JPEG encoding at each quality level?

This measurement drives the design of the relational sentinel architecture
(Option B). Before we can say "relational encoding cancels drift because
DCT quantization is spatially correlated within a block," we need to know:

  1. What is the drift magnitude at each quality level?
  2. Is the drift correlated for adjacent positions in the same 8x8 block?
  3. How does drift compare for positions in the SAME block vs DIFFERENT blocks?

The manifest is used as ground truth throughout (QA mechanism).
If manifest reports diverge from expectations, we have a deeper problem.

Output:
  - Per-generation drift distribution (mean, std, p95, p99)
  - Within-block drift correlation (the key hypothesis for Option B)
  - Survival rate at various CANARY_WIDTH thresholds (1..16)
  - Recommendation: minimum CANARY_WIDTH for each quality level

Usage:
    python sentinel_drift_characterizer.py -i /path/to/DIV2K -o drift_results -n 50
"""

import os
import sys
import io
import json
import math
import time
import numpy as np
from PIL import Image
from collections import defaultdict
from datetime import datetime

from pgps_detector import sample_positions_grid
from compound_markers import (
    MarkerConfig, embed_compound,
    SENTINEL_CANARY_RATIO, MERSENNE_BASKET, CANARY_WIDTH,
)
from dqt_prime import encode_prime_jpeg


# =============================================================================
# CONFIG
# =============================================================================

FLOOR           = 43
DENSITY_FRAC    = 0.08
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512

# Range of CANARY_WIDTH values to test for survival rate
WIDTH_RANGE = list(range(1, 17))  # 1..16


# =============================================================================
# UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def grid_capacity(h, w):
    return len(sample_positions_grid(h, w, 8))

def markers_for_image(h, w):
    return max(10, math.ceil(grid_capacity(h, w) * DENSITY_FRAC))

def same_dct_block(r1, c1, r2, c2):
    """True if two positions are in the same 8×8 DCT block."""
    return (r1 // 8 == r2 // 8) and (c1 // 8 == c2 // 8)


# =============================================================================
# DRIFT MEASUREMENT
# =============================================================================

def measure_sentinel_drift(pixels, sentinels, compressed_px, ch_a=0, ch_b=1):
    """
    For each sentinel in the manifest, measure the drift between the
    intended Mersenne value and the actual channel difference after
    JPEG compression.

    Returns list of drift measurements:
        {sentinel, intended, actual, drift, abs_drift, row, col}
    """
    h, w, _ = compressed_px.shape
    measurements = []

    for s in sentinels:
        if not s.get("placed", True):
            continue
        r, col = s["row"], s["col"]
        if r >= h or col >= w:
            continue

        intended = s["mersenne"]
        actual   = abs(int(compressed_px[r, col, ch_a]) -
                       int(compressed_px[r, col, ch_b]))
        drift    = actual - intended

        measurements.append({
            "type":      s["type"],
            "section":   s["section"],
            "row":       r,
            "col":       col,
            "intended":  intended,
            "actual":    actual,
            "drift":     drift,
            "abs_drift": abs(drift),
        })

    return measurements


def measure_within_block_correlation(sentinels, measurements_by_gen):
    """
    For each generation, find pairs of sentinels in the SAME 8×8 DCT block
    and measure whether their drift values are correlated.

    The relational encoding hypothesis (Option B) predicts:
        drift(p1) ≈ drift(p2) for positions in the same block
        → d(p2) - d(p1) ≈ (intended_p2 + δ) - (intended_p1 + δ) = intended_p2 - intended_p1

    Returns correlation stats per generation.
    """
    correlations = {}

    for gen_idx, measurements in measurements_by_gen.items():
        # Build position lookup
        pos_to_meas = {(m["row"], m["col"]): m for m in measurements}

        same_block_pairs  = []
        diff_block_pairs  = []

        for i, m1 in enumerate(measurements):
            for m2 in measurements[i+1:]:
                r1, c1 = m1["row"], m1["col"]
                r2, c2 = m2["row"], m2["col"]
                drift_diff = abs(m1["drift"] - m2["drift"])

                if same_dct_block(r1, c1, r2, c2):
                    same_block_pairs.append(drift_diff)
                else:
                    diff_block_pairs.append(drift_diff)

        correlations[gen_idx] = {
            "same_block_n":           len(same_block_pairs),
            "diff_block_n":           len(diff_block_pairs),
            "same_block_mean_diff":   float(np.mean(same_block_pairs)) if same_block_pairs else 0,
            "diff_block_mean_diff":   float(np.mean(diff_block_pairs)) if diff_block_pairs else 0,
            "same_block_std":         float(np.std(same_block_pairs))  if same_block_pairs else 0,
            "diff_block_std":         float(np.std(diff_block_pairs))  if diff_block_pairs else 0,
            # Correlation ratio: <1 means same-block drifts are more similar
            # This is the key hypothesis test for Option B
            "correlation_ratio":      (
                float(np.mean(same_block_pairs)) / max(float(np.mean(diff_block_pairs)), 0.001)
                if same_block_pairs and diff_block_pairs else None
            ),
        }

    return correlations


# =============================================================================
# SINGLE IMAGE ANALYSIS
# =============================================================================

def analyze_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    n_req = markers_for_image(h, w)

    config = MarkerConfig(
        name="drift_test",
        description=f"Drift characterization — floor={FLOOR}",
        min_prime=FLOOR,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        magic_value=42,
        magic_tolerance=7,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    # Embed — plain JPEG gen0 (not prime JPEG, that's Layer A's domain)
    marked_pixels, markers, sentinels = embed_compound(
        pixels.copy(), config, variable_offset=42
    )

    placed_sentinels = [s for s in sentinels if s.get("placed", True)]
    if len(placed_sentinels) < 4:
        return None

    gen0_jpeg     = to_jpeg(marked_pixels, quality=95)
    current       = gen0_jpeg
    drift_by_gen  = {}

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current = to_jpeg(decode_jpeg(current), quality=q)

        compressed_px = decode_jpeg(current)
        measurements  = measure_sentinel_drift(
            pixels, placed_sentinels, compressed_px
        )
        drift_by_gen[gen_idx] = measurements

    # Within-block correlation analysis
    correlations = measure_within_block_correlation(
        placed_sentinels, drift_by_gen
    )

    return {
        "image":         fname,
        "n_sentinels":   len(placed_sentinels),
        "drift_by_gen":  drift_by_gen,
        "correlations":  correlations,
    }


# =============================================================================
# CORPUS RUN
# =============================================================================

def run_corpus(input_dir, output_dir, max_images=0):
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
    print(f"SENTINEL DRIFT CHARACTERIZER")
    print(f"{'='*80}")
    print(f"Images:     {n_total}")
    print(f"Floor:      {FLOOR}")
    print(f"Density:    {int(DENSITY_FRAC*100)}%")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Purpose:    Measure actual drift at sentinel positions per generation")
    print(f"            Test within-block drift correlation (Option B hypothesis)")
    print(f"{'='*80}\n")

    all_results = []
    t_start     = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        print(f"[{idx+1:>3d}/{n_total}] {fname}  ", end="", flush=True)
        t_img = time.time()

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

        try:
            result = analyze_one_image(pixels, fname)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()
            result = None

        elapsed = time.time() - t_img

        if result:
            # Quick summary: mean abs drift at G0 and G4
            g0 = result["drift_by_gen"].get(0, [])
            g4 = result["drift_by_gen"].get(4, [])
            g0_mean = np.mean([m["abs_drift"] for m in g0]) if g0 else 0
            g4_mean = np.mean([m["abs_drift"] for m in g4]) if g4 else 0
            corr_g0 = result["correlations"].get(0, {}).get("correlation_ratio")
            corr_g4 = result["correlations"].get(4, {}).get("correlation_ratio")
            cg0_str = f"{corr_g0:.3f}" if corr_g0 is not None else "n/a"
            cg4_str = f"{corr_g4:.3f}" if corr_g4 is not None else "n/a"
            print(f"n={result['n_sentinels']:>4d}  "
                  f"G0_drift={g0_mean:.2f}  G4_drift={g4_mean:.2f}  "
                  f"corr_ratio G0={cg0_str}  G4={cg4_str}  "
                  f"[{elapsed:.1f}s]")
            all_results.append(result)
        else:
            print(f"SKIPPED  [{elapsed:.1f}s]")

    total_time = time.time() - t_start
    n_good = len(all_results)

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    print(f"\n\n{'='*80}")
    print(f"DRIFT CHARACTERIZATION AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if not all_results:
        print("No valid results."); return

    # ── Drift distribution per generation ────────────────────────────────────
    print(f"DRIFT DISTRIBUTION (absolute drift from intended Mersenne value)")
    print(f"{'Gen':>4}  {'Q':>3}  {'mean':>6}  {'std':>6}  "
          f"{'p50':>5}  {'p90':>5}  {'p95':>5}  {'p99':>5}  "
          f"{'max':>5}  notes")
    print("─" * 75)

    drift_summary = {}
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        all_drifts = []
        for r in all_results:
            for m in r["drift_by_gen"].get(gen_idx, []):
                all_drifts.append(m["abs_drift"])

        if not all_drifts:
            continue

        arr = np.array(all_drifts)
        p50, p90, p95, p99 = np.percentile(arr, [50, 90, 95, 99])
        mean, std, maxv     = np.mean(arr), np.std(arr), np.max(arr)

        # What CANARY_WIDTH captures 90% / 95% / 99% of sentinels?
        w90 = int(np.ceil(p90))
        w95 = int(np.ceil(p95))
        w99 = int(np.ceil(p99))

        note = f"need width>={w90} for 90%, >={w95} for 95%, >={w99} for 99%"

        drift_summary[gen_idx] = {
            "quality":   q,
            "mean":      round(float(mean),  3),
            "std":       round(float(std),   3),
            "p50":       round(float(p50),   1),
            "p90":       round(float(p90),   1),
            "p95":       round(float(p95),   1),
            "p99":       round(float(p99),   1),
            "max":       int(maxv),
            "w_for_90":  w90,
            "w_for_95":  w95,
            "w_for_99":  w99,
        }

        print(f"{gen_idx:>4d}  {q:>3d}  {mean:>6.2f}  {std:>6.2f}  "
              f"{p50:>5.1f}  {p90:>5.1f}  {p95:>5.1f}  {p99:>5.1f}  "
              f"{int(maxv):>5d}  {note}")

    # ── Survival rate at each CANARY_WIDTH ───────────────────────────────────
    print(f"\nSURVIVAL RATE — % of sentinels surviving at each CANARY_WIDTH")
    print(f"{'Width':>6}  " + "  ".join(f"{'G'+str(g)+' Q'+str(q):>9}"
                                         for g, q in enumerate(CASCADE_QUALITIES)))
    print("─" * 70)

    survival_table = {}
    for w in WIDTH_RANGE:
        row = f"{w:>6d}  "
        survival_table[w] = {}
        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            all_drifts = [m["abs_drift"] for r in all_results
                          for m in r["drift_by_gen"].get(gen_idx, [])]
            if all_drifts:
                surv = np.mean(np.array(all_drifts) <= w) * 100
                survival_table[w][gen_idx] = round(surv, 1)
                marker = " ✓" if surv >= 90 else "  "
                row += f"  {surv:>7.1f}%{marker}"
            else:
                row += f"  {'n/a':>9}"
        print(row)

    # ── Within-block correlation (Option B hypothesis test) ──────────────────
    print(f"\n{'='*80}")
    print(f"WITHIN-BLOCK DRIFT CORRELATION — Option B Hypothesis Test")
    print(f"{'='*80}")
    print(f"Prediction: same_block_mean_drift_diff < diff_block_mean_drift_diff")
    print(f"  → drift is correlated within 8x8 DCT blocks")
    print(f"  → relational encoding (d2-d1) cancels drift")
    print(f"  correlation_ratio = same_block / diff_block  (<1.0 = hypothesis supported)")
    print()

    print(f"{'Gen':>4}  {'Q':>3}  "
          f"{'same_blk_mean':>14}  {'diff_blk_mean':>14}  "
          f"{'corr_ratio':>11}  {'verdict':>20}")
    print("─" * 75)

    corr_summary = {}
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        same_diffs = []
        diff_diffs = []
        for r in all_results:
            c = r["correlations"].get(gen_idx, {})
            # Reconstruct from per-image data
            pass

        # Re-compute aggregate correlation from raw drift data
        all_same, all_diff = [], []
        for r in all_results:
            meas = r["drift_by_gen"].get(gen_idx, [])
            for i, m1 in enumerate(meas):
                for m2 in meas[i+1:]:
                    dd = abs(m1["drift"] - m2["drift"])
                    if same_dct_block(m1["row"], m1["col"], m2["row"], m2["col"]):
                        all_same.append(dd)
                    else:
                        all_diff.append(dd)

        if all_same and all_diff:
            sm = np.mean(all_same)
            dm = np.mean(all_diff)
            ratio = sm / max(dm, 0.001)
            verdict = "SUPPORTED ✓" if ratio < 0.8 else ("WEAK" if ratio < 1.0 else "NOT SUPPORTED ✗")
            corr_summary[gen_idx] = {
                "same_block_mean": round(float(sm), 3),
                "diff_block_mean": round(float(dm), 3),
                "correlation_ratio": round(float(ratio), 4),
                "hypothesis_supported": ratio < 0.8,
            }
            print(f"{gen_idx:>4d}  {q:>3d}  "
                  f"{sm:>14.3f}  {dm:>14.3f}  "
                  f"{ratio:>11.4f}  {verdict:>20}")
        else:
            print(f"{gen_idx:>4d}  {q:>3d}  insufficient pairs")

    # ── Recommendation ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"DESIGN RECOMMENDATIONS")
    print(f"{'='*80}")

    if drift_summary:
        g0 = drift_summary.get(0, {})
        g4 = drift_summary.get(4, {})

        print(f"\nAbsolute sentinel (existing architecture):")
        print(f"  For 95% survival at Q95 (G0): CANARY_WIDTH >= {g0.get('w_for_95', '?')}")
        print(f"  For 95% survival at Q40 (G4): CANARY_WIDTH >= {g4.get('w_for_95', '?')}")
        print(f"  For 99% survival at Q40 (G4): CANARY_WIDTH >= {g4.get('w_for_99', '?')}")

    if corr_summary:
        g0_corr = corr_summary.get(0, {})
        g4_corr = corr_summary.get(4, {})
        g0_ratio = g0_corr.get("correlation_ratio")
        g4_ratio = g4_corr.get("correlation_ratio")

        print(f"\nRelational sentinel (Option B hypothesis):")
        if g0_ratio and g0_ratio < 1.0:
            reduction = (1.0 - g0_ratio) * 100
            print(f"  Within-block drift correlation confirmed at G0.")
            print(f"  Same-block drift difference is {reduction:.0f}% smaller than")
            print(f"  cross-block drift difference.")
            print(f"  → Relational encoding reduces effective drift by ~{reduction:.0f}%")
            print(f"  → CANARY_WIDTH for relational encoding: ~{max(1, int(drift_summary.get(0,{}).get('w_for_95',8) * g0_ratio))}")
        else:
            print(f"  Within-block correlation NOT confirmed.")
            print(f"  → Relational encoding may not provide benefit over absolute.")
            print(f"  → Investigate DCT block boundary effects.")

    # ── Save ─────────────────────────────────────────────────────────────────
    summary = {
        "n_images":       n_good,
        "floor":          FLOOR,
        "density_frac":   DENSITY_FRAC,
        "drift_by_gen":   drift_summary,
        "correlation":    {str(k): v for k, v in corr_summary.items()},
        "survival_table": {str(w): {str(g): v for g, v in gv.items()}
                           for w, gv in survival_table.items()},
    }
    with open(os.path.join(output_dir, "drift_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    verdict_lines = []
    if drift_summary:
        g0 = drift_summary.get(0, {})
        verdict_lines.append(
            f"G0 Q95: mean drift={g0.get('mean','?')}, "
            f"p95={g0.get('p95','?')}, need width>={g0.get('w_for_95','?')} for 95% survival"
        )
    if corr_summary and corr_summary.get(0):
        r = corr_summary[0]
        verdict_lines.append(
            f"Option B correlation_ratio at G0: {r.get('correlation_ratio','?')} "
            f"({'supported' if r.get('hypothesis_supported') else 'not supported'})"
        )

    with open(os.path.join(output_dir, "DRIFT_VERDICT.txt"), "w") as f:
        f.write("\n".join(verdict_lines) + "\n")
        f.write(f"\nGenerated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}\n")

    print(f"\nResults: {output_dir}/")
    return summary


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sentinel Drift Characterizer")
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="drift_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
