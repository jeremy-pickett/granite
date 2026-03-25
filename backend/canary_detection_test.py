#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Canary Detection Test
======================

Two questions, answered on a corpus:

  1. SENSITIVITY: Does detect_sentinels_blind find canaries in marked images
     after JPEG compression?  How many sections survive at each generation?

  2. SPECIFICITY: Does detect_sentinels_blind fire on clean (unmarked) images?
     If it does, we have a false positive problem.

The detection signal is a two-position pair: [fuzzy_Mersenne][fuzzy_prime]
or [fuzzy_prime][fuzzy_Mersenne].  A Mersenne on its own is not a canary.
This adjacency requirement keeps the false positive rate low even on natural
images with rich prime-distance distributions.

Expected results at the validated operating point (floor=43, density=8%):
  - Marked images:  canaries found at gen0, partially surviving at gen4
  - Clean images:   few or no canaries found (specificity check)
  - Contract intact at gen0, degrading gracefully under compression

Usage:
    python canary_detection_test.py -i /path/to/DIV2K -o canary_results -n 50
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

from pgps_detector import sample_positions_grid
from compound_markers import (
    MarkerConfig, embed_compound,
    detect_sentinels_blind, detect_sentinels,
    SENTINEL_CANARY_RATIO, CANARY_WIDTH,
)
from dqt_prime import encode_prime_jpeg


# =============================================================================
# CONFIG
# =============================================================================

