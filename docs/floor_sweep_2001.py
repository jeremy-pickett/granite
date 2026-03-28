#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Floor Sweep at 2000 Markers — Finding the Sweet Spot
======================================================

v2: Adds local spatial variance (LSV) detection alongside the existing
frequency KS test. The hypothesis:

  GRANITE UNDER SANDSTONE — After heavy JPEG compression (Q40), marked
  positions create quantization artifacts because the prime-gap-perturbed
  values produce anomalous DCT coefficients. The compressor can't smooth
  them away cleanly. This means local spatial variance INCREASES at marked
  positions under compression, while decreasing at clean positions.

  The adversary who compresses to destroy the frequency signal is building
  the spatial variance detection signal.

New metrics added per generation per floor:
  lsv_p_g      KS p-value: local variance distribution (green channel)
  lsv_p_luma   KS p-value: local variance distribution (luminance)
  lsv_stat     KS statistic (larger = more separation)
  lsv_ratio    mean local variance ratio (marked / clean)
  det_lsv      bool: lsv_p_g < 0.05
  det_combo    bool: det_any (freq) OR det_lsv (spatial)

Usage:
    python floor_sweep_2000.py -i /path/to/DIV2K -o floor_results -n 50
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

FLOORS         = [23, 29, 37, 43, 53]
N_MARKERS      = 2000
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION  = 512

# Local variance neighborhood radius (pixels on each side)
LSV_RADIUS     = 2   # 5x5 patch = 25 pixels; balanced between signal and noise


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
    if mse == 0:
        return float('inf')
    return 10 * np.log10(255.0 ** 2 / mse)


# =============================================================================
# FREQUENCY DETECTOR (existing)
# =============================================================================

def blind_aggregate_ks(marked_px, clean_px, ch_a, ch_b):
    """KS test comparing channel-distance distributions (marked vs clean)."""
    h, w, _ = marked_px.shape
    all_pos = sample_positions_grid(h, w, 8)

    marked_dists = []
    clean_dists = []

    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        marked_dists.extend([
            abs(int(marked_px[r,  c, ch_a]) - int(marked_px[r,  c, ch_b])),
            abs(int(marked_px[r, tc, ch_a]) - int(marked_px[r, tc, ch_b])),
        ])
        clean_dists.extend([
            abs(int(clean_px[r,  c, ch_a]) - int(clean_px[r,  c, ch_b])),
            abs(int(clean_px[r, tc, ch_a]) - int(clean_px[r, tc, ch_b])),
        ])

    if len(marked_dists) < 20:
        return 1.0, 0.0
    ks_stat, ks_p = sp_stats.ks_2samp(marked_dists, clean_dists)
    return float(ks_p), float(ks_stat)


