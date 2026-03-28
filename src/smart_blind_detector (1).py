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
Smart Blind Detector — Single-Image Detection Without Clean Reference
======================================================================

Validated operating point (50-image corpus, March 2026):
  Floor:     43
  Density:   8% of eligible grid positions (~465 markers per 1024px image)
  PSNR:      ~41 dB
  Detection: 90% blind detection after Q40 compression
  Mechanism: spatial variance amplification (LSV + CDV detectors)

This script tests WITHOUT a clean reference image — the harder real-world
case.  Instead of comparing marked vs clean, it looks for structural
anomalies within the image itself that are characteristic of the embedding.

Detection strategy (no reference available):
  1. LSV self-scan  — compare local spatial variance at grid positions
                      against a randomised control sample from the same image.
                      Marked images show elevated variance at grid positions
                      relative to off-grid positions.
  2. CDV self-scan  — same but on channel-difference variance.
  3. Freq self-scan — prime-rate enrichment at grid positions vs off-grid.
                      Weak post-compression but included for completeness.
  4. Amplification check — lsv_ratio between grid and off-grid positions.
                            Should be > 1.0 in marked images.

Note: self-scan detection is harder than the reference comparison in
blind_detection_test.py.  The reference comparison is the production
detector.  This script is for situations where no clean baseline exists
(e.g. a detector deployed without access to the original).

Usage:
    python smart_blind_detector.py -i /path/to/DIV2K -o smart_results -n 50
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

from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound


# =============================================================================
# CONFIG
# =============================================================================

FLOOR           = 43
DENSITY_FRAC    = 0.08
LSV_RADIUS      = 2

CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512

# Detection thresholds for self-scan
LSV_RATIO_THRESHOLD  = 1.05   # grid variance / off-grid variance
FREQ_ENRICH_THRESHOLD= 1.20   # grid prime rate / off-grid prime rate
P_THRESHOLD          = 0.05   # KS test significance level


# =============================================================================
# UTILITIES
# =============================================================================

def to_jpeg(pixels, quality=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

def decode_jpeg(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))

def compute_psnr(original, modified):
    mse = np.mean((original.astype(float) - modified.astype(float)) ** 2)
    return float('inf') if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)

def grid_capacity(h, w):
    return len(sample_positions_grid(h, w, 8))

def markers_for_image(h, w):
    return max(10, math.ceil(grid_capacity(h, w) * DENSITY_FRAC))


# =============================================================================
# SELF-SCAN DETECTORS
# (no clean reference — compare grid positions against off-grid positions)
# =============================================================================

def _off_grid_positions(h, w, n_samples, rng):
    """
    Sample positions that are NOT on the 8-stride grid.
    Used as the internal control group for self-scan detection.
    """
    grid_set = set()
    for pos in sample_positions_grid(h, w, 8):
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        grid_set.add((r, c))

    off_grid = []
    attempts = 0
    while len(off_grid) < n_samples and attempts < n_samples * 20:
        r = rng.integers(LSV_RADIUS + 3, h - LSV_RADIUS - 1)
        c = rng.integers(LSV_RADIUS + 3, w - LSV_RADIUS - 1)
        if (r, c) not in grid_set:
            off_grid.append((r, c))
        attempts += 1
    return off_grid


def lsv_self_scan(pixels, radius=LSV_RADIUS, seed=0):
    """
    Compare local spatial variance at grid positions vs off-grid positions.

    In an unmarked image, both sets should have similar variance distributions
    — they're drawn from the same underlying image content distribution.

    In a marked image, grid positions show elevated variance because the
    prime-gap embedding created DCT coefficient anomalies that JPEG
    quantization amplified into spatial variance.

    Returns KS p-value, lsv_ratio (grid/off-grid), and detection bool.
    """
    h, w, _ = pixels.shape
    rng      = np.random.default_rng(seed)

    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1

    grid_vars = []
    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue

        def luma(px, rr, cc):
            p = px[rr-radius:rr+radius+1, cc-radius:cc+radius+1]
            return (299 * p[:,:,0].astype(np.int32) +
                    587 * p[:,:,1].astype(np.int32) +
                    114 * p[:,:,2].astype(np.int32)) // 1000

        grid_vars.append(float(np.var(luma(pixels, r, c).astype(np.float32))))

    if len(grid_vars) < 20:
        return 1.0, 1.0, False

    off_pos  = _off_grid_positions(h, w, len(grid_vars), rng)
    off_vars = [float(np.var(
                    ((299 * pixels[r-radius:r+radius+1, c-radius:c+radius+1, 0].astype(np.int32) +
                      587 * pixels[r-radius:r+radius+1, c-radius:c+radius+1, 1].astype(np.int32) +
                      114 * pixels[r-radius:r+radius+1, c-radius:c+radius+1, 2].astype(np.int32)) // 1000
                    ).astype(np.float32)))
                for r, c in off_pos]

    if len(off_vars) < 20:
        return 1.0, 1.0, False

    gv = np.array(grid_vars)
    ov = np.array(off_vars)
    _, p = sp_stats.ks_2samp(gv, ov)
    ratio = float(np.mean(gv)) / max(float(np.mean(ov)), 0.001)
    detected = p < P_THRESHOLD and ratio > LSV_RATIO_THRESHOLD

    return float(p), round(ratio, 4), detected


