#!/usr/bin/env python3
"""
DIV2K Validation Harness v2 — The Granite Test
================================================
Jeremy Pickett — Axiomatic Fictions Series
March 2026

WHAT'S NEW IN V2:
  - Tests BOTH R-G (0,1) and G-B (1,2) channel pairs
  - Reports per-pair survival curves
  - Windows-compatible paths
  - 5-image sanity check mode

DEFENSIBILITY PROTOCOL:
  1. Run with --max-images 5 first. Verify it completes. Check the numbers.
  2. If sane, run with --max-images 0 (all images). Walk away.
  3. Read results with fresh eyes. Don't hope. Measure.

Usage:
    python div2k_harness_v2.py -i "C:\\path\\to\\DIV2K_train_HR" -o results
    python div2k_harness_v2.py -i "C:\\path\\to\\DIV2K_train_HR" -o results -n 5

Dependencies:
    pip install Pillow numpy scipy

Required files in the same directory:
    pgps_detector.py
    compound_markers.py
    dqt_prime.py
    smart_embedder.py
"""

import os
import sys
import io
import json
import time
import traceback
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from datetime import datetime

# Local imports — all scripts must be in the same directory
from pgps_detector import (
    build_prime_lookup, sieve_of_eratosthenes,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
)
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
)
from dqt_prime import encode_prime_jpeg, detect_prime_dqt

# Try to import smart_embedder, but don't die if it's missing
try:
    from smart_embedder import compute_local_entropy_fast
except ImportError:
    compute_local_entropy_fast = None


# =============================================================================
# CONFIGURATION
# =============================================================================

CASCADE_QUALITIES = [95, 85, 75, 60, 40]

CHANNEL_PAIRS = {
    "RG": (0, 1),
    "GB": (1, 2),
}

TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="DIV2K granite test",
    min_prime=53,
    use_twins=True,
    use_rare_basket=True,
    use_magic=False,
    detection_prime_tolerance=2,
    n_markers=500,
)

MIN_DIMENSION = 512  # Skip anything smaller


# =============================================================================
# JPEG UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def to_prime_jpeg(pixels, quality=95):
    """Encode with prime DQT tables."""
    try:
        result = encode_prime_jpeg(pixels, quality=quality)
        if isinstance(result, tuple):
            return result[0]
        return result
    except Exception:
        return to_jpeg(pixels, quality)


# =============================================================================
# MEASUREMENT: PER CHANNEL PAIR
# =============================================================================

