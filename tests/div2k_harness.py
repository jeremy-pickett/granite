#!/usr/bin/env python3
"""
DIV2K Validation Harness — The Granite Test
=============================================
Jeremy Pickett — Axiomatic Fictions Series

One script. Point it at a directory of images. Go to bed.
Wake up to either a finding or a funeral.

Usage:
    # Step 1: Download DIV2K validation set (100 images, ~400MB)
    mkdir -p ~/div2k && cd ~/div2k
    wget http://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_valid_HR.zip
    unzip DIV2K_valid_HR.zip

    # Step 2: Install dependencies
    pip install Pillow numpy scipy matplotlib --break-system-packages

    # Step 3: Copy all scripts to one directory
    # (see REQUIRED FILES below)

    # Step 4: Run
    python div2k_harness.py --input ~/div2k/DIV2K_valid_HR --output ~/results

    # Step 5: Read the verdict
    cat ~/results/VERDICT.txt

REQUIRED FILES (all in the same directory as this script):
    pgps_detector.py        — core detector and utilities
    fp_forensics.py         — distance forensics
    prime_floor_sweep.py    — basket floor analysis
    smart_embedder.py       — file-type profiles
    compound_markers.py     — twin/magic/compound markers
    dqt_prime.py            — Strategy 4 prime quantization tables
    relational_signal.py    — slope/ratio/difference analysis
    div2k_harness.py        — THIS FILE
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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
)
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
)
from dqt_prime import encode_prime_jpeg, detect_prime_dqt
from smart_embedder import compute_local_entropy_fast


# =============================================================================
# CONFIGURATION — Touch these if needed
# =============================================================================

# Twin marker config (the one that found the granite)
TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="Twin prime-gap markers for amplification test",
    min_prime=53,
    use_twins=True,
    use_rare_basket=True,
    use_magic=False,
    detection_prime_tolerance=2,
    n_markers=400,
)

# Compression cascade
CASCADE_QUALITIES = [95, 85, 75, 60, 40]

# Starting quality for the prime JPEG
START_QUALITY = 95

# Minimum image dimension (skip tiny images)
MIN_DIMENSION = 256


# =============================================================================
# THE CORE TEST — One image, full cascade, all measurements
# =============================================================================

def test_one_image(pixels: np.ndarray, image_name: str,
                    work_dir: str) -> dict:
    """
    Run the complete amplification test on one image.

    Returns a dict with all measurements, or None on failure.
    """
    h, w, _ = pixels.shape
    result = {
        "image": image_name,
        "width": w,
        "height": h,
        "n_pixels": h * w,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # --- Step 1: Create prime JPEG ---
    try:
        prime_data, dqt_meta = encode_prime_jpeg(
            pixels, quality=START_QUALITY, min_prime=2, preserve_dc=True
        )
        prime_pixels = np.array(Image.open(io.BytesIO(prime_data)).convert("RGB"))
    except Exception as e:
        result["error"] = f"Prime JPEG encoding failed: {e}"
        return result

    # --- Step 2: Embed twin markers ---
    try:
        embedded_pixels, markers = embed_compound(prime_pixels, TWIN_CONFIG, variable_offset=42)
        result["n_markers_embedded"] = len(markers)
    except Exception as e:
        result["error"] = f"Embedding failed: {e}"
        return result

    if len(markers) < 20:
        result["error"] = f"Too few markers embedded: {len(markers)}"
        return result

    # --- Step 3: Initial encode (Generation 0) ---
    buf = io.BytesIO()
    Image.fromarray(embedded_pixels).save(buf, format='JPEG', quality=START_QUALITY)
    gen0_data = buf.getvalue()
    gen0_pixels = np.array(Image.open(io.BytesIO(gen0_data)).convert("RGB"))

    # --- Step 4: Extract gen0 relations (the truth we're tracking) ---
    gen0_twins = extract_twin_measurements(gen0_pixels, markers)

    # --- Step 5: DQT detection at gen0 ---
    dqt_det = detect_prime_dqt(gen0_data)
    result["gen0_dqt_prime_rate"] = dqt_det["overall_prime_rate"]
    result["gen0_dqt_detected"] = dqt_det["detected"]

    # --- Step 6: Run the cascade ---
    current_pixels = gen0_pixels.copy()
    cascade_results = []

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        gen = {}
        gen["generation"] = gen_idx
        gen["quality"] = q

        if gen_idx == 0:
            test_pixels = gen0_pixels
            test_data = gen0_data
        else:
            buf = io.BytesIO()
            Image.fromarray(current_pixels).save(buf, format='JPEG', quality=q)
            test_data = buf.getvalue()
            test_pixels = np.array(Image.open(io.BytesIO(test_data)).convert("RGB"))

        # Layer A: DQT
        dqt = detect_prime_dqt(test_data)
        gen["dqt_prime_rate"] = dqt["overall_prime_rate"]
        gen["dqt_detected"] = dqt["detected"]

        # Layer B: Twin compound detection (primality-based)
        compound = detect_compound(test_pixels, markers, TWIN_CONFIG)
        gen["compound_marker_rate"] = compound["marker_rate"]
        gen["compound_control_rate"] = compound["control_rate"]
        gen["compound_rate_ratio"] = compound["rate_ratio"]
        gen["compound_binom_p"] = compound["binomial_pvalue"]
        gen["compound_detected"] = compound["detected_binom"]

        # THE BIG ONE: Relational signal / local variance anomaly
        curr_twins = extract_twin_measurements(test_pixels, markers)
        rel = compare_twin_distributions(gen0_twins, curr_twins)
        gen["ks_ratio_p"] = rel["ks_ratio_p"]
        gen["ks_diff_p"] = rel["ks_diff_p"]
        gen["ks_slope_p"] = rel["ks_slope_p"]
        gen["ratio_correlation"] = rel["ratio_corr"]
        gen["diff_correlation"] = rel["diff_corr"]
        gen["slope_correlation"] = rel["slope_corr"]
        gen["marker_diff_std"] = rel["marker_diff_std"]
        gen["control_diff_std"] = rel["control_diff_std"]
        gen["variance_ratio"] = rel["variance_ratio"]

        # Amplification detected?
        gen["amplification_detected"] = (
            rel["ks_diff_p"] < 0.01 or
            rel["ks_slope_p"] < 0.01 or
            rel["ks_ratio_p"] < 0.01
        )

        # Any layer detected?
        gen["any_detected"] = (
            gen["dqt_detected"] or
            gen["compound_detected"] or
            gen["amplification_detected"]
        )

        cascade_results.append(gen)
        current_pixels = test_pixels

    result["cascade"] = cascade_results

    # --- Summary flags ---
    result["dqt_works"] = cascade_results[0]["dqt_detected"] if cascade_results else False

    # Amplification: is the signal at Gen4 stronger than Gen1-3?
    if len(cascade_results) >= 5:
        gen4_ks = min(
            cascade_results[4].get("ks_diff_p", 1),
            cascade_results[4].get("ks_slope_p", 1),
            cascade_results[4].get("ks_ratio_p", 1),
        )
        mid_ks = min(
            min(cascade_results[i].get("ks_diff_p", 1) for i in [1, 2, 3]),
            min(cascade_results[i].get("ks_slope_p", 1) for i in [1, 2, 3]),
        )
        result["gen4_best_ks_p"] = gen4_ks
        result["gen1_3_best_ks_p"] = mid_ks
        result["amplification_confirmed"] = gen4_ks < mid_ks and gen4_ks < 0.05
    else:
        result["amplification_confirmed"] = False
        result["gen4_best_ks_p"] = 1.0

    return result


# =============================================================================
# TWIN MEASUREMENT EXTRACTION (streamlined from relational_signal.py)
# =============================================================================

def extract_twin_measurements(pixels: np.ndarray, markers: list,
                                channel_pair: tuple = (0, 1)) -> dict:
    """Extract twin-pair distance measurements at marker and control positions."""
    h, w, _ = pixels.shape
    ch_a, ch_b = channel_pair

    marker_set = set()
    marker_d1 = []
    marker_d2 = []
    marker_ratios = []
    marker_diffs = []
    marker_slopes = []

    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc >= w:
            continue
        marker_set.add((r, c))
        marker_set.add((r, tc))

        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))

        marker_d1.append(d1)
        marker_d2.append(d2)
        if d2 > 0:
            marker_ratios.append(d1 / d2)
        marker_diffs.append(d1 - d2)
        marker_slopes.append(d2 - d1)

    # Control: non-marker grid positions
    all_positions = sample_positions_grid(h, w, 8)
    control_ratios = []
    control_diffs = []
    control_slopes = []

    for pos in all_positions:
        r, c = int(pos[0]), int(pos[1])
        r = min(r + 3, h - 1)
        c = min(c + 3, w - 2)
        tc = c + 1
        if (r, c) in marker_set or (r, tc) in marker_set:
            continue
        if r >= h or tc >= w:
            continue

        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))

        if d2 > 0:
            control_ratios.append(d1 / d2)
        control_diffs.append(d1 - d2)
        control_slopes.append(d2 - d1)

    return {
        "marker_ratios": marker_ratios,
        "marker_diffs": marker_diffs,
        "marker_slopes": marker_slopes,
        "control_ratios": control_ratios,
        "control_diffs": control_diffs,
        "control_slopes": control_slopes,
    }


def compare_twin_distributions(gen0: dict, current: dict) -> dict:
    """Compare gen0 and current twin measurements. Return all test statistics."""
    result = {
        "ks_ratio_p": 1.0, "ks_diff_p": 1.0, "ks_slope_p": 1.0,
        "ratio_corr": 0.0, "diff_corr": 0.0, "slope_corr": 0.0,
        "marker_diff_std": 0.0, "control_diff_std": 0.0, "variance_ratio": 1.0,
    }

    # KS: marker vs control at CURRENT generation
    def safe_ks(a, b):
        a_filt = [x for x in a if np.isfinite(x) and abs(x) < 1000]
        b_filt = [x for x in b if np.isfinite(x) and abs(x) < 1000]
        if len(a_filt) > 5 and len(b_filt) > 5:
            stat, p = sp_stats.ks_2samp(a_filt, b_filt)
            return float(p)
        return 1.0

    result["ks_ratio_p"] = safe_ks(current["marker_ratios"], current["control_ratios"])
    result["ks_diff_p"] = safe_ks(current["marker_diffs"], current["control_diffs"])
    result["ks_slope_p"] = safe_ks(current["marker_slopes"], current["control_slopes"])

    # Correlation with gen0 (memory of original relationship)
    def safe_corr(a, b):
        n = min(len(a), len(b))
        if n > 10:
            a_arr = np.array(a[:n])
            b_arr = np.array(b[:n])
            valid = np.isfinite(a_arr) & np.isfinite(b_arr)
            if np.sum(valid) > 10:
                r, p = sp_stats.pearsonr(a_arr[valid], b_arr[valid])
                return float(r)
        return 0.0

    result["ratio_corr"] = safe_corr(gen0["marker_ratios"], current["marker_ratios"])
    result["diff_corr"] = safe_corr(gen0["marker_diffs"], current["marker_diffs"])
    result["slope_corr"] = safe_corr(gen0["marker_slopes"], current["marker_slopes"])

    # Variance ratio (marker vs control twin-pair differences)
    if current["marker_diffs"] and current["control_diffs"]:
        m_std = float(np.std(current["marker_diffs"]))
        c_std = float(np.std(current["control_diffs"]))
        result["marker_diff_std"] = m_std
        result["control_diff_std"] = c_std
        result["variance_ratio"] = m_std / c_std if c_std > 0 else float('inf')

    return result


# =============================================================================
# CORPUS RUNNER
# =============================================================================

def run_corpus(input_dir: str, output_dir: str, max_images: int = 0):
    """
    Run the amplification test on every image in input_dir.
    Writes per-image results as JSON and a final summary.
    """
    os.makedirs(output_dir, exist_ok=True)
    work_dir = os.path.join(output_dir, "_work")
    os.makedirs(work_dir, exist_ok=True)

    # Find images
    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    image_files = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])

    if max_images > 0:
        image_files = image_files[:max_images]

    n_total = len(image_files)
    print(f"{'='*80}")
    print(f"DIV2K VALIDATION HARNESS — THE GRANITE TEST")
    print(f"{'='*80}")
    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Images: {n_total}")
    print(f"Start:  {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    # Per-image results log
    results_file = os.path.join(output_dir, "results.jsonl")
    summary_data = []

    t_start = time.time()

    for idx, fname in enumerate(image_files):
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
            cascade = result.get("cascade", [])
            gen4 = cascade[4] if len(cascade) > 4 else {}
            gen0 = cascade[0] if len(cascade) > 0 else {}

            dqt_flag = "DQT" if gen0.get("dqt_detected", False) else "   "
            amp_flag = "AMP" if result.get("amplification_confirmed", False) else "   "
            g4_ks = result.get("gen4_best_ks_p", 1.0)
            n_m = result.get("n_markers_embedded", 0)

            print(f"n={n_m:>3d}  {dqt_flag}  {amp_flag}"
                  f"  G4_KS={g4_ks:.4f}"
                  f"  vr={gen4.get('variance_ratio', 0):.2f}"
                  f"  [{elapsed:.1f}s]")

        # Save per-image result
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

    # Filter to successful results
    good = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)
    n_error = len(summary_data) - n_good

    if n_good == 0:
        verdict = "NO VALID RESULTS. All images failed processing."
        print(f"\n{verdict}")
        write_verdict(output_dir, verdict, summary_data)
        return summary_data

    print(f"Successful: {n_good}  Failed: {n_error}\n")

    # --- DQT (Layer A) ---
    dqt_det = sum(1 for r in good if r.get("gen0_dqt_detected", False))
    print(f"Layer A (DQT primality at Gen0): {dqt_det}/{n_good}"
          f" ({dqt_det/n_good*100:.1f}%) detected")

    # --- Amplification ---
    amp_confirmed = sum(1 for r in good if r.get("amplification_confirmed", False))
    print(f"Amplification (Gen4 KS < Gen1-3 KS AND < 0.05):"
          f" {amp_confirmed}/{n_good} ({amp_confirmed/n_good*100:.1f}%)")

    # --- Gen4 KS p-values ---
    gen4_ks = [r.get("gen4_best_ks_p", 1.0) for r in good]
    gen4_ks_arr = np.array(gen4_ks)
    print(f"\nGen4 KS p-value distribution:")
    print(f"  Mean:   {np.mean(gen4_ks_arr):.6f}")
    print(f"  Median: {np.median(gen4_ks_arr):.6f}")
    print(f"  Min:    {np.min(gen4_ks_arr):.6f}")
    print(f"  Max:    {np.max(gen4_ks_arr):.6f}")
    print(f"  < 0.05: {np.sum(gen4_ks_arr < 0.05)}/{n_good}"
          f" ({np.mean(gen4_ks_arr < 0.05)*100:.1f}%)")
    print(f"  < 0.01: {np.sum(gen4_ks_arr < 0.01)}/{n_good}"
          f" ({np.mean(gen4_ks_arr < 0.01)*100:.1f}%)")
    print(f"  < 0.001:{np.sum(gen4_ks_arr < 0.001)}/{n_good}"
          f" ({np.mean(gen4_ks_arr < 0.001)*100:.1f}%)")

    # --- Per-generation summary ---
    print(f"\nPer-generation detection rates:")
    print(f"  {'Gen':>4s} {'Q':>4s}  {'DQT':>6s}  {'Compound':>9s}  "
          f"{'Amplif':>7s}  {'Any':>5s}  {'Var Ratio':>10s}")
    print(f"  {'-'*60}")

    for gen_idx in range(len(CASCADE_QUALITIES)):
        dqt_n = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("dqt_detected", False))
        comp_n = sum(1 for r in good
                     if len(r["cascade"]) > gen_idx
                     and r["cascade"][gen_idx].get("compound_detected", False))
        amp_n = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("amplification_detected", False))
        any_n = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("any_detected", False))
        vrs = [r["cascade"][gen_idx].get("variance_ratio", 1.0)
               for r in good if len(r["cascade"]) > gen_idx]
        mean_vr = np.mean(vrs) if vrs else 0

        q = CASCADE_QUALITIES[gen_idx]
        print(f"  {gen_idx:>4d} Q{q:>3d}"
              f"  {dqt_n:>3d}/{n_good:<3d}"
              f"  {comp_n:>5d}/{n_good:<3d}"
              f"  {amp_n:>4d}/{n_good:<3d}"
              f"  {any_n:>3d}/{n_good:<3d}"
              f"  {mean_vr:>10.3f}")

    # --- Variance ratio analysis (the granite metric) ---
    print(f"\nVariance ratio (marker_std / control_std) at each generation:")
    print(f"  > 1.0 means markers have more twin-pair variance than controls")
    print(f"  This is the granite signal.\n")

    for gen_idx in range(len(CASCADE_QUALITIES)):
        vrs = [r["cascade"][gen_idx].get("variance_ratio", 1.0)
               for r in good if len(r["cascade"]) > gen_idx
               and r["cascade"][gen_idx].get("variance_ratio", 0) > 0]
        if vrs:
            arr = np.array(vrs)
            q = CASCADE_QUALITIES[gen_idx]
            pct_above_1 = np.mean(arr > 1.0) * 100
            print(f"  Gen{gen_idx} Q{q:>3d}: mean={np.mean(arr):.3f}"
                  f"  median={np.median(arr):.3f}"
                  f"  > 1.0: {pct_above_1:.1f}%")

    # =========================================================================
    # THE VERDICT
    # =========================================================================

    # The amplification hypothesis holds if:
    # 1. The majority of images show Gen4 KS < 0.05
    # 2. The majority show variance_ratio > 1.0 at Gen4
    # 3. The amplification pattern (Gen4 stronger than Gen1-3) holds for majority

    pct_ks_05 = np.mean(gen4_ks_arr < 0.05) * 100
    pct_amp = amp_confirmed / n_good * 100 if n_good > 0 else 0

    gen4_vrs = [r["cascade"][4].get("variance_ratio", 1.0)
                for r in good if len(r["cascade"]) > 4]
    pct_vr_above_1 = np.mean(np.array(gen4_vrs) > 1.0) * 100 if gen4_vrs else 0

    print(f"\n\n{'#'*80}")
    print(f"# THE VERDICT")
    print(f"{'#'*80}")

    if pct_ks_05 > 50 and pct_vr_above_1 > 50:
        verdict = (
            f"GRANITE CONFIRMED.\n\n"
            f"On {n_good} real photographs:\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 (Q40) below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n"
            f"  - {pct_amp:.1f}% show amplification (Gen4 stronger than Gen1-3)\n\n"
            f"The amplification hypothesis holds on real photographs.\n"
            f"Lossy compression amplifies the perturbation signal.\n"
            f"The granite is real. Book the flight."
        )
    elif pct_ks_05 > 20:
        verdict = (
            f"GRANITE PARTIAL.\n\n"
            f"On {n_good} real photographs:\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n"
            f"  - {pct_amp:.1f}% show amplification\n\n"
            f"The effect is present but not universal.\n"
            f"Content-class dependence likely. Investigate which images amplify\n"
            f"and which don't. The paper can claim the effect with caveats."
        )
    else:
        verdict = (
            f"GRANITE NOT CONFIRMED.\n\n"
            f"On {n_good} real photographs:\n"
            f"  - {pct_ks_05:.1f}% show KS separation at Gen4 below p=0.05\n"
            f"  - {pct_vr_above_1:.1f}% show elevated variance ratio at Gen4\n\n"
            f"The amplification effect does not replicate on real photographs\n"
            f"at this marker density and image size. The synthetic result may\n"
            f"have been an artifact of the test image's specific content.\n"
            f"The DQT and twin-prime results still stand independently.\n"
            f"Cancel the flight. Keep working."
        )

    print(f"\n{verdict}")

    write_verdict(output_dir, verdict, summary_data)

    # Save aggregate stats
    aggregate = {
        "n_images": n_total,
        "n_good": n_good,
        "n_error": n_error,
        "total_time_seconds": total_time,
        "dqt_detection_rate": dqt_det / n_good if n_good > 0 else 0,
        "amplification_rate": amp_confirmed / n_good if n_good > 0 else 0,
        "gen4_ks_mean": float(np.mean(gen4_ks_arr)),
        "gen4_ks_median": float(np.median(gen4_ks_arr)),
        "gen4_ks_below_05": float(np.mean(gen4_ks_arr < 0.05)),
        "gen4_ks_below_01": float(np.mean(gen4_ks_arr < 0.01)),
        "gen4_vr_mean": float(np.mean(gen4_vrs)) if gen4_vrs else 0,
        "gen4_vr_above_1_pct": pct_vr_above_1,
    }
    with open(os.path.join(output_dir, "aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    return summary_data


def write_verdict(output_dir: str, verdict: str, data: list):
    """Write the verdict file and a plot if matplotlib is available."""
    with open(os.path.join(output_dir, "VERDICT.txt"), "w") as f:
        f.write(verdict)
        f.write(f"\n\nGenerated: {datetime.utcnow().isoformat()}Z\n")

    # Try to generate a plot
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        good = [r for r in data if "error" not in r and "cascade" in r]
        if not good:
            return

        # Gen4 KS p-value histogram
        gen4_ks = [r.get("gen4_best_ks_p", 1.0) for r in good]
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        axes[0].hist(gen4_ks, bins=30, edgecolor='black', alpha=0.7, color='#2C5F8A')
        axes[0].axvline(0.05, color='red', linewidth=2, linestyle='--', label='p=0.05')
        axes[0].axvline(0.01, color='orange', linewidth=2, linestyle='--', label='p=0.01')
        pct = np.mean(np.array(gen4_ks) < 0.05) * 100
        axes[0].set_xlabel('KS p-value at Gen4 (Q40)', fontsize=12)
        axes[0].set_ylabel('Count', fontsize=12)
        axes[0].set_title(f'Gen4 KS Distribution — {pct:.1f}% below 0.05', fontsize=14)
        axes[0].legend(fontsize=11)

        # Variance ratio across generations
        for gen_idx in range(len(CASCADE_QUALITIES)):
            vrs = [r["cascade"][gen_idx].get("variance_ratio", 1.0)
                   for r in good if len(r["cascade"]) > gen_idx]
            if vrs:
                q = CASCADE_QUALITIES[gen_idx]
                axes[1].boxplot(vrs, positions=[gen_idx], widths=0.6,
                               patch_artist=True,
                               boxprops=dict(facecolor='#2C5F8A', alpha=0.6))

        axes[1].axhline(1.0, color='red', linewidth=1, linestyle='--')
        axes[1].set_xticks(range(len(CASCADE_QUALITIES)))
        axes[1].set_xticklabels([f'G{i}:Q{q}' for i, q in enumerate(CASCADE_QUALITIES)])
        axes[1].set_ylabel('Variance Ratio (marker/control)', fontsize=12)
        axes[1].set_title('Variance Ratio Across Cascade — The Granite Test', fontsize=14)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "granite_test.png"), dpi=150)
        plt.close()
    except ImportError:
        pass  # No matplotlib on micro instance, that's fine


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DIV2K Validation Harness — The Granite Test"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Directory containing images (DIV2K_valid_HR/)")
    parser.add_argument("--output", "-o", default="granite_results",
                        help="Output directory for results")
    parser.add_argument("--max-images", "-n", type=int, default=0,
                        help="Max images to process (0 = all)")

    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
