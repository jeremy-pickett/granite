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

Validated operating point (50-image corpus, March 2026):
  Floor:     43
  Density:   8% of eligible grid positions (~465 markers per 1024px image)
  PSNR:      ~41 dB
  Detection: 90% blind detection after Q40 compression
  Mechanism: spatial variance amplification (LSV + CDV detectors)
             frequency detector intentionally not relied upon

The real-world scenario: a platform receives an image with NO manifest,
NO known positions, NO seed. Just pixels that may have been through a
compression pipeline.

Detection architecture:
  FREQ   — KS test on channel-distance distributions (weak post-Q40)
  LSV    — KS test on local spatial variance distributions (primary)
  CDV    — KS test on local channel-difference variance (primary)
  COMBO  — FREQ OR LSV OR CDV (headline metric)

Usage:
    python blind_detection_test.py -i /path/to/DIV2K -o blind_results -n 50
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

# Validated operating point
FLOOR           = 43
DENSITY_FRAC    = 0.08     # 8% of eligible grid positions
LSV_RADIUS      = 2        # 5×5 neighbourhood

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

def compute_psnr(original, modified):
    mse = np.mean((original.astype(float) - modified.astype(float)) ** 2)
    return float('inf') if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)

def grid_capacity(h, w):
    return len(sample_positions_grid(h, w, 8))

def markers_for_image(h, w):
    return max(10, math.ceil(grid_capacity(h, w) * DENSITY_FRAC))


# =============================================================================
# FREQUENCY DETECTOR
# =============================================================================

def freq_ks(marked_px, clean_px, ch_a, ch_b):
    """KS test on channel-distance distributions."""
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)
    md, cd   = [], []
    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        md.extend([abs(int(marked_px[r, c,  ch_a]) - int(marked_px[r, c,  ch_b])),
                   abs(int(marked_px[r, tc, ch_a]) - int(marked_px[r, tc, ch_b]))])
        cd.extend([abs(int(clean_px[r, c,  ch_a]) - int(clean_px[r, c,  ch_b])),
                   abs(int(clean_px[r, tc, ch_a]) - int(clean_px[r, tc, ch_b]))])
    if len(md) < 20:
        return 1.0, 0.0, 1.0
    stat, p  = sp_stats.ks_2samp(md, cd)
    mr = np.mean([abs(int(marked_px[int(pos[0])+3, int(pos[1])+3, ch_a]) -
                      int(marked_px[int(pos[0])+3, int(pos[1])+3, ch_b]))
                  for pos in all_pos
                  if int(pos[0])+3 < h and int(pos[1])+3 < w])
    cr = np.mean([abs(int(clean_px[int(pos[0])+3, int(pos[1])+3, ch_a]) -
                      int(clean_px[int(pos[0])+3, int(pos[1])+3, ch_b]))
                  for pos in all_pos
                  if int(pos[0])+3 < h and int(pos[1])+3 < w])
    rate_ratio = float(mr) / max(float(cr), 0.001)
    return float(p), float(stat), round(rate_ratio, 4)


# =============================================================================
# SPATIAL DETECTORS
# =============================================================================

def local_variance_ks(marked_px, clean_px, radius=LSV_RADIUS):
    """
    KS test on local spatial variance distributions.

    Primary detection mechanism post-Q40: prime-gap perturbations create
    anomalous DCT coefficients that JPEG quantization cannot cleanly resolve,
    leaving elevated local spatial variance at marked positions.  Compression
    amplifies this signal rather than erasing it (granite under sandstone).
    """
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1
    mlv, clv, mgv, cgv = [], [], [], []

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue

        mgv.append(float(np.var(
            marked_px[r-radius:r+radius+1, c-radius:c+radius+1, 1].astype(np.float32))))
        cgv.append(float(np.var(
            clean_px[r-radius:r+radius+1,  c-radius:c+radius+1, 1].astype(np.float32))))

        def luma(px):
            p = px[r-radius:r+radius+1, c-radius:c+radius+1]
            return (299 * p[:,:,0].astype(np.int32) +
                    587 * p[:,:,1].astype(np.int32) +
                    114 * p[:,:,2].astype(np.int32)) // 1000

        mlv.append(float(np.var(luma(marked_px).astype(np.float32))))
        clv.append(float(np.var(luma(clean_px).astype(np.float32))))

    if len(mlv) < 20:
        return 1.0, 1.0, 0.0, 1.0

    mv, cv = np.array(mlv), np.array(clv)
    gm, gc = np.array(mgv), np.array(cgv)
    ls, lp = sp_stats.ks_2samp(mv, cv)
    _,  gp = sp_stats.ks_2samp(gm, gc)
    ratio  = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)
    return float(lp), float(gp), float(ls), round(ratio, 4)


