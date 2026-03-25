#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Tamper Simulation Test
=======================

Verifies that detect_sentinels_blind correctly classifies each tamper class
by deliberately inflicting each one on a set of marked images and checking
that the output matches what was done.

Tamper classes simulated:

  none             — unmodified image, all sentinels intact
  full_wipe        — overwrite every sentinel position with random values
  tail_truncation  — remove sentinels from the last 50% of sections
  head_truncation  — remove sentinels from the first 50% of sections
  tail_sweep       — remove exits from the last 3+ consecutive sections
  head_sweep       — remove entries from the first 3+ consecutive sections
  scattered        — randomly remove ~40% of sentinels, no spatial pattern

For each tamper class, we test both:
  - MANIFEST mode  (has receipt — faster, should be near-perfect)
  - BLIND mode     (no receipt — the real-world case)

A correct classification = tamper_class matches what we inflicted.
A detection miss = tamper_detected=False when we tampered.
A false positive = tamper_detected=True on the none case.

Usage:
    python tamper_simulation_test.py -i /path/to/DIV2K -o tamper_results -n 20
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
from collections import defaultdict

from pgps_detector import sample_positions_grid
from compound_markers import (
    MarkerConfig, embed_compound,
    detect_sentinels_blind, detect_sentinels,
    SENTINEL_CANARY_RATIO, CANARY_WIDTH, MERSENNE_BASKET,
)
from dqt_prime import encode_prime_jpeg


# =============================================================================
# CONFIG
# =============================================================================

FLOOR         = 43
DENSITY_FRAC  = 0.08
MIN_DIMENSION = 512

# Compress to Q75 before tamper simulation — realistic intermediate quality
# Not Q40 (that destroys too much) but not lossless (too easy)
TAMPER_QUALITY = 75


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
# TAMPER INFLICTORS
# Each takes (pixels, sentinels, rng) and returns modified pixels.
# Sentinels are passed so the inflictors know exactly where to attack.
# =============================================================================

def inflict_none(pixels, sentinels, rng):
    """No tampering — baseline."""
    return pixels.copy(), sentinels

def inflict_full_wipe(pixels, sentinels, rng):
    """Overwrite every sentinel position with a random channel value."""
    px = pixels.copy()
    for s in sentinels:
        r, col = s["row"], s["col"]
        if r < px.shape[0] and col < px.shape[1]:
            # Set to a random value that is NOT a Mersenne
            noise = int(rng.randint(30, 210))
            while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                noise = int(rng.randint(30, 210))
            px[r, col, 1] = noise
    return px, sentinels

def inflict_tail_truncation(pixels, sentinels, rng):
    """Remove sentinels (both entry and exit) from the last 50% of sections."""
    px = pixels.copy()
    n_sections = max(s["section"] for s in sentinels) + 1 if sentinels else 0
    cutoff     = n_sections // 2
    for s in sentinels:
        if s["section"] >= cutoff:
            r, col = s["row"], s["col"]
            if r < px.shape[0] and col < px.shape[1]:
                noise = int(rng.randint(30, 210))
                while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                    noise = int(rng.randint(30, 210))
                px[r, col, 1] = noise
    return px, sentinels

def inflict_head_truncation(pixels, sentinels, rng):
    """Remove sentinels from the first 50% of sections."""
    px = pixels.copy()
    n_sections = max(s["section"] for s in sentinels) + 1 if sentinels else 0
    cutoff     = n_sections // 2
    for s in sentinels:
        if s["section"] < cutoff:
            r, col = s["row"], s["col"]
            if r < px.shape[0] and col < px.shape[1]:
                noise = int(rng.randint(30, 210))
                while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                    noise = int(rng.randint(30, 210))
                px[r, col, 1] = noise
    return px, sentinels

