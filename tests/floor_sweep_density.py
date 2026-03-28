#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Floor Sweep — Density Tiers
============================

v3: Replaces the fixed 2000-marker count with three density tiers expressed
as a fraction of the image's total eligible grid positions.

  STEALTH   35%  — near-invisible, max PSNR, lower detection confidence
  BALANCED  50%  — practical default for most distribution pipelines
  MAXIMUM   75%  — maximum detection confidence, higher PSNR cost

"Available markers" = len(sample_positions_grid(h, w, 8))
This is the geometric ceiling — the number of 8-stride grid positions in the
image.  Not all will accept a valid prime-gap embedding (depends on floor and
image content), so n_actual < n_requested is normal and expected.  The ratio
of n_actual / n_requested tracks embedding efficiency per floor.

Detectors (both run at every generation / floor / tier):
  FREQ  — channel-distance KS test  (existing, degrades under compression)
  LSV   — local spatial variance KS (new, hypothesised to amplify under compression)
  CDV   — channel-diff variance KS  (new hybrid)
  COMBO — FREQ OR SPATIAL

Key metric in output:
  lsv_ratio  > 1.0  →  granite-under-sandstone amplification confirmed
  rate_ratio < 1.0  →  frequency signal being erased by compression

Usage:
    python floor_sweep_density.py -i /path/to/DIV2K -o density_results -n 50
