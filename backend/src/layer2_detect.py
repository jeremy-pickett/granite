#!/usr/bin/env python3
"""
Layer 2 Detection — Known Position Signal Survival
====================================================
Jeremy Pickett — Axiomatic Fictions Series

Layer 1 (blind aggregate ρ) can't distinguish embedded signal from
JPEG noise at realistic marker densities. The forensics proved it.

Layer 2 asks a different question: at the KNOWN marker positions,
is the prime-gap hit rate higher than at NON-marker positions in the
same image after the same JPEG pipeline?

The image is its own control. Each marker position is an independent
witness. The test is conditional on this specific image, this specific
pipeline, this specific set of positions.

This is the detection mode the paper actually needs.
"""

import os
import sys
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    _gen_synthetic_photo,
)
from smart_embedder import (
    smart_embed, PROFILES, build_smart_basket,
)


BIT_DEPTH = 8
WINDOW_W = 8


def _pixel_luma(pixels, r, c):
    """Integer luma Y for pixel at (r, c).  BT.601 weights."""
    return int(round(0.299 * float(pixels[r, c, 0]) +
                     0.587 * float(pixels[r, c, 1]) +
                     0.114 * float(pixels[r, c, 2])))


def layer2_detect(pixels: np.ndarray, marker_positions: list,
                   min_prime: int = 37, channel_pair: tuple = (0, 1)) -> dict:
    """
    Layer 2 detection: compare prime-gap hit rate at KNOWN marker positions
    vs NON-marker positions in the same image.

    Distance metric: |Y(r,c) - Y(r,c+1)| — adjacent-pixel luma difference.
    This survives JPEG 4:2:0 because luma is not subsampled.

    The image is its own control group.
    """
    h, w, _ = pixels.shape
    prime_lookup = build_prime_lookup(BIT_DEPTH)
    # Apply prime floor: primes below min_prime don't count as signal
    prime_lookup[:min_prime] = False

    # Extract luma-pair distances at marker positions
    marker_set = set((m["row"], m["col"]) for m in marker_positions)
    marker_dists = []
    for m in marker_positions:
        r, c = m["row"], m["col"]
        if 0 <= r < h and 0 <= c < w and c + 1 < w:
            d = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
            marker_dists.append(d)

    # Extract distances at non-marker grid positions (control group)
    all_positions = sample_positions_grid(h, w, WINDOW_W)
    control_dists = []
    for pos in all_positions:
        r, c = int(pos[0]), int(pos[1])
        if (r, c) not in marker_set and c + 1 < w:
            d = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
            control_dists.append(d)

    marker_dists = np.array(marker_dists)
    control_dists = np.array(control_dists)

    if len(marker_dists) == 0 or len(control_dists) == 0:
        return {"error": "empty groups"}

    max_val = 255
    # Prime hit rates
    marker_clamped = np.minimum(marker_dists, max_val)
    control_clamped = np.minimum(control_dists, max_val)

    marker_hits = prime_lookup[marker_clamped]
    control_hits = prime_lookup[control_clamped]

    marker_hit_rate = float(np.mean(marker_hits))
    control_hit_rate = float(np.mean(control_hits))

    # Fisher's exact test: 2x2 contingency table
    # [marker_prime, marker_nonprime]
    # [control_prime, control_nonprime]
    a = int(np.sum(marker_hits))          # marker positions with prime distance
    b = int(np.sum(~marker_hits))         # marker positions without
    c = int(np.sum(control_hits))         # control positions with prime distance
    d = int(np.sum(~control_hits))        # control positions without

    # For large samples, use chi-squared on the contingency table
    contingency = np.array([[a, b], [c, d]])
    if min(a, b, c, d) > 5:
        chi2, chi2_p, dof, expected = sp_stats.chi2_contingency(contingency)
    elif (a + b) > 0 and (c + d) > 0:
        # Small cell counts — use Fisher's exact test instead of chi-squared
        odds, chi2_p = sp_stats.fisher_exact(contingency, alternative='greater')
        chi2 = 0  # Not applicable for Fisher's test
    else:
        chi2, chi2_p = 0, 1.0

    # Also compute odds ratio
    odds_ratio = (a * d) / (b * c) if (b * c) > 0 else float('inf')

    # Per-prime breakdown: which primes survive?
    primes_in_basket = sieve_of_eratosthenes(max_val)
    primes_in_basket = primes_in_basket[primes_in_basket >= min_prime]

    prime_survival = {}
    for p in primes_in_basket:
        marker_count = int(np.sum(marker_dists == p))
        control_count = int(np.sum(control_dists == p))
        marker_rate = marker_count / len(marker_dists)
        control_rate = control_count / len(control_dists)
        if marker_count > 0 or control_count > 0:
            prime_survival[int(p)] = {
                "marker_count": marker_count,
                "control_count": control_count,
                "marker_rate": marker_rate,
                "control_rate": control_rate,
                "enrichment": marker_rate / control_rate if control_rate > 0 else float('inf'),
            }

    # Sort by enrichment
    top_surviving = sorted(prime_survival.items(),
                           key=lambda x: -x[1]["enrichment"])[:15]

    # Binomial test: are marker positions enriched for primes?
    # Under null: marker positions should have same prime rate as control
    # One-sided binomial: P(≥ a primes in n_markers trials | p = control_rate)
    binom_p = 1.0
    if control_hit_rate > 0 and control_hit_rate < 1:
        binom_p = float(sp_stats.binom_test(a, len(marker_dists), control_hit_rate,
                                             alternative='greater')
                        if hasattr(sp_stats, 'binom_test')
                        else sp_stats.binomtest(a, len(marker_dists), control_hit_rate,
                                                alternative='greater').pvalue)

    return {
        "n_marker_positions": len(marker_dists),
        "n_control_positions": len(control_dists),
        "marker_prime_hits": a,
        "marker_nonprime": b,
        "control_prime_hits": c,
        "control_nonprime": d,
        "marker_hit_rate": marker_hit_rate,
        "control_hit_rate": control_hit_rate,
        "rate_ratio": marker_hit_rate / control_hit_rate if control_hit_rate > 0 else float('inf'),
        "odds_ratio": odds_ratio,
        "chi2_statistic": float(chi2),
        "chi2_pvalue": float(chi2_p),
        "binomial_pvalue": binom_p,
        "detected": chi2_p < 0.01 and marker_hit_rate > control_hit_rate,
        "top_surviving_primes": top_surviving,
    }


