#!/usr/bin/env python3
"""
Prime Floor Sweep — Testing the Diffie-Hellman Intuition
=========================================================
Jeremy Pickett — Axiomatic Fictions Series

Hypothesis: small primes (2,3,5,7,11,13) in the basket cause false
positives because natural images concentrate channel-pair distances
in the low range where prime density is highest.

This script sweeps min_prime across [2, 7, 11, 17, 23, 29, 37, 41, 53]
and reports:
  - Basket size at each floor
  - Natural ρ (background hit rate on clean images)
  - False positive rate (chi-squared)
  - Roundtrip: ρ before/after embedding, detection delta, JPEG survival
"""

import os
import sys
import time
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from dataclasses import dataclass, field

# Import from the detector
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    load_and_decode, generate_synthetic_corpus, _gen_synthetic_photo,
    analyze_distances,
)


# =========================================================================
# SWEEP CONFIGURATION
# =========================================================================

PRIME_FLOORS = [2, 7, 11, 17, 23, 29, 37, 41, 53, 67, 83, 97, 127]
JPEG_QUALITY_LEVELS = [95, 85, 75, 60, 40]
N_EMBED_MARKERS = 500
WINDOW_W = 8
BIT_DEPTH = 8


# =========================================================================
# CORE ANALYSIS (inlined with min_prime support)
# =========================================================================

def basket_info(min_prime: int, bit_depth: int = 8) -> dict:
    """Report basket composition at a given floor."""
    max_val = (1 << bit_depth) - 1
    all_primes = sieve_of_eratosthenes(max_val)
    basket = all_primes[all_primes >= min_prime]
    return {
        "min_prime": min_prime,
        "basket_size": len(basket),
        "total_primes_in_range": len(all_primes),
        "density": len(basket) / (max_val + 1),
        "smallest": int(basket[0]) if len(basket) > 0 else None,
        "largest": int(basket[-1]) if len(basket) > 0 else None,
        "dropped": sorted(set(all_primes.tolist()) - set(basket.tolist())),
    }


def analyze_distances_at_floor(distances: np.ndarray, min_prime: int,
                                bit_depth: int = 8) -> dict:
    """Analyze prime-gap hit rate and chi-squared at a given floor."""
    prime_lookup = build_prime_lookup(bit_depth, min_prime=min_prime)
    max_val = (1 << bit_depth) - 1
    n = len(distances)
    if n == 0:
        return {"rho": 0, "chi2_p": 1.0, "n_hits": 0, "hit_rate": 0,
                "expected_uniform": 0}

    clamped = np.minimum(distances, max_val)
    hits = prime_lookup[clamped]
    n_hits = int(np.sum(hits))
    hit_rate = n_hits / n

    # Expected under uniform
    n_primes = int(np.sum(prime_lookup))
    expected_uniform = n_primes / (max_val + 1)

    # Chi-squared: prime bins vs smoothed expectation
    hist, _ = np.histogram(distances, bins=np.arange(0, max_val + 2) - 0.5)
    kernel = np.ones(5) / 5
    smoothed = np.convolve(hist.astype(float), kernel, mode='same')
    smoothed = np.maximum(smoothed, 1e-10)
    total = hist.sum()
    expected = smoothed * (total / smoothed.sum())

    prime_indices = np.where(prime_lookup[:len(hist)])[0]
    chi2_p = 1.0
    chi2_stat = 0.0
    if len(prime_indices) > 1:
        obs = hist[prime_indices].astype(float)
        exp = expected[prime_indices]
        valid = exp > 5
        if np.sum(valid) > 2:
            obs_v = obs[valid]
            exp_v = exp[valid]
            exp_v = exp_v * (obs_v.sum() / exp_v.sum())
            try:
                chi2_stat, chi2_p = sp_stats.chisquare(obs_v, exp_v)
            except:
                pass

    return {
        "rho": hit_rate,
        "chi2_p": float(chi2_p),
        "chi2_stat": float(chi2_stat),
        "n_hits": n_hits,
        "hit_rate": hit_rate,
        "expected_uniform": expected_uniform,
        "n_primes_in_basket": n_primes,
    }


