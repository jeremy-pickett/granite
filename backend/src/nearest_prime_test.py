#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Nearest-Prime Broadcast Mode — The Needle Stack Test
======================================================

Instead of shifting channel distances to rare primes (floor >= 53),
shift to the NEAREST prime. Distance is 12? Shift to 11 or 13.
Cost: 1 pixel value. Benefit: you can embed at EVERY eligible position.

This tests whether saturating the eligible grid with minimal perturbations
creates a detectable aggregate bias toward primality.

The control: same image, no embedding, same pipeline.
The test: KS on distance distributions at all eligible positions.

Additionally tests a COMBINED mode:
  - 200 positions with high-floor primes (fingerprint, Profile A)
  - ALL remaining positions with nearest-prime (broadcast, Profile B)
  - Both running simultaneously

Usage:
    python nearest_prime_test.py -i "C:\\path\\to\\DIV2K" -o nearest_results -n 5
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

from pgps_detector import build_prime_lookup, sieve_of_eratosthenes, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound


# =============================================================================
# CONFIG
# =============================================================================

CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION = 512

# All primes up to 255
ALL_PRIMES = sorted(sieve_of_eratosthenes(255))
PRIME_SET = set(ALL_PRIMES)


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


def nearest_prime(value):
    """Find the nearest prime to a given value (0-255)."""
    if value in PRIME_SET:
        return value, 0
    
    # Search outward
    for offset in range(1, 128):
        if (value - offset) >= 0 and (value - offset) in PRIME_SET:
            return value - offset, offset
        if (value + offset) <= 255 and (value + offset) in PRIME_SET:
            return value + offset, offset
    
    return value, 0  # shouldn't happen


# =============================================================================
# NEAREST-PRIME EMBEDDER
# =============================================================================

def embed_nearest_prime(pixels, ch_a, ch_b, positions=None):
    """
    At every eligible position (or specified positions), shift channel
    values so that |ch_a - ch_b| lands on the nearest prime.
    
    Returns modified pixels, number of positions modified, total
    perturbation applied, and list of positions.
    """
    h, w, _ = pixels.shape
    result = pixels.copy()
    
    if positions is None:
        all_pos = sample_positions_grid(h, w, 8)
        positions = []
        for pos in all_pos:
            r = int(pos[0]) + 3
            c = int(pos[1]) + 3
            tc = c + 1
            if r >= h or c >= w or tc >= w:
                continue
            positions.append((r, c, tc))
    
    n_modified = 0
    total_shift = 0
    max_shift = 0
    
    for r, c, tc in positions:
        for col in [c, tc]:
            va = int(result[r, col, ch_a])
            vb = int(result[r, col, ch_b])
            current_dist = abs(va - vb)
            
            target_prime, shift_needed = nearest_prime(current_dist)
            
            if shift_needed == 0:
                # Already prime, no change needed
                continue
            
            # Determine direction: shift channel b to achieve target distance
            if va >= vb:
                # distance = va - vb, need distance = target_prime
                new_vb = va - target_prime
                if new_vb < 0:
                    new_vb = va + target_prime
                    if new_vb > 255:
                        continue  # Can't achieve, skip
            else:
                # distance = vb - va, need distance = target_prime
                new_vb = va + target_prime
                if new_vb > 255:
                    new_vb = va - target_prime
                    if new_vb < 0:
                        continue  # Can't achieve, skip
            
            actual_shift = abs(int(new_vb) - int(vb))
            result[r, col, ch_b] = np.clip(new_vb, 0, 255).astype(np.uint8)
            total_shift += actual_shift
            max_shift = max(max_shift, actual_shift)
        
        n_modified += 1
    
    return result, n_modified, total_shift, max_shift, positions


# =============================================================================
# BLIND DETECTION: measure primality rate at eligible positions
# =============================================================================

