#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Detection Threshold Sweep
==========================

v4: Finds the MINIMUM marker density that sustains reliable blind detection
after heavy JPEG compression (Q40).

Previous runs showed 100% detection at 35% grid density — but PSNR was only
35 dB, well below the 40 dB target.  This script sweeps much lower densities
to locate the detection floor: the point where combo detection drops below
a configurable threshold (default 90%).

Densities tested: 3%, 5%, 8%, 12%, 18%, 25%
Floors tested:    37, 43, 53  (high-floor = lower PSNR cost per marker)

The operating envelope is defined by two curves:
  - PSNR(density)      — should be monotonically decreasing
  - Detection(density) — should be monotonically increasing

The sweet spot is the lowest density where detection >= DETECT_THRESHOLD
AND PSNR >= PSNR_TARGET.  If those regions don't overlap, the paper
reports the trade-off curves and the closest approach.

Usage:
    python floor_detection_threshold.py -i /path/to/DIV2K -o threshold_results -n 50
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
# CONFIG  — edit these to tune the search
# =============================================================================

# Density tiers as fraction of grid capacity
DENSITY_TIERS = [
    ("d03",  0.03),
    ("d05",  0.05),
    ("d06",  0.06),
    ("d07",  0.07),
    ("d08",  0.08),
    ("d12",  0.12),
    ("d18",  0.18),
    ("d25",  0.25),
]

# Floors to test — focus on high-floor region where PSNR cost is lowest per marker
FLOORS = [37, 43, 53]

CASCADE_QUALITIES = [95, 85, 75, 60, 40]

MIN_DIMENSION  = 512
LSV_RADIUS     = 2

# Sweet-spot criteria
DETECT_THRESHOLD = 90.0   # % combo detection required
PSNR_TARGET      = 40.0   # dB


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

def markers_for_tier(capacity, fraction):
    return max(5, math.ceil(capacity * fraction))


# =============================================================================
# DETECTORS
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
    all_pos      = sample_positions_grid(h, w, 8)
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
    return (passed / total if total > 0 else 0.0), passed, total


def local_variance_ks(marked_px, clean_px, radius=LSV_RADIUS):
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
    return float(lp), float(gp), float(ls), ratio


def channel_diff_variance_ks(marked_px, clean_px, ch_a, ch_b, radius=LSV_RADIUS):
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
    return float(p), float(s), ratio