def embed_at_floor(pixels: np.ndarray, min_prime: int,
                   n_markers: int = 500, seed: int = 99) -> np.ndarray:
    """Embed prime-gap markers using only primes >= min_prime."""
    h, w, c = pixels.shape
    modified = pixels.copy().astype(np.int16)
    rng = np.random.RandomState(seed)

    all_primes = sieve_of_eratosthenes(255)
    basket = all_primes[all_primes >= min_prime]
    # Cap target primes to keep adjustments reasonable
    basket = basket[basket <= 127]

    if len(basket) == 0:
        return pixels.copy()

    positions = sample_positions_grid(h, w, WINDOW_W)
    if n_markers > len(positions):
        n_markers = len(positions)
    indices = rng.choice(len(positions), size=n_markers, replace=False)
    marker_positions = positions[indices]

    for pos in marker_positions:
        r, col = pos
        target = int(rng.choice(basket))
        current_r = int(modified[r, col, 0])
        if current_r >= target:
            new_g = current_r - target
        else:
            new_g = current_r + target
        modified[r, col, 1] = np.clip(new_g, 0, 255)

    return np.clip(modified, 0, 255).astype(np.uint8)


# =========================================================================
# SWEEP
# =========================================================================

def run_sweep(corpus_dir: str, output_dir: str):
    """Run the full prime floor sweep."""
    os.makedirs(output_dir, exist_ok=True)

    # Generate synthetic corpus if needed
    if not os.path.exists(corpus_dir):
        print("Generating synthetic corpus...")
        generate_synthetic_corpus(corpus_dir, n_per_class=10)

    image_paths = sorted([
        os.path.join(corpus_dir, f) for f in os.listdir(corpus_dir)
        if f.endswith('.png')
    ])
    print(f"Corpus: {len(image_paths)} images\n")

    # Pre-extract all distances once (they don't change with min_prime)
    print("Pre-extracting distances from all images...")
    image_distances = {}  # path -> distances array
    image_classes = {}    # path -> class name
    for path in image_paths:
        pixels = load_and_decode(path)
        if pixels is None:
            continue
        h, w, _ = pixels.shape
        positions = sample_positions_grid(h, w, WINDOW_W)
        dists = extract_distances(pixels, positions, DEFAULT_CHANNEL_PAIRS)
        image_distances[path] = dists["ALL"]
        fname = os.path.basename(path)
        image_classes[path] = fname.rsplit("_", 1)[0]
    print(f"Extracted distances from {len(image_distances)} images.\n")

    # Also prepare a test image for roundtrip
    rng = np.random.RandomState(42)
    test_pixels = _gen_synthetic_photo(512, 512, rng)

    # --- SWEEP ---
    results = []
    print(f"{'Floor':>6s}  {'Basket':>6s}  {'Density':>8s}  "
          f"{'ρ mean':>8s}  {'ρ std':>8s}  "
          f"{'FP@.05':>7s}  {'FP@.01':>7s}  {'FP@.001':>8s}  "
          f"{'Δρ embed':>9s}  {'JPEG95':>7s}  {'JPEG75':>7s}  {'JPEG40':>7s}")
    print("-" * 120)

    for floor in PRIME_FLOORS:
        info = basket_info(floor)

        if info["basket_size"] == 0:
            print(f"{floor:>6d}  {'EMPTY':>6s}  — basket exhausted —")
            continue

        # Null hypothesis: analyze all clean images at this floor
        rhos = []
        pvals = []
        class_rhos = {}
        for path, dists in image_distances.items():
            stats = analyze_distances_at_floor(dists, floor)
            rhos.append(stats["rho"])
            pvals.append(stats["chi2_p"])
            cls = image_classes[path]
            if cls not in class_rhos:
                class_rhos[cls] = []
            class_rhos[cls].append(stats["rho"])

        rho_arr = np.array(rhos)
        pval_arr = np.array(pvals)
        fp_05 = float(np.mean(pval_arr < 0.05))
        fp_01 = float(np.mean(pval_arr < 0.01))
        fp_001 = float(np.mean(pval_arr < 0.001))

        # Roundtrip: embed and detect
        h, w, _ = test_pixels.shape
        positions = sample_positions_grid(h, w, WINDOW_W)
        clean_dists = extract_distances(test_pixels, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]
        clean_stats = analyze_distances_at_floor(clean_dists, floor)

        embedded = embed_at_floor(test_pixels, floor, n_markers=N_EMBED_MARKERS)
        emb_dists = extract_distances(embedded, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]
        emb_stats = analyze_distances_at_floor(emb_dists, floor)

        delta_rho = emb_stats["rho"] - clean_stats["rho"]

        # JPEG survival
        jpeg_results = {}
        for q in JPEG_QUALITY_LEVELS:
            tmp_path = os.path.join(output_dir, f"_tmp_q{q}.jpg")
            Image.fromarray(embedded).save(tmp_path, "JPEG", quality=q)
            jpeg_pixels = np.array(Image.open(tmp_path).convert("RGB"))
            jpeg_dists = extract_distances(jpeg_pixels, positions, DEFAULT_CHANNEL_PAIRS)["ALL"]
            jpeg_stats = analyze_distances_at_floor(jpeg_dists, floor)
            jpeg_results[q] = {
                "rho": jpeg_stats["rho"],
                "delta_rho": jpeg_stats["rho"] - clean_stats["rho"],
                "chi2_p": jpeg_stats["chi2_p"],
            }
            os.remove(tmp_path)

        row = {
            "min_prime": floor,
            "basket_size": info["basket_size"],
            "density": info["density"],
            "dropped": info["dropped"],
            "mean_rho": float(np.mean(rho_arr)),
            "std_rho": float(np.std(rho_arr)),
            "median_rho": float(np.median(rho_arr)),
            "fp_rate_05": fp_05,
            "fp_rate_01": fp_01,
            "fp_rate_001": fp_001,
            "per_class_mean_rho": {
                cls: float(np.mean(v)) for cls, v in sorted(class_rhos.items())
            },
            "per_class_std_rho": {
                cls: float(np.std(v)) for cls, v in sorted(class_rhos.items())
            },
            "roundtrip_clean_rho": clean_stats["rho"],
            "roundtrip_embedded_rho": emb_stats["rho"],
            "roundtrip_delta_rho": delta_rho,
            "roundtrip_embedded_p": emb_stats["chi2_p"],
            "jpeg_survival": jpeg_results,
        }
        results.append(row)

        j95 = jpeg_results.get(95, {}).get("delta_rho", 0)
        j75 = jpeg_results.get(75, {}).get("delta_rho", 0)
        j40 = jpeg_results.get(40, {}).get("delta_rho", 0)

        print(f"{floor:>6d}  {info['basket_size']:>6d}  {info['density']:>8.4f}  "
              f"{row['mean_rho']:>8.4f}  {row['std_rho']:>8.4f}  "
              f"{fp_05:>6.1%}  {fp_01:>6.1%}  {fp_001:>7.1%}  "
              f"{delta_rho:>+9.4f}  {j95:>+7.4f}  {j75:>+7.4f}  {j40:>+7.4f}")

    # --- DETAILED REPORT ---
    print("\n\n" + "=" * 80)
    print("PRIME FLOOR SWEEP — DETAILED FINDINGS")
    print("=" * 80)

    print("\n--- Basket Composition ---")
    for r in results:
        dropped_str = ", ".join(str(p) for p in r["dropped"]) if r["dropped"] else "none"
        print(f"  Floor {r['min_prime']:>3d}: basket={r['basket_size']:>2d} primes, "
              f"density={r['density']:.4f}, dropped=[{dropped_str}]")

    print("\n--- Per-Class ρ at Each Floor ---")
    if results:
        classes = sorted(results[0]["per_class_mean_rho"].keys())
        header = f"  {'Floor':>5s}  " + "  ".join(f"{c:>16s}" for c in classes)
        print(header)
        for r in results:
            vals = "  ".join(
                f"{r['per_class_mean_rho'][c]:>7.4f}±{r['per_class_std_rho'][c]:<7.4f}"
                for c in classes
            )
            print(f"  {r['min_prime']:>5d}  {vals}")

    print("\n--- JPEG Survival (Δρ = embedded ρ - clean ρ) ---")
    header = f"  {'Floor':>5s}  {'Clean ρ':>8s}  {'Emb ρ':>8s}  {'Δρ':>8s}  "
    header += "  ".join(f"{'Q'+str(q):>8s}" for q in JPEG_QUALITY_LEVELS)
    print(header)
    for r in results:
        vals = "  ".join(
            f"{r['jpeg_survival'].get(q, {}).get('delta_rho', 0):>+8.4f}"
            for q in JPEG_QUALITY_LEVELS
        )
        print(f"  {r['min_prime']:>5d}  {r['roundtrip_clean_rho']:>8.4f}"
              f"  {r['roundtrip_embedded_rho']:>8.4f}"
              f"  {r['roundtrip_delta_rho']:>+8.4f}  {vals}")

    print("\n--- Key Tradeoff ---")
    print("  Higher floor → lower background ρ → fewer false positives")
    print("  Higher floor → larger gap modifications → more perceptible")
    print("  Higher floor → sparser basket → less embedding flexibility")
    print("  The sweet spot is where FP rate drops to acceptable levels")
    print("  while Δρ (signal strength) remains measurably positive.")

    # Save JSON
    json_path = os.path.join(output_dir, "prime_floor_sweep.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {json_path}")

    return results


