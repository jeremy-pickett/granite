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
Layer 3 Blind Detection Test — The Facebook Test
==================================================

The real-world scenario: a platform receives an image with NO manifest,
NO known positions, NO seed. Just pixels that have been through a pipeline.

Can we detect that provenance was embedded?

This test simulates:
  1. Creator embeds markers (known positions, kept for ground truth only)
  2. Image goes through a compression pipeline (simulating platform transcode)
  3. Detector receives the file with ZERO knowledge of positions
  4. Detector scans ALL eligible positions blindly
  5. Detector compares the aggregate statistics against a CLEAN control image

The control is critical: we compare a marked-then-compressed image against
an unmarked-then-compressed image of the SAME content through the SAME pipeline.
The only difference is whether markers were embedded before compression.

If the detector can distinguish marked from unmarked: Layer 3 works.
If it can't: the economic architecture needs a different foundation.

Usage:
    python blind_detection_test.py -i "C:\\path\\to\\DIV2K" -o blind_results -n 5
    python blind_detection_test.py -i "C:\\path\\to\\DIV2K" -o blind_results -n 0
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

# Local imports
from pgps_detector import build_prime_lookup, sieve_of_eratosthenes, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound


# =============================================================================
# CONFIG
# =============================================================================

CASCADE_QUALITIES = [95, 85, 75, 60, 40]

CHANNEL_PAIRS = {
    "RG": (0, 1),
    "GB": (1, 2),
}

TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="Blind detection test",
    min_prime=53,
    use_twins=True,
    use_rare_basket=True,
    use_magic=False,
    detection_prime_tolerance=2,
    n_markers=500,
)

MIN_DIMENSION = 512


# =============================================================================
# JPEG UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


# =============================================================================
# BLIND SCAN: measure ALL eligible positions, no manifest
# =============================================================================