def run_detectors(marked_px, clean_px, floor):
    d = {}
    ks_p_gb, ks_s_gb = blind_aggregate_ks(marked_px, clean_px, 1, 2)
    ks_p_rg, _       = blind_aggregate_ks(marked_px, clean_px, 0, 1)
    mr, _, _         = measure_prime_rates(marked_px, 1, 2, floor)
    cr, _, _         = measure_prime_rates(clean_px,  1, 2, floor)
    d["ks_p_gb"]     = ks_p_gb
    d["ks_p_rg"]     = ks_p_rg
    d["rate_ratio"]  = round(mr / max(cr, 0.0001), 4)
    d["det_freq"]    = ks_p_gb < 0.05 or ks_p_rg < 0.05

    lsv_lp, lsv_gp, lsv_s, lsv_r = local_variance_ks(marked_px, clean_px)
    d["lsv_p_g"]   = lsv_gp
    d["lsv_ratio"] = round(lsv_r, 4)
    d["det_lsv"]   = lsv_gp < 0.05

    cdv_p, _, cdv_r = channel_diff_variance_ks(marked_px, clean_px, 1, 2)
    d["cdv_p_gb"]    = cdv_p
    d["cdv_ratio_gb"]= round(cdv_r, 4)
    d["det_cdv"]     = cdv_p < 0.05

    cdv_p_rg, _, _   = channel_diff_variance_ks(marked_px, clean_px, 0, 1)
    d["det_cdv_rg"]  = cdv_p_rg < 0.05

    d["det_spatial"] = d["det_lsv"] or d["det_cdv"] or d["det_cdv_rg"]
    d["det_combo"]   = d["det_freq"] or d["det_spatial"]
    return d


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w = pixels.shape[:2]
    cap  = grid_capacity(h, w)
    result = {
        "image":         fname,
        "dimensions":    f"{w}x{h}",
        "grid_capacity": cap,
    }

    clean_jpeg = to_jpeg(pixels, 95)

    for floor in FLOORS:
        for tier_key, tier_frac in DENSITY_TIERS:
            n_req   = markers_for_tier(cap, tier_frac)
            ftkey   = f"f{floor}_{tier_key}"

            config  = MarkerConfig(
                name=ftkey,
                description=f"floor={floor} density={tier_key}",
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

            result[f"{ftkey}_n_req"]     = n_req
            result[f"{ftkey}_n_actual"]  = n_actual
            result[f"{ftkey}_psnr"]      = round(psnr, 2)
            result[f"{ftkey}_embed_eff"] = round(n_actual / max(n_req, 1), 4)

            marked_jpeg    = to_jpeg(marked_pixels, 95)
            current_marked = marked_jpeg
            current_clean  = clean_jpeg

            for gen_idx, q in enumerate(CASCADE_QUALITIES):
                if gen_idx > 0:
                    current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
                    current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

                marked_px = decode_jpeg(current_marked)
                clean_px  = decode_jpeg(current_clean)
                det       = run_detectors(marked_px, clean_px, floor)

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
    print(f"DETECTION THRESHOLD SWEEP (v4)")
    print(f"{'='*80}")
    print(f"Images:     {n_total}")
    print(f"Floors:     {FLOORS}")
    print(f"Densities:  " +
          "  ".join(f"{k}({int(f*100)}%)" for k, f in DENSITY_TIERS))
    print(f"Cascade:    {CASCADE_QUALITIES}")
    print(f"Target:     combo >= {DETECT_THRESHOLD}% AND PSNR >= {PSNR_TARGET}dB")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "threshold_per_image.jsonl")
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

        try:
            result = test_one_image(pixels, fname)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            result = {"image": fname, "error": str(e)}

        elapsed = time.time() - t_img

        # Per-image summary: one line per floor showing all density tiers
        if "error" not in result:
            for floor in FLOORS:
                parts = []
                for tier_key, tier_frac in DENSITY_TIERS:
                    ftkey = f"f{floor}_{tier_key}"
                    psnr  = result.get(f"{ftkey}_psnr", 0)
                    n_act = result.get(f"{ftkey}_n_actual", 0)
                    combo = "✓" if result.get(f"{ftkey}_g4_det_combo",   False) else "✗"
                    freq  = "f" if result.get(f"{ftkey}_g4_det_freq",    False) else "."
                    spat  = "s" if result.get(f"{ftkey}_g4_det_spatial", False) else "."
                    lsvr  = result.get(f"{ftkey}_g4_lsv_ratio", 1.0)
                    parts.append(
                        f"{tier_key}:{n_act:>4d} {psnr:>5.1f}dB {freq}{spat}{combo}"
                    )
                print(f"  f{floor:>2d}  " + "  |  ".join(parts))
        print(f"  cap={cap}  [{elapsed:.1f}s]")

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
    print(f"THRESHOLD SWEEP AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    summary_json = []

    # ── Main results table ────────────────────────────────────────────────────
    col = 10
    print(f"{'Floor':>5}  {'Tier':>4}  {'%cap':>4}  {'n_act':>5}  {'eff':>4}"
          f"  {'PSNR':>6}  {'G0 cmb':>{col}}  {'G4 frq':>{col}}"
          f"  {'G4 spt':>{col}}  {'G4 cmb':>{col}}  {'lsv_r':>6}  {'rr':>6}")
    print("─" * 100)

    for floor in FLOORS:
        for tier_key, tier_frac in DENSITY_TIERS:
            ftkey = f"f{floor}_{tier_key}"

            n_acts   = [r.get(f"{ftkey}_n_actual",  0)   for r in good]
            effs     = [r.get(f"{ftkey}_embed_eff", 0.0) for r in good]
            psnrs    = [r.get(f"{ftkey}_psnr",      0.0) for r in good]
            g0_combo = sum(1 for r in good if r.get(f"{ftkey}_g0_det_combo",   False))
            g4_freq  = sum(1 for r in good if r.get(f"{ftkey}_g4_det_freq",    False))
            g4_spat  = sum(1 for r in good if r.get(f"{ftkey}_g4_det_spatial", False))
            g4_combo = sum(1 for r in good if r.get(f"{ftkey}_g4_det_combo",   False))
            lsv_rs   = [r.get(f"{ftkey}_g4_lsv_ratio",  1.0) for r in good]
            rrs      = [r.get(f"{ftkey}_g4_rate_ratio",  1.0) for r in good]

            combo_pct = g4_combo / n_good * 100
            mean_psnr = np.mean(psnrs)

            def pct_str(n):
                return f"{n}/{n_good} {n/n_good*100:>3.0f}%"

            # Flag rows that meet the sweet-spot criteria
            flag = " ★" if combo_pct >= DETECT_THRESHOLD and mean_psnr >= PSNR_TARGET else ""

            print(f"{floor:>5d}  {tier_key:>4s}  {int(tier_frac*100):>3d}%"
                  f"  {np.mean(n_acts):>5.0f}  {np.mean(effs):>4.2f}"
                  f"  {mean_psnr:>5.1f}dB"
                  f"  {pct_str(g0_combo):>{col}}"
                  f"  {pct_str(g4_freq):>{col}}"
                  f"  {pct_str(g4_spat):>{col}}"
                  f"  {pct_str(g4_combo):>{col}}"
                  f"  {np.mean(lsv_rs):>6.3f}  {np.mean(rrs):>6.3f}"
                  f"{flag}")

            summary_json.append({
                "floor":          floor,
                "tier":           tier_key,
                "tier_pct":       int(tier_frac * 100),
                "mean_n_actual":  round(np.mean(n_acts)),
                "mean_embed_eff": round(np.mean(effs), 3),
                "mean_psnr":      round(mean_psnr, 2),
                "g0_combo_pct":   round(g0_combo / n_good * 100, 1),
                "g4_freq_pct":    round(g4_freq  / n_good * 100, 1),
                "g4_spatial_pct": round(g4_spat  / n_good * 100, 1),
                "g4_combo_pct":   round(combo_pct, 1),
                "g4_lsv_ratio":   round(np.mean(lsv_rs), 4),
                "g4_rate_ratio":  round(np.mean(rrs),    4),
                "meets_target":   combo_pct >= DETECT_THRESHOLD and mean_psnr >= PSNR_TARGET,
            })

    # ── Detection curve: how does combo% evolve across densities? ────────────
    print(f"\n\nG4 COMBO DETECTION % — detection curve per floor")
    print(f"  (find where it falls below {DETECT_THRESHOLD}% — that's your floor)")
    print(f"\n{'Floor':>5}  " +
          "  ".join(f"{tier_key:>8}" for tier_key, _ in DENSITY_TIERS))
    print("─" * 60)
    for floor in FLOORS:
        vals = []
        for tier_key, _ in DENSITY_TIERS:
            ftkey     = f"f{floor}_{tier_key}"
            g4_combo  = sum(1 for r in good if r.get(f"{ftkey}_g4_det_combo", False))
            vals.append(g4_combo / n_good * 100)
        row = f"{floor:>5d}  "
        for v in vals:
            marker = " ←floor" if v < DETECT_THRESHOLD else ""
            row   += f"  {v:>6.1f}%{marker}"
        print(row)

    # ── PSNR curve ────────────────────────────────────────────────────────────
    print(f"\nPSNR — quality cost per density")
    print(f"{'Floor':>5}  " +
          "  ".join(f"{tier_key:>8}" for tier_key, _ in DENSITY_TIERS))
    print("─" * 60)
    for floor in FLOORS:
        vals = [np.mean([r.get(f"f{floor}_{tk}_psnr", 0.0) for r in good])
                for tk, _ in DENSITY_TIERS]
        row = f"{floor:>5d}  "
        for v in vals:
            marker = " ★" if v >= PSNR_TARGET else ""
            row   += f"  {v:>5.1f}dB{marker}"
        print(row)

    # ── LSV ratio curve ───────────────────────────────────────────────────────
    print(f"\nLSV ratio at G4 — spatial amplification grows with density")
    print(f"{'Floor':>5}  " +
          "  ".join(f"{tier_key:>8}" for tier_key, _ in DENSITY_TIERS))
    print("─" * 60)
    for floor in FLOORS:
        vals = [np.mean([r.get(f"f{floor}_{tk}_g4_lsv_ratio", 1.0) for r in good])
                for tk, _ in DENSITY_TIERS]
        print(f"{floor:>5d}  " + "  ".join(f"  {v:>7.3f}" for v in vals))

    # ── Sweet spot summary ────────────────────────────────────────────────────
    sweet = [s for s in summary_json if s["meets_target"]]
    print(f"\n\n{'='*80}")
    print(f"SWEET SPOTS  (combo >= {DETECT_THRESHOLD}% AND PSNR >= {PSNR_TARGET}dB)")
    print(f"{'='*80}")
    if sweet:
        # Best: highest PSNR among those meeting detection threshold
        # (lowest viable density = best image quality)
        best = max(sweet, key=lambda s: s["mean_psnr"])
        for s in sorted(sweet, key=lambda s: (s["floor"], s["tier_pct"])):
            print(f"  ★ Floor {s['floor']:>2d}  {s['tier']:>4s} ({s['tier_pct']:>2d}%)"
                  f"  n≈{s['mean_n_actual']:>4d}"
                  f"  PSNR={s['mean_psnr']:>5.2f}dB"
                  f"  combo={s['g4_combo_pct']:>5.1f}%"
                  f"  lsv_r={s['g4_lsv_ratio']:.3f}")
        print(f"\n  RECOMMENDED: Floor {best['floor']} / {best['tier']}"
              f" ({best['tier_pct']}% density)"
              f"  →  {best['mean_psnr']:.2f}dB  /  {best['g4_combo_pct']:.1f}% detection"
              f"  /  ~{best['mean_n_actual']} markers per image")
    else:
        # Find closest approach
        by_detect = sorted(summary_json,
                           key=lambda s: abs(s["g4_combo_pct"] - DETECT_THRESHOLD))
        by_psnr   = sorted(summary_json,
                           key=lambda s: abs(s["mean_psnr"] - PSNR_TARGET))
        print(f"  No combination meets both targets simultaneously.")
        print(f"\n  Closest to detection target ({DETECT_THRESHOLD}%):")
        s = by_detect[0]
        print(f"    Floor {s['floor']} / {s['tier']} ({s['tier_pct']}%)"
              f"  combo={s['g4_combo_pct']:.1f}%  PSNR={s['mean_psnr']:.2f}dB")
        print(f"\n  Closest to PSNR target ({PSNR_TARGET}dB):")
        s = by_psnr[0]
        print(f"    Floor {s['floor']} / {s['tier']} ({s['tier_pct']}%)"
              f"  PSNR={s['mean_psnr']:.2f}dB  combo={s['g4_combo_pct']:.1f}%")
        print(f"\n  → Try adding a 1% or 2% tier if detection floor is between d03 and d05.")

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"VERDICT")
    print(f"{'='*80}")

    if sweet:
        best = max(sweet, key=lambda s: s["mean_psnr"])
        verdict = (
            f"SWEET SPOT FOUND. "
            f"Floor {best['floor']} / {best['tier']} ({best['tier_pct']}% density): "
            f"{best['g4_combo_pct']:.1f}% blind detection after Q40 compression "
            f"at {best['mean_psnr']:.2f}dB PSNR "
            f"(~{best['mean_n_actual']} markers / image). "
            f"Spatial amplification: lsv_ratio={best['g4_lsv_ratio']:.3f}."
        )
    else:
        # Highest combo that still clears PSNR, or vice versa
        above_psnr  = [s for s in summary_json if s["mean_psnr"] >= PSNR_TARGET]
        above_det   = [s for s in summary_json if s["g4_combo_pct"] >= DETECT_THRESHOLD]
        if above_psnr:
            best_det_above_psnr = max(above_psnr, key=lambda s: s["g4_combo_pct"])
            verdict = (
                f"NO SWEET SPOT YET. "
                f"Best detection above {PSNR_TARGET}dB PSNR: "
                f"Floor {best_det_above_psnr['floor']} / {best_det_above_psnr['tier']} "
                f"→ {best_det_above_psnr['g4_combo_pct']:.1f}% combo at "
                f"{best_det_above_psnr['mean_psnr']:.2f}dB. "
                f"Reduce floor or add mid-range density tiers (1-3%)."
            )
        elif above_det:
            best_psnr_above_det = max(above_det, key=lambda s: s["mean_psnr"])
            verdict = (
                f"NO SWEET SPOT YET. "
                f"Best PSNR above {DETECT_THRESHOLD}% detection: "
                f"Floor {best_psnr_above_det['floor']} / {best_psnr_above_det['tier']} "
                f"→ {best_psnr_above_det['mean_psnr']:.2f}dB at "
                f"{best_psnr_above_det['g4_combo_pct']:.1f}% combo. "
                f"Increase density range or lower PSNR target."
            )
        else:
            verdict = (
                f"TARGETS INCOMPATIBLE at tested parameters. "
                f"Detection and PSNR curves don't overlap. "
                f"Consider relaxing PSNR target or detection threshold."
            )

    print(f"\n  {verdict}\n")

    with open(os.path.join(output_dir, "THRESHOLD_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Floors: {FLOORS}\n")
        f.write(f"Densities: {[(k, int(f*100)) for k, f in DENSITY_TIERS]}\n")
        f.write(f"Targets: combo>={DETECT_THRESHOLD}%  PSNR>={PSNR_TARGET}dB\n")

    with open(os.path.join(output_dir, "threshold_summary.json"), "w") as f:
        json.dump(summary_json, f, indent=2)

    return summary_json


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Detection Threshold Sweep (v4)"
    )
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="threshold_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    parser.add_argument("--detect-threshold", type=float, default=DETECT_THRESHOLD,
                        help=f"Min combo detection %% to qualify (default {DETECT_THRESHOLD})")
    parser.add_argument("--psnr-target",      type=float, default=PSNR_TARGET,
                        help=f"Min PSNR dB to qualify (default {PSNR_TARGET})")
    args = parser.parse_args()

    # Allow CLI override of targets
    DETECT_THRESHOLD = args.detect_threshold
    PSNR_TARGET      = args.psnr_target

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
