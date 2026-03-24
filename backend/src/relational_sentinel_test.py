#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Relational + Structural Gap Sentinel Test
==========================================

Tests two new sentinel architectures designed to survive JPEG compression
where the absolute Mersenne approach (CANARY_WIDTH=2) failed entirely.

OPTION B — Relational Encoding
  Sentinel is encoded as d(p2) - d(p1) = ±Mersenne
  where p1 and p2 are two positions in the SAME 8×8 DCT block.

  Hypothesis: JPEG quantization error is spatially correlated within a
  block. Both positions drift by approximately the same δ, so the
  difference (d2+δ) - (d1+δ) = d2-d1 is preserved.

  Entry: d(p2) - d(p1) = +Mersenne  (positive)
  Exit:  d(p2) - d(p1) = -Mersenne  (negative)
  Sign encodes direction — cannot be accidentally flipped.

OPTION D — Structural Gap
  Sentinel is encoded as the ABSENCE of a prime-gap marker at a
  boundary position. No pixel value to corrupt — compressor cannot
  destroy an absence.

  Entry boundary: gap at position before first marker of section
  Exit boundary:  gap at position after last marker of section

  Detection: scan for regions where marker density drops to zero
  at section boundaries.

COMBINED (B+D)
  Use structural gap to locate section boundaries robustly.
  Use relational encoding to confirm entry/exit type.
  Together: compression-robust (D) + directionally precise (B) +
  hard to forge (both).

MANIFEST QA MECHANISM
  Manifest detection runs alongside all architectures.
  If manifest rates diverge unexpectedly, something is broken at
  the embedding level and we catch it immediately.

Results are reported independently per architecture, per generation,
matching the layer reporting pattern from the main corpus test.

Usage:
    python relational_sentinel_test.py -i /path/to/DIV2K -o rel_results -n 50

NOTE: The embed_relational_sentinel() and embed_gap_sentinel() functions
are STUBS pending the drift characterizer results. Run
sentinel_drift_characterizer.py first to get the correlation ratio,
then implement the embedders with empirically calibrated parameters.
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

from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import (
    MarkerConfig, embed_compound, detect_sentinels,
    SENTINEL_CANARY_RATIO, MERSENNE_BASKET, CANARY_WIDTH,
    WINDOW_W, BIT_DEPTH, _is_fuzzy_prime, _is_fuzzy_mersenne,
)
from dqt_prime import encode_prime_jpeg


# =============================================================================
# CONFIG
# =============================================================================

FLOOR             = 43
DENSITY_FRAC      = 0.08
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512

# Relational encoding width — to be calibrated from drift_characterizer results.
# Start conservative; update after drift analysis.
REL_WIDTH = 4   # fuzzy window for |actual_diff - mersenne| in relational detection