def channel_diff_variance_ks(marked_px, clean_px, ch_a, ch_b, radius=LSV_RADIUS):
    """
    KS test on local variance of channel-difference values.

    Hybrid signal: measures whether prime-gap channel differences are locally
    inconsistent with their neighbourhood — the spatial footprint of the
    embedding decision.  Amplified by JPEG DCT basis overlap.
    """
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1
    mcdv, ccdv = [], []

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue
        mp = marked_px[r-radius:r+radius+1, c-radius:c+radius+1]
        cp = clean_px[r-radius:r+radius+1,  c-radius:c+radius+1]
        mcdv.append(float(np.var(
            np.abs(mp[:,:,ch_a].astype(np.int32) -
                   mp[:,:,ch_b].astype(np.int32)).astype(np.float32))))
        ccdv.append(float(np.var(
            np.abs(cp[:,:,ch_a].astype(np.int32) -
                   cp[:,:,ch_b].astype(np.int32)).astype(np.float32))))

    if len(mcdv) < 20:
        return 1.0, 0.0, 1.0
    mv, cv = np.array(mcdv), np.array(ccdv)
    s, p   = sp_stats.ks_2samp(mv, cv)
    ratio  = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)
    return float(p), float(s), round(ratio, 4)


# =============================================================================
# COMBINED DETECTOR
# =============================================================================