# =========================================================================
# VISUALIZATION
# =========================================================================

def generate_sweep_plots(results: list, output_dir: str):
    """Generate comparison plots across prime floors."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)
    floors = [r["min_prime"] for r in results]

    # --- Plot 1: FP rate vs floor ---
    fig, ax = plt.subplots(1, 1, figsize=(11, 5))
    ax.plot(floors, [r["fp_rate_05"] for r in results], 'o-', linewidth=2,
            markersize=7, label='FP at α=0.05', color='#E85D3A')
    ax.plot(floors, [r["fp_rate_01"] for r in results], 's-', linewidth=2,
            markersize=7, label='FP at α=0.01', color='#2C5F8A')
    ax.plot(floors, [r["fp_rate_001"] for r in results], '^-', linewidth=2,
            markersize=7, label='FP at α=0.001', color='#4CAF50')
    ax.set_xlabel('Minimum Prime in Basket', fontsize=12)
    ax.set_ylabel('False Positive Rate', fontsize=12)
    ax.set_title('False Positive Rate vs Prime Floor — The DH Intuition', fontsize=14)
    ax.legend(fontsize=11)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    for f in [17, 23, 29]:
        ax.axvline(f, color='gray', linestyle=':', alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fp_rate_vs_floor.png'), dpi=150)
    plt.close()

    # --- Plot 2: Background ρ and signal Δρ vs floor ---
    fig, ax1 = plt.subplots(1, 1, figsize=(11, 5))
    ax1.plot(floors, [r["mean_rho"] for r in results], 'o-', linewidth=2,
             markersize=7, label='Background ρ (clean)', color='#E85D3A')
    ax1.fill_between(floors,
                     [r["mean_rho"] - r["std_rho"] for r in results],
                     [r["mean_rho"] + r["std_rho"] for r in results],
                     alpha=0.2, color='#E85D3A')
    ax1.set_xlabel('Minimum Prime in Basket', fontsize=12)
    ax1.set_ylabel('ρ (Background Hit Rate)', fontsize=12, color='#E85D3A')
    ax1.tick_params(axis='y', labelcolor='#E85D3A')

    ax2 = ax1.twinx()
    ax2.plot(floors, [r["roundtrip_delta_rho"] for r in results], 's-',
             linewidth=2, markersize=7, label='Δρ (signal)', color='#2C5F8A')
    # JPEG survival deltas
    for q, style, color in [(95, '--', '#4CAF50'), (75, '-.', '#9C27B0'),
                             (40, ':', '#FF9800')]:
        deltas = [r["jpeg_survival"].get(q, {}).get("delta_rho", 0) for r in results]
        ax2.plot(floors, deltas, style, linewidth=1.5, label=f'Δρ after Q{q}',
                 color=color, alpha=0.8)
    ax2.set_ylabel('Δρ (Signal Strength)', fontsize=12, color='#2C5F8A')
    ax2.tick_params(axis='y', labelcolor='#2C5F8A')
    ax2.axhline(0, color='black', linewidth=0.5, alpha=0.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc='upper right')
    ax1.set_title('Background ρ vs Signal Δρ — The Tradeoff Curve', fontsize=14)
    ax1.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'rho_vs_delta_tradeoff.png'), dpi=150)
    plt.close()

    # --- Plot 3: Per-class ρ heatmap ---
    if results:
        classes = sorted(results[0]["per_class_mean_rho"].keys())
        matrix = np.array([
            [r["per_class_mean_rho"][c] for c in classes]
            for r in results
        ])
        fig, ax = plt.subplots(1, 1, figsize=(12, 6))
        im = ax.imshow(matrix.T, aspect='auto', cmap='YlOrRd', interpolation='nearest')
        ax.set_xticks(range(len(floors)))
        ax.set_xticklabels([str(f) for f in floors], fontsize=10)
        ax.set_yticks(range(len(classes)))
        ax.set_yticklabels(classes, fontsize=10)
        ax.set_xlabel('Minimum Prime in Basket', fontsize=12)
        ax.set_title('Background ρ by Image Class and Prime Floor', fontsize=14)
        plt.colorbar(im, ax=ax, label='ρ')
        # Annotate cells
        for i in range(len(floors)):
            for j in range(len(classes)):
                ax.text(i, j, f'{matrix[i, j]:.3f}', ha='center', va='center',
                        fontsize=8, color='black' if matrix[i, j] < 0.15 else 'white')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'class_rho_heatmap.png'), dpi=150)
        plt.close()

    # --- Plot 4: Basket size and density ---
    fig, ax1 = plt.subplots(1, 1, figsize=(11, 5))
    sizes = [r["basket_size"] for r in results]
    densities = [r["density"] for r in results]
    ax1.bar(range(len(floors)), sizes, alpha=0.6, color='#2C5F8A', label='Basket size')
    ax1.set_xticks(range(len(floors)))
    ax1.set_xticklabels([str(f) for f in floors])
    ax1.set_xlabel('Minimum Prime in Basket', fontsize=12)
    ax1.set_ylabel('Basket Size (# primes)', fontsize=12, color='#2C5F8A')

    ax2 = ax1.twinx()
    ax2.plot(range(len(floors)), densities, 'o-', color='#E85D3A', linewidth=2,
             markersize=7, label='Prime density')
    ax2.set_ylabel('Density (primes / 256)', fontsize=12, color='#E85D3A')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=11)
    ax1.set_title('Basket Size and Density vs Prime Floor', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'basket_composition.png'), dpi=150)
    plt.close()

    print(f"Sweep plots saved to {output_dir}/")


if __name__ == "__main__":
    output_dir = "pgps_results/sweep"
    corpus_dir = "pgps_results/synthetic_corpus"
    os.makedirs(output_dir, exist_ok=True)

    results = run_sweep(corpus_dir, output_dir)
    generate_sweep_plots(results, os.path.join(output_dir, "plots"))
