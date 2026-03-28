#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Floor Sweep at 2000 Markers — Finding the Sweet Spot
======================================================

Fixed density (2000 markers). Variable basket floor.
Which floor gives blind detection at acceptable PSNR?

Floors tested: 23, 29, 37, 43, 53
At each floor: embed 2000 markers, cascade, blind KS vs clean.

Usage:
    python floor_sweep_2000.py -i "C:\\path\\to\\DIV2K" -o floor_results -n 5
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

FLOORS = [23, 29, 37, 43, 53]
N_MARKERS = 2000
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION = 512


def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def compute_psnr(original, modified):
    mse = np.mean((original.astype(float) - modified.astype(float)) ** 2)
    if mse == 0:
        return float('inf')
    return 10 * np.log10(255.0 ** 2 / mse)


def blind_aggregate_ks(marked_px, clean_px, ch_a, ch_b):
    """KS test comparing all eligible positions between marked and clean."""
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
        return 1.0, 0.0
    ks_stat, ks_p = sp_stats.ks_2samp(marked_dists, clean_dists)
    return float(ks_p), float(ks_stat)


def measure_prime_rates(pixels, ch_a, ch_b, floor):
    """Measure twin-prime rate at eligible positions for primes >= floor."""
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    max_val = 255

    # Build lookup for primes at or above floor
    lookup = np.zeros(max_val + 1, dtype=bool)
    for d in range(floor, max_val + 1):
        if primes[d]:
            lookup[d] = True

    all_pos = sample_positions_grid(h, w, 8)
    twin_pass = 0
    total = 0

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if lookup[min(d1, max_val)] and lookup[min(d2, max_val)]:
            twin_pass += 1

    return twin_pass / total if total > 0 else 0, twin_pass, total


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w = pixels.shape[:2]
    result = {
        "image": fname,
        "dimensions": f"{w}x{h}",
    }

    # Clean baseline
    clean_jpeg = to_jpeg(pixels, 95)

    # Test each floor
    for floor in FLOORS:
        config = MarkerConfig(
            name=f"floor_{floor}",
            description=f"Floor sweep n=2000 floor={floor}",
            min_prime=floor,
            use_twins=True,
            use_rare_basket=True,
            use_magic=False,
            detection_prime_tolerance=2,
            n_markers=N_MARKERS,
        )

        # Embed
        marked_pixels, markers = embed_compound(pixels.copy(), config, seed=42)
        n_actual = len(markers)
        psnr = compute_psnr(pixels, marked_pixels)

        marked_jpeg = to_jpeg(marked_pixels, 95)

        fkey = f"f{floor}"
        result[f"{fkey}_n_actual"] = n_actual
        result[f"{fkey}_psnr"] = round(psnr, 2)

        # Cascade both
        current_marked = marked_jpeg
        current_clean = clean_jpeg

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            if gen_idx > 0:
                current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
                current_clean = to_jpeg(decode_jpeg(current_clean), quality=q)

            marked_px = decode_jpeg(current_marked)
            clean_px = decode_jpeg(current_clean)

            # Blind aggregate KS on G-B
            ks_p_gb, ks_stat_gb = blind_aggregate_ks(marked_px, clean_px, 1, 2)
            # Blind aggregate KS on R-G
            ks_p_rg, ks_stat_rg = blind_aggregate_ks(marked_px, clean_px, 0, 1)

            # Prime rate comparison at this floor
            marked_rate, _, _ = measure_prime_rates(marked_px, 1, 2, floor)
            clean_rate, _, _ = measure_prime_rates(clean_px, 1, 2, floor)
            rate_ratio = marked_rate / max(clean_rate, 0.0001)

            result[f"{fkey}_g{gen_idx}_ks_gb"] = ks_p_gb
            result[f"{fkey}_g{gen_idx}_ks_rg"] = ks_p_rg
            result[f"{fkey}_g{gen_idx}_stat_gb"] = round(ks_stat_gb, 6)
            result[f"{fkey}_g{gen_idx}_marked_rate"] = round(marked_rate, 6)
            result[f"{fkey}_g{gen_idx}_clean_rate"] = round(clean_rate, 6)
            result[f"{fkey}_g{gen_idx}_rate_ratio"] = round(rate_ratio, 4)
            result[f"{fkey}_g{gen_idx}_det_gb"] = ks_p_gb < 0.05
            result[f"{fkey}_g{gen_idx}_det_rg"] = ks_p_rg < 0.05
            result[f"{fkey}_g{gen_idx}_det_any"] = ks_p_gb < 0.05 or ks_p_rg < 0.05

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
    print(f"FLOOR SWEEP AT 2000 MARKERS")
    print(f"{'='*80}")
    print(f"Images:     {n_total}")
    print(f"Markers:    {N_MARKERS}")
    print(f"Floors:     {FLOORS}")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "floor_sweep_per_image.jsonl")
    with open(results_file, "w") as f:
        f.write("")

    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
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

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        if "error" not in result:
            for floor in FLOORS:
                fkey = f"f{floor}"
                psnr = result.get(f"{fkey}_psnr", 0)
                n_act = result.get(f"{fkey}_n_actual", 0)
                g0_det = "G0" if result.get(f"{fkey}_g0_det_any", False) else "  "
                g4_det = "G4" if result.get(f"{fkey}_g4_det_any", False) else "  "
                g4_ks = result.get(f"{fkey}_g4_ks_gb", 1.0)
                g4_rr = result.get(f"{fkey}_g4_rate_ratio", 1.0)
                print(f"  floor={floor:>2d}  n={n_act:>4d}  PSNR={psnr:>5.1f}dB"
                      f"  {g0_det} {g4_det}  ks_gb={g4_ks:.2e}  rr={g4_rr:.3f}")

        print(f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    good = [r for r in summary_data if "error" not in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"FLOOR SWEEP RESULTS ({n_good} images, {N_MARKERS} markers)")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if n_good == 0:
        print("No valid results.")
        return

    # Summary table
    print(f"{'Floor':>5s}  {'Actual':>6s}  {'PSNR':>6s}"
          f"  {'G0 Det':>7s}  {'G1 Det':>7s}  {'G2 Det':>7s}"
          f"  {'G3 Det':>7s}  {'G4 Det':>7s}"
          f"  {'G4 RateR':>8s}")
    print(f"{'─'*80}")

    summary_json = []

    for floor in FLOORS:
        fkey = f"f{floor}"

        # Mean values
        actuals = [r.get(f"{fkey}_n_actual", 0) for r in good]
        psnrs = [r.get(f"{fkey}_psnr", 0) for r in good]

        gen_det = []
        gen_rr = []
        for gen_idx in range(5):
            det = sum(1 for r in good if r.get(f"{fkey}_g{gen_idx}_det_any", False))
            rrs = [r.get(f"{fkey}_g{gen_idx}_rate_ratio", 1.0) for r in good]
            gen_det.append(det)
            gen_rr.append(np.mean(rrs))

        mean_actual = np.mean(actuals)
        mean_psnr = np.mean(psnrs)

        det_strs = [f"{d:>3d}/{n_good} {d/n_good*100:>3.0f}%" for d in gen_det]

        print(f"{floor:>5d}  {mean_actual:>6.0f}  {mean_psnr:>5.1f}dB"
              f"  {det_strs[0]}  {det_strs[1]}  {det_strs[2]}"
              f"  {det_strs[3]}  {det_strs[4]}"
              f"  {gen_rr[4]:>8.3f}")

        summary_json.append({
            "floor": floor,
            "mean_actual": round(mean_actual),
            "mean_psnr": round(mean_psnr, 2),
            "gen0_det_pct": round(gen_det[0] / n_good * 100, 1),
            "gen1_det_pct": round(gen_det[1] / n_good * 100, 1),
            "gen2_det_pct": round(gen_det[2] / n_good * 100, 1),
            "gen3_det_pct": round(gen_det[3] / n_good * 100, 1),
            "gen4_det_pct": round(gen_det[4] / n_good * 100, 1),
            "gen4_rate_ratio": round(gen_rr[4], 4),
        })

    # Detailed KS p-values at Gen4
    print(f"\nGen4 Q40 KS p-values (G-B):")
    print(f"{'Floor':>5s}  {'Mean':>10s}  {'Median':>10s}  {'Min':>10s}  {'Max':>10s}")
    print(f"{'─'*50}")

    for floor in FLOORS:
        fkey = f"f{floor}"
        ks_vals = [r.get(f"{fkey}_g4_ks_gb", 1.0) for r in good]
        arr = np.array(ks_vals)
        print(f"{floor:>5d}  {np.mean(arr):>10.4f}  {np.median(arr):>10.4f}"
              f"  {np.min(arr):>10.2e}  {np.max(arr):>10.4f}")

    # Prime rate ratios across generations for each floor
    print(f"\nPrime Rate Ratio (marked/clean) across generations:")
    print(f"{'Floor':>5s}  {'G0':>8s}  {'G1':>8s}  {'G2':>8s}  {'G3':>8s}  {'G4':>8s}")
    print(f"{'─'*50}")

    for floor in FLOORS:
        fkey = f"f{floor}"
        rrs = []
        for gen_idx in range(5):
            vals = [r.get(f"{fkey}_g{gen_idx}_rate_ratio", 1.0) for r in good]
            rrs.append(np.mean(vals))
        print(f"{floor:>5d}  {rrs[0]:>8.3f}  {rrs[1]:>8.3f}  {rrs[2]:>8.3f}"
              f"  {rrs[3]:>8.3f}  {rrs[4]:>8.3f}")

    # =========================================================================
    # VERDICT
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"FLOOR SWEEP VERDICT")
    print(f"{'='*80}")

    best_floor = None
    best_score = 0
    for s in summary_json:
        # Score: Gen4 detection rate, penalized if PSNR < 40
        score = s["gen4_det_pct"]
        if s["mean_psnr"] < 40:
            score *= 0.5  # penalize low PSNR
        if score > best_score:
            best_score = score
            best_floor = s

    if best_floor:
        print(f"  Best floor: {best_floor['floor']}")
        print(f"    PSNR: {best_floor['mean_psnr']}dB")
        print(f"    Gen0 detection: {best_floor['gen0_det_pct']}%")
        print(f"    Gen4 detection: {best_floor['gen4_det_pct']}%")
        print(f"    Gen4 rate ratio: {best_floor['gen4_rate_ratio']}")

        if best_floor['gen4_det_pct'] > 50 and best_floor['mean_psnr'] > 40:
            verdict = (f"SWEET SPOT FOUND. Floor {best_floor['floor']}: "
                      f"{best_floor['gen4_det_pct']}% blind detection "
                      f"at {best_floor['mean_psnr']}dB PSNR.")
        elif best_floor['gen4_det_pct'] > 50:
            verdict = (f"DETECTION WORKS but PSNR cost high. Floor {best_floor['floor']}: "
                      f"{best_floor['gen4_det_pct']}% at {best_floor['mean_psnr']}dB.")
        elif best_floor['gen0_det_pct'] > 50:
            verdict = (f"GEN0 DETECTION ONLY. Floor {best_floor['floor']}: "
                      f"Gen0={best_floor['gen0_det_pct']}% Gen4={best_floor['gen4_det_pct']}%.")
        else:
            verdict = f"NO SWEET SPOT. Best floor {best_floor['floor']} at {best_floor['gen4_det_pct']}% Gen4."
    else:
        verdict = "NO RESULTS."

    print(f"\n  {verdict}")

    with open(os.path.join(output_dir, "FLOOR_SWEEP_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Markers: {N_MARKERS}\n")
        f.write(f"Floors tested: {FLOORS}\n")

    with open(os.path.join(output_dir, "floor_sweep_summary.json"), "w") as f:
        json.dump(summary_json, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Floor Sweep at 2000 Markers"
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="floor_sweep_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
