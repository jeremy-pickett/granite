#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Density Sweep — How Many Markers for Blind Detection?
======================================================

Test blind detection at increasing marker densities:
  200, 500, 1000, 2000, 3000 markers

For each density:
  1. Embed markers
  2. Compress through cascade
  3. Blind-scan using the smart detector (twin pairing + prime enrichment)
  4. Also blind-scan using simple aggregate KS (to confirm it's still dead)
  5. Report detection rate and PSNR cost

The question: at what density does blind detection become viable,
and what does it cost in image quality?

Usage:
    python density_sweep.py -i "C:\\path\\to\\DIV2K" -o density_results -n 5
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

# Test at these marker counts
DENSITY_LEVELS = [200, 500, 1000, 2000, 3000]

# Only test gen0 (Q95) and gen4 (Q40) to save time
TEST_QUALITIES = [(0, 95), (4, 40)]

MIN_DIMENSION = 512


def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def compute_psnr(original, modified):
    """Peak Signal to Noise Ratio between two images."""
    mse = np.mean((original.astype(float) - modified.astype(float)) ** 2)
    if mse == 0:
        return float('inf')
    return 10 * np.log10(255.0 ** 2 / mse)


# =============================================================================
# BLIND DETECTION: aggregate KS (the one that failed)
# =============================================================================

def blind_aggregate_ks(marked_px, clean_px, ch_a, ch_b):
    """Simple aggregate KS test: compare all eligible positions between
    marked and clean images."""
    h, w, _ = marked_px.shape
    all_pos = sample_positions_grid(h, w, 8)

    marked_dists = []
    clean_dists = []

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue

        md1 = abs(int(marked_px[r, c, ch_a]) - int(marked_px[r, c, ch_b]))
        md2 = abs(int(marked_px[r, tc, ch_a]) - int(marked_px[r, tc, ch_b]))
        marked_dists.extend([md1, md2])

        cd1 = abs(int(clean_px[r, c, ch_a]) - int(clean_px[r, c, ch_b]))
        cd2 = abs(int(clean_px[r, tc, ch_a]) - int(clean_px[r, tc, ch_b]))
        clean_dists.extend([cd1, cd2])

    if len(marked_dists) < 20:
        return 1.0
    ks_stat, ks_p = sp_stats.ks_2samp(marked_dists, clean_dists)
    return float(ks_p)


# =============================================================================
# BLIND DETECTION: smart (twin pairing + prime enrichment in self-comparison)
# =============================================================================

def blind_smart_self(pixels, ch_a, ch_b, min_prime=53, tolerance=2):
    """
    Smart blind detection on a SINGLE image (no clean reference).
    Scores positions by local anomaly, then checks for twin-pair
    co-occurrence and prime enrichment in the anomalous tail.
    """
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    max_val = 255

    fuzzy = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for off in range(-tolerance, tolerance + 1):
            check = d + off
            if 0 <= check <= max_val and check >= min_prime and primes[check]:
                fuzzy[d] = True
                break

    all_pos = sample_positions_grid(h, w, 8)
    scores = []

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue

        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))

        # Local neighborhood distances (off-grid, radius 3)
        nbr_dists = []
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w:
                    nd = abs(int(pixels[nr, nc, ch_a]) - int(pixels[nr, nc, ch_b]))
                    nbr_dists.append(nd)

        if len(nbr_dists) < 5:
            continue

        nbr_mean = np.mean(nbr_dists)
        nbr_std = max(np.std(nbr_dists), 0.5)
        nbr_var = np.var(nbr_dists)

        # Anomaly: how far are the twin distances from local mean
        anomaly = (abs(d1 - nbr_mean) + abs(d2 - nbr_mean)) / (2 * nbr_std)

        # Smooth weight
        smooth_w = 1.0 / (1.0 + nbr_var)

        both_prime = fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]

        scores.append({
            "r": r, "c": c, "tc": tc,
            "d1": d1, "d2": d2,
            "anomaly": anomaly,
            "weighted": anomaly * smooth_w,
            "both_prime": both_prime,
            "local_var": nbr_var,
        })

    if len(scores) < 20:
        return {"detected": False, "n_signals": 0, "detail": "too few positions"}

    n = len(scores)

    # Sort by weighted anomaly
    scores.sort(key=lambda x: x["weighted"], reverse=True)

    # --- Signal 1: Twin pair co-occurrence in top 10% ---
    top_n = max(n // 10, 10)
    top_positions = scores[:top_n]
    top_coords = set()
    for s in top_positions:
        top_coords.add((s["r"], s["c"]))
        top_coords.add((s["r"], s["tc"]))

    twin_hits = 0
    for s in top_positions:
        # Check if this position's twin is ALSO in the top set
        # by its own merit (not just because we added both coords)
        twin_col = s["tc"]
        for s2 in top_positions:
            if s2["r"] == s["r"] and s2["c"] == twin_col and s2 is not s:
                twin_hits += 1
                break

    p_top = top_n / n
    expected_twins = p_top * p_top * n
    twin_ratio = twin_hits / max(expected_twins, 0.1)

    # --- Signal 2: Prime enrichment in top 25% vs bottom 75% ---
    q1 = n // 4
    top_q = scores[:q1]
    bot_q = scores[q1:]
    top_prime = sum(1 for s in top_q if s["both_prime"]) / max(len(top_q), 1)
    bot_prime = sum(1 for s in bot_q if s["both_prime"]) / max(len(bot_q), 1)
    prime_ratio = top_prime / max(bot_prime, 0.0001)

    # Binomial test
    if bot_prime > 0 and len(top_q) > 0:
        k = sum(1 for s in top_q if s["both_prime"])
        from scipy.stats import binomtest
        prime_p = binomtest(k, len(top_q), bot_prime, alternative='greater').pvalue
    else:
        prime_p = 1.0

    # --- Signal 3: Smooth-region prime concentration ---
    scores_by_var = sorted(scores, key=lambda x: x["local_var"])
    smooth_q = scores_by_var[:n // 4]
    rough_q = scores_by_var[-(n // 4):]
    smooth_prime = sum(1 for s in smooth_q if s["both_prime"]) / max(len(smooth_q), 1)
    rough_prime = sum(1 for s in rough_q if s["both_prime"]) / max(len(rough_q), 1)
    smooth_ratio = smooth_prime / max(rough_prime, 0.0001)

    # --- Signal 4: Kurtosis of weighted anomaly distribution ---
    all_weighted = np.array([s["weighted"] for s in scores])
    kurt = float(sp_stats.kurtosis(all_weighted, fisher=True))

    # --- Signal 5: Overall prime rate elevation ---
    overall_prime_rate = sum(1 for s in scores if s["both_prime"]) / n
    # Expected twin-prime rate for random: roughly (primes_in_basket / 256)^2
    # With basket floor 53, roughly 40 primes in 53-255 range out of 203 values
    # ~20% single prime rate, ~4% twin prime rate
    expected_twin_prime = 0.04
    prime_elevation = overall_prime_rate / max(expected_twin_prime, 0.001)

    # --- Composite decision ---
    signals = []
    if twin_ratio > 2.0:
        signals.append(f"twin_cooccur:{twin_ratio:.1f}")
    if prime_ratio > 1.5 and prime_p < 0.05:
        signals.append(f"prime_enrich:{prime_ratio:.1f}")
    if smooth_ratio > 1.5:
        signals.append(f"smooth_prime:{smooth_ratio:.1f}")
    if kurt > 5.0:
        signals.append(f"kurtosis:{kurt:.1f}")
    if prime_elevation > 1.3:
        signals.append(f"prime_elevated:{prime_elevation:.2f}")

    detected = len(signals) >= 2

    return {
        "detected": detected,
        "n_signals": len(signals),
        "signals": signals,
        "twin_ratio": round(twin_ratio, 2),
        "twin_hits": twin_hits,
        "expected_twins": round(expected_twins, 2),
        "prime_ratio": round(prime_ratio, 4),
        "prime_p": float(prime_p),
        "smooth_ratio": round(smooth_ratio, 4),
        "kurtosis": round(kurt, 4),
        "prime_elevation": round(prime_elevation, 4),
        "overall_prime_rate": round(overall_prime_rate, 6),
        "n_positions": n,
    }


# =============================================================================
# SINGLE IMAGE, SINGLE DENSITY
# =============================================================================

def test_one_density(pixels, n_markers, seed=42):
    """Embed at given density, cascade, blind detect."""
    config = MarkerConfig(
        name="density_test",
        description=f"Density sweep n={n_markers}",
        min_prime=53,
        use_twins=True,
        use_rare_basket=True,
        use_magic=False,
        detection_prime_tolerance=2,
        n_markers=n_markers,
    )

    # Embed
    marked_pixels, markers = embed_compound(pixels.copy(), config, seed=seed)
    actual_markers = len(markers)

    if actual_markers < 10:
        return {"n_requested": n_markers, "n_actual": actual_markers,
                "error": "too few markers"}

    # PSNR
    psnr = compute_psnr(pixels, marked_pixels)

    # Encode both
    marked_jpeg = to_jpeg(marked_pixels, 95)
    clean_jpeg = to_jpeg(pixels, 95)

    results = {
        "n_requested": n_markers,
        "n_actual": actual_markers,
        "psnr": round(psnr, 2),
    }

    # Test at Gen0 Q95 and Gen4 Q40
    current_marked = marked_jpeg
    current_clean = clean_jpeg

    for gen_idx in range(5):
        q = [95, 85, 75, 60, 40][gen_idx]
        if gen_idx > 0:
            current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
            current_clean = to_jpeg(decode_jpeg(current_clean), quality=q)

        # Only test gen0 and gen4 to save time
        if gen_idx not in [0, 4]:
            continue

        marked_px = decode_jpeg(current_marked)
        clean_px = decode_jpeg(current_clean)

        label = f"gen{gen_idx}_q{q}"

        # Aggregate KS (the test that failed)
        agg_ks_gb = blind_aggregate_ks(marked_px, clean_px, 1, 2)
        agg_ks_rg = blind_aggregate_ks(marked_px, clean_px, 0, 1)

        # Smart self-detection on marked image
        smart_marked_gb = blind_smart_self(marked_px, 1, 2,
                                            min_prime=53, tolerance=2)
        smart_marked_rg = blind_smart_self(marked_px, 0, 1,
                                            min_prime=53, tolerance=2)

        # Smart self-detection on clean image (for FP rate)
        smart_clean_gb = blind_smart_self(clean_px, 1, 2,
                                           min_prime=53, tolerance=2)
        smart_clean_rg = blind_smart_self(clean_px, 0, 1,
                                           min_prime=53, tolerance=2)

        results[f"{label}_agg_ks_gb"] = agg_ks_gb
        results[f"{label}_agg_ks_rg"] = agg_ks_rg
        results[f"{label}_agg_detected_gb"] = agg_ks_gb < 0.05
        results[f"{label}_agg_detected_rg"] = agg_ks_rg < 0.05

        results[f"{label}_smart_marked_gb"] = smart_marked_gb.get("detected", False)
        results[f"{label}_smart_marked_gb_signals"] = smart_marked_gb.get("signals", [])
        results[f"{label}_smart_marked_gb_nsig"] = smart_marked_gb.get("n_signals", 0)
        results[f"{label}_smart_marked_gb_prime_elev"] = smart_marked_gb.get("prime_elevation", 0)
        results[f"{label}_smart_marked_gb_twin"] = smart_marked_gb.get("twin_ratio", 0)

        results[f"{label}_smart_marked_rg"] = smart_marked_rg.get("detected", False)
        results[f"{label}_smart_marked_rg_signals"] = smart_marked_rg.get("signals", [])
        results[f"{label}_smart_marked_rg_nsig"] = smart_marked_rg.get("n_signals", 0)

        results[f"{label}_smart_clean_gb"] = smart_clean_gb.get("detected", False)
        results[f"{label}_smart_clean_rg"] = smart_clean_rg.get("detected", False)

        # TP = marked detected AND clean not detected
        results[f"{label}_TP_gb"] = (smart_marked_gb.get("detected", False) and
                                      not smart_clean_gb.get("detected", False))
        results[f"{label}_TP_rg"] = (smart_marked_rg.get("detected", False) and
                                      not smart_clean_rg.get("detected", False))
        results[f"{label}_any_TP"] = results[f"{label}_TP_gb"] or results[f"{label}_TP_rg"]
        results[f"{label}_any_FP"] = (smart_clean_gb.get("detected", False) or
                                       smart_clean_rg.get("detected", False))

    return results


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
    print(f"DENSITY SWEEP — Blind Detection vs Marker Count")
    print(f"{'='*80}")
    print(f"Images:     {n_total}")
    print(f"Densities:  {DENSITY_LEVELS}")
    print(f"Testing:    Gen0 Q95 + Gen4 Q40")
    print(f"{'='*80}\n")

    all_results = {d: [] for d in DENSITY_LEVELS}
    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        print(f"[{idx+1:>3d}/{n_total}] {fname}")

        try:
            img = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"  SKIP")
            continue

        max_dim = max(h, w)
        if max_dim > 1024:
            scale = 1024 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)

        for n_markers in DENSITY_LEVELS:
            t_d = time.time()
            result = test_one_density(pixels, n_markers)
            result["image"] = fname
            elapsed = time.time() - t_d

            # Quick status
            gen4_tp = result.get("gen4_q40_any_TP", False)
            psnr = result.get("psnr", 0)
            n_actual = result.get("n_actual", 0)
            tp_flag = "TP" if gen4_tp else "  "
            agg_flag = "AGG" if result.get("gen4_q40_agg_detected_gb", False) else "   "

            print(f"  n={n_markers:>5d} actual={n_actual:>4d}"
                  f"  PSNR={psnr:>5.1f}dB"
                  f"  {tp_flag} {agg_flag}"
                  f"  [{elapsed:.1f}s]")

            all_results[n_markers].append(result)

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE PER DENSITY LEVEL
    # =========================================================================

    print(f"\n\n{'='*80}")
    print(f"DENSITY SWEEP RESULTS ({n_total} images)")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    print(f"{'Markers':>8s}  {'Actual':>7s}  {'PSNR':>7s}"
          f"  {'G0 Agg':>7s}  {'G4 Agg':>7s}"
          f"  {'G0 Smart':>9s}  {'G4 Smart':>9s}"
          f"  {'G4 FP':>6s}")
    print(f"{'─'*75}")

    summary = []
    for n_markers in DENSITY_LEVELS:
        results = all_results[n_markers]
        if not results:
            continue

        good = [r for r in results if "error" not in r]
        if not good:
            continue

        n = len(good)
        mean_actual = np.mean([r.get("n_actual", 0) for r in good])
        mean_psnr = np.mean([r.get("psnr", 0) for r in good])

        # Gen0 aggregate KS detection
        g0_agg = sum(1 for r in good
                     if r.get("gen0_q95_agg_detected_gb", False)
                     or r.get("gen0_q95_agg_detected_rg", False))

        # Gen4 aggregate KS detection
        g4_agg = sum(1 for r in good
                     if r.get("gen4_q40_agg_detected_gb", False)
                     or r.get("gen4_q40_agg_detected_rg", False))

        # Gen0 smart TP
        g0_tp = sum(1 for r in good if r.get("gen0_q95_any_TP", False))

        # Gen4 smart TP
        g4_tp = sum(1 for r in good if r.get("gen4_q40_any_TP", False))

        # Gen4 FP
        g4_fp = sum(1 for r in good if r.get("gen4_q40_any_FP", False))

        print(f"{n_markers:>8d}  {mean_actual:>7.0f}  {mean_psnr:>6.1f}dB"
              f"  {g0_agg:>3d}/{n} {g0_agg/n*100:>3.0f}%"
              f"  {g4_agg:>3d}/{n} {g4_agg/n*100:>3.0f}%"
              f"  {g0_tp:>4d}/{n} {g0_tp/n*100:>3.0f}%"
              f"  {g4_tp:>4d}/{n} {g4_tp/n*100:>3.0f}%"
              f"  {g4_fp:>2d}/{n} {g4_fp/n*100:>2.0f}%")

        summary.append({
            "n_markers": n_markers,
            "mean_actual": round(mean_actual),
            "mean_psnr": round(mean_psnr, 2),
            "n_images": n,
            "gen0_agg_pct": round(g0_agg / n * 100, 1),
            "gen4_agg_pct": round(g4_agg / n * 100, 1),
            "gen0_smart_tp_pct": round(g0_tp / n * 100, 1),
            "gen4_smart_tp_pct": round(g4_tp / n * 100, 1),
            "gen4_fp_pct": round(g4_fp / n * 100, 1),
        })

    print(f"\n{'='*80}")
    print(f"THE DENSITY QUESTION")
    print(f"{'='*80}")
    print(f"At what density does blind detection become viable?")
    print(f"What PSNR cost is acceptable? (>40dB generally imperceptible)")
    print(f"{'='*80}")

    with open(os.path.join(output_dir, "density_sweep.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Save per-image details
    for n_markers in DENSITY_LEVELS:
        fname = os.path.join(output_dir, f"density_{n_markers}.jsonl")
        with open(fname, "w") as f:
            for r in all_results[n_markers]:
                f.write(json.dumps(r, default=str) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Density Sweep — How many markers for blind detection?"
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="density_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