def cdv_self_scan(pixels, ch_a, ch_b, radius=LSV_RADIUS, seed=0):
    """
    Compare channel-difference variance at grid positions vs off-grid.
    Same principle as lsv_self_scan but using the channel-pair signal
    that the embedder specifically perturbed.
    """
    h, w, _ = pixels.shape
    rng      = np.random.default_rng(seed)

    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1

    grid_cdv = []
    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue
        patch = pixels[r-radius:r+radius+1, c-radius:c+radius+1]
        grid_cdv.append(float(np.var(
            np.abs(patch[:,:,ch_a].astype(np.int32) -
                   patch[:,:,ch_b].astype(np.int32)).astype(np.float32))))

    if len(grid_cdv) < 20:
        return 1.0, 1.0, False

    off_pos = _off_grid_positions(h, w, len(grid_cdv), rng)
    off_cdv = [float(np.var(
                   np.abs(pixels[r-radius:r+radius+1, c-radius:c+radius+1, ch_a].astype(np.int32) -
                          pixels[r-radius:r+radius+1, c-radius:c+radius+1, ch_b].astype(np.int32)
                          ).astype(np.float32)))
               for r, c in off_pos]

    if len(off_cdv) < 20:
        return 1.0, 1.0, False

    gv = np.array(grid_cdv)
    ov = np.array(off_cdv)
    _, p  = sp_stats.ks_2samp(gv, ov)
    ratio = float(np.mean(gv)) / max(float(np.mean(ov)), 0.001)
    detected = p < P_THRESHOLD and ratio > LSV_RATIO_THRESHOLD

    return float(p), round(ratio, 4), detected


