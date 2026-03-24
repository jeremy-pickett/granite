#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Same-Block Drift Correlation Test
===================================

The drift characterizer revealed that absolute Mersenne sentinels have
mean drift of ~33 counts at Q95, with catastrophic drift (>100) in ~10%
of cases. Max drift = 127 = the Mersenne value itself, meaning JPEG
sometimes completely zeros the channel difference.

The critical unanswered question for Option B (relational encoding) and
spanning:

  When two pixels in the SAME 8×8 DCT block both drift catastrophically,
  do they drift TOGETHER (correlated) or INDEPENDENTLY?

  Correlated:   d1 → 0, d2 → 0  simultaneously
                → d2 - d1 = 0 - 0 = 0 (relational survives!)
                
  Independent:  d1 → 0, d2 survives
                → d2 - d1 = d2 - 0 = d2 (relational does NOT survive)

Previous test failed to answer this because grid stride=8 guarantees
at most one grid position per 8×8 block. This test deliberately places
two sentinels inside the same block to get the correlation data.

Design:
  For each image, inject pairs of sentinel values at positions
  (r, c) and (r, c+1) where both are confirmed in the same 8×8 block.
  Use various pair separations: 1 pixel, 2 pixels, 3 pixels apart.
  Measure drift at both positions after each JPEG generation.
  Compute correlation of drift pairs.

Metrics reported:
  - Pearson correlation of (drift_p1, drift_p2) per generation
  - % of pairs where BOTH catastrophically fail (drift > threshold)
  - % of pairs where ONE fails but not the other
  - For correlated failures: what is d2 - d1 after failure?

This directly answers:
  1. Whether relational encoding (d2-d1) survives catastrophic failure
  2. What REL_WIDTH is needed for relational sentinels
  3. Whether spanning pixels provide real redundancy or redundant failure

Usage:
    python same_block_correlation_test.py -i /path/to/DIV2K -o block_results -n 50