def measure_prime_rates(pixels, ch_a, ch_b, floor):
    """Mean twin-prime rate at eligible positions for primes >= floor."""
    h, w, _ = pixels.shape
    primes   = build_prime_lookup(8)
    max_val  = 255

    lookup = np.zeros(max_val + 1, dtype=bool)
    for d in range(floor, max_val + 1):
        if primes[d]:
            lookup[d] = True

    all_pos  = sample_positions_grid(h, w, 8)
    twin_pass = 0
    total     = 0

    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        total += 1
        d1 = abs(int(pixels[r,  c, ch_a]) - int(pixels[r,  c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if lookup[min(d1, max_val)] and lookup[min(d2, max_val)]:
            twin_pass += 1

    return twin_pass / total if total > 0 else 0.0, twin_pass, total


# =============================================================================
# SPATIAL VARIANCE DETECTOR (new)
# =============================================================================

def _luma(px, r, c):
    """Fast integer luminance approximation (BT.601, no float multiply)."""
    # (299*R + 587*G + 114*B) / 1000 — use shifts to avoid floats
    return (299 * int(px[r, c, 0]) +
            587 * int(px[r, c, 1]) +
            114 * int(px[r, c, 2])) // 1000


def local_variance_ks(marked_px, clean_px, radius=LSV_RADIUS):
    """
    KS test on the distribution of LOCAL SPATIAL VARIANCES.

    For every eligible grid position, compute the variance of pixel
    luminance in a (2*radius+1)^2 neighbourhood.  Compare marked vs clean.

    Hypothesis: after heavy JPEG compression the prime-gap perturbations
    create DCT-coefficient anomalies that manifest as elevated local
    variance at exactly those positions.  The KS test on the variance
    distributions should therefore be significant even when the direct
    channel-distance frequency test is not (rate_ratio < 1).

    Returns
    -------
    ks_p_luma  : float   p-value (luma channel)
    ks_p_g     : float   p-value (green channel only — faster proxy)
    ks_stat    : float   KS statistic (luma)
    lsv_ratio  : float   mean(marked variances) / mean(clean variances)
    """
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)

    marked_luma_vars = []
    clean_luma_vars  = []
    marked_g_vars    = []
    clean_g_vars     = []

    r_min = radius + 3
    r_max = h - radius - 1
    c_min = radius + 3
    c_max = w - radius - 1

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue

        # Green-channel variance (fast)
        m_g = marked_px[r - radius:r + radius + 1,
                        c - radius:c + radius + 1, 1].astype(np.float32)
        c_g = clean_px[r - radius:r + radius + 1,
                       c - radius:c + radius + 1, 1].astype(np.float32)
        marked_g_vars.append(float(np.var(m_g)))
        clean_g_vars.append(float(np.var(c_g)))

        # Luma variance
        m_l = (299 * marked_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 0].astype(np.int32) +
               587 * marked_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 1].astype(np.int32) +
               114 * marked_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 2].astype(np.int32)) // 1000
        c_l = (299 * clean_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 0].astype(np.int32) +
               587 * clean_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 1].astype(np.int32) +
               114 * clean_px[r - radius:r + radius + 1,
                               c - radius:c + radius + 1, 2].astype(np.int32)) // 1000
        marked_luma_vars.append(float(np.var(m_l.astype(np.float32))))
        clean_luma_vars.append(float(np.var(c_l.astype(np.float32))))

    if len(marked_luma_vars) < 20:
        return 1.0, 1.0, 0.0, 1.0

    mv = np.array(marked_luma_vars)
    cv = np.array(clean_luma_vars)
    gv_m = np.array(marked_g_vars)
    gv_c = np.array(clean_g_vars)

    ks_stat_luma, ks_p_luma = sp_stats.ks_2samp(mv, cv)
    _,            ks_p_g    = sp_stats.ks_2samp(gv_m, gv_c)

    # Ratio: do marked positions have higher local variance on average?
    lsv_ratio = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)

    return float(ks_p_luma), float(ks_p_g), float(ks_stat_luma), lsv_ratio


# =============================================================================
# CHANNEL-DIFFERENCE VARIANCE (hybrid: spatial variance of channel distances)
# =============================================================================