def run_layer2_test(output_dir: str):
    """Full Layer 2 detection test across profiles and JPEG quality levels."""
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    pixels = _gen_synthetic_photo(512, 512, rng)

    print("=" * 80)
    print("LAYER 2 DETECTION — KNOWN POSITION SIGNAL SURVIVAL")
    print("=" * 80)

    # Test profiles
    test_profiles = ["jpeg_75", "generic", "png"]
    marker_counts = [200, 500, 1000]
    jpeg_qualities = [None, 95, 85, 75, 60, 40]  # None = no JPEG (lossless)

    results = {}

    for n_markers in marker_counts:
        for profile_name in test_profiles:
            profile = PROFILES[profile_name]
            profile.n_markers = n_markers

            print(f"\n{'='*70}")
            print(f"Profile: {profile_name}  |  Markers: {n_markers}")
            print(f"{'='*70}")

            try:
                embedded, meta = smart_embed(pixels, profile, seed=42)
            except ValueError as e:
                print(f"  EMBED FAILED: {e}")
                continue

            actual_embedded = meta.n_markers_embedded
            print(f"  Actually embedded: {actual_embedded}")

            key = f"{profile_name}_m{n_markers}"
            results[key] = {}

            print(f"\n  {'Quality':>8s}  {'Marker ρ':>10s}  {'Control ρ':>10s}  "
                  f"{'Ratio':>7s}  {'χ² p':>10s}  {'Binom p':>10s}  {'Status':>10s}")
            print(f"  {'-'*72}")

            for q in jpeg_qualities:
                if q is None:
                    test_pixels = embedded
                    label = "lossless"
                else:
                    tmp = os.path.join(output_dir, f"_tmp_l2_{key}_q{q}.jpg")
                    Image.fromarray(embedded).save(tmp, "JPEG", quality=q)
                    test_pixels = np.array(Image.open(tmp).convert("RGB"))
                    os.remove(tmp)
                    label = f"Q{q}"

                detection = layer2_detect(test_pixels, meta.positions,
                                           min_prime=37)

                status = "DETECTED" if detection["detected"] else "not detected"
                results[key][label] = detection

                print(f"  {label:>8s}  {detection['marker_hit_rate']:>10.4f}"
                      f"  {detection['control_hit_rate']:>10.4f}"
                      f"  {detection['rate_ratio']:>7.2f}"
                      f"  {detection['chi2_pvalue']:>10.2e}"
                      f"  {detection['binomial_pvalue']:>10.2e}"
                      f"  {status:>10s}")

            # Show surviving primes for lossless case
            lossless = results[key].get("lossless", {})
            if lossless and "top_surviving_primes" in lossless:
                print(f"\n  Top enriched primes (lossless):")
                for prime, info in lossless["top_surviving_primes"][:8]:
                    print(f"    p={prime:>3d}  marker={info['marker_count']:>3d}"
                          f"  control={info['control_count']:>4d}"
                          f"  enrichment={info['enrichment']:>6.2f}x")

    # Summary table
    print(f"\n\n{'='*80}")
    print("SUMMARY — Detection p-values (χ² | binomial)")
    print(f"{'='*80}")
    print(f"\n{'Config':>25s}  {'Lossless':>12s}  {'Q95':>12s}  {'Q85':>12s}  "
          f"{'Q75':>12s}  {'Q60':>12s}  {'Q40':>12s}")
    print("-" * 110)

    for key, quality_results in results.items():
        line = f"{key:>25s}"
        for label in ["lossless", "Q95", "Q85", "Q75", "Q60", "Q40"]:
            r = quality_results.get(label, {})
            if r:
                p = r.get("chi2_pvalue", 1)
                det = "*" if r.get("detected", False) else " "
                line += f"  {p:>10.2e}{det}"
            else:
                line += f"  {'—':>12s}"
        print(line)

    print(f"\n  * = detected at α=0.01")
    print(f"\n  Rate ratio > 1.0 means marker positions are enriched for primes.")
    print(f"  The higher the ratio, the stronger the signal.")

    # Save
    serializable = {}
    for k, v in results.items():
        serializable[k] = {}
        for q, data in v.items():
            safe = {key: val for key, val in data.items()
                    if key != "top_surviving_primes"}
            serializable[k][q] = safe

    with open(os.path.join(output_dir, "layer2_results.json"), "w") as f:
        json.dump(serializable, f, indent=2, default=str)

    return results