def inflict_tail_sweep(pixels, sentinels, rng):
    """Remove EXIT sentinels from last 3+ consecutive sections."""
    px = pixels.copy()
    n_sections = max(s["section"] for s in sentinels) + 1 if sentinels else 0
    sweep_start = max(0, n_sections - max(3, n_sections // 3))
    for s in sentinels:
        if s["section"] >= sweep_start and s["type"] == "exit":
            r, col = s["row"], s["col"]
            if r < px.shape[0] and col < px.shape[1]:
                noise = int(rng.randint(30, 210))
                while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                    noise = int(rng.randint(30, 210))
                px[r, col, 1] = noise
    return px, sentinels

def inflict_head_sweep(pixels, sentinels, rng):
    """Remove ENTRY sentinels from first 3+ consecutive sections."""
    px = pixels.copy()
    n_sections = max(s["section"] for s in sentinels) + 1 if sentinels else 0
    sweep_end = max(3, n_sections // 3)
    for s in sentinels:
        if s["section"] < sweep_end and s["type"] == "entry":
            r, col = s["row"], s["col"]
            if r < px.shape[0] and col < px.shape[1]:
                noise = int(rng.randint(30, 210))
                while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                    noise = int(rng.randint(30, 210))
                px[r, col, 1] = noise
    return px, sentinels

def inflict_scattered(pixels, sentinels, rng):
    """Randomly remove ~40% of sentinels with no spatial pattern."""
    px = pixels.copy()
    for s in sentinels:
        if rng.random() < 0.4:
            r, col = s["row"], s["col"]
            if r < px.shape[0] and col < px.shape[1]:
                noise = int(rng.randint(30, 210))
                while any(abs(noise - m) <= CANARY_WIDTH for m in MERSENNE_BASKET):
                    noise = int(rng.randint(30, 210))
                px[r, col, 1] = noise
    return px, sentinels


TAMPER_CASES = {
    "none":             inflict_none,
    "full_wipe":        inflict_full_wipe,
    "tail_truncation":  inflict_tail_truncation,
    "head_truncation":  inflict_head_truncation,
    "tail_sweep":       inflict_tail_sweep,
    "head_sweep":       inflict_head_sweep,
    "scattered":        inflict_scattered,
}


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    n_req = markers_for_image(h, w)
    rng   = np.random.default_rng(99)

    config = MarkerConfig(
        name="compound",
        description=f"Tamper test — floor={FLOOR} density={DENSITY_FRAC}",
        min_prime=FLOOR,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        magic_value=42,
        magic_tolerance=7,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    prime_data, _   = encode_prime_jpeg(pixels, quality=95, min_prime=2, preserve_dc=True)
    prime_pixels    = decode_jpeg(prime_data)
    marked_px, markers, sentinels = embed_compound(
        prime_pixels, config, variable_offset=42
    )

    if len(sentinels) < 4:
        return {"image": fname, "error": f"Too few sentinels: {len(sentinels)}"}

    # Compress to TAMPER_QUALITY — this is the image the adversary receives
    compressed = decode_jpeg(to_jpeg(marked_px, quality=TAMPER_QUALITY))

    results = {}
    for tamper_name, inflict_fn in TAMPER_CASES.items():
        tampered_px, _ = inflict_fn(compressed.copy(), sentinels, rng)

        blind    = detect_sentinels_blind(tampered_px, floor=FLOOR)
        manifest = detect_sentinels(tampered_px, sentinels)

        expected_tamper = tamper_name != "none"

        results[tamper_name] = {
            # Blind mode
            "blind_tamper_detected":  blind["tamper_detected"],
            "blind_tamper_class":     blind["tamper_class"],
            "blind_n_canaries":       blind["n_canaries"],
            "blind_n_intact":         blind["n_intact"],
            "blind_intact_pct":       blind["intact_pct"],
            # Manifest mode
            "manifest_tamper_detected": manifest["tamper_detected"],
            "manifest_tamper_class":    manifest["tamper_class"],
            "manifest_intact_pct":      manifest["intact_pct"],
            # Correctness
            "expected_tamper":          expected_tamper,
            "blind_correct_detection":  blind["tamper_detected"] == expected_tamper,
            "manifest_correct_detection": manifest["tamper_detected"] == expected_tamper,
            "blind_class_match": (
                blind["tamper_class"] == tamper_name
                if expected_tamper else blind["tamper_class"] == "none"
            ),
            "manifest_class_match": (
                manifest["tamper_class"] == tamper_name
                if expected_tamper else manifest["tamper_class"] == "none"
            ),
        }

    return {
        "image":       fname,
        "n_markers":   len(markers),
        "n_sentinels": len(sentinels),
        "tamper_quality": TAMPER_QUALITY,
        "results":     results,
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
    print(f"TAMPER SIMULATION TEST")
    print(f"{'='*80}")
    print(f"Images:          {n_total}")
    print(f"Floor:           {FLOOR}")
    print(f"CANARY_WIDTH:    {CANARY_WIDTH}")
    print(f"Canary ratio:    1 pair per {SENTINEL_CANARY_RATIO} markers")
    print(f"Tamper quality:  Q{TAMPER_QUALITY} (image state when tampered)")
    print(f"Tamper cases:    {', '.join(TAMPER_CASES.keys())}")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "tamper_per_image.jsonl")
    open(results_file, "w").close()

    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>3d}/{n_total}] {fname}")

        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"  LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"  SKIP"); continue
        if max(h, w) > 1024:
            scale  = 1024 / max(h, w)
            img    = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        if "error" not in result:
            print(f"  markers={result['n_markers']}  sentinels={result['n_sentinels']}")
            print(f"  {'Tamper case':>16s}  {'blind_det':>10s}  {'blind_class':>16s}  "
                  f"{'blind_ok':>8s}  {'manifest_det':>12s}  {'manifest_ok':>11s}")
            for tname, tr in result["results"].items():
                bd  = "TAMPER" if tr["blind_tamper_detected"]    else "clean "
                md  = "TAMPER" if tr["manifest_tamper_detected"] else "clean "
                bok = "✓" if tr["blind_correct_detection"]    else "✗"
                mok = "✓" if tr["manifest_correct_detection"] else "✗"
                bcl = tr["blind_tamper_class"]
                print(f"  {tname:>16s}  {bd:>10s}  {bcl:>16s}  "
                      f"{bok:>8s}  {md:>12s}  {mok:>11s}")
        print(f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start
    good = [r for r in summary_data if "error" not in r and "results" in r]
    n_good = len(good)

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    print(f"\n\n{'='*80}")
    print(f"TAMPER SIMULATION AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    # Per tamper-class accuracy table
    print(f"{'Tamper case':>16s}  {'blind_det%':>10s}  {'blind_class%':>12s}  "
          f"{'manifest_det%':>13s}  {'manifest_class%':>15s}")
    print("─" * 75)

    aggregate_by_class = {}
    for tname in TAMPER_CASES:
        blind_det   = sum(1 for r in good if r["results"][tname]["blind_correct_detection"])
        blind_cls   = sum(1 for r in good if r["results"][tname]["blind_class_match"])
        manif_det   = sum(1 for r in good if r["results"][tname]["manifest_correct_detection"])
        manif_cls   = sum(1 for r in good if r["results"][tname]["manifest_class_match"])

        bd_pct = blind_det   / n_good * 100
        bc_pct = blind_cls   / n_good * 100
        md_pct = manif_det   / n_good * 100
        mc_pct = manif_cls   / n_good * 100

        print(f"{tname:>16s}  {bd_pct:>9.1f}%  {bc_pct:>11.1f}%  "
              f"{md_pct:>12.1f}%  {mc_pct:>14.1f}%")

        aggregate_by_class[tname] = {
            "blind_correct_detection_pct":    round(bd_pct, 1),
            "blind_class_match_pct":          round(bc_pct, 1),
            "manifest_correct_detection_pct": round(md_pct, 1),
            "manifest_class_match_pct":       round(mc_pct, 1),
        }

    # Overall
    all_blind_det = np.mean([
        aggregate_by_class[t]["blind_correct_detection_pct"]
        for t in TAMPER_CASES
    ])
    all_blind_cls = np.mean([
        aggregate_by_class[t]["blind_class_match_pct"]
        for t in TAMPER_CASES
    ])

    print(f"\n{'='*80}")
    print(f"TAMPER VERDICT")
    print(f"{'='*80}")
    print(f"  Mean blind detection accuracy:    {all_blind_det:.1f}%")
    print(f"  Mean blind classification accuracy: {all_blind_cls:.1f}%")
    print()

    if all_blind_det >= 80 and all_blind_cls >= 60:
        verdict = (f"TAMPER DETECTION WORKS. "
                   f"{all_blind_det:.1f}% correct detection, "
                   f"{all_blind_cls:.1f}% correct classification (blind mode).")
    elif all_blind_det >= 60:
        verdict = (f"TAMPER DETECTION PARTIAL. "
                   f"{all_blind_det:.1f}% detection, "
                   f"{all_blind_cls:.1f}% classification. "
                   f"Consider raising CANARY_WIDTH.")
    else:
        verdict = (f"TAMPER DETECTION WEAK. {all_blind_det:.1f}% detection. "
                   f"Check sentinel survival at Q{TAMPER_QUALITY}.")

    print(f"  {verdict}")

    with open(os.path.join(output_dir, "TAMPER_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"CANARY_WIDTH: {CANARY_WIDTH}\n")
        f.write(f"SENTINEL_CANARY_RATIO: {SENTINEL_CANARY_RATIO}\n")
        f.write(f"Tamper quality: Q{TAMPER_QUALITY}\n")
        f.write(f"Mean blind detection: {all_blind_det:.1f}%\n")
        f.write(f"Mean blind classification: {all_blind_cls:.1f}%\n")

    aggregate = {
        "n_images":              n_good,
        "floor":                 FLOOR,
        "canary_width":          CANARY_WIDTH,
        "sentinel_canary_ratio": SENTINEL_CANARY_RATIO,
        "tamper_quality":        TAMPER_QUALITY,
        "mean_blind_detection_pct":       round(all_blind_det, 1),
        "mean_blind_classification_pct":  round(all_blind_cls, 1),
        "by_tamper_class":       aggregate_by_class,
        "total_time":            round(total_time, 1),
    }
    with open(os.path.join(output_dir, "tamper_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tamper Simulation Test")
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="tamper_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