def blind_scan(pixels, ch_a, ch_b, min_prime=53, tolerance=2):
    """
    Scan ALL eligible positions on the grid. No knowledge of which
    positions are markers. Return aggregate statistics.
    """
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    max_val = 255

    # Fuzzy prime lookup
    fuzzy = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for off in range(-tolerance, tolerance + 1):
            check = d + off
            if 0 <= check <= max_val and primes[check]:
                fuzzy[d] = True
                break

    # Restrict fuzzy to basket primes (>= min_prime)
    for d in range(min_prime):
        fuzzy[d] = False

    # Scan all eligible grid positions
    all_pos = sample_positions_grid(h, w, 8)
    
    twin_pass = 0
    twin_total = 0
    all_distances = []
    local_variances = []

    for pos in all_pos:
        r = int(pos[0]) + 3  # block center offset
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue

        twin_total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        all_distances.append(d1)
        all_distances.append(d2)

        if fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]:
            twin_pass += 1

        # Local variance: compare this twin pair's distances to a small neighborhood
        neighborhood_dists = []
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w:
                    nd = abs(int(pixels[nr, nc, ch_a]) - int(pixels[nr, nc, ch_b]))
                    neighborhood_dists.append(nd)
        if len(neighborhood_dists) > 4:
            local_variances.append(np.var(neighborhood_dists))

    twin_rate = twin_pass / twin_total if twin_total > 0 else 0

    return {
        "twin_rate": round(twin_rate, 6),
        "twin_pass": twin_pass,
        "twin_total": twin_total,
        "distance_mean": round(float(np.mean(all_distances)), 4) if all_distances else 0,
        "distance_std": round(float(np.std(all_distances)), 4) if all_distances else 0,
        "distance_median": round(float(np.median(all_distances)), 4) if all_distances else 0,
        "local_var_mean": round(float(np.mean(local_variances)), 4) if local_variances else 0,
        "local_var_std": round(float(np.std(local_variances)), 4) if local_variances else 0,
        "distances": np.array(all_distances),
        "local_vars": np.array(local_variances),
        "n_positions": twin_total,
    }


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    """
    For one image:
    1. Create MARKED version (embed + compress through cascade)
    2. Create CLEAN version (same image, same cascade, NO embedding)
    3. Blind-scan both at every generation
    4. Compare: can we distinguish marked from clean?
    """
    h, w = pixels.shape[:2]
    result = {
        "image": fname,
        "dimensions": f"{w}x{h}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # --- MARKED PATH ---
    # Embed markers
    marked_pixels, markers = embed_compound(pixels.copy(), TWIN_CONFIG, seed=42)
    result["n_markers"] = len(markers)

    if len(markers) < 20:
        result["error"] = f"Too few markers: {len(markers)}"
        return result

    # Initial encode
    marked_jpeg = to_jpeg(marked_pixels, quality=95)

    # --- CLEAN PATH (same image, no embedding, same pipeline) ---
    clean_jpeg = to_jpeg(pixels, quality=95)

    # --- CASCADE BOTH ---
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

        for pair_name, (ch_a, ch_b) in CHANNEL_PAIRS.items():
            # Blind scan marked image
            marked_scan = blind_scan(marked_px, ch_a, ch_b,
                                      min_prime=TWIN_CONFIG.min_prime,
                                      tolerance=TWIN_CONFIG.detection_prime_tolerance)
            # Blind scan clean image
            clean_scan = blind_scan(clean_px, ch_a, ch_b,
                                     min_prime=TWIN_CONFIG.min_prime,
                                     tolerance=TWIN_CONFIG.detection_prime_tolerance)

            # THE TEST: can we distinguish marked from clean?

            # Test 1: Twin prime rate difference
            rate_diff = marked_scan["twin_rate"] - clean_scan["twin_rate"]
            rate_ratio = (marked_scan["twin_rate"] / clean_scan["twin_rate"]
                         if clean_scan["twin_rate"] > 0 else float('inf'))

            # Test 2: KS test on distance distributions
            if (len(marked_scan["distances"]) > 10 and
                len(clean_scan["distances"]) > 10):
                ks_stat, ks_p = sp_stats.ks_2samp(
                    marked_scan["distances"],
                    clean_scan["distances"]
                )
            else:
                ks_stat, ks_p = 0.0, 1.0

            # Test 3: KS test on local variance distributions
            if (len(marked_scan["local_vars"]) > 10 and
                len(clean_scan["local_vars"]) > 10):
                var_ks_stat, var_ks_p = sp_stats.ks_2samp(
                    marked_scan["local_vars"],
                    clean_scan["local_vars"]
                )
            else:
                var_ks_stat, var_ks_p = 0.0, 1.0

            # Test 4: Mann-Whitney U on distances
            if (len(marked_scan["distances"]) > 10 and
                len(clean_scan["distances"]) > 10):
                mw_stat, mw_p = sp_stats.mannwhitneyu(
                    marked_scan["distances"],
                    clean_scan["distances"],
                    alternative='two-sided'
                )
            else:
                mw_stat, mw_p = 0.0, 1.0

            # Store results
            gen[f"{pair_name}_marked_twin_rate"] = marked_scan["twin_rate"]
            gen[f"{pair_name}_clean_twin_rate"] = clean_scan["twin_rate"]
            gen[f"{pair_name}_rate_ratio"] = round(rate_ratio, 4)
            gen[f"{pair_name}_rate_diff"] = round(rate_diff, 6)
            gen[f"{pair_name}_dist_ks_stat"] = round(float(ks_stat), 6)
            gen[f"{pair_name}_dist_ks_p"] = float(ks_p)
            gen[f"{pair_name}_var_ks_stat"] = round(float(var_ks_stat), 6)
            gen[f"{pair_name}_var_ks_p"] = float(var_ks_p)
            gen[f"{pair_name}_mw_p"] = float(mw_p)
            gen[f"{pair_name}_marked_dist_mean"] = marked_scan["distance_mean"]
            gen[f"{pair_name}_clean_dist_mean"] = clean_scan["distance_mean"]
            gen[f"{pair_name}_marked_var_mean"] = marked_scan["local_var_mean"]
            gen[f"{pair_name}_clean_var_mean"] = clean_scan["local_var_mean"]

            # Is it detected? Any statistical test below threshold
            detected = (ks_p < 0.05 or var_ks_p < 0.05 or mw_p < 0.05)
            gen[f"{pair_name}_blind_detected"] = detected

        # Any pair detected?
        gen["any_blind_detected"] = any(
            gen.get(f"{pn}_blind_detected", False) for pn in CHANNEL_PAIRS
        )

        cascade.append(gen)

    result["cascade"] = cascade

    # Summary stats
    for pair_name in CHANNEL_PAIRS:
        gen4 = cascade[4] if len(cascade) > 4 else {}
        result[f"{pair_name}_gen4_dist_ks_p"] = gen4.get(f"{pair_name}_dist_ks_p", 1.0)
        result[f"{pair_name}_gen4_var_ks_p"] = gen4.get(f"{pair_name}_var_ks_p", 1.0)
        result[f"{pair_name}_gen4_mw_p"] = gen4.get(f"{pair_name}_mw_p", 1.0)
        result[f"{pair_name}_gen4_blind_detected"] = gen4.get(f"{pair_name}_blind_detected", False)

    result["gen4_any_detected"] = cascade[4].get("any_blind_detected", False) if len(cascade) > 4 else False

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
    print(f"LAYER 3 BLIND DETECTION TEST — The Facebook Test")
    print(f"{'='*80}")
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Images:     {n_total}")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Method:     Marked image vs clean image, same pipeline, blind scan")
    print(f"Started:    {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "blind_per_image.jsonl")
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

        # Resize to 1024 max dimension
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
            det = "DET" if result.get("gen4_any_detected", False) else "   "
            gb_p = result.get("GB_gen4_dist_ks_p", 1.0)
            rg_p = result.get("RG_gen4_dist_ks_p", 1.0)
            print(f"n={result.get('n_markers',0):>3d}  {det}"
                  f"  GB_ks={gb_p:.2e}  RG_ks={rg_p:.2e}"
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
    print(f"LAYER 3 BLIND DETECTION — AGGREGATE ({n_good} images)")
    print(f"Total time: {total_time:.0f}s ({total_time/max(n_good,1):.1f}s/image)")
    print(f"{'='*80}")

    if n_good == 0:
        print("No valid results.")
        return

    for pair_name in CHANNEL_PAIRS:
        print(f"\n{'─'*60}")
        print(f"Channel Pair: {pair_name}")
        print(f"{'─'*60}")

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            dist_ks_ps = []
            var_ks_ps = []
            mw_ps = []
            detected = 0

            for r in good:
                cascade = r.get("cascade", [])
                if len(cascade) > gen_idx:
                    g = cascade[gen_idx]
                    dist_ks_ps.append(g.get(f"{pair_name}_dist_ks_p", 1.0))
                    var_ks_ps.append(g.get(f"{pair_name}_var_ks_p", 1.0))
                    mw_ps.append(g.get(f"{pair_name}_mw_p", 1.0))
                    if g.get(f"{pair_name}_blind_detected", False):
                        detected += 1

            dist_arr = np.array(dist_ks_ps)
            var_arr = np.array(var_ks_ps)
            mw_arr = np.array(mw_ps)

            print(f"  Gen{gen_idx} Q{q:>3d}:")
            print(f"    Distance KS < 0.05: {np.sum(dist_arr < 0.05):>4d}/{n_good}"
                  f" ({np.mean(dist_arr < 0.05)*100:>5.1f}%)"
                  f"  mean_p={np.mean(dist_arr):.4f}")
            print(f"    Variance KS < 0.05: {np.sum(var_arr < 0.05):>4d}/{n_good}"
                  f" ({np.mean(var_arr < 0.05)*100:>5.1f}%)"
                  f"  mean_p={np.mean(var_arr):.4f}")
            print(f"    Mann-Whitney < 0.05: {np.sum(mw_arr < 0.05):>4d}/{n_good}"
                  f" ({np.mean(mw_arr < 0.05)*100:>5.1f}%)"
                  f"  mean_p={np.mean(mw_arr):.4f}")
            print(f"    Any test detected:   {detected:>4d}/{n_good}"
                  f" ({detected/n_good*100:>5.1f}%)")

    # Overall Layer 3 detection rate
    print(f"\n{'='*80}")
    print(f"THE FACEBOOK VERDICT")
    print(f"{'='*80}")

    gen4_any = sum(1 for r in good if r.get("gen4_any_detected", False))
    pct = gen4_any / n_good * 100

    # Per-pair
    for pair_name in CHANNEL_PAIRS:
        det = sum(1 for r in good if r.get(f"{pair_name}_gen4_blind_detected", False))
        print(f"  {pair_name} blind detected at Gen4: {det}/{n_good} ({det/n_good*100:.1f}%)")

    print(f"  Either pair detected at Gen4: {gen4_any}/{n_good} ({pct:.1f}%)")

    if pct > 80:
        verdict = f"LAYER 3 WORKS. {pct:.1f}% blind detection on {n_good} images."
    elif pct > 50:
        verdict = f"LAYER 3 PARTIAL. {pct:.1f}% blind detection. Viable with caveats."
    elif pct > 20:
        verdict = f"LAYER 3 MARGINAL. {pct:.1f}% blind detection. Needs improvement."
    else:
        verdict = f"LAYER 3 FAILS. {pct:.1f}% blind detection. Economic architecture needs rethinking."

    print(f"\n  {verdict}")

    with open(os.path.join(output_dir, "BLIND_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"\nGenerated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Method: Marked vs clean, same pipeline, blind scan all eligible positions\n")

    # Save aggregate
    aggregate = {
        "n_images": n_good,
        "total_time": round(total_time, 1),
        "gen4_any_detected_pct": round(pct, 1),
    }
    for pair_name in CHANNEL_PAIRS:
        det = sum(1 for r in good if r.get(f"{pair_name}_gen4_blind_detected", False))
        aggregate[f"{pair_name}_gen4_blind_pct"] = round(det / n_good * 100, 1)

    with open(os.path.join(output_dir, "blind_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    print(f"\nResults: {output_dir}/")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Layer 3 Blind Detection — The Facebook Test"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Directory containing images")
    parser.add_argument("--output", "-o", default="blind_results",
                        help="Output directory")
    parser.add_argument("--max-images", "-n", type=int, default=0,
                        help="Max images (0 = all). Use 5 for sanity check.")

    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
