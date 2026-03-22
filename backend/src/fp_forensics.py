#!/usr/bin/env python3
"""
False Positive Forensics — Hunting the Ghost Signal
=====================================================
Jeremy Pickett — Axiomatic Fictions Series

Dissects every false positive to understand:
  1. WHAT specifically in the distance distribution triggers the chi-squared
  2. WHERE in the prime spectrum the excess/deficit occurs
  3. WHY JPEG transforms create structure that mimics prime-gap embedding
  4. HOW the DCT quantization grid maps onto the prime-gap measurement domain

The goal: find the mechanism, not just the symptom.
"""

import os
import sys
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup, build_prime_set,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    load_and_decode, generate_synthetic_corpus, _gen_synthetic_photo,
)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


# =============================================================================
# CONFIGURATION
# =============================================================================

PRIME_FLOOR = 37  # Use the best floor from sweep
WINDOW_W = 8
BIT_DEPTH = 8
JPEG_QUALITY_LEVELS = [95, 85, 75, 60, 40]


# =============================================================================
# FORENSIC DISTANCE ANALYSIS
# =============================================================================

def full_distance_forensics(distances: np.ndarray, min_prime: int = 37,
                             label: str = "") -> dict:
    """
    Exhaustive forensic breakdown of a distance distribution.
    Returns every number you'd want to hunt with.
    """
    max_val = 255
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=min_prime)
    n = len(distances)

    # Full histogram
    hist, bin_edges = np.histogram(distances, bins=np.arange(0, max_val + 2) - 0.5)

    # Smoothed expectation (the model the chi-squared tests against)
    kernel = np.ones(5) / 5
    smoothed = np.convolve(hist.astype(float), kernel, mode='same')
    smoothed = np.maximum(smoothed, 1e-10)
    expected = smoothed * (hist.sum() / smoothed.sum())

    # Per-bin analysis: observed vs expected, residual, is_prime
    prime_indices = np.where(prime_lookup[:len(hist)])[0]
    nonprime_indices = np.where(~prime_lookup[:len(hist)])[0]

    # Residuals at prime bins
    residuals = np.zeros(len(hist), dtype=float)
    for i in range(len(hist)):
        if expected[i] > 0:
            residuals[i] = (hist[i] - expected[i]) / np.sqrt(expected[i])

    prime_residuals = residuals[prime_indices]
    nonprime_residuals = residuals[nonprime_indices] if len(nonprime_indices) > 0 else np.array([0])

    # Chi-squared components per prime bin
    chi2_components = np.zeros(len(hist))
    for i in prime_indices:
        if expected[i] > 5:
            chi2_components[i] = (hist[i] - expected[i])**2 / expected[i]

    # Top offenders: which prime bins contribute most to chi-squared
    offender_indices = np.argsort(chi2_components)[::-1]
    top_offenders = []
    for idx in offender_indices[:15]:
        if chi2_components[idx] > 0:
            top_offenders.append({
                "distance": int(idx),
                "is_prime": bool(prime_lookup[idx]) if idx < len(prime_lookup) else False,
                "observed": int(hist[idx]),
                "expected": float(expected[idx]),
                "residual": float(residuals[idx]),
                "chi2_contribution": float(chi2_components[idx]),
                "direction": "EXCESS" if hist[idx] > expected[idx] else "DEFICIT",
            })

    # Distance distribution shape metrics
    clamped = np.minimum(distances, max_val)
    prime_hits = prime_lookup[clamped]
    prime_dists = distances[prime_hits]
    nonprime_dists = distances[~prime_hits]

    # Mode analysis: what are the most common distances?
    top_distances = np.argsort(hist)[::-1][:20]
    mode_analysis = []
    for d in top_distances:
        if hist[d] > 0:
            mode_analysis.append({
                "distance": int(d),
                "count": int(hist[d]),
                "fraction": float(hist[d]) / n,
                "is_prime": bool(prime_lookup[d]) if d < len(prime_lookup) else False,
                "expected": float(expected[d]),
                "excess_ratio": float(hist[d] / expected[d]) if expected[d] > 0 else 0,
            })

    # Clustering analysis: are prime-valued distances clumping?
    # Look at runs of consecutive prime distances
    prime_positions = np.where(prime_hits)[0]
    if len(prime_positions) > 1:
        gaps_between_prime_hits = np.diff(prime_positions)
        clustering_metric = float(np.std(gaps_between_prime_hits) /
                                   np.mean(gaps_between_prime_hits))
    else:
        clustering_metric = 0.0

    # Quantization signature: do distances cluster at multiples of common
    # JPEG quantization table values?
    # Standard JPEG luminance quantization table (first row, most impactful):
    jpeg_quant_common = [16, 11, 10, 16, 24, 40, 51, 61]
    quant_multiples_hits = {}
    for q in jpeg_quant_common:
        multiples = np.arange(0, max_val + 1, q) if q > 0 else np.array([0])
        mult_set = set(multiples.tolist())
        hits_at_multiples = sum(1 for d in distances if int(d) in mult_set)
        quant_multiples_hits[q] = {
            "n_multiples_in_range": len(multiples),
            "hits": hits_at_multiples,
            "hit_rate": hits_at_multiples / n if n > 0 else 0,
            "expected_uniform": len(multiples) / (max_val + 1),
        }

    # Periodicity detection via autocorrelation of histogram
    hist_centered = hist.astype(float) - hist.mean()
    if np.std(hist_centered) > 0:
        autocorr = np.correlate(hist_centered, hist_centered, mode='full')
        autocorr = autocorr[len(autocorr)//2:]  # positive lags only
        autocorr = autocorr / autocorr[0]  # normalize
        # Find peaks in autocorrelation (skip lag 0)
        peak_lags = []
        for lag in range(2, min(64, len(autocorr))):
            if (autocorr[lag] > autocorr[lag-1] and
                autocorr[lag] > autocorr[lag+1] if lag+1 < len(autocorr) else True):
                if autocorr[lag] > 0.1:  # significance threshold
                    peak_lags.append({
                        "lag": int(lag),
                        "correlation": float(autocorr[lag]),
                        "is_prime": bool(prime_lookup[lag]) if lag < len(prime_lookup) else False,
                    })
    else:
        autocorr = np.zeros(1)
        peak_lags = []

    return {
        "label": label,
        "n_samples": n,
        "n_prime_hits": int(np.sum(prime_hits)),
        "prime_hit_rate": float(np.sum(prime_hits)) / n if n > 0 else 0,
        "mean_prime_residual": float(np.mean(prime_residuals)),
        "std_prime_residual": float(np.std(prime_residuals)),
        "mean_nonprime_residual": float(np.mean(nonprime_residuals)),
        "max_prime_residual": float(np.max(np.abs(prime_residuals))) if len(prime_residuals) > 0 else 0,
        "top_offenders": top_offenders,
        "mode_analysis": mode_analysis[:15],
        "clustering_metric": clustering_metric,
        "quant_multiples": quant_multiples_hits,
        "autocorrelation_peaks": sorted(peak_lags, key=lambda x: -x["correlation"])[:10],
        "histogram": hist.tolist(),
        "smoothed": smoothed.tolist(),
        "expected": expected.tolist(),
        "residuals": residuals.tolist(),
        "chi2_components": chi2_components.tolist(),
        "autocorrelation": autocorr[:64].tolist() if len(autocorr) > 0 else [],
    }


# =============================================================================
# JPEG TRANSFORM FORENSICS
# =============================================================================

def jpeg_transform_forensics(pixels: np.ndarray, quality: int,
                              min_prime: int = 37, output_dir: str = ".") -> dict:
    """
    Forensic comparison of distance distributions before and after JPEG.
    Identifies exactly what JPEG does to the measurement domain.
    """
    h, w, _ = pixels.shape
    positions = sample_positions_grid(h, w, WINDOW_W)
    dists_before = extract_distances(pixels, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]

    # JPEG roundtrip
    tmp_path = os.path.join(output_dir, f"_tmp_forensic_q{quality}.jpg")
    Image.fromarray(pixels).save(tmp_path, "JPEG", quality=quality)
    jpeg_pixels = np.array(Image.open(tmp_path).convert("RGB"))
    os.remove(tmp_path)

    dists_after = extract_distances(jpeg_pixels, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]

    before = full_distance_forensics(dists_before, min_prime, f"pre-JPEG")
    after = full_distance_forensics(dists_after, min_prime, f"post-JPEG-Q{quality}")

    # Difference analysis
    hist_before = np.array(before["histogram"])
    hist_after = np.array(after["histogram"])
    hist_diff = hist_after.astype(float) - hist_before.astype(float)

    # Which distances gained/lost the most?
    max_val = 255
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=min_prime)
    movement = []
    for d in range(max_val + 1):
        if abs(hist_diff[d]) > 10:
            movement.append({
                "distance": d,
                "before": int(hist_before[d]),
                "after": int(hist_after[d]),
                "delta": int(hist_diff[d]),
                "is_prime": bool(prime_lookup[d]) if d < len(prime_lookup) else False,
                "direction": "GAINED" if hist_diff[d] > 0 else "LOST",
            })
    movement.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # Per-pixel value change analysis
    pixel_diff = jpeg_pixels.astype(np.int16) - pixels.astype(np.int16)
    flat_diff = pixel_diff.reshape(-1)

    # Quantization grid signature: JPEG quantizes in 8x8 blocks
    # Check if distance changes cluster at DCT-related intervals
    # Common quantization step sizes create value changes that are
    # multiples of those steps
    value_change_hist, _ = np.histogram(flat_diff, bins=np.arange(-128, 129) - 0.5)

    # Do the VALUE changes (not distances) show periodicity?
    change_autocorr = np.correlate(
        value_change_hist.astype(float) - value_change_hist.mean(),
        value_change_hist.astype(float) - value_change_hist.mean(),
        mode='full'
    )
    change_autocorr = change_autocorr[len(change_autocorr)//2:]
    if change_autocorr[0] > 0:
        change_autocorr = change_autocorr / change_autocorr[0]

    return {
        "quality": quality,
        "before": before,
        "after": after,
        "top_movements": movement[:20],
        "pixel_value_change_mean": float(np.mean(flat_diff)),
        "pixel_value_change_std": float(np.std(flat_diff)),
        "pixel_value_change_median": float(np.median(flat_diff)),
        "pixel_value_change_p95": float(np.percentile(np.abs(flat_diff), 95)),
        "value_change_histogram": value_change_hist.tolist(),
        "value_change_autocorrelation": change_autocorr[:32].tolist(),
        "hist_diff": hist_diff.tolist(),
    }


# =============================================================================
# FALSE POSITIVE CATALOG
# =============================================================================

def catalog_false_positives(corpus_dir: str, output_dir: str,
                             min_prime: int = 37, alpha: float = 0.01):
    """
    Identify and forensically examine every false positive in the corpus.
    """
    os.makedirs(output_dir, exist_ok=True)

    image_paths = sorted([
        os.path.join(corpus_dir, f) for f in os.listdir(corpus_dir)
        if f.endswith('.png')
    ])

    print(f"Scanning {len(image_paths)} images at floor={min_prime}, α={alpha}\n")

    fp_catalog = []
    all_results = []
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=min_prime)

    for path in image_paths:
        fname = os.path.basename(path)
        pixels = load_and_decode(path)
        if pixels is None:
            continue

        h, w, _ = pixels.shape
        positions = sample_positions_grid(h, w, WINDOW_W)
        dists = extract_distances(pixels, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]

        forensics = full_distance_forensics(dists, min_prime, fname)

        # Run chi-squared
        hist = np.array(forensics["histogram"])
        exp = np.array(forensics["expected"])
        prime_indices = np.where(prime_lookup[:len(hist)])[0]
        chi2_p = 1.0
        chi2_stat = 0.0
        if len(prime_indices) > 1:
            obs = hist[prime_indices].astype(float)
            exp_v = exp[prime_indices]
            valid = exp_v > 5
            if np.sum(valid) > 2:
                obs_v = obs[valid]
                exp_v2 = exp_v[valid]
                exp_v2 = exp_v2 * (obs_v.sum() / exp_v2.sum())
                try:
                    chi2_stat, chi2_p = sp_stats.chisquare(obs_v, exp_v2)
                except:
                    pass

        is_fp = chi2_p < alpha
        forensics["chi2_p"] = chi2_p
        forensics["chi2_stat"] = chi2_stat
        forensics["is_false_positive"] = is_fp

        cls = fname.rsplit("_", 1)[0]
        forensics["image_class"] = cls
        forensics["filepath"] = path
        forensics["dimensions"] = f"{w}x{h}"

        all_results.append(forensics)
        if is_fp:
            fp_catalog.append(forensics)

        status = "*** FP ***" if is_fp else "OK"
        print(f"  {fname:35s}  p={chi2_p:.6f}  ρ={forensics['prime_hit_rate']:.4f}  [{status}]")

    print(f"\n{'='*72}")
    print(f"FALSE POSITIVE CATALOG — floor={min_prime}, α={alpha}")
    print(f"{'='*72}")
    print(f"\nTotal images: {len(all_results)}")
    print(f"False positives: {len(fp_catalog)} ({len(fp_catalog)/len(all_results)*100:.1f}%)")

    # Group FPs by class
    fp_by_class = {}
    for fp in fp_catalog:
        cls = fp["image_class"]
        if cls not in fp_by_class:
            fp_by_class[cls] = []
        fp_by_class[cls].append(fp)

    print(f"\nFP breakdown by class:")
    for cls, fps in sorted(fp_by_class.items()):
        print(f"  {cls}: {len(fps)} FPs")

    # For each FP, print the top offending bins
    print(f"\n{'='*72}")
    print(f"FORENSIC DETAIL — WHAT'S TRIGGERING EACH FP")
    print(f"{'='*72}")

    for fp in fp_catalog:
        print(f"\n--- {fp['label']} ({fp['image_class']}) ---")
        print(f"  p={fp['chi2_p']:.2e}  ρ={fp['prime_hit_rate']:.4f}")
        print(f"  Mean prime residual: {fp['mean_prime_residual']:+.3f}")
        print(f"  Mean non-prime residual: {fp['mean_nonprime_residual']:+.3f}")
        print(f"  Max |prime residual|: {fp['max_prime_residual']:.3f}")

        print(f"\n  Top chi-squared offenders (what's driving the FP):")
        for off in fp["top_offenders"][:8]:
            prime_flag = " [PRIME]" if off["is_prime"] else ""
            print(f"    d={off['distance']:>3d}{prime_flag:>8s}  obs={off['observed']:>5d}"
                  f"  exp={off['expected']:>8.1f}  residual={off['residual']:>+6.2f}"
                  f"  χ²={off['chi2_contribution']:>8.2f}  {off['direction']}")

        print(f"\n  Distance modes (most common distances):")
        for m in fp["mode_analysis"][:8]:
            prime_flag = " [PRIME]" if m["is_prime"] else ""
            print(f"    d={m['distance']:>3d}{prime_flag:>8s}  count={m['count']:>5d}"
                  f"  frac={m['fraction']:.4f}  excess_ratio={m['excess_ratio']:.3f}")

        if fp["autocorrelation_peaks"]:
            print(f"\n  Autocorrelation peaks (periodicity in histogram):")
            for pk in fp["autocorrelation_peaks"][:5]:
                prime_flag = " [PRIME]" if pk["is_prime"] else ""
                print(f"    lag={pk['lag']:>3d}{prime_flag:>8s}"
                      f"  corr={pk['correlation']:.4f}")

    return fp_catalog, all_results