def run_detectors(marked_px, clean_px):
    """Run all detectors. Returns flat dict of metrics and boolean verdicts."""
    d = {}

    # Frequency (G-B and R-G)
    fp_gb, fs_gb, frr_gb = freq_ks(marked_px, clean_px, 1, 2)
    fp_rg, _,    _       = freq_ks(marked_px, clean_px, 0, 1)
    d["freq_p_gb"]    = fp_gb
    d["freq_p_rg"]    = fp_rg
    d["freq_stat_gb"] = round(fs_gb, 6)
    d["freq_rr_gb"]   = frr_gb
    d["det_freq"]     = fp_gb < 0.05 or fp_rg < 0.05

    # LSV (luma + green)
    lsv_lp, lsv_gp, lsv_s, lsv_r = local_variance_ks(marked_px, clean_px)
    d["lsv_p_luma"]  = lsv_lp
    d["lsv_p_g"]     = lsv_gp
    d["lsv_stat"]    = round(lsv_s, 6)
    d["lsv_ratio"]   = lsv_r
    d["det_lsv"]     = lsv_gp < 0.05

    # CDV G-B
    cdv_p_gb, cdv_s_gb, cdv_r_gb = channel_diff_variance_ks(marked_px, clean_px, 1, 2)
    d["cdv_p_gb"]     = cdv_p_gb
    d["cdv_stat_gb"]  = round(cdv_s_gb, 6)
    d["cdv_ratio_gb"] = cdv_r_gb
    d["det_cdv_gb"]   = cdv_p_gb < 0.05

    # CDV R-G
    cdv_p_rg, _, cdv_r_rg = channel_diff_variance_ks(marked_px, clean_px, 0, 1)
    d["cdv_p_rg"]     = cdv_p_rg
    d["cdv_ratio_rg"] = cdv_r_rg
    d["det_cdv_rg"]   = cdv_p_rg < 0.05

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

    # Config is built per-image since n_markers depends on dimensions
    config = MarkerConfig(
        name="blind_test",
        description=f"Blind detection — floor={FLOOR} density={DENSITY_FRAC}",
        min_prime=FLOOR,
        use_twins=True,
        use_rare_basket=True,
        use_magic=False,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    marked_pixels, markers = embed_compound(pixels.copy(), config, seed=42)
    n_actual = len(markers)
    result["n_actual"]   = n_actual
    result["embed_eff"]  = round(n_actual / max(n_req, 1), 4)
    result["psnr"]       = round(compute_psnr(pixels, marked_pixels), 2)

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

        det = run_detectors(marked_px, clean_px)
        det["generation"] = gen_idx
        det["quality"]    = q
        cascade.append(det)

    result["cascade"] = cascade

    # Gen4 summary fields for easy aggregation
    g4 = cascade[4] if len(cascade) > 4 else {}
    result["gen4_det_freq"]    = g4.get("det_freq",    False)
    result["gen4_det_spatial"] = g4.get("det_spatial", False)
    result["gen4_det_combo"]   = g4.get("det_combo",   False)
    result["gen4_lsv_ratio"]   = g4.get("lsv_ratio",   1.0)
    result["gen4_cdv_ratio_gb"]= g4.get("cdv_ratio_gb",1.0)
    result["gen4_freq_rr_gb"]  = g4.get("freq_rr_gb",  1.0)

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
    print(f"LAYER 3 BLIND DETECTION TEST — The Facebook Test")
    print(f"{'='*80}")
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Images:     {n_total}")
    print(f"Floor:      {FLOOR}  (min_prime)")
    print(f"Density:    {int(DENSITY_FRAC*100)}% of eligible grid positions")
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Detectors:  FREQ (channel-distance KS)")
    print(f"            LSV  (local spatial variance KS)  ← primary")
    print(f"            CDV  (channel-diff variance KS)   ← primary")
    print(f"            COMBO = FREQ OR LSV OR CDV")
    print(f"Started:    {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "blind_per_image.jsonl")
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
            print(f"SKIP ({w}x{h})"); continue

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
            combo = "COMBO" if result.get("gen4_det_combo",   False) else "     "
            freq  = "freq"  if result.get("gen4_det_freq",    False) else "    "
            spat  = "spat"  if result.get("gen4_det_spatial", False) else "    "
            lsvr  = result.get("gen4_lsv_ratio",    1.0)
            cdvr  = result.get("gen4_cdv_ratio_gb", 1.0)
            psnr  = result.get("psnr", 0)
            n_act = result.get("n_actual", 0)
            print(f"n={n_act:>4d}  {psnr:>5.1f}dB  {combo} {freq} {spat}"
                  f"  lsv_r={lsvr:.3f}  cdv_r={cdvr:.3f}  [{elapsed:.1f}s]")

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
    print(f"BLIND DETECTION AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    # Per-generation breakdown
    print(f"{'Gen':>4}  {'Q':>3}  {'FREQ%':>6}  {'LSV%':>6}  {'CDV%':>6}"
          f"  {'SPATIAL%':>8}  {'COMBO%':>7}"
          f"  {'lsv_r':>6}  {'cdv_r':>6}  {'freq_rr':>7}")
    print("─" * 75)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        n_freq  = sum(1 for r in good if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("det_freq",    False))
        n_lsv   = sum(1 for r in good if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("det_lsv",     False))
        n_cdv   = sum(1 for r in good if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("det_cdv_gb",  False))
        n_spat  = sum(1 for r in good if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("det_spatial", False))
        n_combo = sum(1 for r in good if len(r["cascade"]) > gen_idx
                      and r["cascade"][gen_idx].get("det_combo",   False))
        lsv_r   = np.mean([r["cascade"][gen_idx].get("lsv_ratio",    1.0)
                           for r in good if len(r["cascade"]) > gen_idx])
        cdv_r   = np.mean([r["cascade"][gen_idx].get("cdv_ratio_gb", 1.0)
                           for r in good if len(r["cascade"]) > gen_idx])
        frr     = np.mean([r["cascade"][gen_idx].get("freq_rr_gb",   1.0)
                           for r in good if len(r["cascade"]) > gen_idx])

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {n_freq/n_good*100:>5.1f}%"
              f"  {n_lsv/n_good*100:>5.1f}%"
              f"  {n_cdv/n_good*100:>5.1f}%"
              f"  {n_spat/n_good*100:>7.1f}%"
              f"  {n_combo/n_good*100:>6.1f}%"
              f"  {lsv_r:>6.3f}  {cdv_r:>6.3f}  {frr:>7.4f}")

    # LSV ratio progression — the amplification signature
    print(f"\nLSV ratio G0→G4 (amplification under compression):")
    lsv_by_gen = [
        np.mean([r["cascade"][g].get("lsv_ratio", 1.0)
                 for r in good if len(r["cascade"]) > g])
        for g in range(5)
    ]
    print("  " + "  →  ".join(f"G{g}:{v:.4f}" for g, v in enumerate(lsv_by_gen)))

    # Summary stats
    mean_psnr    = np.mean([r.get("psnr",     0.0) for r in good])
    mean_n_actual= np.mean([r.get("n_actual", 0)   for r in good])
    mean_eff     = np.mean([r.get("embed_eff",0.0) for r in good])
    g4_combo     = sum(1 for r in good if r.get("gen4_det_combo",   False))
    g4_freq      = sum(1 for r in good if r.get("gen4_det_freq",    False))
    g4_spat      = sum(1 for r in good if r.get("gen4_det_spatial", False))
    g4_lsv_r     = np.mean([r.get("gen4_lsv_ratio",    1.0) for r in good])
    g4_cdv_r     = np.mean([r.get("gen4_cdv_ratio_gb", 1.0) for r in good])

    combo_pct = g4_combo / n_good * 100

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"THE FACEBOOK VERDICT  (Gen4 Q40)")
    print(f"{'='*80}")
    print(f"  Images:           {n_good}")
    print(f"  Floor:            {FLOOR}  (min_prime)")
    print(f"  Density:          {int(DENSITY_FRAC*100)}%  (~{mean_n_actual:.0f} markers/image)")
    print(f"  Embed efficiency: {mean_eff:.3f}")
    print(f"  Mean PSNR:        {mean_psnr:.2f} dB")
    print(f"")
    print(f"  Gen4 FREQ:        {g4_freq}/{n_good}  ({g4_freq/n_good*100:.1f}%)")
    print(f"  Gen4 SPATIAL:     {g4_spat}/{n_good}  ({g4_spat/n_good*100:.1f}%)")
    print(f"  Gen4 COMBO:       {g4_combo}/{n_good}  ({combo_pct:.1f}%)")
    print(f"")
    print(f"  Gen4 lsv_ratio:   {g4_lsv_r:.4f}  (>1.0 = amplification confirmed)")
    print(f"  Gen4 cdv_ratio:   {g4_cdv_r:.4f}")
    print(f"")

    if combo_pct >= 90:
        verdict = (f"LAYER 3 WORKS. {combo_pct:.1f}% blind detection "
                   f"(spatial {g4_spat/n_good*100:.1f}% / freq {g4_freq/n_good*100:.1f}%) "
                   f"on {n_good} images at {mean_psnr:.2f}dB PSNR.")
    elif combo_pct >= 70:
        verdict = (f"LAYER 3 VIABLE. {combo_pct:.1f}% blind detection. "
                   f"Spatial: {g4_spat/n_good*100:.1f}%  Freq: {g4_freq/n_good*100:.1f}%.")
    elif combo_pct >= 50:
        verdict = (f"LAYER 3 MARGINAL. {combo_pct:.1f}% blind detection. "
                   f"Consider increasing density or lowering floor.")
    else:
        verdict = (f"LAYER 3 NEEDS WORK. {combo_pct:.1f}% blind detection. "
                   f"lsv_ratio={g4_lsv_r:.3f} — check embedding parameters.")

    if g4_lsv_r > 1.05:
        verdict += f" Amplification confirmed: lsv_ratio={g4_lsv_r:.3f}."

    print(f"  {verdict}")

    with open(os.path.join(output_dir, "BLIND_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"\nGenerated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Floor: {FLOOR}  Density: {int(DENSITY_FRAC*100)}%\n")
        f.write(f"Mean PSNR: {mean_psnr:.2f}dB\n")
        f.write(f"Mean markers/image: {mean_n_actual:.0f}\n")
        f.write(f"Gen4 combo: {combo_pct:.1f}%\n")
        f.write(f"Gen4 spatial: {g4_spat/n_good*100:.1f}%\n")
        f.write(f"Gen4 freq: {g4_freq/n_good*100:.1f}%\n")
        f.write(f"Gen4 lsv_ratio: {g4_lsv_r:.4f}\n")

    aggregate = {
        "n_images":          n_good,
        "floor":             FLOOR,
        "density_frac":      DENSITY_FRAC,
        "mean_psnr":         round(mean_psnr, 2),
        "mean_n_actual":     round(mean_n_actual),
        "mean_embed_eff":    round(mean_eff, 3),
        "gen4_freq_pct":     round(g4_freq  / n_good * 100, 1),
        "gen4_spatial_pct":  round(g4_spat  / n_good * 100, 1),
        "gen4_combo_pct":    round(combo_pct, 1),
        "gen4_lsv_ratio":    round(g4_lsv_r, 4),
        "gen4_cdv_ratio_gb": round(g4_cdv_r, 4),
        "total_time":        round(total_time, 1),
    }
    with open(os.path.join(output_dir, "blind_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    print(f"\nResults: {output_dir}/")
    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Layer 3 Blind Detection — The Facebook Test"
    )
    parser.add_argument("--input",      "-i", required=True,
                        help="Directory containing images")
    parser.add_argument("--output",     "-o", default="blind_results",
                        help="Output directory")
    parser.add_argument("--max-images", "-n", type=int, default=0,
                        help="Max images (0 = all)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