def channel_diff_variance_ks(marked_px, clean_px, ch_a, ch_b, radius=LSV_RADIUS):
    """
    Compute the LOCAL VARIANCE of CHANNEL DISTANCES in a neighbourhood.

    This combines both signals:
      - It uses the prime-gap channel difference as the base signal
      - It measures whether that difference is locally *inconsistent*

    A smooth natural region has consistent channel differences across
    neighbours.  A marked region has one or two positions with different
    channel differences (the prime-gap value), creating elevated local
    variance of channel differences.

    After JPEG compression, the prime value leaks into neighbouring pixels
    via DCT basis overlap, which should further increase this local
    channel-difference variance.
    """
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)

    marked_cdv = []
    clean_cdv  = []

    r_min = radius + 3
    r_max = h - radius - 1
    c_min = radius + 3
    c_max = w - radius - 1

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue

        # Channel difference patch
        m_patch = marked_px[r - radius:r + radius + 1,
                            c - radius:c + radius + 1]
        c_patch = clean_px[r - radius:r + radius + 1,
                           c - radius:c + radius + 1]

        m_cd = np.abs(m_patch[:, :, ch_a].astype(np.int32) -
                      m_patch[:, :, ch_b].astype(np.int32))
        c_cd = np.abs(c_patch[:, :, ch_a].astype(np.int32) -
                      c_patch[:, :, ch_b].astype(np.int32))

        marked_cdv.append(float(np.var(m_cd.astype(np.float32))))
        clean_cdv.append(float(np.var(c_cd.astype(np.float32))))

    if len(marked_cdv) < 20:
        return 1.0, 0.0, 1.0

    mv = np.array(marked_cdv)
    cv = np.array(clean_cdv)
    ks_stat, ks_p = sp_stats.ks_2samp(mv, cv)
    cdv_ratio = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)

    return float(ks_p), float(ks_stat), cdv_ratio


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w = pixels.shape[:2]
    result = {
        "image":      fname,
        "dimensions": f"{w}x{h}",
    }

    clean_jpeg = to_jpeg(pixels, 95)

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

        marked_pixels, markers = embed_compound(pixels.copy(), config, seed=42)
        n_actual = len(markers)
        psnr     = compute_psnr(pixels, marked_pixels)

        marked_jpeg = to_jpeg(marked_pixels, 95)

        fkey = f"f{floor}"
        result[f"{fkey}_n_actual"] = n_actual
        result[f"{fkey}_psnr"]     = round(psnr, 2)

        current_marked = marked_jpeg
        current_clean  = clean_jpeg

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            if gen_idx > 0:
                current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
                current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

            marked_px = decode_jpeg(current_marked)
            clean_px  = decode_jpeg(current_clean)

            # ── Frequency detector (existing) ──────────────────────────────
            ks_p_gb,  ks_stat_gb  = blind_aggregate_ks(marked_px, clean_px, 1, 2)
            ks_p_rg,  _           = blind_aggregate_ks(marked_px, clean_px, 0, 1)
            marked_rate, _, _     = measure_prime_rates(marked_px, 1, 2, floor)
            clean_rate,  _, _     = measure_prime_rates(clean_px,  1, 2, floor)
            rate_ratio            = marked_rate / max(clean_rate, 0.0001)

            det_freq_gb  = ks_p_gb  < 0.05
            det_freq_rg  = ks_p_rg  < 0.05
            det_freq_any = det_freq_gb or det_freq_rg

            # ── Spatial variance detector (new) ────────────────────────────
            lsv_p_luma, lsv_p_g, lsv_stat, lsv_ratio = local_variance_ks(
                marked_px, clean_px)

            cdv_p_gb, cdv_stat_gb, cdv_ratio_gb = channel_diff_variance_ks(
                marked_px, clean_px, 1, 2)
            cdv_p_rg, _,          _             = channel_diff_variance_ks(
                marked_px, clean_px, 0, 1)

            det_lsv       = lsv_p_g  < 0.05   # spatial luma/green variance
            det_cdv_gb    = cdv_p_gb < 0.05    # channel-diff variance G-B
            det_cdv_rg    = cdv_p_rg < 0.05    # channel-diff variance R-G
            det_spatial   = det_lsv or det_cdv_gb or det_cdv_rg
            det_combo     = det_freq_any or det_spatial

            gkey = f"{fkey}_g{gen_idx}"
            result[f"{gkey}_ks_gb"]       = ks_p_gb
            result[f"{gkey}_ks_rg"]       = ks_p_rg
            result[f"{gkey}_stat_gb"]     = round(ks_stat_gb, 6)
            result[f"{gkey}_marked_rate"] = round(marked_rate, 6)
            result[f"{gkey}_clean_rate"]  = round(clean_rate,  6)
            result[f"{gkey}_rate_ratio"]  = round(rate_ratio,  4)
            result[f"{gkey}_det_gb"]      = det_freq_gb
            result[f"{gkey}_det_rg"]      = det_freq_rg
            result[f"{gkey}_det_any"]     = det_freq_any

            result[f"{gkey}_lsv_p_luma"]  = lsv_p_luma
            result[f"{gkey}_lsv_p_g"]     = lsv_p_g
            result[f"{gkey}_lsv_stat"]    = round(lsv_stat, 6)
            result[f"{gkey}_lsv_ratio"]   = round(lsv_ratio, 4)
            result[f"{gkey}_cdv_p_gb"]    = cdv_p_gb
            result[f"{gkey}_cdv_p_rg"]    = cdv_p_rg
            result[f"{gkey}_cdv_stat_gb"] = round(cdv_stat_gb, 6)
            result[f"{gkey}_cdv_ratio_gb"]= round(cdv_ratio_gb, 4)
            result[f"{gkey}_det_lsv"]     = det_lsv
            result[f"{gkey}_det_cdv_gb"]  = det_cdv_gb
            result[f"{gkey}_det_cdv_rg"]  = det_cdv_rg
            result[f"{gkey}_det_spatial"] = det_spatial
            result[f"{gkey}_det_combo"]   = det_combo

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
    print(f"FLOOR SWEEP AT 2000 MARKERS  (v2 — spatial variance detection)")
    print(f"{'='*80}")
    print(f"Images:     {n_total}")
    print(f"Markers:    {N_MARKERS}")
    print(f"Floors:     {FLOORS}")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"LSV radius: {LSV_RADIUS}")
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
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"  SKIP (too small)")
            continue

        max_dim = max(h, w)
        if max_dim > 1024:
            scale = 1024 / max_dim
            img    = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        if "error" not in result:
            for floor in FLOORS:
                fkey = f"f{floor}"
                psnr  = result.get(f"{fkey}_psnr", 0)
                n_act = result.get(f"{fkey}_n_actual", 0)
                g4_freq  = "F" if result.get(f"{fkey}_g4_det_any",   False) else "."
                g4_spat  = "S" if result.get(f"{fkey}_g4_det_spatial", False) else "."
                g4_combo = "C" if result.get(f"{fkey}_g4_det_combo",  False) else "."
                lsv_r    = result.get(f"{fkey}_g4_lsv_ratio",    1.0)
                cdv_r    = result.get(f"{fkey}_g4_cdv_ratio_gb", 1.0)
                rr       = result.get(f"{fkey}_g4_rate_ratio",   1.0)
                print(f"  f{floor:>2d}  n={n_act:>4d}  {psnr:>5.1f}dB"
                      f"  freq={g4_freq} spat={g4_spat} combo={g4_combo}"
                      f"  rr={rr:.3f}  lsv_r={lsv_r:.3f}  cdv_r={cdv_r:.3f}")

        print(f"  [{elapsed:.1f}s]")

        summary_data.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start

    # =========================================================================
    # AGGREGATE
    # =========================================================================
    good   = [r for r in summary_data if "error" not in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"FLOOR SWEEP RESULTS (v2)  —  {n_good} images  /  {N_MARKERS} markers")
    print(f"Total time: {total_time:.0f}s")
    print(f"{'='*80}\n")

    if n_good == 0:
        print("No valid results.")
        return

    # Detection rate table
    header = (f"{'Floor':>5}  {'Actual':>6}  {'PSNR':>6}"
              f"  {'G0 combo':>9}"
              f"  {'G4 freq':>8}  {'G4 spat':>8}  {'G4 combo':>9}"
              f"  {'lsv_r':>6}  {'cdv_r':>6}  {'rr':>6}")
    print(header)
    print("─" * len(header))

    summary_json = []

    for floor in FLOORS:
        fkey = f"f{floor}"

        actuals = [r.get(f"{fkey}_n_actual", 0)   for r in good]
        psnrs   = [r.get(f"{fkey}_psnr",    0.0)  for r in good]

        g0_combo = sum(1 for r in good if r.get(f"{fkey}_g0_det_combo",   False))
        g4_freq  = sum(1 for r in good if r.get(f"{fkey}_g4_det_any",     False))
        g4_spat  = sum(1 for r in good if r.get(f"{fkey}_g4_det_spatial", False))
        g4_combo = sum(1 for r in good if r.get(f"{fkey}_g4_det_combo",   False))

        lsv_ratios  = [r.get(f"{fkey}_g4_lsv_ratio",    1.0) for r in good]
        cdv_ratios  = [r.get(f"{fkey}_g4_cdv_ratio_gb", 1.0) for r in good]
        rate_ratios = [r.get(f"{fkey}_g4_rate_ratio",   1.0) for r in good]

        mean_actual = np.mean(actuals)
        mean_psnr   = np.mean(psnrs)
        mean_lsv    = np.mean(lsv_ratios)
        mean_cdv    = np.mean(cdv_ratios)
        mean_rr     = np.mean(rate_ratios)

        def pct(n):
            return f"{n:>3d}/{n_good} {n/n_good*100:>3.0f}%"

        print(f"{floor:>5d}  {mean_actual:>6.0f}  {mean_psnr:>5.1f}dB"
              f"  {pct(g0_combo):>9}"
              f"  {pct(g4_freq):>8}  {pct(g4_spat):>8}  {pct(g4_combo):>9}"
              f"  {mean_lsv:>6.3f}  {mean_cdv:>6.3f}  {mean_rr:>6.3f}")

        summary_json.append({
            "floor":          floor,
            "mean_actual":    round(mean_actual),
            "mean_psnr":      round(mean_psnr, 2),
            "g0_combo_pct":   round(g0_combo  / n_good * 100, 1),
            "g4_freq_pct":    round(g4_freq   / n_good * 100, 1),
            "g4_spatial_pct": round(g4_spat   / n_good * 100, 1),
            "g4_combo_pct":   round(g4_combo  / n_good * 100, 1),
            "g4_lsv_ratio":   round(mean_lsv, 4),
            "g4_cdv_ratio":   round(mean_cdv, 4),
            "g4_rate_ratio":  round(mean_rr,  4),
        })

    # Per-generation breakdown for best floor (f53)
    print(f"\nPer-generation detection breakdown (all detectors, floor=53):")
    print(f"{'Gen':>4}  {'Q':>3}  {'freq%':>6}  {'spat%':>6}  {'combo%':>7}"
          f"  {'lsv_r':>6}  {'cdv_r':>6}  {'rr':>6}")
    print("─" * 60)
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        gkey = f"f53_g{gen_idx}"
        n_freq  = sum(1 for r in good if r.get(f"{gkey}_det_any",     False))
        n_spat  = sum(1 for r in good if r.get(f"{gkey}_det_spatial", False))
        n_combo = sum(1 for r in good if r.get(f"{gkey}_det_combo",   False))
        lsv_r   = np.mean([r.get(f"{gkey}_lsv_ratio",    1.0) for r in good])
        cdv_r   = np.mean([r.get(f"{gkey}_cdv_ratio_gb", 1.0) for r in good])
        rr      = np.mean([r.get(f"{gkey}_rate_ratio",   1.0) for r in good])
        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {n_freq/n_good*100:>5.1f}%"
              f"  {n_spat/n_good*100:>5.1f}%"
              f"  {n_combo/n_good*100:>6.1f}%"
              f"  {lsv_r:>6.3f}  {cdv_r:>6.3f}  {rr:>6.3f}")

    # LSV/CDV ratio progression — does spatial variance INCREASE under compression?
    print(f"\nSpatial variance ratio progression (marked/clean) — THE KEY TEST")
    print(f"  lsv_ratio > 1.0 confirms granite-under-sandstone amplification")
    print(f"{'Floor':>5}  {'G0':>7}  {'G1':>7}  {'G2':>7}  {'G3':>7}  {'G4':>7}")
    print("─" * 50)
    for floor in FLOORS:
        fkey = f"f{floor}"
        vals = []
        for gen_idx in range(5):
            gkey = f"{fkey}_g{gen_idx}"
            vals.append(np.mean([r.get(f"{gkey}_lsv_ratio", 1.0) for r in good]))
        print(f"{floor:>5d}  " + "  ".join(f"{v:>7.4f}" for v in vals))

    print(f"\nChannel-diff variance ratio progression:")
    print(f"{'Floor':>5}  {'G0':>7}  {'G1':>7}  {'G2':>7}  {'G3':>7}  {'G4':>7}")
    print("─" * 50)
    for floor in FLOORS:
        fkey = f"f{floor}"
        vals = []
        for gen_idx in range(5):
            gkey = f"{fkey}_g{gen_idx}"
            vals.append(np.mean([r.get(f"{gkey}_cdv_ratio_gb", 1.0) for r in good]))
        print(f"{floor:>5d}  " + "  ".join(f"{v:>7.4f}" for v in vals))

    # =========================================================================
    # VERDICT
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"FLOOR SWEEP VERDICT (v2)")
    print(f"{'='*80}")

    best = max(summary_json, key=lambda s: s["g4_combo_pct"], default=None)

    if best:
        combo = best["g4_combo_pct"]
        freq  = best["g4_freq_pct"]
        spat  = best["g4_spatial_pct"]
        psnr  = best["mean_psnr"]

        print(f"  Best floor:    {best['floor']}")
        print(f"  PSNR:          {psnr:.2f}dB")
        print(f"  G4 freq only:  {freq:.1f}%")
        print(f"  G4 spatial:    {spat:.1f}%")
        print(f"  G4 combo:      {combo:.1f}%")
        print(f"  G4 lsv_ratio:  {best['g4_lsv_ratio']:.4f}  (>1 = amplification confirmed)")
        print(f"  G4 cdv_ratio:  {best['g4_cdv_ratio']:.4f}")
        print(f"  G4 rate_ratio: {best['g4_rate_ratio']:.4f}  (freq signal; <1 = degrading)")

        if combo > 85 and psnr > 40:
            verdict = (f"SWEET SPOT FOUND. Floor {best['floor']}: "
                       f"{combo:.1f}% blind detection at {psnr:.2f}dB PSNR.")
        elif combo > 85:
            verdict = (f"STRONG DETECTION. Floor {best['floor']}: "
                       f"{combo:.1f}% at {psnr:.2f}dB. PSNR below 40dB target.")
        elif combo > 70:
            verdict = (f"DETECTION WORKS. Floor {best['floor']}: "
                       f"{combo:.1f}% combo (freq={freq:.1f}% spat={spat:.1f}%).")
        elif combo > 50:
            verdict = (f"DETECTION VIABLE. Floor {best['floor']}: "
                       f"{combo:.1f}% — spatial detector contributing {spat:.1f}%.")
        else:
            verdict = (f"NEEDS WORK. Best combo={combo:.1f}%. "
                       f"Spatial={spat:.1f}% Freq={freq:.1f}%.")

        # Specific note on amplification
        if best['g4_lsv_ratio'] > 1.05:
            verdict += (f" Amplification CONFIRMED: lsv_ratio={best['g4_lsv_ratio']:.3f}.")
        elif best['g4_lsv_ratio'] > 1.0:
            verdict += f" Weak amplification: lsv_ratio={best['g4_lsv_ratio']:.3f}."
        else:
            verdict += f" No amplification yet: lsv_ratio={best['g4_lsv_ratio']:.3f}."
    else:
        verdict = "NO RESULTS."

    print(f"\n  {verdict}")

    with open(os.path.join(output_dir, "FLOOR_SWEEP_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Markers: {N_MARKERS}\n")
        f.write(f"Floors tested: {FLOORS}\n")
        f.write(f"LSV radius: {LSV_RADIUS}\n")

    with open(os.path.join(output_dir, "floor_sweep_summary.json"), "w") as f:
        json.dump(summary_json, f, indent=2)

    return summary_json


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Floor Sweep at 2000 Markers (v2 — spatial variance)"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="floor_sweep_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