# Gap detection: how many consecutive grid positions with no prime-gap marker
# constitutes a structural gap signal
GAP_MIN_LENGTH = 3   # minimum consecutive empty positions to count as a gap


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
    return (r1 // 8 == r2 // 8) and (c1 // 8 == c2 // 8)


# =============================================================================
# OPTION B — RELATIONAL SENTINEL EMBEDDER
# =============================================================================

def embed_relational_sentinel(modified: np.ndarray, r: int, col: int,
                               mersenne: int, direction: str,
                               ch_a: int = 0, ch_b: int = 1) -> dict:
    """
    Embed a relational sentinel using two positions in the same 8×8 DCT block.

    direction: 'entry' → d(p2) - d(p1) = +mersenne
               'exit'  → d(p2) - d(p1) = -mersenne

    Chooses p2 = the adjacent position within the same block.
    Returns metadata dict with positions, intended diff, direction.

    STATUS: IMPLEMENTATION PENDING drift characterizer results.
    The approach is correct; the parameter calibration depends on the
    within-block correlation ratio from sentinel_drift_characterizer.py.
    """
    h, w = modified.shape[:2]

    # Find p2: adjacent position within the same 8×8 block
    # Try col+1 first, then col-1
    p1_r, p1_c = r, col
    p2_c = col + 1 if col + 1 < w and same_dct_block(r, col, r, col+1) else col - 1

    if p2_c < 0 or p2_c >= w:
        return None  # Can't find same-block partner

    if not same_dct_block(r, col, r, p2_c):
        return None  # Partner not in same block

    # Current channel differences
    d1_current = abs(int(modified[r, p1_c, ch_a]) - int(modified[r, p1_c, ch_b]))
    d2_current = abs(int(modified[r, p2_c, ch_a]) - int(modified[r, p2_c, ch_b]))

    # Target: d2 - d1 = +mersenne (entry) or -mersenne (exit)
    target_diff = mersenne if direction == 'entry' else -mersenne

    # Set d2 = d1 + target_diff by adjusting the ch_b value at p2
    # Keep d1 as-is (don't modify p1 to preserve marker integrity)
    target_d2  = d1_current + target_diff
    if target_d2 < 0:
        target_d2 = -target_d2  # use absolute value, encode sign in placement

    # Adjust p2 channel b to achieve target_d2
    val_a2  = int(modified[r, p2_c, ch_a])
    opt1    = val_a2 - target_d2
    opt2    = val_a2 + target_d2
    opts    = [v for v in [opt1, opt2] if 20 <= v <= 235]
    if not opts:
        return None

    new_b2 = min(opts, key=lambda x: abs(x - int(modified[r, p2_c, ch_b])))
    modified[r, p2_c, ch_b] = new_b2

    return {
        "type":         direction,
        "p1_row":       r,
        "p1_col":       p1_c,
        "p2_row":       r,
        "p2_col":       p2_c,
        "mersenne":     mersenne,
        "target_diff":  target_diff,
        "placed":       True,
        "same_block":   True,
    }


def detect_relational_sentinel(pixels: np.ndarray, rel_sentinels: list,
                                ch_a: int = 0, ch_b: int = 1,
                                width: int = REL_WIDTH) -> dict:
    """
    Check each relational sentinel: does d(p2) - d(p1) ≈ target_diff?

    Returns per-sentinel survival stats and overall contract evaluation.
    """
    h, w, _ = pixels.shape
    results  = []

    for s in rel_sentinels:
        r1, c1 = s["p1_row"], s["p1_col"]
        r2, c2 = s["p2_row"], s["p2_col"]
        if r1 >= h or c1 >= w or r2 >= h or c2 >= w:
            continue

        d1 = abs(int(pixels[r1, c1, ch_a]) - int(pixels[r1, c1, ch_b]))
        d2 = abs(int(pixels[r2, c2, ch_a]) - int(pixels[r2, c2, ch_b]))

        actual_diff    = d2 - d1
        intended_diff  = s["target_diff"]
        residual       = abs(actual_diff - intended_diff)
        survived       = residual <= width

        results.append({
            "type":          s["type"],
            "intended_diff": intended_diff,
            "actual_diff":   actual_diff,
            "residual":      residual,
            "survived":      survived,
        })

    n_total    = len(results)
    n_survived = sum(1 for r in results if r["survived"])
    n_entry    = sum(1 for r in results if r["type"] == "entry")
    n_exit     = sum(1 for r in results if r["type"] == "exit")
    n_ent_surv = sum(1 for r in results if r["type"] == "entry" and r["survived"])
    n_ex_surv  = sum(1 for r in results if r["type"] == "exit"  and r["survived"])

    mean_residual = float(np.mean([r["residual"] for r in results])) if results else 0

    return {
        "n_total":          n_total,
        "n_survived":       n_survived,
        "intact_pct":       round(n_survived / max(n_total, 1) * 100, 1),
        "n_entry_survived": n_ent_surv,
        "n_exit_survived":  n_ex_surv,
        "mean_residual":    round(mean_residual, 3),
        "details":          results,
    }


# =============================================================================
# OPTION D — STRUCTURAL GAP SENTINEL
# =============================================================================

def place_gap_sentinels(selected_positions: list) -> dict:
    """
    Define section boundaries as GAPS in the marker sequence.

    Returns gap manifest: for each section, the grid positions that
    should be LEFT EMPTY (not embedded) at the boundaries.

    The embedder must SKIP these positions when placing markers.
    No pixel modification required — the absence is the signal.
    """
    n          = len(selected_positions)
    n_sections = max(1, n // SENTINEL_CANARY_RATIO)
    section_size = n // n_sections

    gaps = []
    for sec_idx in range(n_sections):
        start = sec_idx * section_size
        end   = start + section_size if sec_idx < n_sections - 1 else n

        # Entry gap: the grid position just before the section starts
        # Exit gap:  the grid position just after the section ends
        if start > 0:
            entry_pos = selected_positions[start - 1]
            gaps.append({
                "type":    "entry",
                "section": sec_idx,
                "row":     int(entry_pos[0]),
                "col":     int(entry_pos[1]),
            })

        if end < n:
            exit_pos = selected_positions[end]
            gaps.append({
                "type":    "exit",
                "section": sec_idx,
                "row":     int(exit_pos[0]),
                "col":     int(exit_pos[1]),
            })

    return gaps


def detect_gap_sentinels_blind(pixels: np.ndarray,
                                floor: int = FLOOR,
                                prime_tol: int = 2,
                                gap_min: int = GAP_MIN_LENGTH) -> dict:
    """
    Blind scan for structural gaps: regions where prime-gap markers
    are absent for gap_min or more consecutive grid positions.

    In a marked image, gaps appear at section boundaries.
    In a clean image, gaps appear randomly throughout.

    The detection signal: does the gap pattern show the regular
    spacing expected from SENTINEL_CANARY_RATIO × WINDOW_W?
    Regular-interval gaps = structured embedding.
    Random gaps = natural image content.

    Returns:
        n_gaps_found: total gap regions detected
        gap_spacings: distances between consecutive gaps
        regular_spacing_score: how well spacings match expected period
        detected: bool
    """
    h, w, _ = pixels.shape
    prime_lookup = build_prime_lookup(BIT_DEPTH)
    all_pos = sample_positions_grid(h, w, WINDOW_W)

    # Scan for prime-gap markers at each grid position
    marker_present = []
    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        d1 = abs(int(pixels[r, c,  0]) - int(pixels[r, c,  1]))
        d2 = abs(int(pixels[r, tc, 0]) - int(pixels[r, tc, 1]))
        is_marker = (_is_fuzzy_prime(d1, prime_lookup, floor, prime_tol) and
                     _is_fuzzy_prime(d2, prime_lookup, floor, prime_tol))
        marker_present.append((r, c, is_marker))

    # Find gap regions (runs of non-marker positions)
    gaps_found = []
    run_start  = None
    run_len    = 0

    for i, (r, c, is_m) in enumerate(marker_present):
        if not is_m:
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= gap_min:
                gaps_found.append({
                    "start_idx": run_start,
                    "length":    run_len,
                    "row":       marker_present[run_start][0],
                    "col":       marker_present[run_start][1],
                    "raster":    marker_present[run_start][0] * w +
                                 marker_present[run_start][1],
                })
            run_start = None
            run_len   = 0

    if run_len >= gap_min and run_start is not None:
        gaps_found.append({
            "start_idx": run_start,
            "length":    run_len,
            "row":       marker_present[run_start][0],
            "col":       marker_present[run_start][1],
            "raster":    marker_present[run_start][0] * w +
                         marker_present[run_start][1],
        })

    # Measure spacing between gaps
    spacings = []
    for i in range(1, len(gaps_found)):
        spacings.append(gaps_found[i]["raster"] - gaps_found[i-1]["raster"])

    # Expected spacing
    expected_spacing = SENTINEL_CANARY_RATIO * WINDOW_W

    # Regularity score: how consistent are the spacings?
    # Perfect regularity = all spacings equal expected_spacing
    reg_score = 0.0
    if spacings:
        spacing_arr = np.array(spacings)
        mean_sp     = np.mean(spacing_arr)
        std_sp      = np.std(spacing_arr)
        # Score: fraction within 50% of expected spacing, normalized by std
        within_range = np.mean(np.abs(spacing_arr - expected_spacing) <
                               expected_spacing * 0.5)
        reg_score    = float(within_range) * (1.0 / (1.0 + std_sp / max(mean_sp, 1)))

    return {
        "n_gaps_found":         len(gaps_found),
        "gap_spacings":         spacings,
        "mean_spacing":         float(np.mean(spacings)) if spacings else 0,
        "expected_spacing":     expected_spacing,
        "regularity_score":     round(reg_score, 4),
        "detected":             reg_score > 0.5 and len(gaps_found) >= 3,
        "gaps":                 gaps_found,
    }


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    n_req = markers_for_image(h, w)

    config = MarkerConfig(
        name="compound",
        description=f"Relational/gap test — floor={FLOOR}",
        min_prime=FLOOR,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        magic_value=42,
        magic_tolerance=7,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    # Embed standard markers + absolute sentinels (for manifest QA baseline)
    marked_pixels, markers, abs_sentinels = embed_compound(
        pixels.copy(), config, variable_offset=42
    )

    if len(markers) < 10:
        return {"image": fname, "error": "too few markers"}

    # === OPTION B: embed relational sentinels ===
    # We embed BOTH absolute and relational sentinels on the same image
    # so we can directly compare survival rates on identical content.
    rel_modified = marked_pixels.copy().astype(np.int16)
    rel_sentinels = []
    rng = np.random.default_rng(42)

    n_sections = max(1, len(markers) // SENTINEL_CANARY_RATIO)
    section_size = len(markers) // n_sections

    for sec_idx in range(n_sections):
        start = sec_idx * section_size
        end   = start + section_size if sec_idx < n_sections - 1 else len(markers)

        # Entry: use first marker position's row
        if start < len(markers):
            m = markers[start]
            mersenne = int(rng.choice(MERSENNE_BASKET))
            rs = embed_relational_sentinel(
                rel_modified, m["row"], m["col"],
                mersenne, "entry"
            )
            if rs:
                rel_sentinels.append({**rs, "section": sec_idx})

        # Exit: use last marker position's row
        if end - 1 < len(markers):
            m = markers[end - 1]
            mersenne = int(rng.choice(MERSENNE_BASKET))
            rs = embed_relational_sentinel(
                rel_modified, m["row"], m["col"],
                mersenne, "exit"
            )
            if rs:
                rel_sentinels.append({**rs, "section": sec_idx})

    rel_pixels = np.clip(rel_modified, 0, 255).astype(np.uint8)

    # Gen0 JPEG (plain — no prime encode after pixel embedding)
    gen0_abs = to_jpeg(marked_pixels, quality=95)
    gen0_rel = to_jpeg(rel_pixels,    quality=95)
    gen0_clean = to_jpeg(pixels,      quality=95)

    current_abs   = gen0_abs
    current_rel   = gen0_rel
    current_clean = gen0_clean
    cascade       = []

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current_abs   = to_jpeg(decode_jpeg(current_abs),   quality=q)
            current_rel   = to_jpeg(decode_jpeg(current_rel),   quality=q)
            current_clean = to_jpeg(decode_jpeg(current_clean), quality=q)

        px_abs   = decode_jpeg(current_abs)
        px_rel   = decode_jpeg(current_rel)
        px_clean = decode_jpeg(current_clean)

        # MANIFEST QA — absolute sentinels
        abs_manifest = detect_sentinels(px_abs, abs_sentinels)

        # OPTION B — relational detection (manifest mode)
        rel_manifest = detect_relational_sentinel(px_rel, rel_sentinels)

        # OPTION D — structural gap (blind mode, on abs-embedded image)
        gap_marked = detect_gap_sentinels_blind(px_abs,  floor=FLOOR)
        gap_clean  = detect_gap_sentinels_blind(px_clean, floor=FLOOR)

        cascade.append({
            "generation":          gen_idx,
            "quality":             q,
            # Manifest QA (absolute sentinels — our canary for the canary)
            "abs_manifest_intact": abs_manifest["intact_pct"],
            "abs_manifest_class":  abs_manifest["tamper_class"],
            # Option B: relational survival
            "rel_intact_pct":      rel_manifest["intact_pct"],
            "rel_mean_residual":   rel_manifest["mean_residual"],
            "rel_n_survived":      rel_manifest["n_survived"],
            "rel_n_total":         rel_manifest["n_total"],
            # Option D: structural gap (marked)
            "gap_n_found":         gap_marked["n_gaps_found"],
            "gap_regularity":      gap_marked["regularity_score"],
            "gap_detected":        gap_marked["detected"],
            # Option D: structural gap (clean — FP check)
            "gap_fp_n_found":      gap_clean["n_gaps_found"],
            "gap_fp_regularity":   gap_clean["regularity_score"],
            "gap_fp_detected":     gap_clean["detected"],
        })

    result = {
        "image":         fname,
        "n_markers":     len(markers),
        "n_abs_sents":   len(abs_sentinels),
        "n_rel_sents":   len(rel_sentinels),
        "cascade":       cascade,
    }

    g4 = cascade[4] if len(cascade) > 4 else {}
    result["gen4_abs_manifest"]  = g4.get("abs_manifest_intact", 0.0)
    result["gen4_rel_intact"]    = g4.get("rel_intact_pct",       0.0)
    result["gen4_gap_detected"]  = g4.get("gap_detected",         False)
    result["gen4_gap_fp"]        = g4.get("gap_fp_detected",      False)

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
    print(f"RELATIONAL + STRUCTURAL GAP SENTINEL TEST")
    print(f"{'='*80}")
    print(f"Images:      {n_total}")
    print(f"Floor:       {FLOOR}")
    print(f"REL_WIDTH:   {REL_WIDTH}  (relational detection window — calibrate after drift test)")
    print(f"GAP_MIN:     {GAP_MIN_LENGTH}  (min consecutive empty positions = gap)")
    print(f"Reporting:   Abs manifest (QA) | Option B (relational) | Option D (gap)")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "relational_per_image.jsonl")
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
            abs_m = result.get("gen4_abs_manifest",  0.0)
            rel_i = result.get("gen4_rel_intact",     0.0)
            gap_d = "GAP" if result.get("gen4_gap_detected", False) else "   "
            gap_f = "FP!" if result.get("gen4_gap_fp",       False) else "   "
            print(f"abs_manifest={abs_m:>5.1f}%  rel_intact={rel_i:>5.1f}%  "
                  f"gap={gap_d}  gap_fp={gap_f}  [{elapsed:.1f}s]")
        else:
            print(f"ERROR  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start
    good = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"RELATIONAL/GAP SENTINEL AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    print(f"{'Gen':>4}  {'Q':>3}  "
          f"{'abs_manifest%':>14}  {'rel_intact%':>12}  "
          f"{'gap_det%':>9}  {'gap_FP%':>8}")
    print("─" * 65)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        def gmean(key):
            vals = [r["cascade"][gen_idx].get(key, 0)
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(vals) / len(vals) if vals else 0

        gap_det = sum(1 for r in good
                      if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("gap_detected", False))
        gap_fp  = sum(1 for r in good
                      if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("gap_fp_detected", False))

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {gmean('abs_manifest_intact'):>13.1f}%"
              f"  {gmean('rel_intact_pct'):>11.1f}%"
              f"  {gap_det/n_good*100:>8.1f}%"
              f"  {gap_fp/n_good*100:>7.1f}%")

    print(f"\n{'='*80}")
    print(f"VERDICT  (Gen4 Q40)")
    print(f"{'='*80}")

    g4_abs = np.mean([r.get("gen4_abs_manifest", 0.0) for r in good])
    g4_rel = np.mean([r.get("gen4_rel_intact",   0.0) for r in good])
    g4_gap = sum(1 for r in good if r.get("gen4_gap_detected", False))
    g4_gfp = sum(1 for r in good if r.get("gen4_gap_fp",       False))

    print(f"  Abs manifest (QA):  {g4_abs:.1f}% intact  — "
          f"{'OK' if g4_abs > 10 else 'WARNING: sentinels dying pre-cascade'}")
    print(f"  Option B relational:{g4_rel:.1f}% intact  — "
          f"{'IMPROVEMENT' if g4_rel > g4_abs else 'no improvement over absolute'}")
    print(f"  Option D gap detect:{g4_gap}/{n_good} ({g4_gap/n_good*100:.1f}%)  FP: "
          f"{g4_gfp}/{n_good} ({g4_gfp/n_good*100:.1f}%)")

    if g4_rel > g4_abs * 1.5:
        rel_verdict = f"RELATIONAL ENCODING CONFIRMED: {g4_rel:.1f}% vs {g4_abs:.1f}% absolute. Within-block correlation working."
    elif g4_rel > g4_abs:
        rel_verdict = f"RELATIONAL MARGINAL: {g4_rel:.1f}% vs {g4_abs:.1f}%. Some improvement. Check REL_WIDTH calibration."
    else:
        rel_verdict = f"RELATIONAL NO IMPROVEMENT: {g4_rel:.1f}% vs {g4_abs:.1f}%. DCT block correlation insufficient."

    print(f"\n  {rel_verdict}")

    aggregate = {
        "n_images":         n_good,
        "floor":            FLOOR,
        "rel_width":        REL_WIDTH,
        "gap_min_length":   GAP_MIN_LENGTH,
        "gen4_abs_manifest_pct": round(float(g4_abs), 1),
        "gen4_rel_intact_pct":   round(float(g4_rel), 1),
        "gen4_gap_detected_pct": round(g4_gap / n_good * 100, 1),
        "gen4_gap_fp_pct":       round(g4_gfp / n_good * 100, 1),
        "total_time":       round(total_time, 1),
    }
    with open(os.path.join(output_dir, "relational_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    with open(os.path.join(output_dir, "RELATIONAL_VERDICT.txt"), "w") as f:
        f.write(rel_verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"REL_WIDTH: {REL_WIDTH}\n")
        f.write(f"Gen4 abs manifest: {g4_abs:.1f}%\n")
        f.write(f"Gen4 rel intact: {g4_rel:.1f}%\n")
        f.write(f"Gen4 gap detection: {g4_gap/n_good*100:.1f}%\n")
        f.write(f"Gen4 gap FP: {g4_gfp/n_good*100:.1f}%\n")

    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Relational + Structural Gap Sentinel Test"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="relational_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