"""

import os
import sys
import io
import json
import math
import time
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from datetime import datetime

from pgps_detector import sample_positions_grid


# =============================================================================
# CONFIG
# =============================================================================

CASCADE_QUALITIES  = [95, 85, 75, 60, 40]
MIN_DIMENSION      = 512
CATASTROPHIC_DRIFT = 40   # drift > this = catastrophic (conservative threshold)

# Mersenne values to test as injected pairs
MERSENNE_BASKET = [3, 7, 31, 127]

# Pixel separations within same block to test
# 1 = adjacent, 2 = skip one, 3 = skip two (max within 8-wide block)
SEPARATIONS = [1, 2, 3]

# Number of injection pairs per image
N_PAIRS_PER_IMAGE = 50


# =============================================================================
# UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def same_dct_block(r1, c1, r2, c2):
    return (r1 // 8 == r2 // 8) and (c1 // 8 == c2 // 8)

def channel_diff(pixels, r, c, ch_a=0, ch_b=1):
    return abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))


# =============================================================================
# INJECT SAME-BLOCK PAIRS
# =============================================================================

def inject_pair(pixels, r, c1, c2, mersenne, ch_a=0, ch_b=1):
    """
    Inject |ch_a - ch_b| = mersenne at BOTH (r,c1) and (r,c2).
    Both positions must be in the same 8×8 DCT block.
    Returns modified pixels and whether injection succeeded.
    """
    assert same_dct_block(r, c1, r, c2), "positions not in same block"
    modified = pixels.copy()
    h, w, _ = modified.shape

    def inject_one(px, rr, cc):
        val_a = int(px[rr, cc, ch_a])
        opts  = [v for v in [val_a - mersenne, val_a + mersenne]
                 if 20 <= v <= 235]
        if not opts:
            return False
        px[rr, cc, ch_b] = min(opts, key=lambda x: abs(x - int(px[rr, cc, ch_b])))
        return True

    ok1 = inject_one(modified, r, c1)
    ok2 = inject_one(modified, r, c2)
    return modified, ok1 and ok2


def find_injection_pairs(h, w, n_pairs, rng, separations=SEPARATIONS):
    """
    Find (r, c1, c2, sep) tuples where c1 and c2 are in the same 8×8 block,
    separated by `sep` columns, with enough room for value range checks.
    """
    pairs = []
    for _ in range(n_pairs * 20):  # oversample, take first n_pairs that work
        sep = int(rng.choice(separations))
        r   = int(rng.integers(8, h - 8))
        # c1 must be at least sep from end of its block
        block_start = (int(rng.integers(0, w // 8))) * 8
        c1 = block_start + int(rng.integers(0, 8 - sep))
        c2 = c1 + sep
        if c2 >= w or not same_dct_block(r, c1, r, c2):
            continue
        if 20 <= r < h - 20 and 20 <= c1 and c2 < w - 20:
            pairs.append((r, c1, c2, sep))
        if len(pairs) >= n_pairs:
            break
    return pairs


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w, _ = pixels.shape
    rng      = np.random.default_rng(42)

    # Find injection sites
    all_pairs = find_injection_pairs(h, w, N_PAIRS_PER_IMAGE * len(MERSENNE_BASKET), rng)
    if len(all_pairs) < 4:
        return {"image": fname, "error": "too few valid injection pairs"}

    results_by_mersenne = {m: [] for m in MERSENNE_BASKET}

    for mersenne in MERSENNE_BASKET:
        pairs_for_m = all_pairs[:N_PAIRS_PER_IMAGE]

        for r, c1, c2, sep in pairs_for_m:
            modified, ok = inject_pair(pixels, r, c1, c2, mersenne)
            if not ok:
                continue

            # Record intended values
            intended_d1 = channel_diff(modified, r, c1)
            intended_d2 = channel_diff(modified, r, c2)

            # Cascade
            current = to_jpeg(modified, quality=95)
            pair_result = {
                "mersenne": mersenne,
                "sep":      sep,
                "r": r, "c1": c1, "c2": c2,
                "intended_d1": intended_d1,
                "intended_d2": intended_d2,
                "generations": [],
            }

            for gen_idx, q in enumerate(CASCADE_QUALITIES):
                if gen_idx > 0:
                    current = to_jpeg(decode_jpeg(current), quality=q)

                px = decode_jpeg(current)
                actual_d1 = channel_diff(px, r, c1)
                actual_d2 = channel_diff(px, r, c2)
                drift1    = actual_d1 - intended_d1
                drift2    = actual_d2 - intended_d2
                rel_diff  = actual_d2 - actual_d1   # the relational signal

                pair_result["generations"].append({
                    "gen":       gen_idx,
                    "quality":   q,
                    "actual_d1": actual_d1,
                    "actual_d2": actual_d2,
                    "drift1":    drift1,
                    "drift2":    drift2,
                    "abs_drift1": abs(drift1),
                    "abs_drift2": abs(drift2),
                    "rel_diff":   rel_diff,        # d2 - d1 (should be 0 if drifts equal)
                    "intended_rel": intended_d2 - intended_d1,  # should be ~0 (both = mersenne)
                    "rel_residual": abs(rel_diff),  # |d2 - d1| after compression
                    "both_catastrophic": (abs(drift1) > CATASTROPHIC_DRIFT and
                                          abs(drift2) > CATASTROPHIC_DRIFT),
                    "one_catastrophic":  ((abs(drift1) > CATASTROPHIC_DRIFT) !=
                                          (abs(drift2) > CATASTROPHIC_DRIFT)),
                })

            results_by_mersenne[mersenne].append(pair_result)

    return {
        "image":   fname,
        "results": results_by_mersenne,
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
    print(f"SAME-BLOCK DRIFT CORRELATION TEST")
    print(f"{'='*80}")
    print(f"Images:            {n_total}")
    print(f"Cascade:           {CASCADE_QUALITIES}")
    print(f"Mersenne values:   {MERSENNE_BASKET}")
    print(f"Separations:       {SEPARATIONS} pixels within same 8×8 block")
    print(f"Pairs/image:       {N_PAIRS_PER_IMAGE}")
    print(f"Catastrophic thr:  drift > {CATASTROPHIC_DRIFT}")
    print(f"")
    print(f"Hypothesis: drifts of same-block pixel pairs are correlated.")
    print(f"  Correlated → d2-d1 preserved (relational encoding works)")
    print(f"  Independent → relational encoding does NOT help")
    print(f"{'='*80}\n")

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

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        if "error" not in result:
            # Quick summary: mean rel_residual at G0 and G4 for M=127
            g4_rels = []
            g0_rels = []
            for pr in result["results"].get(127, []):
                if len(pr["generations"]) > 4:
                    g0_rels.append(pr["generations"][0]["rel_residual"])
                    g4_rels.append(pr["generations"][4]["rel_residual"])
            g0r = np.mean(g0_rels) if g0_rels else 0
            g4r = np.mean(g4_rels) if g4_rels else 0
            print(f"M=127: G0_rel_residual={g0r:.1f}  G4_rel_residual={g4r:.1f}  [{elapsed:.1f}s]")
            all_results.append(result)
        else:
            print(f"ERROR  [{elapsed:.1f}s]")

    total_time = time.time() - t_start
    n_good = len(all_results)

    # =========================================================================
    # AGGREGATE — this is the core hypothesis test
    # =========================================================================
    print(f"\n\n{'='*80}")
    print(f"CORRELATION AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if not all_results:
        print("No valid results."); return

    # For each Mersenne value and separation, compute:
    # - Pearson correlation of (drift1, drift2)
    # - Mean rel_residual (|d2-d1| after compression)
    # - % both catastrophic vs one catastrophic

    summary = {}

    for mersenne in MERSENNE_BASKET:
        print(f"\nMersenne = {mersenne}")
        print(f"{'Sep':>4}  {'Gen':>4}  {'Q':>3}  "
              f"{'corr':>7}  {'rel_res':>8}  "
              f"{'both_cat%':>10}  {'one_cat%':>9}  "
              f"{'verdict':>25}")
        print("─" * 80)

        for sep in SEPARATIONS:
            for gen_idx, q in enumerate(CASCADE_QUALITIES):
                drifts1, drifts2, rel_residuals = [], [], []
                n_both_cat, n_one_cat, n_total_pairs = 0, 0, 0

                for r in all_results:
                    for pr in r["results"].get(mersenne, []):
                        if pr["sep"] != sep:
                            continue
                        if len(pr["generations"]) <= gen_idx:
                            continue
                        g = pr["generations"][gen_idx]
                        drifts1.append(g["drift1"])
                        drifts2.append(g["drift2"])
                        rel_residuals.append(g["rel_residual"])
                        n_total_pairs += 1
                        if g["both_catastrophic"]:
                            n_both_cat += 1
                        if g["one_catastrophic"]:
                            n_one_cat += 1

                if len(drifts1) < 10:
                    continue

                d1, d2 = np.array(drifts1), np.array(drifts2)
                corr, pval = sp_stats.pearsonr(d1, d2)
                mean_rel   = np.mean(rel_residuals)
                both_pct   = n_both_cat / n_total_pairs * 100
                one_pct    = n_one_cat  / n_total_pairs * 100

                # Verdict on relational encoding viability
                if corr > 0.8 and mean_rel < 20:
                    verdict = "RELATIONAL WORKS ✓"
                elif corr > 0.5 and mean_rel < 40:
                    verdict = "RELATIONAL PARTIAL"
                elif corr > 0.3:
                    verdict = "WEAK CORRELATION"
                else:
                    verdict = "INDEPENDENT ✗"

                key = f"m{mersenne}_sep{sep}_g{gen_idx}"
                summary[key] = {
                    "mersenne":      mersenne,
                    "sep":           sep,
                    "gen":           gen_idx,
                    "quality":       q,
                    "n_pairs":       n_total_pairs,
                    "pearson_corr":  round(float(corr),  4),
                    "pearson_pval":  round(float(pval),  6),
                    "mean_rel_residual": round(float(mean_rel), 3),
                    "both_cat_pct":  round(both_pct, 1),
                    "one_cat_pct":   round(one_pct, 1),
                    "verdict":       verdict,
                }

                print(f"{sep:>4d}  {gen_idx:>4d}  {q:>3d}  "
                      f"{corr:>7.4f}  {mean_rel:>8.2f}  "
                      f"{both_pct:>9.1f}%  {one_pct:>8.1f}%  "
                      f"{verdict:>25}")

    # ── Headline findings ────────────────────────────────────────────────────
    print(f"\n\n{'='*80}")
    print(f"HEADLINE FINDINGS")
    print(f"{'='*80}")

    # Best case for relational encoding: highest correlation at G4 for M=127
    best_corr = max(
        (v for v in summary.values() if v["gen"] == 4 and v["mersenne"] == 127),
        key=lambda x: x["pearson_corr"],
        default=None
    )
    worst_corr = min(
        (v for v in summary.values() if v["gen"] == 4 and v["mersenne"] == 127),
        key=lambda x: x["pearson_corr"],
        default=None
    )

    if best_corr:
        print(f"\n  Best G4 correlation (M=127): "
              f"sep={best_corr['sep']} corr={best_corr['pearson_corr']:.4f} "
              f"rel_residual={best_corr['mean_rel_residual']:.2f} "
              f"→ {best_corr['verdict']}")

    if worst_corr:
        print(f"  Worst G4 correlation (M=127): "
              f"sep={worst_corr['sep']} corr={worst_corr['pearson_corr']:.4f} "
              f"→ {worst_corr['verdict']}")

    # Both-catastrophic rate — key for spanning design
    print(f"\n  Both-catastrophic rate at G4 (M=127, sep=1):")
    key = "m127_sep1_g4"
    if key in summary:
        s = summary[key]
        print(f"    {s['both_cat_pct']:.1f}% of pairs: BOTH pixels drift catastrophically")
        print(f"    {s['one_cat_pct']:.1f}% of pairs: ONE pixel drifts, one survives")
        print(f"    → Implication for spanning:")
        if s['both_cat_pct'] > s['one_cat_pct']:
            print(f"      Failures are CORRELATED. Spanning pixels fail together.")
            print(f"      Relational (d2-d1) survives because δ1 ≈ δ2.")
            print(f"      → Spanning amplifies what survives, not what fails.")
        else:
            print(f"      Failures are INDEPENDENT. Spanning gives real redundancy.")
            print(f"      When anchor fails, flanking pixels may survive.")
            print(f"      → Spanning provides genuine fault tolerance.")

    # REL_WIDTH recommendation
    print(f"\n  Recommended REL_WIDTH for relational sentinel detection:")
    for sep in SEPARATIONS:
        key = f"m127_sep{sep}_g4"
        if key in summary:
            s = summary[key]
            print(f"    sep={sep}: mean_rel_residual={s['mean_rel_residual']:.2f} "
                  f"→ REL_WIDTH should be ≥{int(np.ceil(s['mean_rel_residual'] * 1.5))}")

    print(f"\n  For spanning architecture:")
    for sep in SEPARATIONS:
        key_g0 = f"m127_sep{sep}_g0"
        key_g4 = f"m127_sep{sep}_g4"
        if key_g0 in summary and key_g4 in summary:
            g0, g4 = summary[key_g0], summary[key_g4]
            print(f"    sep={sep}: corr G0={g0['pearson_corr']:.3f} → G4={g4['pearson_corr']:.3f}  "
                  f"rel_residual G0={g0['mean_rel_residual']:.1f} → G4={g4['mean_rel_residual']:.1f}")

    # Save
    with open(os.path.join(output_dir, "block_correlation.json"), "w") as f:
        json.dump(summary, f, indent=2)

    verdict = "INCONCLUSIVE" if not best_corr else best_corr["verdict"]
    with open(os.path.join(output_dir, "BLOCK_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}\n")
        if best_corr:
            f.write(f"Best G4 corr (M=127): {best_corr['pearson_corr']:.4f}\n")
            f.write(f"Mean rel_residual (M=127, sep=1, G4): "
                    f"{summary.get('m127_sep1_g4',{}).get('mean_rel_residual','?')}\n")

    print(f"\nResults: {output_dir}/")
    return summary


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Same-Block Drift Correlation Test")
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="block_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