"""

import os
import sys
import io
import json
import time
import math
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from datetime import datetime

from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound


# =============================================================================
# CONFIG
# =============================================================================

FLOORS            = [23, 29, 37, 43, 53]
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512
LSV_RADIUS        = 2          # 5×5 patch

# Density tiers: (label, fraction_of_grid)
DENSITY_TIERS = [
    ("STEALTH",  0.35),
    ("BALANCED", 0.50),
    ("MAXIMUM",  0.75),
]

# Short keys used in output dict: d35 / d50 / d75
TIER_KEYS = {label: f"d{int(frac*100)}" for label, frac in DENSITY_TIERS}


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
    """Number of eligible 8-stride grid positions (geometric ceiling)."""
    return len(sample_positions_grid(h, w, 8))


def markers_for_tier(capacity, fraction):
    """Round up so very small images still get at least 10 markers."""
    return max(10, math.ceil(capacity * fraction))


# =============================================================================
# FREQUENCY DETECTOR
# =============================================================================

def blind_aggregate_ks(marked_px, clean_px, ch_a, ch_b):
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
        return 1.0, 0.0
    stat, p = sp_stats.ks_2samp(md, cd)
    return float(p), float(stat)


def measure_prime_rates(pixels, ch_a, ch_b, floor):
    h, w, _ = pixels.shape
    primes   = build_prime_lookup(8)
    lookup   = np.zeros(256, dtype=bool)
    for d in range(floor, 256):
        if primes[d]:
            lookup[d] = True
    all_pos   = sample_positions_grid(h, w, 8)
    passed, total = 0, 0
    for pos in all_pos:
        r  = int(pos[0]) + 3
        c  = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        total += 1
        d1 = abs(int(pixels[r, c,  ch_a]) - int(pixels[r, c,  ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if lookup[min(d1, 255)] and lookup[min(d2, 255)]:
            passed += 1
    rate = passed / total if total > 0 else 0.0
    return rate, passed, total


# =============================================================================
# SPATIAL VARIANCE DETECTOR
# =============================================================================

def local_variance_ks(marked_px, clean_px, radius=LSV_RADIUS):
    """KS test on local spatial variance distributions (luma + green)."""
    h, w, _ = marked_px.shape
    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1

    mlv, clv = [], []   # luma variance
    mgv, cgv = [], []   # green variance

    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue

        # Green
        mgv.append(float(np.var(
            marked_px[r-radius:r+radius+1, c-radius:c+radius+1, 1].astype(np.float32))))
        cgv.append(float(np.var(
            clean_px[r-radius:r+radius+1,  c-radius:c+radius+1, 1].astype(np.float32))))

        # Luma  (integer BT.601, no alloc per-pixel)
        def luma_patch(px):
            p = px[r-radius:r+radius+1, c-radius:c+radius+1]
            return (299 * p[:,:,0].astype(np.int32) +
                    587 * p[:,:,1].astype(np.int32) +
                    114 * p[:,:,2].astype(np.int32)) // 1000
        mlv.append(float(np.var(luma_patch(marked_px).astype(np.float32))))
        clv.append(float(np.var(luma_patch(clean_px).astype(np.float32))))

    if len(mlv) < 20:
        return 1.0, 1.0, 0.0, 1.0

    mv, cv   = np.array(mlv), np.array(clv)
    gm, gc   = np.array(mgv), np.array(cgv)
    ls, lp   = sp_stats.ks_2samp(mv, cv)
    _,  gp   = sp_stats.ks_2samp(gm, gc)
    ratio    = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)
    return float(lp), float(gp), float(ls), ratio


def channel_diff_variance_ks(marked_px, clean_px, ch_a, ch_b, radius=LSV_RADIUS):
    """KS test on local variance of channel-difference values."""
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
            np.abs(mp[:,:,ch_a].astype(np.int32) - mp[:,:,ch_b].astype(np.int32)).astype(np.float32))))
        ccdv.append(float(np.var(
            np.abs(cp[:,:,ch_a].astype(np.int32) - cp[:,:,ch_b].astype(np.int32)).astype(np.float32))))

    if len(mcdv) < 20:
        return 1.0, 0.0, 1.0
    mv, cv   = np.array(mcdv), np.array(ccdv)
    s, p     = sp_stats.ks_2samp(mv, cv)
    ratio    = float(np.mean(mv)) / max(float(np.mean(cv)), 0.001)
    return float(p), float(s), ratio


# =============================================================================
# RUN ALL DETECTORS FOR ONE (marked_px, clean_px) PAIR
# =============================================================================

def run_detectors(marked_px, clean_px, floor):
    """Returns a flat dict of all detector metrics."""
    d = {}

    # Frequency
    ks_p_gb, ks_s_gb = blind_aggregate_ks(marked_px, clean_px, 1, 2)
    ks_p_rg, _       = blind_aggregate_ks(marked_px, clean_px, 0, 1)
    mr, _, _         = measure_prime_rates(marked_px, 1, 2, floor)
    cr, _, _         = measure_prime_rates(clean_px,  1, 2, floor)
    rr               = mr / max(cr, 0.0001)

    d["ks_p_gb"]     = ks_p_gb
    d["ks_p_rg"]     = ks_p_rg
    d["ks_stat_gb"]  = round(ks_s_gb, 6)
    d["marked_rate"] = round(mr, 6)
    d["clean_rate"]  = round(cr, 6)
    d["rate_ratio"]  = round(rr, 4)
    d["det_freq_gb"] = ks_p_gb < 0.05
    d["det_freq_rg"] = ks_p_rg < 0.05
    d["det_freq"]    = ks_p_gb < 0.05 or ks_p_rg < 0.05

    # Spatial — LSV
    lsv_lp, lsv_gp, lsv_s, lsv_r = local_variance_ks(marked_px, clean_px)
    d["lsv_p_luma"]  = lsv_lp
    d["lsv_p_g"]     = lsv_gp
    d["lsv_stat"]    = round(lsv_s, 6)
    d["lsv_ratio"]   = round(lsv_r, 4)
    d["det_lsv"]     = lsv_gp < 0.05

    # Spatial — CDV (G-B)
    cdv_p, cdv_s, cdv_r = channel_diff_variance_ks(marked_px, clean_px, 1, 2)
    d["cdv_p_gb"]    = cdv_p
    d["cdv_stat_gb"] = round(cdv_s, 6)
    d["cdv_ratio_gb"]= round(cdv_r, 4)
    d["det_cdv_gb"]  = cdv_p < 0.05

    # CDV (R-G)
    cdv_p_rg, _, _   = channel_diff_variance_ks(marked_px, clean_px, 0, 1)
    d["cdv_p_rg"]    = cdv_p_rg
    d["det_cdv_rg"]  = cdv_p_rg < 0.05

    d["det_spatial"] = d["det_lsv"] or d["det_cdv_gb"] or d["det_cdv_rg"]
    d["det_combo"]   = d["det_freq"]  or d["det_spatial"]

    return d


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    cap   = grid_capacity(h, w)

    result = {
        "image":          fname,
        "dimensions":     f"{w}x{h}",
        "grid_capacity":  cap,
    }

    clean_jpeg = to_jpeg(pixels, 95)

    for floor in FLOORS:
        fkey = f"f{floor}"

        for tier_label, tier_frac in DENSITY_TIERS:
            tkey    = TIER_KEYS[tier_label]    # d35 / d50 / d75
            n_req   = markers_for_tier(cap, tier_frac)
            ftkey   = f"{fkey}_{tkey}"         # e.g. f53_d75

            config  = MarkerConfig(
                name=f"f{floor}_{tkey}",
                description=f"floor={floor} density={tier_label}",
                min_prime=floor,
                use_twins=True,
                use_rare_basket=True,
                use_magic=False,
                detection_prime_tolerance=2,
                n_markers=n_req,
            )

            marked_pixels, markers = embed_compound(pixels.copy(), config, seed=42)
            n_actual = len(markers)
            psnr     = compute_psnr(pixels, marked_pixels)
            embed_eff= n_actual / n_req if n_req > 0 else 0.0   # < 1 at high floor

            marked_jpeg = to_jpeg(marked_pixels, 95)

            result[f"{ftkey}_n_req"]    = n_req
            result[f"{ftkey}_n_actual"] = n_actual
            result[f"{ftkey}_psnr"]     = round(psnr, 2)
            result[f"{ftkey}_embed_eff"]= round(embed_eff, 4)

            current_marked = marked_jpeg
            current_clean  = clean_jpeg

            for gen_idx, q in enumerate(CASCADE_QUALITIES):
                if gen_idx > 0:
                    current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
                    current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

                marked_px = decode_jpeg(current_marked)
                clean_px  = decode_jpeg(current_clean)

                det = run_detectors(marked_px, clean_px, floor)

                gkey = f"{ftkey}_g{gen_idx}"
                for k, v in det.items():
                    result[f"{gkey}_{k}"] = v

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
    print(f"FLOOR SWEEP — DENSITY TIERS (v3)")
    print(f"{'='*80}")
    print(f"Images:   {n_total}")
    print(f"Floors:   {FLOORS}")
    print(f"Tiers:    " +
          "  ".join(f"{lbl} {int(f*100)}%" for lbl, f in DENSITY_TIERS))
    print(f"Cascade:  {CASCADE_QUALITIES}")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "density_sweep_per_image.jsonl")
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
            h, w   = pixels.shape[:2]

        cap = grid_capacity(h, w)
        tier_ns = [markers_for_tier(cap, f) for _, f in DENSITY_TIERS]
        print(f"  grid_cap={cap:>5d}  "
              + "  ".join(f"{lbl}={n}" for (lbl,_), n in zip(DENSITY_TIERS, tier_ns)))

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        # Quick summary line per floor / tier for the most compressed gen
        if "error" not in result:
            for floor in FLOORS:
                fkey = f"f{floor}"
                parts = []
                for tier_label, _ in DENSITY_TIERS:
                    tkey  = TIER_KEYS[tier_label]
                    ftkey = f"{fkey}_{tkey}"
                    psnr  = result.get(f"{ftkey}_psnr", 0)
                    n_act = result.get(f"{ftkey}_n_actual", 0)
                    combo = "C" if result.get(f"{ftkey}_g4_det_combo",   False) else "."
                    freq  = "F" if result.get(f"{ftkey}_g4_det_freq",    False) else "."
                    spat  = "S" if result.get(f"{ftkey}_g4_det_spatial", False) else "."
                    lsvr  = result.get(f"{ftkey}_g4_lsv_ratio", 1.0)
                    parts.append(f"{tkey}:{n_act:>4d} {psnr:>5.1f}dB {freq}{spat}{combo} lsv={lsvr:.3f}")
                print(f"  f{floor:>2d}  " + "  |  ".join(parts))
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
    print(f"DENSITY SWEEP AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    summary_json = []

    # ── Table: one row per (floor, tier) ─────────────────────────────────────
    col_w = 9
    header = (f"{'Floor':>5}  {'Tier':>8}  {'n_req':>6}  {'n_act':>6}"
              f"  {'eff':>5}  {'PSNR':>6}"
              f"  {'G0 cmb':>{col_w}}  {'G4 frq':>{col_w}}"
              f"  {'G4 spt':>{col_w}}  {'G4 cmb':>{col_w}}"
              f"  {'lsv_r':>6}  {'cdv_r':>6}  {'rr':>6}")
    print(header)
    print("─" * len(header))

    for floor in FLOORS:
        fkey = f"f{floor}"
        for tier_label, tier_frac in DENSITY_TIERS:
            tkey  = TIER_KEYS[tier_label]
            ftkey = f"{fkey}_{tkey}"

            n_reqs   = [r.get(f"{ftkey}_n_req",    0)   for r in good]
            n_acts   = [r.get(f"{ftkey}_n_actual",  0)   for r in good]
            effs     = [r.get(f"{ftkey}_embed_eff", 0.0) for r in good]
            psnrs    = [r.get(f"{ftkey}_psnr",      0.0) for r in good]

            g0_combo = sum(1 for r in good if r.get(f"{ftkey}_g0_det_combo",   False))
            g4_freq  = sum(1 for r in good if r.get(f"{ftkey}_g4_det_freq",    False))
            g4_spat  = sum(1 for r in good if r.get(f"{ftkey}_g4_det_spatial", False))
            g4_combo = sum(1 for r in good if r.get(f"{ftkey}_g4_det_combo",   False))

            lsv_rs = [r.get(f"{ftkey}_g4_lsv_ratio",    1.0) for r in good]
            cdv_rs = [r.get(f"{ftkey}_g4_cdv_ratio_gb", 1.0) for r in good]
            rrs    = [r.get(f"{ftkey}_g4_rate_ratio",   1.0) for r in good]

            def pct_str(n):
                return f"{n}/{n_good} {n/n_good*100:>3.0f}%"

            print(f"{floor:>5d}  {tier_label:>8s}  {np.mean(n_reqs):>6.0f}  {np.mean(n_acts):>6.0f}"
                  f"  {np.mean(effs):>5.2f}  {np.mean(psnrs):>5.1f}dB"
                  f"  {pct_str(g0_combo):>{col_w}}"
                  f"  {pct_str(g4_freq):>{col_w}}"
                  f"  {pct_str(g4_spat):>{col_w}}"
                  f"  {pct_str(g4_combo):>{col_w}}"
                  f"  {np.mean(lsv_rs):>6.3f}  {np.mean(cdv_rs):>6.3f}  {np.mean(rrs):>6.3f}")

            summary_json.append({
                "floor":          floor,
                "tier":           tier_label,
                "tier_frac":      tier_frac,
                "mean_n_req":     round(np.mean(n_reqs)),
                "mean_n_actual":  round(np.mean(n_acts)),
                "mean_embed_eff": round(np.mean(effs), 3),
                "mean_psnr":      round(np.mean(psnrs), 2),
                "g0_combo_pct":   round(g0_combo / n_good * 100, 1),
                "g4_freq_pct":    round(g4_freq  / n_good * 100, 1),
                "g4_spatial_pct": round(g4_spat  / n_good * 100, 1),
                "g4_combo_pct":   round(g4_combo / n_good * 100, 1),
                "g4_lsv_ratio":   round(np.mean(lsv_rs), 4),
                "g4_cdv_ratio":   round(np.mean(cdv_rs), 4),
                "g4_rate_ratio":  round(np.mean(rrs),    4),
            })

    # ── Amplification check: does lsv_ratio grow G0 → G4? ───────────────────
    print(f"\n\nLSV ratio progression G0→G4 (>1.0 = amplification; watch for growth)")
    print(f"{'Floor':>5}  {'Tier':>8}  " +
          "  ".join(f"{'G'+str(i):>7}" for i in range(5)))
    print("─" * 60)
    for floor in FLOORS:
        fkey = f"f{floor}"
        for tier_label, _ in DENSITY_TIERS:
            tkey  = TIER_KEYS[tier_label]
            ftkey = f"{fkey}_{tkey}"
            vals  = [np.mean([r.get(f"{ftkey}_g{g}_lsv_ratio", 1.0) for r in good])
                     for g in range(5)]
            print(f"{floor:>5d}  {tier_label:>8s}  " +
                  "  ".join(f"{v:>7.4f}" for v in vals))

    print(f"\nRate ratio progression G0→G4 (<1.0 = freq signal degrading)")
    print(f"{'Floor':>5}  {'Tier':>8}  " +
          "  ".join(f"{'G'+str(i):>7}" for i in range(5)))
    print("─" * 60)
    for floor in FLOORS:
        fkey = f"f{floor}"
        for tier_label, _ in DENSITY_TIERS:
            tkey  = TIER_KEYS[tier_label]
            ftkey = f"{fkey}_{tkey}"
            vals  = [np.mean([r.get(f"{ftkey}_g{g}_rate_ratio", 1.0) for r in good])
                     for g in range(5)]
            print(f"{floor:>5d}  {tier_label:>8s}  " +
                  "  ".join(f"{v:>7.4f}" for v in vals))

    # ── PSNR vs detection trade-off summary ──────────────────────────────────
    print(f"\n\nPSNR vs G4 combo detection — the trade-off table")
    print(f"{'Floor':>5}  {'Tier':>8}  {'PSNR':>6}  {'G4 combo%':>10}  notes")
    print("─" * 55)
    for s in summary_json:
        note = ""
        if s["mean_psnr"] >= 40 and s["g4_combo_pct"] >= 80:
            note = "★ SWEET SPOT"
        elif s["mean_psnr"] >= 40 and s["g4_combo_pct"] >= 60:
            note = "◑ viable"
        elif s["g4_combo_pct"] >= 80:
            note = "◑ high detect / low PSNR"
        if s["g4_lsv_ratio"] > 1.05:
            note += "  [amplification ✓]"
        print(f"{s['floor']:>5d}  {s['tier']:>8s}  {s['mean_psnr']:>5.1f}dB"
              f"  {s['g4_combo_pct']:>8.1f}%  {note}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"VERDICT")
    print(f"{'='*80}")

    # Best by combo pct, tie-break by PSNR
    best = max(summary_json, key=lambda s: (s["g4_combo_pct"], s["mean_psnr"]),
               default=None)

    if best:
        combo, psnr = best["g4_combo_pct"], best["mean_psnr"]
        freq,  spat = best["g4_freq_pct"],  best["g4_spatial_pct"]

        tag = ("SWEET SPOT"        if combo > 85 and psnr >= 40  else
               "STRONG DETECTION"  if combo > 85                  else
               "DETECTION WORKS"   if combo > 70                  else
               "DETECTION VIABLE"  if combo > 50                  else
               "NEEDS WORK")

        verdict = (f"{tag}. Floor {best['floor']} / {best['tier']} "
                   f"({int(best['tier_frac']*100)}% density): "
                   f"{combo:.1f}% combo detection "
                   f"(freq {freq:.1f}%  spat {spat:.1f}%) "
                   f"at {psnr:.2f}dB PSNR.")

        amp = best["g4_lsv_ratio"]
        if amp > 1.05:
            verdict += f" Amplification CONFIRMED: lsv_ratio={amp:.3f}."
        elif amp > 1.0:
            verdict += f" Weak amplification: lsv_ratio={amp:.3f}."
        else:
            verdict += f" No amplification yet: lsv_ratio={amp:.3f}."
    else:
        verdict = "NO RESULTS."

    print(f"\n  {verdict}")

    with open(os.path.join(output_dir, "DENSITY_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Floors: {FLOORS}\n")
        f.write(f"Tiers: {[(l, f) for l,f in DENSITY_TIERS]}\n")

    with open(os.path.join(output_dir, "density_summary.json"), "w") as f:
        json.dump(summary_json, f, indent=2)

    return summary_json


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Floor Sweep — Density Tiers (v3)"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="density_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