FLOOR           = 43
DENSITY_FRAC    = 0.08
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512


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


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    n_req = markers_for_image(h, w)
    cap   = grid_capacity(h, w)
    n_expected_sections = max(1, n_req // SENTINEL_CANARY_RATIO)

    result = {
        "image":              fname,
        "dimensions":         f"{w}x{h}",
        "grid_capacity":      cap,
        "n_req":              n_req,
        "n_expected_sections":n_expected_sections,
    }

    config = MarkerConfig(
        name="compound",
        description=f"Canary test — floor={FLOOR} density={DENSITY_FRAC}",
        min_prime=FLOOR,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        magic_value=42,
        magic_tolerance=7,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    # Embed into prime-table JPEG pixels
    prime_data, _ = encode_prime_jpeg(pixels, quality=95, min_prime=2, preserve_dc=True)
    prime_pixels  = decode_jpeg(prime_data)

    marked_pixels, markers, sentinels = embed_compound(
        prime_pixels, config, variable_offset=42
    )
    result["n_markers"]    = len(markers)
    result["n_sentinels"]  = len(sentinels)
    result["n_placed"]     = sum(1 for s in sentinels if s.get("placed", False))

    gen0_prime_data, _ = encode_prime_jpeg(
        marked_pixels, quality=95, min_prime=2, preserve_dc=True
    )
    clean_jpeg = to_jpeg(pixels, quality=95)

    current_marked = gen0_prime_data
    current_clean  = clean_jpeg
    cascade = []

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
            current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

        marked_px = decode_jpeg(current_marked)
        clean_px  = decode_jpeg(current_clean)

        # --- Blind scan: marked ---
        blind_marked = detect_sentinels_blind(marked_px, floor=FLOOR)

        # --- Blind scan: clean (false positive check) ---
        blind_clean  = detect_sentinels_blind(clean_px,  floor=FLOOR)

        # --- Manifest scan: marked (ground truth) ---
        manifest     = detect_sentinels(marked_px, sentinels)

        gen = {
            "generation":      gen_idx,
            "quality":         q,
            # Blind on marked
            "blind_n_canaries":        blind_marked["n_canaries"],
            "blind_n_entries":         blind_marked["n_entries"],
            "blind_n_exits":           blind_marked["n_exits"],
            "blind_n_sections":        blind_marked["n_sections"],
            "blind_n_intact":          blind_marked["n_intact"],
            "blind_intact_pct":        blind_marked["intact_pct"],
            "blind_tamper_detected":   blind_marked["tamper_detected"],
            "blind_tamper_class":      blind_marked["tamper_class"],
            # Blind on clean (FP)
            "clean_n_canaries":        blind_clean["n_canaries"],
            "clean_n_sections":        blind_clean["n_sections"],
            "clean_tamper_detected":   blind_clean["tamper_detected"],
            # Manifest (reference)
            "manifest_n_intact":       manifest["n_intact"],
            "manifest_intact_pct":     manifest["intact_pct"],
            "manifest_tamper_class":   manifest["tamper_class"],
        }
        cascade.append(gen)

    result["cascade"] = cascade

    g4 = cascade[4] if len(cascade) > 4 else {}
    result["gen4_blind_canaries"]      = g4.get("blind_n_canaries",      0)
    result["gen4_blind_intact_pct"]    = g4.get("blind_intact_pct",      0.0)
    result["gen4_clean_canaries"]      = g4.get("clean_n_canaries",      0)
    result["gen4_blind_tamper"]        = g4.get("blind_tamper_detected",  False)
    result["gen4_manifest_intact_pct"] = g4.get("manifest_intact_pct",   0.0)

    return result


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
    print(f"CANARY DETECTION TEST")
    print(f"{'='*80}")
    print(f"Images:         {n_total}")
    print(f"Floor:          {FLOOR}")
    print(f"Density:        {int(DENSITY_FRAC*100)}%")
    print(f"CANARY_WIDTH:   {CANARY_WIDTH}  (fuzzy Mersenne window)")
    print(f"Canary ratio:   1 sentinel pair per {SENTINEL_CANARY_RATIO} markers")
    print(f"Cascade:        {CASCADE_QUALITIES}")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "canary_per_image.jsonl")
    open(results_file, "w").close()

    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>4d}/{n_total}] {fname}  ", end="", flush=True)

        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"SKIP"); continue
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
            g4_bc  = result.get("gen4_blind_canaries",   0)
            g4_ip  = result.get("gen4_blind_intact_pct", 0.0)
            g4_fp  = result.get("gen4_clean_canaries",   0)
            g4_mn  = result.get("gen4_manifest_intact_pct", 0.0)
            n_sec  = result.get("n_expected_sections",   0)
            print(f"secs={n_sec:>3d}  "
                  f"G4_blind_canaries={g4_bc:>4d}  intact={g4_ip:>5.1f}%  "
                  f"FP_canaries={g4_fp:>4d}  "
                  f"manifest={g4_mn:>5.1f}%  [{elapsed:.1f}s]")
        else:
            print(f"ERROR  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start
    good = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    print(f"\n\n{'='*80}")
    print(f"CANARY DETECTION AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    print(f"{'Gen':>4}  {'Q':>3}  "
          f"{'blind_c':>8}  {'intact%':>8}  {'FP_c':>6}  "
          f"{'manifest%':>10}  {'FP_tamper%':>10}")
    print("─" * 70)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        def gmean(key):
            vals = [r["cascade"][gen_idx].get(key, 0)
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(vals) / len(vals) if vals else 0

        fp_tamper = sum(1 for r in good
                        if len(r["cascade"]) > gen_idx
                        and r["cascade"][gen_idx].get("clean_tamper_detected", False))

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {gmean('blind_n_canaries'):>8.1f}"
              f"  {gmean('blind_intact_pct'):>8.1f}%"
              f"  {gmean('clean_n_canaries'):>6.1f}"
              f"  {gmean('manifest_intact_pct'):>9.1f}%"
              f"  {fp_tamper/n_good*100:>9.1f}%")

    # Gen4 summary
    g4_bi    = np.mean([r.get("gen4_blind_intact_pct",    0.0) for r in good])
    g4_mi    = np.mean([r.get("gen4_manifest_intact_pct", 0.0) for r in good])
    g4_fp    = np.mean([r.get("gen4_clean_canaries",      0)   for r in good])
    g4_tamper= sum(1 for r in good if r.get("gen4_blind_tamper", False))

    print(f"\n{'='*80}")
    print(f"CANARY VERDICT  (Gen4 Q40)")
    print(f"{'='*80}")
    print(f"  Blind scan  — mean intact sections: {g4_bi:.1f}%")
    print(f"  Manifest    — mean intact sections: {g4_mi:.1f}%")
    print(f"  Clean FP    — mean canaries on unmarked: {g4_fp:.1f}")
    print(f"  Tamper fired on marked (contract broken): {g4_tamper}/{n_good}")
    print()

    if g4_bi >= 50 and g4_fp < 5:
        verdict = (f"CANARY WORKS. {g4_bi:.1f}% sections intact at Gen4. "
                   f"FP canaries on clean: {g4_fp:.1f}/image.")
    elif g4_bi >= 20:
        verdict = (f"CANARY PARTIAL. {g4_bi:.1f}% sections intact at Gen4. "
                   f"Detectable but degraded. Consider raising CANARY_WIDTH.")
    else:
        verdict = (f"CANARY WEAK at Gen4. {g4_bi:.1f}% intact. "
                   f"Gen0 survival more relevant — check per-gen breakdown.")

    if g4_fp > 10:
        verdict += f" WARNING: high FP canary rate on clean images ({g4_fp:.1f}/img)."

    print(f"  {verdict}")

    with open(os.path.join(output_dir, "CANARY_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"CANARY_WIDTH: {CANARY_WIDTH}\n")
        f.write(f"SENTINEL_CANARY_RATIO: {SENTINEL_CANARY_RATIO}\n")
        f.write(f"Gen4 blind intact: {g4_bi:.1f}%\n")
        f.write(f"Gen4 manifest intact: {g4_mi:.1f}%\n")
        f.write(f"Gen4 clean FP canaries: {g4_fp:.1f}\n")

    aggregate = {
        "n_images":              n_good,
        "floor":                 FLOOR,
        "density_frac":          DENSITY_FRAC,
        "canary_width":          CANARY_WIDTH,
        "sentinel_canary_ratio": SENTINEL_CANARY_RATIO,
        "gen4_blind_intact_pct": round(g4_bi, 1),
        "gen4_manifest_intact_pct": round(g4_mi, 1),
        "gen4_clean_fp_canaries":round(g4_fp, 1),
        "total_time":            round(total_time, 1),
    }
    with open(os.path.join(output_dir, "canary_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Canary Detection Test")
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="canary_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