# =============================================================================
# JPEG ARTIFACT HUNTING
# =============================================================================

def hunt_jpeg_artifacts(output_dir: str, min_prime: int = 37):
    """
    Detailed forensic analysis of what JPEG does to the distance distribution.
    This is the core question: what specifically does DCT quantization do
    in the prime-gap measurement domain?
    """
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)

    # Test on multiple image types
    test_images = {
        "photo_synthetic": _gen_synthetic_photo(512, 512, rng),
        "noise_uniform": rng.randint(0, 256, (512, 512, 3)).astype(np.uint8),
        "noise_gaussian": np.clip(rng.normal(128, 40, (512, 512, 3)), 0, 255).astype(np.uint8),
        "low_contrast": np.clip(rng.normal(128, 10, (512, 512, 3)), 0, 255).astype(np.uint8),
    }

    print(f"\n{'='*72}")
    print(f"JPEG ARTIFACT FORENSICS — What DCT Does to the Measurement Domain")
    print(f"{'='*72}")

    all_jpeg_forensics = {}

    for img_name, pixels in test_images.items():
        print(f"\n{'='*60}")
        print(f"Image: {img_name} (512x512)")
        print(f"{'='*60}")

        all_jpeg_forensics[img_name] = {}

        for q in JPEG_QUALITY_LEVELS:
            print(f"\n  --- JPEG Q{q} ---")
            forensics = jpeg_transform_forensics(pixels, q, min_prime, output_dir)
            all_jpeg_forensics[img_name][q] = forensics

            print(f"  Pixel value change: mean={forensics['pixel_value_change_mean']:+.2f}"
                  f"  std={forensics['pixel_value_change_std']:.2f}"
                  f"  p95_abs={forensics['pixel_value_change_p95']:.1f}")

            before_rho = forensics["before"]["prime_hit_rate"]
            after_rho = forensics["after"]["prime_hit_rate"]
            delta = after_rho - before_rho
            print(f"  ρ: {before_rho:.4f} → {after_rho:.4f}  (Δ={delta:+.4f})")

            # What moved?
            print(f"\n  Largest distance bin movements (JPEG redistribution):")
            for mv in forensics["top_movements"][:10]:
                prime_flag = " [PRIME]" if mv["is_prime"] else ""
                print(f"    d={mv['distance']:>3d}{prime_flag:>8s}"
                      f"  {mv['before']:>5d} → {mv['after']:>5d}"
                      f"  (Δ={mv['delta']:>+5d})  {mv['direction']}")

            # Autocorrelation peaks in post-JPEG
            if forensics["after"]["autocorrelation_peaks"]:
                print(f"\n  Post-JPEG distance histogram periodicity:")
                for pk in forensics["after"]["autocorrelation_peaks"][:5]:
                    prime_flag = " [PRIME]" if pk["is_prime"] else ""
                    print(f"    period={pk['lag']:>3d}{prime_flag:>8s}"
                          f"  strength={pk['correlation']:.4f}")

            # Quantization multiple analysis
            print(f"\n  Quantization grid alignment (post-JPEG):")
            for qv, info in sorted(forensics["after"]["quant_multiples"].items()):
                ratio = info["hit_rate"] / info["expected_uniform"] if info["expected_uniform"] > 0 else 0
                flag = " ***" if ratio > 1.5 else ""
                print(f"    multiples of {qv:>2d}: hit_rate={info['hit_rate']:.4f}"
                      f"  expected={info['expected_uniform']:.4f}"
                      f"  ratio={ratio:.2f}{flag}")

    return all_jpeg_forensics


