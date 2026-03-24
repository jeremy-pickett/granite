#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
#
# Copyright (c) 2026, Jeremy Pickett
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
# THE POSSIBILITY OF SUCH DAMAGE.
# =============================================================================
#
# Author:  Jeremy Pickett <jeremy@signaldelta.com>
# Project: Participation Over Permission — Provenance Signal Detection
#          Axiomatic Fictions Series
# Date:    March 2026
#
# Co-developed with Claude (Anthropic). Human-directed, AI-assisted.
# =============================================================================
"""
Smart Blind Detector — Layer 3 Position-Level Anomaly Detection
================================================================

The aggregate test failed because it averaged 200 signal positions
into 3,800 noise positions. The signal drowned.

This detector doesn't average. It scores EACH position individually,
then looks for structural patterns that natural images don't produce:

  1. Per-position anomaly: how different is this position from its
     local neighborhood? (the whisper-in-the-library test)

  2. Twin-pair co-occurrence: do anomalous positions come in adjacent
     pairs at a rate higher than chance? (exploiting the known twin
     structure)

  3. Prime-distance enrichment at anomalous positions: do the high-
     scoring positions show prime channel distances more often than
     low-scoring positions? (exploiting the known basket)

  4. Smooth-region weighting: anomalies in smooth regions are weighted
     higher because (a) the embedder preferentially places markers there
     and (b) anomalies in smooth regions are more likely to be intentional.

The test: does this image have more locally-anomalous, twin-paired,
prime-valued positions in smooth regions than a natural image would?

Usage:
    python smart_blind_detector.py -i "C:\\path\\to\\DIV2K" -o smart_blind -n 5
"""

import os
import sys
import io
import json
import time
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from datetime import datetime

from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound


# =============================================================================
# CONFIG
# =============================================================================

CASCADE_QUALITIES = [95, 85, 75, 60, 40]

TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="Smart blind test",
    min_prime=53,
    use_twins=True,
    use_rare_basket=True,
    use_magic=False,
    detection_prime_tolerance=2,
    n_markers=500,
)

MIN_DIMENSION = 512


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
# SMART BLIND SCANNER
# =============================================================================

def compute_local_smoothness(pixels, r, c, ch_a, ch_b, radius=4):
    """
    Compute local smoothness (inverse of variance) in a neighborhood
    around (r, c) using off-grid positions as the reference.
    Lower variance = smoother region = higher weight for anomaly detection.
    """
    h, w, _ = pixels.shape
    dists = []
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                d = abs(int(pixels[nr, nc, ch_a]) - int(pixels[nr, nc, ch_b]))
                dists.append(d)
    if len(dists) < 5:
        return 0.0, 0.0, []
    variance = float(np.var(dists))
    mean = float(np.mean(dists))
    return variance, mean, dists