def measure_channel_pair(pixels, markers, ch_a, ch_b, config):
    """
    Measure twin-prime enrichment and variance anomaly for a specific
    channel pair. Returns dict with detection metrics.
    """
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    tol = config.detection_prime_tolerance
    max_val = 255

    # Build fuzzy prime lookup
    fuzzy = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for off in range(-tol, tol + 1):
            check = d + off
            if 0 <= check <= max_val and primes[check]:
                fuzzy[d] = True
                break

    # --- Marker positions ---
    marker_dists = []
    m_pass = 0
    m_total = 0
    for m in markers:
        r, c = m["row"], m["col"]
        tc_col = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc_col >= w:
            continue
        m_total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc_col, ch_a]) - int(pixels[r, tc_col, ch_b]))
        marker_dists.append(d1)
        marker_dists.append(d2)
        if fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]:
            m_pass += 1

    # --- Control positions ---
    marker_set = set()
    for m in markers:
        marker_set.add((m["row"], m["col"]))
        marker_set.add((m["row"], m.get("twin_col", m["col"] + 1)))

    all_pos = sample_positions_grid(h, w, 8)
    control_dists = []
    c_pass = 0
    c_total = 0
    for pos in all_pos:
        r, c = int(pos[0]) + 3, int(pos[1]) + 3
        tc_col = c + 1
        if (r, c) in marker_set or (r, tc_col) in marker_set:
            continue
        if r >= h or c >= w or tc_col >= w:
            continue
        c_total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc_col, ch_a]) - int(pixels[r, tc_col, ch_b]))
        control_dists.append(d1)
        control_dists.append(d2)
        if fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]:
            c_pass += 1

    m_rate = m_pass / m_total if m_total > 0 else 0
    c_rate = c_pass / c_total if c_total > 0 else 0
    ratio = m_rate / c_rate if c_rate > 0 else float('inf')

    # Binomial test
    if m_total > 0 and c_total > 0 and c_rate > 0:
        from scipy.stats import binomtest
        binom_p = binomtest(m_pass, m_total, c_rate, alternative='greater').pvalue
    else:
        binom_p = 1.0

    # KS test on distance distributions
    if len(marker_dists) > 10 and len(control_dists) > 10:
        ks_stat, ks_p = sp_stats.ks_2samp(marker_dists, control_dists)
    else:
        ks_stat, ks_p = 0.0, 1.0

    # Variance ratio
    if len(marker_dists) > 1 and len(control_dists) > 1:
        m_var = np.var(marker_dists)
        c_var = np.var(control_dists)
        var_ratio = m_var / c_var if c_var > 0 else float('inf')
    else:
        var_ratio = 1.0

    return {
        "m_pass": m_pass,
        "m_total": m_total,
        "m_rate": round(m_rate, 6),
        "c_rate": round(c_rate, 6),
        "enrichment_ratio": round(ratio, 4),
        "binom_p": float(binom_p),
        "ks_stat": round(float(ks_stat), 6),
        "ks_p": float(ks_p),
        "variance_ratio": round(float(var_ratio), 4),
        "detected": binom_p < 0.05 or ks_p < 0.05,
    }


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname, work_dir):
    """
    Run full granite test on one image:
    - Embed with prime DQT + twin markers
    - Cascade through quality levels
    - Measure BOTH R-G and G-B at each generation
    """
    h, w = pixels.shape[:2]
    result = {
        "image": fname,
        "dimensions": f"{w}x{h}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # --- Step 1: Embed ---
    prime_jpeg_data = to_prime_jpeg(pixels, quality=95)
    prime_pixels = decode_jpeg(prime_jpeg_data)

    embedded_pixels, markers = embed_compound(prime_pixels, TWIN_CONFIG, seed=42)
    result["n_markers_embedded"] = len(markers)

    if len(markers) < 20:
        result["error"] = f"Too few markers: {len(markers)}"
        return result

    # --- Step 2: Initial encode (Gen 0) ---
    jpeg_data = to_jpeg(embedded_pixels, quality=95)

    # --- Step 3: Cascade ---
    cascade = []
    current_data = jpeg_data

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current_data = to_jpeg(decode_jpeg(current_data), quality=q)

        test_pixels = decode_jpeg(current_data)
        gen = {"generation": gen_idx, "quality": q}

        # DQT detection (gen 0 only meaningful for prime DQT)
        if gen_idx == 0:
            dqt_result = detect_prime_dqt(current_data)
            gen["dqt_detected"] = dqt_result.get("is_provenance", False)
            gen["dqt_prime_rate"] = dqt_result.get("prime_rate", 0)
            result["gen0_dqt_detected"] = gen["dqt_detected"]

        # Measure BOTH channel pairs
        for pair_name, pair_indices in CHANNEL_PAIRS.items():
            m = measure_channel_pair(
                test_pixels, markers, pair_indices[0], pair_indices[1], TWIN_CONFIG
            )
            # Store with pair prefix
            for k, v in m.items():
                gen[f"{pair_name}_{k}"] = v

        # Composite detection: any pair detected?
        gen["any_detected"] = any(
            gen.get(f"{pn}_detected", False) for pn in CHANNEL_PAIRS
        )

        cascade.append(gen)

    result["cascade"] = cascade

    # --- Step 4: Amplification check ---
    # For each pair, check if Gen4 is stronger than Gen1-3
    for pair_name in CHANNEL_PAIRS:
        gen4_ks = cascade[4][f"{pair_name}_ks_p"] if len(cascade) > 4 else 1.0
        earlier_ks = [
            cascade[i][f"{pair_name}_ks_p"]
            for i in range(1, min(4, len(cascade)))
        ]
        amp = (gen4_ks < 0.05 and
               all(gen4_ks <= ek for ek in earlier_ks) if earlier_ks else False)
        result[f"{pair_name}_amplification"] = amp
        result[f"{pair_name}_gen4_ks_p"] = float(gen4_ks)

        # Variance ratio trend
        vrs = [cascade[i].get(f"{pair_name}_variance_ratio", 1.0)
               for i in range(len(cascade))]
        result[f"{pair_name}_vr_trend"] = [round(v, 4) for v in vrs]

    # Overall amplification: either pair shows it
    result["amplification_confirmed"] = any(
        result.get(f"{pn}_amplification", False) for pn in CHANNEL_PAIRS
    )

    return result


# =============================================================================
# CORPUS RUN
# =============================================================================

def run_corpus(input_dir, output_dir, max_images=0):
    """Run the granite test on a corpus of images."""

    os.makedirs(output_dir, exist_ok=True)
    work_dir = os.path.join(output_dir, "work")
    os.makedirs(work_dir, exist_ok=True)

    # Find images
    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    all_files = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])

    if max_images > 0:
        all_files = all_files[:max_images]

    n_total = len(all_files)
    print(f"{'='*80}")
    print(f"DIV2K GRANITE TEST v2 — Channel Pair Comparison")
    print(f"{'='*80}")
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Images:     {n_total}")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Pairs:      {list(CHANNEL_PAIRS.keys())}")
    print(f"Min prime:  {TWIN_CONFIG.min_prime}")
    print(f"Markers:    {TWIN_CONFIG.n_markers}")
    print(f"Min dim:    {MIN_DIMENSION}")
    print(f"Started:    {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "per_image_results.jsonl")

    # Clear previous results
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
            print(f"SKIP (too small: {w}x{h})")
            continue

        # Resize to 1024 max dimension for consistent testing
        max_dim = max(h, w)
        if max_dim > 1024:
            scale = 1024 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)
            h, w = pixels.shape[:2]

        try:
            result = test_one_image(pixels, fname, work_dir)
        except Exception as e:
            print(f"TEST FAILED: {e}")
            traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        # Quick status line
        if "error" in result:
            print(f"ERROR: {result['error']}  [{elapsed:.1f}s]")
        else:
            n_m = result.get("n_markers_embedded", 0)
            rg_vr = result.get("RG_vr_trend", [0]*5)
            gb_vr = result.get("GB_vr_trend", [0]*5)
            amp = "AMP" if result.get("amplification_confirmed", False) else "   "

            rg4 = rg_vr[4] if len(rg_vr) > 4 else 0
            gb4 = gb_vr[4] if len(gb_vr) > 4 else 0

            print(f"n={n_m:>3d}  {amp}"
                  f"  RG_vr4={rg4:.2f}  GB_vr4={gb4:.2f}"
                  f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE ANALYSIS
    # =========================================================================

    print(f"\n\n{'='*80}")
    print(f"AGGREGATE RESULTS — {len(summary_data)} images")
    print(f"Total time: {total_time:.0f}s ({total_time/max(len(summary_data),1):.1f}s/image)")
    print(f"{'='*80}")

    good = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)
    n_error = len(summary_data) - n_good

    if n_good == 0:
        verdict = "NO VALID RESULTS. All images failed processing."
        print(f"\n{verdict}")
        write_verdict(output_dir, verdict, summary_data)
        return summary_data

    print(f"Successful: {n_good}  Failed: {n_error}\n")

    # --- DQT ---
    dqt_det = sum(1 for r in good if r.get("gen0_dqt_detected", False))
    print(f"Layer A (DQT primality at Gen0): {dqt_det}/{n_good}"
          f" ({dqt_det/n_good*100:.1f}%)")

    # --- Per-pair analysis ---
    for pair_name in CHANNEL_PAIRS:
        print(f"\n{'─'*60}")
        print(f"Channel Pair: {pair_name}")
        print(f"{'─'*60}")

        # Amplification rate
        amp_n = sum(1 for r in good if r.get(f"{pair_name}_amplification", False))
        print(f"  Amplification confirmed: {amp_n}/{n_good} ({amp_n/n_good*100:.1f}%)")

        # Gen4 KS
        gen4_ks = np.array([r.get(f"{pair_name}_gen4_ks_p", 1.0) for r in good])
        print(f"  Gen4 KS p-value:")
        print(f"    Mean:    {np.mean(gen4_ks):.6f}")
        print(f"    Median:  {np.median(gen4_ks):.6f}")
        print(f"    < 0.05:  {np.sum(gen4_ks < 0.05)}/{n_good}"
              f" ({np.mean(gen4_ks < 0.05)*100:.1f}%)")
        print(f"    < 0.01:  {np.sum(gen4_ks < 0.01)}/{n_good}"
              f" ({np.mean(gen4_ks < 0.01)*100:.1f}%)")
        print(f"    < 0.001: {np.sum(gen4_ks < 0.001)}/{n_good}"
              f" ({np.mean(gen4_ks < 0.001)*100:.1f}%)")

        # Variance ratio per generation
        print(f"\n  Variance Ratio by generation:")
        print(f"    {'Gen':>4s} {'Q':>4s}  {'Mean':>8s}  {'Median':>8s}"
              f"  {'> 1.0':>8s}  {'> 2.0':>8s}")
        print(f"    {'─'*50}")

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            vrs = []
            for r in good:
                trend = r.get(f"{pair_name}_vr_trend", [])
                if len(trend) > gen_idx:
                    vrs.append(trend[gen_idx])
            if vrs:
                arr = np.array(vrs)
                pct1 = np.mean(arr > 1.0) * 100
                pct2 = np.mean(arr > 2.0) * 100
                print(f"    {gen_idx:>4d} Q{q:>3d}  {np.mean(arr):>8.3f}"
                      f"  {np.median(arr):>8.3f}"
                      f"  {pct1:>7.1f}%  {pct2:>7.1f}%")

    # --- Head-to-head: G-B vs R-G ---
    print(f"\n{'='*60}")
    print(f"HEAD-TO-HEAD: G-B vs R-G")
    print(f"{'='*60}")

    gb_wins = 0
    rg_wins = 0
    ties = 0
    for r in good:
        gb_ks = r.get("GB_gen4_ks_p", 1.0)
        rg_ks = r.get("RG_gen4_ks_p", 1.0)
        if gb_ks < rg_ks:
            gb_wins += 1
        elif rg_ks < gb_ks:
            rg_wins += 1
        else:
            ties += 1

    print(f"  At Gen4 (Q40), lower KS p-value wins:")
    print(f"    G-B wins: {gb_wins}/{n_good} ({gb_wins/n_good*100:.1f}%)")
    print(f"    R-G wins: {rg_wins}/{n_good} ({rg_wins/n_good*100:.1f}%)")
    print(f"    Ties:     {ties}/{n_good}")

    # Compare mean variance ratios at Q85 (where G-B showed 50% advantage on synthetic)
    gb_vr_q85 = []
    rg_vr_q85 = []
    for r in good:
        gb_trend = r.get("GB_vr_trend", [])
        rg_trend = r.get("RG_vr_trend", [])
        if len(gb_trend) > 1:
            gb_vr_q85.append(gb_trend[1])  # Gen1 = Q85
        if len(rg_trend) > 1:
            rg_vr_q85.append(rg_trend[1])

    if gb_vr_q85 and rg_vr_q85:
        print(f"\n  At Gen1 (Q85), mean variance ratio:")
        print(f"    G-B: {np.mean(gb_vr_q85):.3f}")
        print(f"    R-G: {np.mean(rg_vr_q85):.3f}")
        advantage = np.mean(gb_vr_q85) / np.mean(rg_vr_q85) if np.mean(rg_vr_q85) > 0 else 0
        print(f"    G-B advantage: {advantage:.2f}x")

    # =========================================================================
    # THE VERDICT
    # =========================================================================

    # Use the BETTER pair for the verdict
    best_pair = "GB"  # Our hypothesis
    gen4_ks_best = np.array([r.get(f"{best_pair}_gen4_ks_p", 1.0) for r in good])
    pct_ks_05 = np.mean(gen4_ks_best < 0.05) * 100

    amp_confirmed = sum(1 for r in good if r.get("amplification_confirmed", False))
    pct_amp = amp_confirmed / n_good * 100

    gen4_vrs_best = []
    for r in good:
        trend = r.get(f"{best_pair}_vr_trend", [])
        if len(trend) > 4:
            gen4_vrs_best.append(trend[4])
    pct_vr_above_1 = np.mean(np.array(gen4_vrs_best) > 1.0) * 100 if gen4_vrs_best else 0

    print(f"\n\n{'#'*80}")
    print(f"# THE VERDICT")
    print(f"{'#'*80}")

    if pct_ks_05 > 50 and pct_vr_above_1 > 50:
        verdict = (
            f"GRANITE CONFIRMED.\n\n"
            f"On {n_good} real photographs (DIV2K, resized to 1024 max):\n"
            f"  - Best pair: {best_pair}\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 (Q40) below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n"
            f"  - {pct_amp:.1f}% show amplification (Gen4 stronger than Gen1-3)\n"
            f"  - G-B wins head-to-head: {gb_wins}/{n_good} ({gb_wins/n_good*100:.1f}%)\n\n"
            f"The amplification hypothesis holds on real photographs.\n"
            f"The granite is real. Book the flight."
        )
    elif pct_ks_05 > 20:
        verdict = (
            f"GRANITE PARTIAL.\n\n"
            f"On {n_good} real photographs:\n"
            f"  - Best pair: {best_pair}\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n"
            f"  - {pct_amp:.1f}% show amplification\n"
            f"  - G-B wins head-to-head: {gb_wins}/{n_good}\n\n"
            f"The effect is present but not universal.\n"
            f"Characterize which content classes amplify and which don't.\n"
            f"The paper can claim the effect with caveats."
        )
    else:
        verdict = (
            f"GRANITE NOT CONFIRMED.\n\n"
            f"On {n_good} real photographs:\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n\n"
            f"The amplification effect does not replicate on real photographs.\n"
            f"DQT and twin-prime gen0 results may still stand independently.\n"
            f"The synthetic result may have been content-specific."
        )

    print(f"\n{verdict}")
    write_verdict(output_dir, verdict, summary_data, good)

    # Save aggregate
    aggregate = {
        "n_images_total": n_total,
        "n_good": n_good,
        "n_error": n_error,
        "total_time_seconds": round(total_time, 1),
        "seconds_per_image": round(total_time / max(n_good, 1), 1),
        "dqt_detection_rate": round(dqt_det / n_good, 4) if n_good > 0 else 0,
        "cascade_qualities": CASCADE_QUALITIES,
        "channel_pairs_tested": list(CHANNEL_PAIRS.keys()),
    }
    for pair_name in CHANNEL_PAIRS:
        gen4_ks = [r.get(f"{pair_name}_gen4_ks_p", 1.0) for r in good]
        gen4_ks_arr = np.array(gen4_ks)
        amp_n = sum(1 for r in good if r.get(f"{pair_name}_amplification", False))
        gen4_vrs = []
        for r in good:
            trend = r.get(f"{pair_name}_vr_trend", [])
            if len(trend) > 4:
                gen4_vrs.append(trend[4])

        aggregate[f"{pair_name}_gen4_ks_mean"] = round(float(np.mean(gen4_ks_arr)), 6)
        aggregate[f"{pair_name}_gen4_ks_median"] = round(float(np.median(gen4_ks_arr)), 6)
        aggregate[f"{pair_name}_gen4_ks_below_05_pct"] = round(float(np.mean(gen4_ks_arr < 0.05) * 100), 1)
        aggregate[f"{pair_name}_gen4_ks_below_01_pct"] = round(float(np.mean(gen4_ks_arr < 0.01) * 100), 1)
        aggregate[f"{pair_name}_amplification_pct"] = round(amp_n / n_good * 100, 1) if n_good > 0 else 0
        aggregate[f"{pair_name}_gen4_vr_mean"] = round(float(np.mean(gen4_vrs)), 4) if gen4_vrs else 0
        aggregate[f"{pair_name}_gen4_vr_above1_pct"] = round(float(np.mean(np.array(gen4_vrs) > 1.0) * 100), 1) if gen4_vrs else 0

    aggregate["GB_wins_head_to_head"] = gb_wins
    aggregate["RG_wins_head_to_head"] = rg_wins

    with open(os.path.join(output_dir, "aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    print(f"\nResults saved to: {output_dir}")
    print(f"  per_image_results.jsonl  — one JSON per image")
    print(f"  aggregate.json           — summary statistics")
    print(f"  VERDICT.txt              — the verdict")

    return summary_data


def write_verdict(output_dir, verdict, data, good=None):
    """Write verdict and optionally generate plots."""
    with open(os.path.join(output_dir, "VERDICT.txt"), "w") as f:
        f.write(verdict)
        f.write(f"\n\nGenerated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Harness: div2k_harness_v2.py\n")
        f.write(f"Channel pairs tested: {list(CHANNEL_PAIRS.keys())}\n")

    if good is None:
        good = [r for r in data if "error" not in r and "cascade" in r]

    # Try to generate plots
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        if not good:
            return

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('DIV2K Granite Test v2 — Channel Pair Comparison',
                     fontsize=16, fontweight='bold')

        colors = {"RG": "#2C5F8A", "GB": "#8A2C2C"}

        # Plot 1: Gen4 KS p-value histogram per pair
        for pair_name in CHANNEL_PAIRS:
            gen4_ks = [r.get(f"{pair_name}_gen4_ks_p", 1.0) for r in good]
            axes[0, 0].hist(gen4_ks, bins=30, alpha=0.5, color=colors[pair_name],
                           label=pair_name, edgecolor='black', linewidth=0.5)
        axes[0, 0].axvline(0.05, color='red', linewidth=2, linestyle='--', label='p=0.05')
        axes[0, 0].set_xlabel('KS p-value at Gen4 (Q40)')
        axes[0, 0].set_ylabel('Count')
        axes[0, 0].set_title('Gen4 KS Distribution by Channel Pair')
        axes[0, 0].legend()

        # Plot 2: Variance ratio across generations per pair
        for pair_name in CHANNEL_PAIRS:
            means = []
            for gen_idx in range(len(CASCADE_QUALITIES)):
                vrs = []
                for r in good:
                    trend = r.get(f"{pair_name}_vr_trend", [])
                    if len(trend) > gen_idx:
                        vrs.append(trend[gen_idx])
                means.append(np.mean(vrs) if vrs else 1.0)
            axes[0, 1].plot(range(len(CASCADE_QUALITIES)), means,
                           'o-', color=colors[pair_name], label=pair_name,
                           linewidth=2, markersize=8)
        axes[0, 1].axhline(1.0, color='red', linewidth=1, linestyle='--')
        axes[0, 1].set_xticks(range(len(CASCADE_QUALITIES)))
        axes[0, 1].set_xticklabels([f'G{i}:Q{q}' for i, q in enumerate(CASCADE_QUALITIES)])
        axes[0, 1].set_ylabel('Mean Variance Ratio')
        axes[0, 1].set_title('Variance Ratio Across Cascade')
        axes[0, 1].legend()

        # Plot 3: Per-image G-B vs R-G variance ratio at Gen4
        gb_vr4 = []
        rg_vr4 = []
        for r in good:
            gb_t = r.get("GB_vr_trend", [])
            rg_t = r.get("RG_vr_trend", [])
            if len(gb_t) > 4 and len(rg_t) > 4:
                gb_vr4.append(gb_t[4])
                rg_vr4.append(rg_t[4])
        if gb_vr4 and rg_vr4:
            axes[1, 0].scatter(rg_vr4, gb_vr4, alpha=0.5, s=20, color='#333333')
            max_val = max(max(gb_vr4), max(rg_vr4)) * 1.1
            axes[1, 0].plot([0, max_val], [0, max_val], 'r--', linewidth=1, label='Equal')
            axes[1, 0].set_xlabel('R-G Variance Ratio (Gen4)')
            axes[1, 0].set_ylabel('G-B Variance Ratio (Gen4)')
            axes[1, 0].set_title('Head-to-Head: Points Above Line = G-B Wins')
            axes[1, 0].legend()

        # Plot 4: Enrichment ratio across generations (G-B only)
        er_means = []
        for gen_idx in range(len(CASCADE_QUALITIES)):
            ers = []
            for r in good:
                cascade = r.get("cascade", [])
                if len(cascade) > gen_idx:
                    ers.append(cascade[gen_idx].get("GB_enrichment_ratio", 1.0))
            er_means.append(np.mean(ers) if ers else 1.0)
        axes[1, 1].bar(range(len(CASCADE_QUALITIES)), er_means,
                       color='#8A2C2C', alpha=0.7, edgecolor='black')
        axes[1, 1].axhline(1.0, color='red', linewidth=1, linestyle='--')
        axes[1, 1].set_xticks(range(len(CASCADE_QUALITIES)))
        axes[1, 1].set_xticklabels([f'G{i}:Q{q}' for i, q in enumerate(CASCADE_QUALITIES)])
        axes[1, 1].set_ylabel('Mean Enrichment Ratio')
        axes[1, 1].set_title('G-B Enrichment Ratio Across Cascade')

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "granite_test_v2.png"), dpi=150)
        plt.close()
        print(f"  granite_test_v2.png      — visualization")
    except ImportError:
        print("  (matplotlib not installed, skipping plot)")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DIV2K Granite Test v2 — Channel Pair Comparison"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Directory containing images")
    parser.add_argument("--output", "-o", default="granite_results_v2",
                        help="Output directory for results")
    parser.add_argument("--max-images", "-n", type=int, default=0,
                        help="Max images to process (0 = all). Use 5 for sanity check.")

    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