# =============================================================================
# VISUALIZATION
# =============================================================================

def plot_fp_forensics(fp_catalog: list, all_results: list, output_dir: str,
                       min_prime: int = 37):
    """Generate forensic visualizations of the false positives."""
    os.makedirs(output_dir, exist_ok=True)
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=min_prime)
    prime_indices = np.where(prime_lookup)[0]

    # --- Plot 1: FP vs OK residual distributions ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    fp_residuals_all = []
    ok_residuals_all = []
    for r in all_results:
        residuals = np.array(r["residuals"])
        prime_resid = residuals[prime_indices[prime_indices < len(residuals)]]
        if r["is_false_positive"]:
            fp_residuals_all.extend(prime_resid.tolist())
        else:
            ok_residuals_all.extend(prime_resid.tolist())

    if fp_residuals_all:
        axes[0].hist(fp_residuals_all, bins=50, alpha=0.7, color='#E85D3A',
                     label=f'FP images (n={len(fp_catalog)})', density=True)
    if ok_residuals_all:
        axes[0].hist(ok_residuals_all, bins=50, alpha=0.5, color='#2C5F8A',
                     label=f'OK images', density=True)
    axes[0].set_xlabel('Standardized Residual at Prime Bins', fontsize=11)
    axes[0].set_ylabel('Density', fontsize=11)
    axes[0].set_title('Prime Bin Residuals: FP vs Clean', fontsize=13)
    axes[0].legend(fontsize=10)
    axes[0].axvline(0, color='black', linewidth=0.5)

    # Per-prime-bin average residual for FPs
    fp_mean_per_bin = np.zeros(256)
    fp_count = 0
    for r in all_results:
        if r["is_false_positive"]:
            res = np.array(r["residuals"])
            fp_mean_per_bin[:len(res)] += res
            fp_count += 1
    if fp_count > 0:
        fp_mean_per_bin /= fp_count

    axes[1].bar(range(256), fp_mean_per_bin, width=1.0, color='#CCCCCC', alpha=0.5)
    # Highlight prime bins
    for p in prime_indices:
        if p < 256:
            axes[1].bar(p, fp_mean_per_bin[p], width=1.0, color='#E85D3A', alpha=0.9)
    axes[1].set_xlabel('Distance Value', fontsize=11)
    axes[1].set_ylabel('Mean Residual', fontsize=11)
    axes[1].set_title('Mean Residual by Distance — FP Images Only (red = prime bins)',
                       fontsize=13)
    axes[1].set_xlim(-1, 256)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fp_residual_analysis.png'), dpi=150)
    plt.close()

    # --- Plot 2: Chi-squared contribution heatmap per FP ---
    if fp_catalog:
        fig, ax = plt.subplots(1, 1, figsize=(14, max(4, len(fp_catalog) * 0.5 + 1)))
        chi2_matrix = []
        labels = []
        for fp in fp_catalog:
            components = np.array(fp["chi2_components"])
            # Only show prime bins
            prime_components = np.zeros(256)
            for p in prime_indices:
                if p < len(components):
                    prime_components[p] = components[p]
            chi2_matrix.append(prime_components)
            labels.append(f"{fp['label']} ({fp['image_class']})")

        matrix = np.array(chi2_matrix)
        # Only show columns with nonzero values
        active_cols = np.where(matrix.sum(axis=0) > 0)[0]
        if len(active_cols) > 0:
            sub_matrix = matrix[:, active_cols]
            im = ax.imshow(sub_matrix, aspect='auto', cmap='Reds', interpolation='nearest')
            ax.set_xticks(range(len(active_cols)))
            ax.set_xticklabels([str(c) for c in active_cols], fontsize=7, rotation=90)
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels, fontsize=9)
            ax.set_xlabel('Distance Value (prime bins only)', fontsize=11)
            ax.set_title('Chi-squared Contribution by Prime Bin — Each FP Image', fontsize=13)
            plt.colorbar(im, ax=ax, label='χ² contribution')

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'fp_chi2_heatmap.png'), dpi=150)
        plt.close()

    # --- Plot 3: Distance histograms — FP examples vs OK examples ---
    # Pick the worst FP and the most "normal" OK image
    if fp_catalog and all_results:
        worst_fp = min(fp_catalog, key=lambda x: x["chi2_p"])
        ok_images = [r for r in all_results if not r["is_false_positive"]]
        best_ok = max(ok_images, key=lambda x: x["chi2_p"]) if ok_images else None

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # Worst FP
        hist_fp = np.array(worst_fp["histogram"])
        exp_fp = np.array(worst_fp["expected"])
        x = np.arange(len(hist_fp))
        axes[0].bar(x, hist_fp, width=1.0, color='#CCCCCC', alpha=0.6, label='Observed')
        axes[0].plot(x, exp_fp, color='#2C5F8A', linewidth=1.5, label='Smoothed expected')
        for p in prime_indices:
            if p < len(hist_fp):
                color = '#E85D3A' if hist_fp[p] > exp_fp[p] else '#4CAF50'
                axes[0].bar(p, hist_fp[p], width=1.0, color=color, alpha=0.9)
        axes[0].set_title(f'Worst FP: {worst_fp["label"]} — p={worst_fp["chi2_p"]:.2e}'
                          f' (red=prime excess, green=prime deficit)', fontsize=12)
        axes[0].set_xlabel('Distance', fontsize=10)
        axes[0].set_ylabel('Count', fontsize=10)
        axes[0].legend(fontsize=10)
        axes[0].set_xlim(-1, 180)

        # Best OK
        if best_ok:
            hist_ok = np.array(best_ok["histogram"])
            exp_ok = np.array(best_ok["expected"])
            axes[1].bar(x[:len(hist_ok)], hist_ok, width=1.0, color='#CCCCCC',
                        alpha=0.6, label='Observed')
            axes[1].plot(x[:len(exp_ok)], exp_ok, color='#2C5F8A', linewidth=1.5,
                         label='Smoothed expected')
            for p in prime_indices:
                if p < len(hist_ok):
                    color = '#E85D3A' if hist_ok[p] > exp_ok[p] else '#4CAF50'
                    axes[1].bar(p, hist_ok[p], width=1.0, color=color, alpha=0.9)
            axes[1].set_title(f'Best OK: {best_ok["label"]} — p={best_ok["chi2_p"]:.2e}',
                              fontsize=12)
            axes[1].set_xlabel('Distance', fontsize=10)
            axes[1].set_ylabel('Count', fontsize=10)
            axes[1].legend(fontsize=10)
            axes[1].set_xlim(-1, 180)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'fp_vs_ok_histograms.png'), dpi=150)
        plt.close()

    # --- Plot 4: FP by image class — stacked bar ---
    class_counts = {}
    class_totals = {}
    for r in all_results:
        cls = r["image_class"]
        class_totals[cls] = class_totals.get(cls, 0) + 1
        if r["is_false_positive"]:
            class_counts[cls] = class_counts.get(cls, 0) + 1

    classes = sorted(class_totals.keys())
    fig, ax = plt.subplots(1, 1, figsize=(10, 5))
    fp_counts = [class_counts.get(c, 0) for c in classes]
    ok_counts = [class_totals[c] - class_counts.get(c, 0) for c in classes]
    x = np.arange(len(classes))
    ax.bar(x, fp_counts, color='#E85D3A', alpha=0.8, label='False Positive')
    ax.bar(x, ok_counts, bottom=fp_counts, color='#2C5F8A', alpha=0.6, label='OK')
    ax.set_xticks(x)
    ax.set_xticklabels(classes, rotation=35, ha='right', fontsize=10)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title(f'False Positives by Image Class (floor={min_prime}, α=0.01)', fontsize=14)
    ax.legend(fontsize=11)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fp_by_class.png'), dpi=150)
    plt.close()