def freq_self_scan(pixels, ch_a, ch_b, seed=0):
    """
    Compare prime-gap rate at grid positions vs off-grid positions.
    Weak post-compression but included for completeness and comparison.
    """
    h, w, _ = pixels.shape
    rng      = np.random.default_rng(seed)
    primes   = build_prime_lookup(8)
    lookup   = np.zeros(256, dtype=bool)
    for d in range(FLOOR, 256):
        if primes[d]:
            lookup[d] = True

    all_pos = sample_positions_grid(h, w, 8)
    grid_pass, grid_total = 0, 0
    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        grid_total += 1
        d1 = abs(int(pixels[r, c,  ch_a]) - int(pixels[r, c,  ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if lookup[min(d1, 255)] and lookup[min(d2, 255)]:
            grid_pass += 1

    grid_rate = grid_pass / max(grid_total, 1)

    off_pos = _off_grid_positions(h, w, grid_total, rng)
    off_pass = 0
    for r, c in off_pos:
        tc = c + 1
        if tc >= w:
            continue
        d1 = abs(int(pixels[r, c,  ch_a]) - int(pixels[r, c,  ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if lookup[min(d1, 255)] and lookup[min(d2, 255)]:
            off_pass += 1

    off_rate  = off_pass / max(len(off_pos), 1)
    enrichment= grid_rate / max(off_rate, 0.001)
    detected  = enrichment > FREQ_ENRICH_THRESHOLD

    return round(grid_rate, 6), round(off_rate, 6), round(enrichment, 4), detected


# =============================================================================
# COMBINED SELF-SCAN
# =============================================================================

def smart_scan(pixels):
    """Run all self-scan detectors. Returns flat dict."""
    d = {}

    # LSV
    lsv_p, lsv_r, lsv_det = lsv_self_scan(pixels)
    d["lsv_p"]       = lsv_p
    d["lsv_ratio"]   = lsv_r
    d["det_lsv"]     = lsv_det

    # CDV G-B
    cdv_p_gb, cdv_r_gb, cdv_det_gb = cdv_self_scan(pixels, 1, 2)
    d["cdv_p_gb"]    = cdv_p_gb
    d["cdv_ratio_gb"]= cdv_r_gb
    d["det_cdv_gb"]  = cdv_det_gb

    # CDV R-G
    cdv_p_rg, cdv_r_rg, cdv_det_rg = cdv_self_scan(pixels, 0, 1)
    d["cdv_p_rg"]    = cdv_p_rg
    d["cdv_ratio_rg"]= cdv_r_rg
    d["det_cdv_rg"]  = cdv_det_rg

    # Freq G-B
    fg_rate, fo_rate, f_enrich, f_det = freq_self_scan(pixels, 1, 2)
    d["freq_grid_rate"] = fg_rate
    d["freq_off_rate"]  = fo_rate
    d["freq_enrichment"]= f_enrich
    d["det_freq"]       = f_det

    d["det_spatial"] = d["det_lsv"] or d["det_cdv_gb"] or d["det_cdv_rg"]
    d["det_combo"]   = d["det_freq"] or d["det_spatial"]

    return d


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    n_req = markers_for_image(h, w)

    result = {
        "image":         fname,
        "dimensions":    f"{w}x{h}",
        "timestamp":     datetime.utcnow().isoformat() + "Z",
        "grid_capacity": grid_capacity(h, w),
        "n_req":         n_req,
        "floor":         FLOOR,
        "density_frac":  DENSITY_FRAC,
    }

    config = MarkerConfig(
        name="smart_blind",
        description=f"Smart blind — floor={FLOOR} density={DENSITY_FRAC}",
        min_prime=FLOOR,
        use_twins=True,
        use_rare_basket=True,
        use_magic=False,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    marked_pixels, markers = embed_compound(pixels.copy(), config, seed=42)
    n_actual = len(markers)
    result["n_actual"]  = n_actual
    result["embed_eff"] = round(n_actual / max(n_req, 1), 4)
    result["psnr"]      = round(compute_psnr(pixels, marked_pixels), 2)

    if n_actual < 10:
        result["error"] = f"Too few markers: {n_actual}"
        return result

    marked_jpeg    = to_jpeg(marked_pixels, quality=95)
    clean_jpeg     = to_jpeg(pixels,        quality=95)
    current_marked = marked_jpeg
    current_clean  = clean_jpeg

    cascade = []
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
            current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

        marked_px = decode_jpeg(current_marked)
        clean_px  = decode_jpeg(current_clean)

        marked_scan = smart_scan(marked_px)
        clean_scan  = smart_scan(clean_px)

        gen = {
            "generation":         gen_idx,
            "quality":            q,
            # Marked image detections
            "marked_det_lsv":     marked_scan["det_lsv"],
            "marked_det_cdv_gb":  marked_scan["det_cdv_gb"],
            "marked_det_spatial": marked_scan["det_spatial"],
            "marked_det_freq":    marked_scan["det_freq"],
            "marked_det_combo":   marked_scan["det_combo"],
            "marked_lsv_ratio":   marked_scan["lsv_ratio"],
            "marked_cdv_ratio_gb":marked_scan["cdv_ratio_gb"],
            "marked_freq_enrich": marked_scan["freq_enrichment"],
            # Clean image (false positive check)
            "clean_det_combo":    clean_scan["det_combo"],
            "clean_lsv_ratio":    clean_scan["lsv_ratio"],
            # True/false positive
            "TP": marked_scan["det_combo"] and not clean_scan["det_combo"],
            "FP": clean_scan["det_combo"],
            "FN": not marked_scan["det_combo"],
        }
        cascade.append(gen)

    result["cascade"] = cascade

    g4 = cascade[4] if len(cascade) > 4 else {}
    result["gen4_TP"]          = g4.get("TP",  False)
    result["gen4_FP"]          = g4.get("FP",  False)
    result["gen4_FN"]          = g4.get("FN",  True)
    result["gen4_marked_combo"]= g4.get("marked_det_combo",   False)
    result["gen4_clean_combo"] = g4.get("clean_det_combo",    False)
    result["gen4_lsv_ratio"]   = g4.get("marked_lsv_ratio",   1.0)
    result["gen4_cdv_ratio_gb"]= g4.get("marked_cdv_ratio_gb",1.0)
    result["gen4_freq_enrich"] = g4.get("marked_freq_enrich", 1.0)

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
    print(f"SMART BLIND DETECTOR — Self-Scan (No Reference)")
    print(f"{'='*80}")
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Images:     {n_total}")
    print(f"Floor:      {FLOOR}")
    print(f"Density:    {int(DENSITY_FRAC*100)}% of eligible grid positions")
    print(f"Method:     Grid positions vs off-grid control (self-scan)")
    print(f"Detectors:  LSV (local spatial variance)")
    print(f"            CDV (channel-diff variance)")
    print(f"            FREQ (prime enrichment, weak post-Q40)")
    print(f"Started:    {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "smart_blind_per_image.jsonl")
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

        if "error" in result:
            print(f"ERROR: {result['error']}  [{elapsed:.1f}s]")
        else:
            tp   = "TP" if result.get("gen4_TP", False) else "  "
            fp   = "FP!" if result.get("gen4_FP", False) else "   "
            lsvr = result.get("gen4_lsv_ratio",    1.0)
            cdvr = result.get("gen4_cdv_ratio_gb", 1.0)
            fenr = result.get("gen4_freq_enrich",  1.0)
            psnr = result.get("psnr", 0)
            n_act= result.get("n_actual", 0)
            print(f"n={n_act:>4d}  {psnr:>5.1f}dB  {tp} {fp}"
                  f"  lsv_r={lsvr:.3f}  cdv_r={cdvr:.3f}  f_enr={fenr:.3f}"
                  f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    good   = [r for r in summary_data if "error" not in r and "cascade" in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"SMART BLIND DETECTOR — AGGREGATE  ({n_good} images)")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    print(f"{'Gen':>4}  {'Q':>3}  {'TP%':>6}  {'FP%':>6}  {'FN%':>6}"
          f"  {'lsv_r':>6}  {'cdv_r':>6}  {'f_enr':>6}")
    print("─" * 60)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        n_tp = sum(1 for r in good if len(r["cascade"]) > gen_idx
                   and r["cascade"][gen_idx].get("TP", False))
        n_fp = sum(1 for r in good if len(r["cascade"]) > gen_idx
                   and r["cascade"][gen_idx].get("FP", False))
        n_fn = sum(1 for r in good if len(r["cascade"]) > gen_idx
                   and r["cascade"][gen_idx].get("FN", True))
        lsvr = np.mean([r["cascade"][gen_idx].get("marked_lsv_ratio",    1.0)
                        for r in good if len(r["cascade"]) > gen_idx])
        cdvr = np.mean([r["cascade"][gen_idx].get("marked_cdv_ratio_gb", 1.0)
                        for r in good if len(r["cascade"]) > gen_idx])
        fenr = np.mean([r["cascade"][gen_idx].get("marked_freq_enrich",  1.0)
                        for r in good if len(r["cascade"]) > gen_idx])

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {n_tp/n_good*100:>5.1f}%"
              f"  {n_fp/n_good*100:>5.1f}%"
              f"  {n_fn/n_good*100:>5.1f}%"
              f"  {lsvr:>6.3f}  {cdvr:>6.3f}  {fenr:>6.3f}")

    g4_tp   = sum(1 for r in good if r.get("gen4_TP", False))
    g4_fp   = sum(1 for r in good if r.get("gen4_FP", False))
    g4_lsvr = np.mean([r.get("gen4_lsv_ratio",    1.0) for r in good])
    g4_cdvr = np.mean([r.get("gen4_cdv_ratio_gb", 1.0) for r in good])
    tp_pct  = g4_tp / n_good * 100
    fp_pct  = g4_fp / n_good * 100

    print(f"\n{'='*80}")
    print(f"SMART BLIND VERDICT (Gen4 Q40 — self-scan, no reference)")
    print(f"{'='*80}")
    print(f"  True Positives:   {g4_tp}/{n_good} ({tp_pct:.1f}%)")
    print(f"  False Positives:  {g4_fp}/{n_good} ({fp_pct:.1f}%)")
    print(f"  Gen4 lsv_ratio:   {g4_lsvr:.4f}")
    print(f"  Gen4 cdv_ratio:   {g4_cdvr:.4f}")
    print()

    if tp_pct >= 80 and fp_pct < 10:
        verdict = (f"SELF-SCAN WORKS. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP "
                   f"(lsv_ratio={g4_lsvr:.3f}).")
    elif tp_pct >= 60 and fp_pct < 20:
        verdict = (f"SELF-SCAN VIABLE. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP. "
                   f"Reference detector preferred when available.")
    elif tp_pct >= 40:
        verdict = (f"SELF-SCAN MARGINAL. {tp_pct:.1f}% TP, {fp_pct:.1f}% FP. "
                   f"Use reference detector (blind_detection_test.py) for production.")
    else:
        verdict = (f"SELF-SCAN INSUFFICIENT. {tp_pct:.1f}% TP. "
                   f"No-reference detection at this density requires higher marker count.")

    print(f"  {verdict}")

    with open(os.path.join(output_dir, "SMART_BLIND_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Floor: {FLOOR}  Density: {int(DENSITY_FRAC*100)}%\n")
        f.write(f"Gen4 TP: {tp_pct:.1f}%  FP: {fp_pct:.1f}%\n")
        f.write(f"Gen4 lsv_ratio: {g4_lsvr:.4f}\n")

    aggregate = {
        "n_images":          n_good,
        "floor":             FLOOR,
        "density_frac":      DENSITY_FRAC,
        "gen4_TP_pct":       round(tp_pct, 1),
        "gen4_FP_pct":       round(fp_pct, 1),
        "gen4_lsv_ratio":    round(g4_lsvr, 4),
        "gen4_cdv_ratio_gb": round(g4_cdvr, 4),
        "total_time":        round(total_time, 1),
    }
    with open(os.path.join(output_dir, "smart_blind_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Smart Blind Detector — Self-Scan (No Reference)"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="smart_blind_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