def plot_layer2(results: dict, output_dir: str):
    """Visualize Layer 2 detection results."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    # Rate ratio heatmap
    configs = sorted(results.keys())
    qualities = ["lossless", "Q95", "Q85", "Q75", "Q60", "Q40"]

    matrix = np.zeros((len(configs), len(qualities)))
    pval_matrix = np.zeros((len(configs), len(qualities)))

    for i, config in enumerate(configs):
        for j, q in enumerate(qualities):
            data = results[config].get(q, {})
            matrix[i, j] = data.get("rate_ratio", 1.0)
            pval_matrix[i, j] = data.get("chi2_pvalue", 1.0)

    fig, axes = plt.subplots(1, 2, figsize=(16, max(4, len(configs) * 0.6 + 1)))

    # Rate ratio
    im1 = axes[0].imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=0.8, vmax=2.0)
    axes[0].set_xticks(range(len(qualities)))
    axes[0].set_xticklabels(qualities, fontsize=10)
    axes[0].set_yticks(range(len(configs)))
    axes[0].set_yticklabels(configs, fontsize=9)
    axes[0].set_title('Rate Ratio (marker ρ / control ρ)', fontsize=13)
    plt.colorbar(im1, ax=axes[0])
    for i in range(len(configs)):
        for j in range(len(qualities)):
            axes[0].text(j, i, f'{matrix[i,j]:.2f}', ha='center', va='center',
                        fontsize=8, fontweight='bold' if matrix[i,j] > 1.2 else 'normal')

    # P-value (log scale)
    log_p = -np.log10(np.maximum(pval_matrix, 1e-50))
    im2 = axes[1].imshow(log_p, aspect='auto', cmap='Reds', vmin=0, vmax=20)
    axes[1].set_xticks(range(len(qualities)))
    axes[1].set_xticklabels(qualities, fontsize=10)
    axes[1].set_yticks(range(len(configs)))
    axes[1].set_yticklabels(configs, fontsize=9)
    axes[1].set_title('-log₁₀(p-value) — Higher = More Significant', fontsize=13)
    plt.colorbar(im2, ax=axes[1], label='-log₁₀(p)')
    for i in range(len(configs)):
        for j in range(len(qualities)):
            detected = pval_matrix[i, j] < 0.01 and matrix[i, j] > 1.0
            marker = "✓" if detected else ""
            axes[1].text(j, i, f'{log_p[i,j]:.1f}{marker}', ha='center', va='center',
                        fontsize=8, color='white' if log_p[i,j] > 5 else 'black')

    plt.suptitle('Layer 2 Known-Position Detection — Signal Survival', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'layer2_detection.png'), dpi=150)
    plt.close()

    print(f"Layer 2 plots saved to {output_dir}/")


if __name__ == "__main__":
    output_dir = "pgps_results/layer2"
    results = run_layer2_test(output_dir)
    plot_layer2(results, os.path.join(output_dir, "plots"))