def plot_jpeg_forensics(jpeg_forensics: dict, output_dir: str, min_prime: int = 37):
    """Visualize JPEG artifact structure in the measurement domain."""
    os.makedirs(output_dir, exist_ok=True)
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=min_prime)
    prime_indices = np.where(prime_lookup)[0]

    for img_name, quality_data in jpeg_forensics.items():
        # --- Per-image: distance histogram diff across quality levels ---
        fig, axes = plt.subplots(len(quality_data), 1,
                                 figsize=(14, 3 * len(quality_data)))
        if len(quality_data) == 1:
            axes = [axes]

        for idx, (q, forensics) in enumerate(sorted(quality_data.items())):
            diff = np.array(forensics["hist_diff"])
            x = np.arange(len(diff))
            colors = ['#E85D3A' if i in set(prime_indices.tolist()) else '#CCCCCC'
                      for i in range(len(diff))]
            axes[idx].bar(x, diff, width=1.0, color=colors, alpha=0.7)
            axes[idx].axhline(0, color='black', linewidth=0.5)
            axes[idx].set_ylabel('Δ Count', fontsize=10)
            axes[idx].set_title(f'{img_name} — Q{q}: Distance bin changes '
                                f'(red = prime bins)', fontsize=11)
            axes[idx].set_xlim(-1, 180)

        axes[-1].set_xlabel('Distance Value', fontsize=11)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'jpeg_diff_{img_name}.png'), dpi=150)
        plt.close()

        # --- Value change autocorrelation ---
        fig, axes = plt.subplots(1, len(quality_data), figsize=(4 * len(quality_data), 4))
        if len(quality_data) == 1:
            axes = [axes]
        for idx, (q, forensics) in enumerate(sorted(quality_data.items())):
            ac = forensics["value_change_autocorrelation"]
            axes[idx].bar(range(len(ac)), ac, width=1.0, color='#2C5F8A', alpha=0.7)
            axes[idx].set_title(f'Q{q} value change autocorr', fontsize=10)
            axes[idx].set_xlabel('Lag', fontsize=9)
            axes[idx].set_ylim(-0.3, 1.05)
            # Mark JPEG-relevant periods
            for period in [8, 16]:
                if period < len(ac):
                    axes[idx].axvline(period, color='red', linestyle=':', alpha=0.5,
                                      label=f'period={period}')
            axes[idx].legend(fontsize=8)
        plt.suptitle(f'{img_name} — Pixel Value Change Autocorrelation', fontsize=12)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'jpeg_autocorr_{img_name}.png'), dpi=150)
        plt.close()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    output_dir = "pgps_results/forensics"
    corpus_dir = "pgps_results/synthetic_corpus"
    os.makedirs(output_dir, exist_ok=True)

    # Ensure corpus exists
    if not os.path.exists(corpus_dir):
        print("Generating synthetic corpus...")
        generate_synthetic_corpus(corpus_dir, n_per_class=10)

    # Phase 1: Catalog all false positives
    print("\n" + "#" * 72)
    print("# PHASE 1: FALSE POSITIVE CATALOG")
    print("#" * 72)
    fp_catalog, all_results = catalog_false_positives(
        corpus_dir, output_dir, min_prime=PRIME_FLOOR, alpha=0.01
    )

    # Phase 2: JPEG artifact hunting
    print("\n\n" + "#" * 72)
    print("# PHASE 2: JPEG ARTIFACT FORENSICS")
    print("#" * 72)
    jpeg_forensics = hunt_jpeg_artifacts(output_dir, min_prime=PRIME_FLOOR)

    # Phase 3: Visualizations
    print("\n\n" + "#" * 72)
    print("# PHASE 3: GENERATING FORENSIC PLOTS")
    print("#" * 72)
    plot_dir = os.path.join(output_dir, "plots")
    plot_fp_forensics(fp_catalog, all_results, plot_dir, min_prime=PRIME_FLOOR)
    plot_jpeg_forensics(jpeg_forensics, plot_dir, min_prime=PRIME_FLOOR)

    # Save raw forensics
    # (skip histogram/autocorr arrays in the JSON to keep it readable)
    summary = {
        "min_prime": PRIME_FLOOR,
        "alpha": 0.01,
        "n_images": len(all_results),
        "n_fps": len(fp_catalog),
        "fp_rate": len(fp_catalog) / len(all_results) if all_results else 0,
        "fp_images": [
            {
                "label": fp["label"],
                "class": fp["image_class"],
                "chi2_p": fp["chi2_p"],
                "rho": fp["prime_hit_rate"],
                "mean_prime_residual": fp["mean_prime_residual"],
                "top_offenders": fp["top_offenders"][:5],
                "autocorrelation_peaks": fp["autocorrelation_peaks"][:5],
            }
            for fp in fp_catalog
        ],
    }
    with open(os.path.join(output_dir, "fp_forensics_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nAll forensic artifacts saved to {output_dir}/")
    print("Done.")