def measure_primality(pixels, ch_a, ch_b, tolerance=0):
    """
    At ALL eligible positions, measure what fraction of twin pairs
    have BOTH channel distances landing on a prime.
    
    With tolerance=0: exact prime
    With tolerance=1: within 1 of a prime
    """
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8)
    max_val = 255
    
    if tolerance > 0:
        fuzzy = np.zeros(max_val + 1, dtype=bool)
        for d in range(max_val + 1):
            for off in range(-tolerance, tolerance + 1):
                check = d + off
                if 0 <= check <= max_val and primes[check]:
                    fuzzy[d] = True
                    break
    else:
        fuzzy = primes  # exact match
    
    all_pos = sample_positions_grid(h, w, 8)
    
    single_prime_count = 0
    twin_prime_count = 0
    total_positions = 0
    all_dists = []
    
    for pos in all_pos:
        r = int(pos[0]) + 3
        c = int(pos[1]) + 3
        tc = c + 1
        if r >= h or c >= w or tc >= w:
            continue
        
        total_positions += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        all_dists.extend([d1, d2])
        
        p1 = fuzzy[min(d1, max_val)]
        p2 = fuzzy[min(d2, max_val)]
        
        if p1:
            single_prime_count += 1
        if p2:
            single_prime_count += 1
        if p1 and p2:
            twin_prime_count += 1
    
    single_rate = single_prime_count / (2 * total_positions) if total_positions > 0 else 0
    twin_rate = twin_prime_count / total_positions if total_positions > 0 else 0
    
    return {
        "single_prime_rate": round(single_rate, 6),
        "twin_prime_rate": round(twin_rate, 6),
        "total_positions": total_positions,
        "single_prime_count": single_prime_count,
        "twin_prime_count": twin_prime_count,
        "distances": np.array(all_dists),
    }


# =============================================================================
# SINGLE IMAGE TEST
# =============================================================================

