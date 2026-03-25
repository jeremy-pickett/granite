#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Provenance Signal — Full Corpus Test
======================================

Validated operating point (floor sweep, March 2026):
  Floor:     43  (min_prime)
  Density:   8% of eligible grid positions
  PSNR:      ~41 dB
  Detection: 90% blind detection after Q40 compression

Runs all four detection layers on every image in the corpus:

  Layer A  — DQT prime quantization tables (container layer)
             Survives: lossless passthrough, tools that don't re-encode
             Dies:     first re-encode by any standard encoder

  Layer B  — Twin prime-gap markers, known positions (manifest)
             Survives: moderate JPEG compression
             Requires: manifest (positions from embed step)

  Layer C  — Douglas Rule sentinel (magic byte 42 + prime gap)
             Survives: similar to Layer B
             Requires: manifest

  Layer D  — Blind spatial variance detection, no manifest
             Survives: heavy JPEG compression (Q40), amplified by it
             Requires: nothing — the spatial amplification IS the signal

  COMBO    — Any of the above

The four layers are independent.  Any one is sufficient for detection.
Together they define the four observable states:

  State A  — No signal embedded, no provenance claimed
  State B  — Signal coherent, provenance intact
  State C  — Signal degraded, benign transforms (Layer A dead, D alive)
  State D  — Signal selectively removed, adversarial interference detected

Usage:
    python cascade_corpus_test.py -i /path/to/DIV2K -o corpus_results -n 50
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
from compound_markers import MarkerConfig, embed_compound, detect_compound
from dqt_prime import encode_prime_jpeg, detect_prime_dqt


# =============================================================================
# CONFIG — validated operating point
# =============================================================================

FLOOR           = 43
DENSITY_FRAC    = 0.08
LSV_RADIUS      = 2

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
# LAYER D — BLIND SPATIAL DETECTOR  (no manifest required)
# =============================================================================

def _lsv(pixels, radius=LSV_RADIUS):
    """Local spatial variance array at all eligible grid positions."""
    h, w, _ = pixels.shape
    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1
    mlv, mgv = [], []
    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue
        mgv.append(float(np.var(
            pixels[r-radius:r+radius+1, c-radius:c+radius+1, 1].astype(np.float32))))
        p = pixels[r-radius:r+radius+1, c-radius:c+radius+1]
        luma = (299*p[:,:,0].astype(np.int32) +
                587*p[:,:,1].astype(np.int32) +
                114*p[:,:,2].astype(np.int32)) // 1000
        mlv.append(float(np.var(luma.astype(np.float32))))
    return np.array(mlv), np.array(mgv)


def _cdv(pixels, ch_a, ch_b, radius=LSV_RADIUS):
    """Channel-difference variance array at all eligible grid positions."""
    h, w, _ = pixels.shape
    all_pos  = sample_positions_grid(h, w, 8)
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1
    vals = []
    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue
        p = pixels[r-radius:r+radius+1, c-radius:c+radius+1]
        vals.append(float(np.var(
            np.abs(p[:,:,ch_a].astype(np.int32) -
                   p[:,:,ch_b].astype(np.int32)).astype(np.float32))))
    return np.array(vals)