def smart_blind_scan(pixels, ch_a, ch_b, min_prime=53, tolerance=2):
    """
    Score every eligible position for anomaly, then look for structural
    patterns that indicate intentional embedding.
    """
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    max_val = 255

    # Fuzzy prime lookup (basket primes only)
    fuzzy = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for off in range(-tolerance, tolerance + 1):
            check = d + off
            if 0 <= check <= max_val and check >= min_prime and primes[check]:
                fuzzy[d] = True
                break

    # Get all eligible grid positions
    all_pos = sample_positions_grid(h, w, 8)

    # Score each position
    positions = []
    for pos in all_pos:
        r = int(pos[0]) + 3  # block center offset
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue

        # Channel distances at twin pair
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))

        # Local smoothness at this position
        local_var, local_mean, local_dists = compute_local_smoothness(
            pixels, r, c, ch_a, ch_b
        )

        if not local_dists or local_var == 0:
            continue

        # Anomaly score: how far is this twin pair's distance from the
        # local neighborhood mean, normalized by local std
        local_std = max(np.std(local_dists), 0.01)
        anomaly_d1 = abs(d1 - local_mean) / local_std
        anomaly_d2 = abs(d2 - local_mean) / local_std
        anomaly = (anomaly_d1 + anomaly_d2) / 2.0

        # Smooth-region weight: inverse of local variance
        # Smoother regions get higher weight
        smoothness_weight = 1.0 / (1.0 + local_var)

        # Weighted anomaly score
        weighted_anomaly = anomaly * smoothness_weight

        # Prime check
        is_prime_d1 = fuzzy[min(d1, max_val)]
        is_prime_d2 = fuzzy[min(d2, max_val)]
        both_prime = is_prime_d1 and is_prime_d2

        positions.append({
            "r": r, "c": c, "tc": tc,
            "d1": d1, "d2": d2,
            "anomaly": round(anomaly, 4),
            "smoothness_weight": round(smoothness_weight, 6),
            "weighted_anomaly": round(weighted_anomaly, 6),
            "local_var": round(local_var, 4),
            "local_mean": round(local_mean, 4),
            "both_prime": both_prime,
        })

    if not positions:
        return {"error": "no positions", "detected": False}

    n_pos = len(positions)

    # Sort by weighted anomaly score
    positions.sort(key=lambda x: x["weighted_anomaly"], reverse=True)

    # =========================================================================
    # TEST 1: Twin-pair anomaly co-occurrence
    # =========================================================================
    # Among the top N% of anomalous positions, how many form twin pairs?
    # In a natural image, high anomaly positions scatter randomly.
    # In a marked image, high anomaly positions come in adjacent pairs.

    for percentile_cutoff in [90, 80, 70]:
        threshold_idx = int(n_pos * (100 - percentile_cutoff) / 100)
        top_positions = positions[:max(threshold_idx, 1)]
        top_set = set()
        for p in top_positions:
            top_set.add((p["r"], p["c"]))
            top_set.add((p["r"], p["tc"]))

        # Count twin pairs where BOTH are in top set
        twin_pairs_in_top = 0
        for p in top_positions:
            twin_key = (p["r"], p["tc"])
            if twin_key in top_set:
                # Check the twin is also in the top set via its own score
                # (not just because we added it)
                for p2 in top_positions:
                    if p2["r"] == p["r"] and p2["c"] == p["tc"]:
                        twin_pairs_in_top += 1
                        break

        # Expected twin pairs by chance in top N%
        # If we randomly select threshold_idx positions from n_pos,
        # the probability of selecting both a position and its twin is:
        # approximately (threshold_idx / n_pos)^2 * n_pos
        p_select = threshold_idx / n_pos
        expected_twin_pairs = p_select * p_select * n_pos
        # More precise: hypergeometric, but this approximation is fine

        if percentile_cutoff == 90:
            twin_test_90 = {
                "cutoff": percentile_cutoff,
                "top_n": len(top_positions),
                "twin_pairs": twin_pairs_in_top,
                "expected": round(expected_twin_pairs, 2),
                "ratio": round(twin_pairs_in_top / max(expected_twin_pairs, 0.01), 2),
            }
        elif percentile_cutoff == 80:
            twin_test_80 = {
                "cutoff": percentile_cutoff,
                "top_n": len(top_positions),
                "twin_pairs": twin_pairs_in_top,
                "expected": round(expected_twin_pairs, 2),
                "ratio": round(twin_pairs_in_top / max(expected_twin_pairs, 0.01), 2),
            }
        elif percentile_cutoff == 70:
            twin_test_70 = {
                "cutoff": percentile_cutoff,
                "top_n": len(top_positions),
                "twin_pairs": twin_pairs_in_top,
                "expected": round(expected_twin_pairs, 2),
                "ratio": round(twin_pairs_in_top / max(expected_twin_pairs, 0.01), 2),
            }

    # =========================================================================
    # TEST 2: Prime enrichment in anomalous vs non-anomalous positions
    # =========================================================================
    # Top 25% by weighted anomaly vs bottom 75%
    split_idx = n_pos // 4
    top_quarter = positions[:split_idx]
    bottom_three_quarters = positions[split_idx:]

    top_prime_rate = (sum(1 for p in top_quarter if p["both_prime"]) /
                      max(len(top_quarter), 1))
    bottom_prime_rate = (sum(1 for p in bottom_three_quarters if p["both_prime"]) /
                         max(len(bottom_three_quarters), 1))
    prime_enrichment = (top_prime_rate / max(bottom_prime_rate, 0.001))

    # Binomial test: is top-quarter prime rate significantly higher?
    if len(top_quarter) > 0 and bottom_prime_rate > 0:
        n_top = len(top_quarter)
        k_top = sum(1 for p in top_quarter if p["both_prime"])
        from scipy.stats import binomtest
        prime_binom_p = binomtest(k_top, n_top, bottom_prime_rate,
                                   alternative='greater').pvalue
    else:
        prime_binom_p = 1.0

    # =========================================================================
    # TEST 3: Anomaly score distribution — fat tail test
    # =========================================================================
    # In a natural image, anomaly scores should be approximately
    # exponentially distributed (or similar light-tailed distribution).
    # Markers create excess mass in the tail.
    all_anomalies = np.array([p["weighted_anomaly"] for p in positions])
    
    # Compute the 95th percentile count and compare to expected
    p95_threshold = np.percentile(all_anomalies, 95)
    n_above_p95 = np.sum(all_anomalies > p95_threshold)
    # In a natural image, exactly 5% should be above the 95th percentile
    # (by definition). But if markers inflate the tail, more than 5% of
    # the smoothness-WEIGHTED scores will be above the raw 95th percentile.
    # ... actually this is circular. Better approach:

    # Compare the tail shape: ratio of 95th to 50th percentile
    p50 = np.percentile(all_anomalies, 50)
    p95 = np.percentile(all_anomalies, 95)
    p99 = np.percentile(all_anomalies, 99)
    tail_ratio_95_50 = p95 / max(p50, 0.001)
    tail_ratio_99_50 = p99 / max(p50, 0.001)

    # Kurtosis: heavy tails = high kurtosis
    kurtosis = float(sp_stats.kurtosis(all_anomalies, fisher=True))

    # =========================================================================
    # TEST 4: Smooth region prime concentration
    # =========================================================================
    # Among positions in the SMOOTHEST 25% of regions, what's the prime rate?
    # The embedder preferentially places markers in smooth regions.
    # So smooth positions should show higher prime rates if marked.
    positions_by_smoothness = sorted(positions,
                                      key=lambda x: x["local_var"])
    smoothest_quarter = positions_by_smoothness[:n_pos // 4]
    roughest_quarter = positions_by_smoothness[-(n_pos // 4):]

    smooth_prime_rate = (sum(1 for p in smoothest_quarter if p["both_prime"]) /
                         max(len(smoothest_quarter), 1))
    rough_prime_rate = (sum(1 for p in roughest_quarter if p["both_prime"]) /
                        max(len(roughest_quarter), 1))
    smooth_rough_prime_ratio = smooth_prime_rate / max(rough_prime_rate, 0.001)

    # Anomaly scores in smooth vs rough regions
    smooth_anomaly_mean = np.mean([p["anomaly"] for p in smoothest_quarter])
    rough_anomaly_mean = np.mean([p["anomaly"] for p in roughest_quarter])
    smooth_rough_anomaly_ratio = smooth_anomaly_mean / max(rough_anomaly_mean, 0.001)

    # =========================================================================
    # COMPOSITE DETECTION DECISION
    # =========================================================================
    # Multiple independent signals that each contribute evidence:
    signals = []

    # Twin pair enrichment at 90th percentile
    if twin_test_90["ratio"] > 2.0:
        signals.append(("twin_90", twin_test_90["ratio"]))

    # Twin pair enrichment at 80th percentile
    if twin_test_80["ratio"] > 1.5:
        signals.append(("twin_80", twin_test_80["ratio"]))

    # Prime enrichment in top anomalous positions
    if prime_enrichment > 1.5 and prime_binom_p < 0.05:
        signals.append(("prime_enrich", prime_enrichment))

    # Heavy tail (kurtosis)
    if kurtosis > 3.0:
        signals.append(("kurtosis", kurtosis))

    # Smooth region prime concentration
    if smooth_rough_prime_ratio > 1.5:
        signals.append(("smooth_prime", smooth_rough_prime_ratio))

    # Detection: 2 or more independent signals
    detected = len(signals) >= 2
    confidence = len(signals) / 5.0  # 0 to 1

    return {
        "n_positions": n_pos,
        "twin_test_90": twin_test_90,
        "twin_test_80": twin_test_80,
        "twin_test_70": twin_test_70,
        "prime_enrichment": round(prime_enrichment, 4),
        "prime_binom_p": float(prime_binom_p),
        "top_prime_rate": round(top_prime_rate, 6),
        "bottom_prime_rate": round(bottom_prime_rate, 6),
        "kurtosis": round(kurtosis, 4),
        "tail_ratio_95_50": round(tail_ratio_95_50, 4),
        "tail_ratio_99_50": round(tail_ratio_99_50, 4),
        "smooth_prime_rate": round(smooth_prime_rate, 6),
        "rough_prime_rate": round(rough_prime_rate, 6),
        "smooth_rough_prime_ratio": round(smooth_rough_prime_ratio, 4),
        "smooth_anomaly_mean": round(float(smooth_anomaly_mean), 4),
        "rough_anomaly_mean": round(float(rough_anomaly_mean), 4),
        "smooth_rough_anomaly_ratio": round(float(smooth_rough_anomaly_ratio), 4),
        "signals": signals,
        "n_signals": len(signals),
        "confidence": round(confidence, 2),
        "detected": detected,
    }


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w = pixels.shape[:2]
    result = {
        "image": fname,
        "dimensions": f"{w}x{h}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # --- MARKED PATH ---
    marked_pixels, markers = embed_compound(pixels.copy(), TWIN_CONFIG, seed=42)
    result["n_markers"] = len(markers)

    if len(markers) < 20:
        result["error"] = f"Too few markers: {len(markers)}"
        return result

    marked_jpeg = to_jpeg(marked_pixels, quality=95)

    # --- CLEAN PATH ---
    clean_jpeg = to_jpeg(pixels, quality=95)

    # --- CASCADE AND TEST ---
    cascade = []
    current_marked = marked_jpeg
    current_clean = clean_jpeg

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
            current_clean = to_jpeg(decode_jpeg(current_clean), quality=q)

        marked_px = decode_jpeg(current_marked)
        clean_px = decode_jpeg(current_clean)

        gen = {"generation": gen_idx, "quality": q}

        for pair_name, (ch_a, ch_b) in [("GB", (1, 2)), ("RG", (0, 1))]:
            # Smart scan on marked image
            marked_result = smart_blind_scan(
                marked_px, ch_a, ch_b,
                min_prime=TWIN_CONFIG.min_prime,
                tolerance=TWIN_CONFIG.detection_prime_tolerance
            )
            # Smart scan on clean image
            clean_result = smart_blind_scan(
                clean_px, ch_a, ch_b,
                min_prime=TWIN_CONFIG.min_prime,
                tolerance=TWIN_CONFIG.detection_prime_tolerance
            )

            gen[f"{pair_name}_marked_detected"] = marked_result.get("detected", False)
            gen[f"{pair_name}_marked_n_signals"] = marked_result.get("n_signals", 0)
            gen[f"{pair_name}_marked_confidence"] = marked_result.get("confidence", 0)
            gen[f"{pair_name}_marked_twin90_ratio"] = marked_result.get("twin_test_90", {}).get("ratio", 0)
            gen[f"{pair_name}_marked_prime_enrich"] = marked_result.get("prime_enrichment", 0)
            gen[f"{pair_name}_marked_kurtosis"] = marked_result.get("kurtosis", 0)
            gen[f"{pair_name}_marked_smooth_prime"] = marked_result.get("smooth_rough_prime_ratio", 0)
            gen[f"{pair_name}_marked_signals"] = [s[0] for s in marked_result.get("signals", [])]

            gen[f"{pair_name}_clean_detected"] = clean_result.get("detected", False)
            gen[f"{pair_name}_clean_n_signals"] = clean_result.get("n_signals", 0)
            gen[f"{pair_name}_clean_confidence"] = clean_result.get("confidence", 0)
            gen[f"{pair_name}_clean_twin90_ratio"] = clean_result.get("twin_test_90", {}).get("ratio", 0)

            # TRUE POSITIVE: marked detected, clean not detected
            # FALSE POSITIVE: clean detected
            # FALSE NEGATIVE: marked not detected
            gen[f"{pair_name}_TP"] = marked_result.get("detected", False) and not clean_result.get("detected", False)
            gen[f"{pair_name}_FP"] = clean_result.get("detected", False)
            gen[f"{pair_name}_FN"] = not marked_result.get("detected", False)

        # Any pair true positive
        gen["any_TP"] = any(gen.get(f"{pn}_TP", False) for pn in ["GB", "RG"])
        gen["any_FP"] = any(gen.get(f"{pn}_FP", False) for pn in ["GB", "RG"])

        cascade.append(gen)

    result["cascade"] = cascade

    # Gen4 summary
    gen4 = cascade[4] if len(cascade) > 4 else {}
    for pair_name in ["GB", "RG"]:
        result[f"{pair_name}_gen4_TP"] = gen4.get(f"{pair_name}_TP", False)
        result[f"{pair_name}_gen4_FP"] = gen4.get(f"{pair_name}_FP", False)
        result[f"{pair_name}_gen4_marked_signals"] = gen4.get(f"{pair_name}_marked_signals", [])
        result[f"{pair_name}_gen4_marked_confidence"] = gen4.get(f"{pair_name}_marked_confidence", 0)
    result["gen4_any_TP"] = gen4.get("any_TP", False)
    result["gen4_any_FP"] = gen4.get("any_FP", False)

    return result


# =============================================================================
# CORPUS RUN
# =============================================================================

def run_corpus(input_dir, output_dir, max_images=0):
    os.makedirs(output_dir, exist_ok=True)

    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    all_files = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])

    if max_images > 0:
        all_files = all_files[:max_images]

    n_total = len(all_files)
    print(f"{'='*80}")
    print(f"SMART BLIND DETECTOR — Position-Level Anomaly Detection")
    print(f"{'='*80}")
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Images:     {n_total}")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Method:     Per-position anomaly + twin pairing + prime enrichment")
    print(f"            + smooth-region weighting")
    print(f"Started:    {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "smart_blind_per_image.jsonl")
    with open(results_file, "w") as f:
        f.write("")

    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>4d}/{n_total}] {fname}  ", end="", flush=True)

        try:
            img = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}")
            continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"SKIP")
            continue

        max_dim = max(h, w)
        if max_dim > 1024:
            scale = 1024 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        if "error" in result:
            print(f"ERROR: {result['error']}  [{elapsed:.1f}s]")
        else:
            tp = "TP" if result.get("gen4_any_TP", False) else "  "
            fp = "FP!" if result.get("gen4_any_FP", False) else "   "
            gb_conf = result.get("GB_gen4_marked_confidence", 0)
            gb_sigs = result.get("GB_gen4_marked_signals", [])
            print(f"n={result.get('n_markers',0):>3d}  {tp} {fp}"
                  f"  conf={gb_conf:.2f}  sigs={gb_sigs}"
                  f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    good = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"SMART BLIND DETECTOR — AGGREGATE ({n_good} images)")
    print(f"Total time: {total_time:.0f}s ({total_time/max(n_good,1):.1f}s/image)")
    print(f"{'='*80}")

    if n_good == 0:
        print("No valid results.")
        return

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        print(f"\n  Gen{gen_idx} Q{q:>3d}:")
        for pair_name in ["GB", "RG"]:
            tp = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get(f"{pair_name}_TP", False))
            fp = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get(f"{pair_name}_FP", False))
            fn = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get(f"{pair_name}_FN", True))
            print(f"    {pair_name}: TP={tp}/{n_good} ({tp/n_good*100:.1f}%)"
                  f"  FP={fp}/{n_good} ({fp/n_good*100:.1f}%)"
                  f"  FN={fn}/{n_good} ({fn/n_good*100:.1f}%)")

        any_tp = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get("any_TP", False))
        any_fp = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get("any_FP", False))
        print(f"    Either: TP={any_tp}/{n_good} ({any_tp/n_good*100:.1f}%)"
              f"  FP={any_fp}/{n_good} ({any_fp/n_good*100:.1f}%)")

    # Final verdict
    gen4_tp = sum(1 for r in good if r.get("gen4_any_TP", False))
    gen4_fp = sum(1 for r in good if r.get("gen4_any_FP", False))
    tp_pct = gen4_tp / n_good * 100
    fp_pct = gen4_fp / n_good * 100

    print(f"\n{'='*80}")
    print(f"SMART BLIND VERDICT (Gen4 Q40)")
    print(f"{'='*80}")
    print(f"  True Positives:  {gen4_tp}/{n_good} ({tp_pct:.1f}%)")
    print(f"  False Positives: {gen4_fp}/{n_good} ({fp_pct:.1f}%)")

    if tp_pct > 80 and fp_pct < 10:
        verdict = f"LAYER 3 WORKS. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP."
    elif tp_pct > 50 and fp_pct < 20:
        verdict = f"LAYER 3 VIABLE. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP. Needs tuning."
    elif tp_pct > 20:
        verdict = f"LAYER 3 MARGINAL. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP."
    else:
        verdict = f"LAYER 3 NEEDS WORK. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP."

    print(f"\n  {verdict}")

    with open(os.path.join(output_dir, "SMART_BLIND_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")

    aggregate = {
        "n_images": n_good,
        "total_time": round(total_time, 1),
        "gen4_TP_pct": round(tp_pct, 1),
        "gen4_FP_pct": round(fp_pct, 1),
    }
    with open(os.path.join(output_dir, "smart_blind_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Smart Blind Detector — Layer 3 Position-Level Anomaly"
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="smart_blind_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