def test_one_image(pixels, fname):
    h, w = pixels.shape[:2]
    result = {
        "image": fname,
        "dimensions": f"{w}x{h}",
    }
    
    ch_a, ch_b = 1, 2  # G-B primary
    
    # =========================================================================
    # MODE 1: Nearest-prime at ALL eligible positions (broadcast)
    # =========================================================================
    broadcast_pixels, n_mod_b, total_shift_b, max_shift_b, all_positions = \
        embed_nearest_prime(pixels, ch_a, ch_b)
    psnr_broadcast = compute_psnr(pixels, broadcast_pixels)
    
    result["broadcast_n_modified"] = n_mod_b
    result["broadcast_total_shift"] = total_shift_b
    result["broadcast_max_shift"] = max_shift_b
    result["broadcast_mean_shift"] = round(total_shift_b / max(n_mod_b * 2, 1), 3)
    result["broadcast_psnr"] = round(psnr_broadcast, 2)
    
    # =========================================================================
    # MODE 2: High-floor fingerprint at 200 positions (Profile A)
    # =========================================================================
    config_a = MarkerConfig(
        name="fingerprint",
        description="Profile A fingerprint",
        min_prime=53,
        use_twins=True,
        use_rare_basket=True,
        use_magic=False,
        detection_prime_tolerance=2,
        n_markers=200,
    )
    fingerprint_pixels, markers_a = embed_compound(pixels.copy(), config_a, seed=42)
    psnr_fingerprint = compute_psnr(pixels, fingerprint_pixels)
    
    result["fingerprint_n_markers"] = len(markers_a)
    result["fingerprint_psnr"] = round(psnr_fingerprint, 2)
    
    # =========================================================================
    # MODE 3: Combined — fingerprint at 200 + nearest-prime at all remaining
    # =========================================================================
    combined_pixels = fingerprint_pixels.copy()
    # Get the fingerprint marker positions so we skip them
    marker_set = set()
    for m in markers_a:
        marker_set.add((m["row"], m["col"]))
        marker_set.add((m["row"], m.get("twin_col", m["col"] + 1)))
    
    # Nearest-prime embed at all OTHER eligible positions
    remaining_positions = []
    for r, c, tc in all_positions:
        if (r, c) not in marker_set and (r, tc) not in marker_set:
            remaining_positions.append((r, c, tc))
    
    combined_pixels, n_mod_c, total_shift_c, max_shift_c, _ = \
        embed_nearest_prime(combined_pixels, ch_a, ch_b, positions=remaining_positions)
    psnr_combined = compute_psnr(pixels, combined_pixels)
    
    result["combined_broadcast_modified"] = n_mod_c
    result["combined_psnr"] = round(psnr_combined, 2)
    
    # =========================================================================
    # CASCADE AND DETECT
    # =========================================================================
    
    # Prepare all four versions
    versions = {
        "clean": to_jpeg(pixels, 95),
        "broadcast": to_jpeg(broadcast_pixels, 95),
        "fingerprint": to_jpeg(fingerprint_pixels, 95),
        "combined": to_jpeg(combined_pixels, 95),
    }
    
    cascade = []
    
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        if gen_idx > 0:
            for vname in versions:
                versions[vname] = to_jpeg(decode_jpeg(versions[vname]), quality=q)
        
        gen = {"generation": gen_idx, "quality": q}
        
        for vname, jpeg_data in versions.items():
            px = decode_jpeg(jpeg_data)
            
            # Measure primality at all eligible positions
            # Exact prime match
            m_exact = measure_primality(px, ch_a, ch_b, tolerance=0)
            # Fuzzy prime match (within 1)
            m_fuzzy = measure_primality(px, ch_a, ch_b, tolerance=1)
            
            gen[f"{vname}_exact_single_rate"] = m_exact["single_prime_rate"]
            gen[f"{vname}_exact_twin_rate"] = m_exact["twin_prime_rate"]
            gen[f"{vname}_fuzzy_single_rate"] = m_fuzzy["single_prime_rate"]
            gen[f"{vname}_fuzzy_twin_rate"] = m_fuzzy["twin_prime_rate"]
            
            # Store distances for KS comparison
            gen[f"{vname}_dists"] = m_exact["distances"]
        
        # KS tests: each embedded version vs clean
        for vname in ["broadcast", "fingerprint", "combined"]:
            if (len(gen.get(f"{vname}_dists", [])) > 10 and
                len(gen.get("clean_dists", [])) > 10):
                ks_stat, ks_p = sp_stats.ks_2samp(
                    gen[f"{vname}_dists"],
                    gen["clean_dists"]
                )
                gen[f"{vname}_vs_clean_ks_p"] = float(ks_p)
                gen[f"{vname}_vs_clean_ks_stat"] = round(float(ks_stat), 6)
            else:
                gen[f"{vname}_vs_clean_ks_p"] = 1.0
                gen[f"{vname}_vs_clean_ks_stat"] = 0.0
        
        # Primality rate ratio: embedded / clean
        for vname in ["broadcast", "fingerprint", "combined"]:
            clean_twin = gen.get("clean_exact_twin_rate", 0)
            emb_twin = gen.get(f"{vname}_exact_twin_rate", 0)
            gen[f"{vname}_twin_ratio"] = round(
                emb_twin / max(clean_twin, 0.0001), 4
            )
            
            clean_single = gen.get("clean_exact_single_rate", 0)
            emb_single = gen.get(f"{vname}_exact_single_rate", 0)
            gen[f"{vname}_single_ratio"] = round(
                emb_single / max(clean_single, 0.0001), 4
            )
        
        # Remove raw distance arrays before storing
        for key in list(gen.keys()):
            if key.endswith("_dists"):
                del gen[key]
        
        cascade.append(gen)
    
    result["cascade"] = cascade
    
    # Summary at Gen0 and Gen4
    for gen_idx, label in [(0, "gen0"), (4, "gen4")]:
        if len(cascade) > gen_idx:
            g = cascade[gen_idx]
            for vname in ["broadcast", "fingerprint", "combined"]:
                result[f"{label}_{vname}_ks_p"] = g.get(f"{vname}_vs_clean_ks_p", 1.0)
                result[f"{label}_{vname}_twin_ratio"] = g.get(f"{vname}_twin_ratio", 1.0)
                result[f"{label}_{vname}_single_ratio"] = g.get(f"{vname}_single_ratio", 1.0)
                result[f"{label}_{vname}_detected"] = g.get(f"{vname}_vs_clean_ks_p", 1.0) < 0.05
    
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
    print(f"NEAREST-PRIME BROADCAST MODE — The Needle Stack Test")
    print(f"{'='*80}")
    print(f"Images:  {n_total}")
    print(f"Modes:   broadcast (nearest prime, all positions)")
    print(f"         fingerprint (floor>=53, 200 positions)")
    print(f"         combined (fingerprint + broadcast on remaining)")
    print(f"Pair:    G-B (1,2)")
    print(f"{'='*80}\n")
    
    summary_data = []
    results_file = os.path.join(output_dir, "nearest_prime_per_image.jsonl")
    with open(results_file, "w") as f:
        f.write("")
    
    t_start = time.time()
    
    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>3d}/{n_total}] {fname}  ", end="", flush=True)
        
        try:
            img = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}")
            continue
        
        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print(f"SKIP")
            continue
        
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
            print(f"ERROR [{elapsed:.1f}s]")
        else:
            b_psnr = result.get("broadcast_psnr", 0)
            c_psnr = result.get("combined_psnr", 0)
            b_det0 = "DET" if result.get("gen0_broadcast_detected", False) else "   "
            b_det4 = "DET" if result.get("gen4_broadcast_detected", False) else "   "
            c_det0 = "DET" if result.get("gen0_combined_detected", False) else "   "
            c_det4 = "DET" if result.get("gen4_combined_detected", False) else "   "
            
            b_ks4 = result.get("gen4_broadcast_ks_p", 1.0)
            c_ks4 = result.get("gen4_combined_ks_p", 1.0)
            
            print(f"BCAST:{b_psnr:.1f}dB G0:{b_det0} G4:{b_det4} ks={b_ks4:.2e}"
                  f"  COMB:{c_psnr:.1f}dB G0:{c_det0} G4:{c_det4} ks={c_ks4:.2e}"
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
    print(f"NEAREST-PRIME RESULTS ({n_good} images)")
    print(f"Total time: {total_time:.0f}s ({total_time/max(n_good,1):.1f}s/image)")
    print(f"{'='*80}\n")
    
    if n_good == 0:
        print("No valid results.")
        return
    
    # PSNR summary
    print(f"PSNR Summary:")
    for mode in ["broadcast", "fingerprint", "combined"]:
        psnrs = [r.get(f"{mode}_psnr", 0) for r in good if f"{mode}_psnr" in r]
        if psnrs:
            print(f"  {mode:>12s}: mean={np.mean(psnrs):.1f}dB"
                  f"  min={np.min(psnrs):.1f}dB  max={np.max(psnrs):.1f}dB")
    
    # Mean shift for broadcast
    shifts = [r.get("broadcast_mean_shift", 0) for r in good]
    print(f"\n  Broadcast mean shift per pixel: {np.mean(shifts):.2f} values")
    print(f"  Broadcast max shift seen: {max(r.get('broadcast_max_shift', 0) for r in good)} values")
    
    # Detection rates per generation
    print(f"\nDetection Rates (KS vs clean, p < 0.05):")
    print(f"  {'Gen':>4s} {'Q':>4s}  {'Broadcast':>10s}  {'Fingerprint':>12s}  {'Combined':>10s}")
    print(f"  {'─'*50}")
    
    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        for mode in ["broadcast", "fingerprint", "combined"]:
            pass  # collect below
        
        b_det = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("broadcast_vs_clean_ks_p", 1) < 0.05)
        f_det = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("fingerprint_vs_clean_ks_p", 1) < 0.05)
        c_det = sum(1 for r in good
                    if len(r["cascade"]) > gen_idx
                    and r["cascade"][gen_idx].get("combined_vs_clean_ks_p", 1) < 0.05)
        
        print(f"  {gen_idx:>4d} Q{q:>3d}"
              f"  {b_det:>4d}/{n_good} {b_det/n_good*100:>4.0f}%"
              f"  {f_det:>6d}/{n_good} {f_det/n_good*100:>4.0f}%"
              f"  {c_det:>4d}/{n_good} {c_det/n_good*100:>4.0f}%")
    
    # Primality rate comparison
    print(f"\nPrimality Rate Ratios (embedded / clean) at Gen4 Q40:")
    for mode in ["broadcast", "fingerprint", "combined"]:
        twin_ratios = []
        single_ratios = []
        for r in good:
            if len(r["cascade"]) > 4:
                g = r["cascade"][4]
                twin_ratios.append(g.get(f"{mode}_twin_ratio", 1.0))
                single_ratios.append(g.get(f"{mode}_single_ratio", 1.0))
        if twin_ratios:
            print(f"  {mode:>12s}: twin_ratio={np.mean(twin_ratios):.3f}"
                  f"  single_ratio={np.mean(single_ratios):.3f}")
    
    # Clean baseline
    clean_twins = []
    for r in good:
        if len(r["cascade"]) > 4:
            clean_twins.append(r["cascade"][4].get("clean_exact_twin_rate", 0))
    if clean_twins:
        print(f"\n  Clean natural twin-prime rate: {np.mean(clean_twins):.4f}")
    
    # =========================================================================
    # VERDICT
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"NEAREST-PRIME VERDICT")
    print(f"{'='*80}")
    
    # Broadcast at Gen4
    b_gen4_det = sum(1 for r in good if r.get("gen4_broadcast_detected", False))
    c_gen4_det = sum(1 for r in good if r.get("gen4_combined_detected", False))
    b_psnr_mean = np.mean([r.get("broadcast_psnr", 0) for r in good])
    c_psnr_mean = np.mean([r.get("combined_psnr", 0) for r in good])
    
    print(f"  Broadcast mode:")
    print(f"    Gen4 detection: {b_gen4_det}/{n_good} ({b_gen4_det/n_good*100:.1f}%)")
    print(f"    Mean PSNR: {b_psnr_mean:.1f}dB")
    print(f"  Combined mode (fingerprint + broadcast):")
    print(f"    Gen4 detection: {c_gen4_det}/{n_good} ({c_gen4_det/n_good*100:.1f}%)")
    print(f"    Mean PSNR: {c_psnr_mean:.1f}dB")
    
    if b_gen4_det / n_good > 0.5 and b_psnr_mean > 40:
        verdict = f"BROADCAST MODE WORKS. {b_gen4_det/n_good*100:.0f}% detection at {b_psnr_mean:.0f}dB PSNR."
    elif b_gen4_det / n_good > 0.5:
        verdict = f"BROADCAST DETECTS but PSNR may be too low ({b_psnr_mean:.0f}dB)."
    elif c_gen4_det / n_good > 0.5:
        verdict = f"COMBINED MODE WORKS. {c_gen4_det/n_good*100:.0f}% detection at {c_psnr_mean:.0f}dB PSNR."
    else:
        verdict = f"NEAREST-PRIME INSUFFICIENT. Detection: broadcast {b_gen4_det/n_good*100:.0f}%, combined {c_gen4_det/n_good*100:.0f}%."
    
    print(f"\n  {verdict}")
    
    with open(os.path.join(output_dir, "NEAREST_PRIME_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
    
    aggregate = {
        "n_images": n_good,
        "broadcast_psnr_mean": round(b_psnr_mean, 2),
        "combined_psnr_mean": round(c_psnr_mean, 2),
        "broadcast_gen4_det_pct": round(b_gen4_det / n_good * 100, 1),
        "combined_gen4_det_pct": round(c_gen4_det / n_good * 100, 1),
        "broadcast_mean_shift": round(np.mean(shifts), 3),
    }
    with open(os.path.join(output_dir, "nearest_prime_aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Nearest-Prime Broadcast Mode — The Needle Stack Test"
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="nearest_prime_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    args = parser.parse_args()
    
    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory")
        sys.exit(1)
    
    run_corpus(args.input, args.output, max_images=args.max_images)