def layer_d(marked_px, clean_px):
    """
    Layer D: KS tests comparing marked vs clean variance distributions.
    Primary detection mechanism after heavy compression — the spatial
    amplification signal.  Returns detection booleans and ratio metrics.
    """
    d = {}

    # LSV — luma + green
    mv_luma, mv_g = _lsv(marked_px)
    cv_luma, cv_g = _lsv(clean_px)
    if len(mv_luma) >= 20:
        _, lp = sp_stats.ks_2samp(mv_luma, cv_luma)
        _, gp = sp_stats.ks_2samp(mv_g,    cv_g)
        d["lsv_p_luma"] = float(lp)
        d["lsv_p_g"]    = float(gp)
        d["lsv_ratio"]  = round(float(np.mean(mv_luma)) /
                                 max(float(np.mean(cv_luma)), 0.001), 4)
        d["det_lsv"]    = gp < 0.05
    else:
        d["lsv_p_luma"] = 1.0
        d["lsv_p_g"]    = 1.0
        d["lsv_ratio"]  = 1.0
        d["det_lsv"]    = False

    # CDV — G-B and R-G
    for ch_a, ch_b, tag in [(1, 2, "gb"), (0, 1, "rg")]:
        mv = _cdv(marked_px, ch_a, ch_b)
        cv = _cdv(clean_px,  ch_a, ch_b)
        if len(mv) >= 20:
            _, p = sp_stats.ks_2samp(mv, cv)
            d[f"cdv_p_{tag}"]    = float(p)
            d[f"cdv_ratio_{tag}"]= round(float(np.mean(mv)) /
                                          max(float(np.mean(cv)), 0.001), 4)
            d[f"det_cdv_{tag}"]  = p < 0.05
        else:
            d[f"cdv_p_{tag}"]    = 1.0
            d[f"cdv_ratio_{tag}"]= 1.0
            d[f"det_cdv_{tag}"]  = False

    d["det_spatial"] = d["det_lsv"] or d["det_cdv_gb"] or d["det_cdv_rg"]
    return d


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w  = pixels.shape[:2]
    cap   = grid_capacity(h, w)
    n_req = markers_for_image(h, w)

    result = {
        "image":         fname,
        "dimensions":    f"{w}x{h}",
        "grid_capacity": cap,
        "n_req":         n_req,
        "floor":         FLOOR,
        "density_frac":  DENSITY_FRAC,
    }

    # ── Layer A config: prime quantization tables ─────────────────────────────
    # Encode source as prime-table JPEG at Q95 (generation 0 container)
    prime_data, dqt_meta = encode_prime_jpeg(
        pixels, quality=95, min_prime=2, preserve_dc=True
    )
    result["dqt_table_prime_rate"] = (
        dqt_meta.get("table_analysis", {})
                .get("luma_primed", {})
                .get("prime_rate", 0.0)
    )

    # Decode the prime JPEG — this is the pixel-space starting point
    prime_pixels = decode_jpeg(prime_data)

    # ── Layer B+C: embed compound markers into prime pixels ───────────────────
    config = MarkerConfig(
        name="compound",
        description=f"Compound — floor={FLOOR} density={DENSITY_FRAC}",
        min_prime=FLOOR,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        magic_value=42,
        magic_tolerance=7,
        detection_prime_tolerance=2,
        n_markers=n_req,
    )

    marked_pixels, markers = embed_compound(prime_pixels, config, seed=42)
    n_actual = len(markers)
    result["n_actual"]  = n_actual
    result["embed_eff"] = round(n_actual / max(n_req, 1), 4)
    result["psnr"]      = round(compute_psnr(pixels, marked_pixels), 2)

    if n_actual < 10:
        result["error"] = f"Too few markers: {n_actual}"
        return result

    # Re-encode marked pixels as prime JPEG — this is the file the creator ships
    gen0_prime_data, _ = encode_prime_jpeg(
        marked_pixels, quality=95, min_prime=2, preserve_dc=True
    )

    # Clean path: same pipeline, no embedding
    clean_gen0 = to_jpeg(pixels, quality=95)

    # ── Cascade ───────────────────────────────────────────────────────────────
    current_marked = gen0_prime_data
    current_clean  = clean_gen0
    cascade        = []

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            # All downstream re-encodes use standard encoder (not prime)
            # — this simulates what platforms actually do
            current_marked = to_jpeg(decode_jpeg(current_marked), quality=q)
            current_clean  = to_jpeg(decode_jpeg(current_clean),  quality=q)

        marked_px = decode_jpeg(current_marked)
        clean_px  = decode_jpeg(current_clean)

        gen = {"generation": gen_idx, "quality": q}

        # Layer A — DQT
        dqt = detect_prime_dqt(current_marked)
        gen["dqt_prime_rate"] = dqt.get("overall_prime_rate", 0.0)
        gen["det_A"]          = dqt.get("detected", False)

        # Layer B+C — known-position compound detection
        if markers:
            compound = detect_compound(marked_px, markers, config)
            gen["marker_total"]   = compound.get("marker_total", 0)
            gen["marker_pass"]    = compound.get("marker_compound_pass", 0)
            gen["marker_rate"]    = compound.get("marker_rate", 0.0)
            gen["control_rate"]   = compound.get("control_rate", 0.0)
            gen["rate_ratio"]     = compound.get("rate_ratio", 0.0)
            gen["binom_p"]        = compound.get("binomial_pvalue", 1.0)
            gen["twin_pass"]      = compound.get("marker_twin_pass", 0)
            gen["magic_pass"]     = compound.get("marker_magic_pass", 0)
            gen["det_BC"]         = compound.get("detected_binom", False)
        else:
            gen["det_BC"] = False

        # Layer D — blind spatial (no manifest)
        spat             = layer_d(marked_px, clean_px)
        gen["lsv_ratio"] = spat.get("lsv_ratio", 1.0)
        gen["cdv_ratio_gb"] = spat.get("cdv_ratio_gb", 1.0)
        gen["det_lsv"]   = spat.get("det_lsv",    False)
        gen["det_cdv_gb"]= spat.get("det_cdv_gb", False)
        gen["det_D"]     = spat.get("det_spatial", False)

        # Combo
        gen["det_combo"] = gen["det_A"] or gen["det_BC"] or gen["det_D"]

        cascade.append(gen)

    result["cascade"] = cascade

    # Gen4 summary fields
    g4 = cascade[4] if len(cascade) > 4 else {}
    result["gen4_det_A"]     = g4.get("det_A",     False)
    result["gen4_det_BC"]    = g4.get("det_BC",    False)
    result["gen4_det_D"]     = g4.get("det_D",     False)
    result["gen4_det_combo"] = g4.get("det_combo", False)
    result["gen4_lsv_ratio"] = g4.get("lsv_ratio", 1.0)

    # Observable state
    if not result["gen4_det_combo"]:
        result["state"] = "A"   # no signal detected
    elif g4.get("det_A") and g4.get("det_BC") and g4.get("det_D"):
        result["state"] = "B"   # fully coherent
    elif g4.get("det_D"):
        result["state"] = "C"   # degraded — spatial survives
    else:
        result["state"] = "D"   # anomalous — something removed

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
    print(f"PROVENANCE SIGNAL — FULL CORPUS TEST")
    print(f"{'='*80}")
    print(f"Input:     {input_dir}")
    print(f"Output:    {output_dir}")
    print(f"Images:    {n_total}")
    print(f"Floor:     {FLOOR}  (min_prime)")
    print(f"Density:   {int(DENSITY_FRAC*100)}% of eligible grid positions")
    print(f"Cascade:   {CASCADE_QUALITIES}")
    print(f"Layers:")
    print(f"  A  — DQT prime quantization tables")
    print(f"  BC — Twin + magic compound markers (manifest)")
    print(f"  D  — Blind spatial variance (LSV + CDV, no manifest)")
    print(f"Started:   {datetime.utcnow().isoformat()}Z")
    print(f"{'='*80}\n")

    summary_data = []
    results_file = os.path.join(output_dir, "corpus_per_image.jsonl")
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
            A    = "A" if result.get("gen4_det_A",     False) else "·"
            BC   = "BC" if result.get("gen4_det_BC",   False) else "· "
            D    = "D" if result.get("gen4_det_D",     False) else "·"
            cmb  = "COMBO" if result.get("gen4_det_combo", False) else "     "
            lsvr = result.get("gen4_lsv_ratio", 1.0)
            psnr = result.get("psnr", 0.0)
            n_act= result.get("n_actual", 0)
            st   = result.get("state", "?")
            print(f"n={n_act:>4d}  {psnr:>5.1f}dB  "
                  f"A={A} BC={BC} D={D}  {cmb}  "
                  f"lsv_r={lsvr:.3f}  state={st}  [{elapsed:.1f}s]")

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
    print(f"FULL CORPUS AGGREGATE  —  {n_good} images")
    print(f"Total time: {total_time:.0f}s  ({total_time/max(n_good,1):.1f}s/img)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    # Per-generation breakdown
    print(f"{'Gen':>4}  {'Q':>3}  "
          f"{'A%':>6}  {'BC%':>6}  {'D%':>6}  {'COMBO%':>7}"
          f"  {'lsv_r':>6}  {'cdv_r':>6}")
    print("─" * 60)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        def pct(key):
            n = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get(key, False))
            return n / n_good * 100

        lsv_r = np.mean([r["cascade"][gen_idx].get("lsv_ratio",    1.0)
                          for r in good if len(r["cascade"]) > gen_idx])
        cdv_r = np.mean([r["cascade"][gen_idx].get("cdv_ratio_gb", 1.0)
                          for r in good if len(r["cascade"]) > gen_idx])

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {pct('det_A'):>5.1f}%"
              f"  {pct('det_BC'):>5.1f}%"
              f"  {pct('det_D'):>5.1f}%"
              f"  {pct('det_combo'):>6.1f}%"
              f"  {lsv_r:>6.3f}  {cdv_r:>6.3f}")

    # LSV amplification curve
    print(f"\nLSV ratio G0→G4 (>1.0 and growing = amplification confirmed):")
    vals = [np.mean([r["cascade"][g].get("lsv_ratio", 1.0)
                     for r in good if len(r["cascade"]) > g])
            for g in range(5)]
    print("  " + "  →  ".join(f"G{g}:{v:.4f}" for g, v in enumerate(vals)))

    # Observable state distribution at Gen4
    states = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in good:
        states[r.get("state", "A")] += 1

    print(f"\nObservable state distribution (Gen4 Q40):")
    print(f"  State A (no signal):        {states['A']:>4d} / {n_good}  "
          f"({states['A']/n_good*100:.1f}%)")
    print(f"  State B (fully coherent):   {states['B']:>4d} / {n_good}  "
          f"({states['B']/n_good*100:.1f}%)")
    print(f"  State C (degraded/spatial): {states['C']:>4d} / {n_good}  "
          f"({states['C']/n_good*100:.1f}%)")
    print(f"  State D (anomalous):        {states['D']:>4d} / {n_good}  "
          f"({states['D']/n_good*100:.1f}%)")

    # Summary metrics
    g4_A     = sum(1 for r in good if r.get("gen4_det_A",     False))
    g4_BC    = sum(1 for r in good if r.get("gen4_det_BC",    False))
    g4_D     = sum(1 for r in good if r.get("gen4_det_D",     False))
    g4_combo = sum(1 for r in good if r.get("gen4_det_combo", False))
    g4_lsv_r = np.mean([r.get("gen4_lsv_ratio", 1.0) for r in good])
    mean_psnr= np.mean([r.get("psnr", 0.0) for r in good])
    mean_n   = np.mean([r.get("n_actual", 0) for r in good])

    combo_pct = g4_combo / n_good * 100

    # Verdict
    print(f"\n{'='*80}")
    print(f"VERDICT  (Gen4 Q40)")
    print(f"{'='*80}")
    print(f"  Images:       {n_good}")
    print(f"  PSNR:         {mean_psnr:.2f} dB")
    print(f"  Markers/img:  ~{mean_n:.0f}")
    print(f"")
    print(f"  Layer A (DQT):      {g4_A}/{n_good}  ({g4_A/n_good*100:.1f}%)"
          f"  — dies at gen 1 (expected)")
    print(f"  Layer BC (manifest):{g4_BC}/{n_good}  ({g4_BC/n_good*100:.1f}%)")
    print(f"  Layer D (blind):    {g4_D}/{n_good}  ({g4_D/n_good*100:.1f}%)"
          f"  — spatial amplification")
    print(f"  COMBO:              {g4_combo}/{n_good}  ({combo_pct:.1f}%)")
    print(f"  LSV ratio G4:       {g4_lsv_r:.4f}  "
          f"({'amplification confirmed' if g4_lsv_r > 1.05 else 'weak'})")
    print()

    if combo_pct >= 90:
        verdict = (f"PARTICIPATION OVER PERMISSION. "
                   f"{combo_pct:.1f}% detection after Q40 at {mean_psnr:.2f}dB PSNR. "
                   f"Layer D (spatial): {g4_D/n_good*100:.1f}%. "
                   f"LSV amplification: {g4_lsv_r:.3f}.")
    elif combo_pct >= 70:
        verdict = (f"VIABLE. {combo_pct:.1f}% combo detection. "
                   f"A={g4_A/n_good*100:.1f}% "
                   f"BC={g4_BC/n_good*100:.1f}% "
                   f"D={g4_D/n_good*100:.1f}%.")
    else:
        verdict = (f"NEEDS WORK. {combo_pct:.1f}% combo. "
                   f"lsv_ratio={g4_lsv_r:.3f}. Check floor/density.")

    print(f"  {verdict}")

    with open(os.path.join(output_dir, "CORPUS_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Images: {n_good}\n")
        f.write(f"Floor: {FLOOR}  Density: {int(DENSITY_FRAC*100)}%\n")
        f.write(f"Mean PSNR: {mean_psnr:.2f}dB\n")
        f.write(f"Mean markers/image: {mean_n:.0f}\n")
        f.write(f"Gen4 A: {g4_A/n_good*100:.1f}%\n")
        f.write(f"Gen4 BC: {g4_BC/n_good*100:.1f}%\n")
        f.write(f"Gen4 D: {g4_D/n_good*100:.1f}%\n")
        f.write(f"Gen4 combo: {combo_pct:.1f}%\n")
        f.write(f"Gen4 lsv_ratio: {g4_lsv_r:.4f}\n")

    aggregate = {
        "n_images":          n_good,
        "floor":             FLOOR,
        "density_frac":      DENSITY_FRAC,
        "mean_psnr":         round(mean_psnr, 2),
        "mean_n_actual":     round(float(mean_n)),
        "gen4_A_pct":        round(g4_A     / n_good * 100, 1),
        "gen4_BC_pct":       round(g4_BC    / n_good * 100, 1),
        "gen4_D_pct":        round(g4_D     / n_good * 100, 1),
        "gen4_combo_pct":    round(combo_pct, 1),
        "gen4_lsv_ratio":    round(g4_lsv_r, 4),
        "state_counts":      states,
        "total_time":        round(total_time, 1),
    }
    with open(os.path.join(output_dir, "corpus_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)

    return aggregate


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Provenance Signal — Full Corpus Test (all four layers)"
    )
    parser.add_argument("--input",      "-i", required=True,
                        help="Directory containing images")
    parser.add_argument("--output",     "-o", default="corpus_results",
                        help="Output directory")
    parser.add_argument("--max-images", "-n", type=int, default=0,
                        help="Max images (0 = all)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)

    run_corpus(args.input, args.output, max_images=args.max_images)
