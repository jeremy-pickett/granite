#!/usr/bin/env python3
"""
Compound Markers — Making the Canary Harder to Fake
=====================================================
Jeremy Pickett — Axiomatic Fictions Series

Three compound marker strategies that reduce false positive rate by
multiplying independent conditions:

  1. RARE BASKET — Primes selected for maximum distance from quantization
     grids AND from each other (sparse in measurement domain)
  2. TWIN MARKERS — Two prime-gap distances at adjacent pixel positions.
     Must BOTH be prime. P(FP) drops from ~0.06 to ~0.0036.
  3. MAGIC SENTINEL — Prime-gap distance must be adjacent to a pixel with
     a known sentinel value (42). Like ELF magic bytes.
  4. COMPOUND — All three combined. The full handshake.

The hypothesis: compound markers survive JPEG better than single markers
because JPEG's correlated quantization error within 8×8 blocks moves
adjacent pixels together. The relationship survives even when individual
values don't.
"""

import os
import sys
import json
import time
import numpy as np
from PIL import Image
from scipy import stats as sp_stats
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    _gen_synthetic_photo,
)
from smart_embedder import (
    PROFILES, build_smart_basket, compute_local_entropy_fast,
    JPEG_LUMA_QUANT, jpeg_quant_at_quality, get_jpeg_grid_multiples,
)


BIT_DEPTH = 8
WINDOW_W = 8
MAGIC_VALUE = 42  # The answer to life, the universe, and everything
MAGIC_TOLERANCE = 2  # Allow ±2 for JPEG survival

# Fuzzy prime tolerance for post-JPEG detection
PRIME_TOLERANCE = 2


# =============================================================================
# RARE BASKET — Primes maximally distant from quant grids and each other
# =============================================================================

def build_rare_basket(min_prime: int = 53, max_prime: int = 251,
                      quality: int = 75, min_gap: int = 4) -> np.ndarray:
    """
    Build a basket of primes that are:
    1. Above the floor
    2. Not multiples of any JPEG quant table entry
    3. At least min_gap apart from each other (spread in measurement space)
    4. At least min_gap from any quant grid multiple
    """
    grid = get_jpeg_grid_multiples(quality)
    all_primes = sieve_of_eratosthenes(max_prime)
    candidates = all_primes[all_primes >= min_prime]

    # Filter: must be at least min_gap from any grid multiple
    filtered = []
    for p in candidates:
        min_dist_to_grid = min(abs(p - g) for g in grid) if grid else 999
        if min_dist_to_grid >= min_gap:
            filtered.append(int(p))

    # Greedy selection: spread primes apart
    if not filtered:
        return np.array(candidates)  # Fallback

    basket = [filtered[0]]
    for p in filtered[1:]:
        if all(abs(p - b) >= min_gap for b in basket):
            basket.append(p)

    return np.array(sorted(basket))


# =============================================================================
# MARKER TYPE DEFINITIONS
# =============================================================================

@dataclass
class MarkerConfig:
    """Configuration for a compound marker type."""
    name: str
    description: str
    min_prime: int = 53
    use_twins: bool = False
    use_magic: bool = False
    magic_value: int = 42
    magic_tolerance: int = 2
    use_rare_basket: bool = False
    rare_min_gap: int = 4
    detection_prime_tolerance: int = 2  # Fuzzy N for detection
    n_markers: int = 400


MARKER_TYPES = {
    "single_basic": MarkerConfig(
        name="single_basic",
        description="Single prime-gap marker, floor=37 (baseline)",
        min_prime=37,
    ),
    "single_rare": MarkerConfig(
        name="single_rare",
        description="Single marker with rare basket (grid-avoidant, spaced)",
        min_prime=53,
        use_rare_basket=True,
        rare_min_gap=4,
    ),
    "twin": MarkerConfig(
        name="twin",
        description="Twin markers — two adjacent positions both prime-gap",
        min_prime=53,
        use_twins=True,
        use_rare_basket=True,
    ),
    "magic": MarkerConfig(
        name="magic",
        description="Magic sentinel — prime-gap adjacent to channel=42",
        min_prime=53,
        use_magic=True,
        use_rare_basket=True,
    ),
    "compound": MarkerConfig(
        name="compound",
        description="Full compound: twin + magic + rare basket",
        min_prime=53,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
    ),
}


# =============================================================================
# COMPOUND EMBEDDER
# =============================================================================

def embed_compound(pixels: np.ndarray, config: MarkerConfig,
                    variable_offset: int = 42) -> tuple[np.ndarray, list]:
    """
    Embed compound markers according to config.
    Returns (modified_pixels, marker_metadata_list).

    variable_offset controls which positions are selected from the eligible
    pool and which prime is assigned to each position.  The same image
    embedded with different variable_offsets produces different marker
    positions and prime assignments, even with identical config.

    For Layer BC (manifest-based) detection, the variable_offset used at
    embed time must be known — store it in the sidecar receipt alongside
    the image hash, floor, and density.  Layer D (blind spatial) detection
    requires no knowledge of the variable_offset.

    The default value of 42 is used for research and testing.  Production
    embeddings should use a unique value per image and record it in the
    receipt.
    """
    h, w, c = pixels.shape
    modified = pixels.copy().astype(np.int16)
    rng = np.random.RandomState(variable_offset)

    # Build basket
    if config.use_rare_basket:
        basket = build_rare_basket(min_prime=config.min_prime, min_gap=config.rare_min_gap)
    else:
        all_p = sieve_of_eratosthenes(251)
        basket = all_p[all_p >= config.min_prime]

    # Cap to embeddable range
    basket = basket[basket <= 200]

    if len(basket) == 0:
        raise ValueError(f"Empty basket for config {config.name}")

    # Get eligible positions (away from edges for twins, in mid-range values)
    all_positions = sample_positions_grid(h, w, WINDOW_W)

    # Entropy scoring for position selection
    entropy_map = compute_local_entropy_fast(pixels)

    # Filter positions
    eligible = []
    for pos in all_positions:
        r, col = int(pos[0]), int(pos[1])

        # Offset into block center if JPEG-aware
        if config.use_twins or config.use_magic or config.use_rare_basket:
            r = min(r + 3, h - 1)
            col = min(col + 3, w - 2 if config.use_twins else w - 1)

        # Value range check
        if not (20 <= pixels[r, col, 0] <= 235 and 20 <= pixels[r, col, 1] <= 235):
            continue
        # For twins: need adjacent position in bounds with good values
        if config.use_twins:
            if col + 1 >= w:
                continue
            if not (20 <= pixels[r, col+1, 0] <= 235 and 20 <= pixels[r, col+1, 1] <= 235):
                continue

        eligible.append((r, col, entropy_map[min(r, h-1), min(col, w-1)]))

    if not eligible:
        raise ValueError("No eligible positions")

    # Sort by entropy (higher = better hiding spot), take top candidates
    eligible.sort(key=lambda x: -x[2])
    n_use = min(config.n_markers, len(eligible))
    # Weighted random from top half by entropy
    top_n = max(n_use, len(eligible) // 2)
    top_eligible = eligible[:top_n]
    indices = rng.choice(len(top_eligible), size=n_use, replace=False)
    selected = [top_eligible[i] for i in indices]

    markers = []
    for r, col, ent in selected:
        target_prime = int(rng.choice(basket))

        # --- Primary marker: make |R-G| at (r, col) = target_prime ---
        val_r = int(modified[r, col, 0])
        opt1 = val_r - target_prime
        opt2 = val_r + target_prime
        candidates = []
        for new_g in [opt1, opt2]:
            if 20 <= new_g <= 235:
                candidates.append(new_g)
        if not candidates:
            continue

        new_g = min(candidates, key=lambda x: abs(x - int(modified[r, col, 1])))
        modified[r, col, 1] = new_g

        marker_info = {
            "row": int(r), "col": int(col),
            "prime": target_prime,
            "type": "primary",
        }

        # --- Twin marker: make |R-G| at (r, col+1) also a prime ---
        if config.use_twins and col + 1 < w:
            twin_prime = int(rng.choice(basket))
            val_r2 = int(modified[r, col+1, 0])
            opt1 = val_r2 - twin_prime
            opt2 = val_r2 + twin_prime
            t_candidates = []
            for new_g2 in [opt1, opt2]:
                if 20 <= new_g2 <= 235:
                    t_candidates.append(new_g2)
            if t_candidates:
                new_g2 = min(t_candidates, key=lambda x: abs(x - int(modified[r, col+1, 1])))
                modified[r, col+1, 1] = new_g2
                marker_info["twin_prime"] = twin_prime
                marker_info["twin_col"] = int(col + 1)
            else:
                if config.use_twins:
                    continue  # Can't complete twin, skip

        # --- Magic sentinel: set B channel at (r, col) to MAGIC_VALUE ---
        if config.use_magic:
            modified[r, col, 2] = config.magic_value
            marker_info["magic_channel"] = 2
            marker_info["magic_value"] = config.magic_value

        markers.append(marker_info)

    modified = np.clip(modified, 0, 255).astype(np.uint8)
    return modified, markers


# =============================================================================
# COMPOUND DETECTOR
# =============================================================================

def detect_compound(pixels: np.ndarray, markers: list, config: MarkerConfig,
                     ) -> dict:
    """
    Layer 2 compound detection. At each known marker position, check
    whether ALL conditions of the compound marker are satisfied.

    Returns detection statistics comparing marker positions vs control.
    """
    h, w, c = pixels.shape
    prime_lookup = build_prime_lookup(BIT_DEPTH, min_prime=config.min_prime)
    tol = config.detection_prime_tolerance

    # Build fuzzy prime lookup
    max_val = 255
    fuzzy_prime = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for offset in range(-tol, tol + 1):
            check = d + offset
            if 0 <= check <= max_val and prime_lookup[check]:
                fuzzy_prime[d] = True
                break

    marker_set = set()
    marker_pass = 0
    marker_total = 0
    marker_primary_pass = 0
    marker_twin_pass = 0
    marker_magic_pass = 0

    for m in markers:
        r, col = m["row"], m["col"]
        if r >= h or col >= w:
            continue
        marker_set.add((r, col))
        marker_total += 1

        # Check primary: |R-G| is fuzzy-prime
        d_primary = abs(int(pixels[r, col, 0]) - int(pixels[r, col, 1]))
        primary_ok = bool(fuzzy_prime[min(d_primary, max_val)])
        if primary_ok:
            marker_primary_pass += 1

        # Check twin
        twin_ok = True
        if config.use_twins:
            twin_ok = False
            tc = m.get("twin_col", col + 1)
            if tc < w:
                d_twin = abs(int(pixels[r, tc, 0]) - int(pixels[r, tc, 1]))
                twin_ok = bool(fuzzy_prime[min(d_twin, max_val)])
                if twin_ok:
                    marker_twin_pass += 1
                marker_set.add((r, tc))

        # Check magic
        magic_ok = True
        if config.use_magic:
            magic_ok = False
            magic_ch = m.get("magic_channel", 2)
            actual_val = int(pixels[r, col, magic_ch])
            if abs(actual_val - config.magic_value) <= config.magic_tolerance:
                magic_ok = True
                marker_magic_pass += 1

        # Full compound pass
        if primary_ok and twin_ok and magic_ok:
            marker_pass += 1

    # Control group: check same conditions at non-marker positions
    all_positions = sample_positions_grid(h, w, WINDOW_W)
    control_pass = 0
    control_total = 0
    control_primary_pass = 0
    control_twin_pass = 0
    control_magic_pass = 0

    for pos in all_positions:
        r, col = int(pos[0]), int(pos[1])
        if (r, col) in marker_set:
            continue
        if r >= h or col >= w:
            continue
        control_total += 1

        d_primary = abs(int(pixels[r, col, 0]) - int(pixels[r, col, 1]))
        primary_ok = bool(fuzzy_prime[min(d_primary, max_val)])
        if primary_ok:
            control_primary_pass += 1

        twin_ok = True
        if config.use_twins:
            twin_ok = False
            if col + 1 < w:
                d_twin = abs(int(pixels[r, col+1, 0]) - int(pixels[r, col+1, 1]))
                twin_ok = bool(fuzzy_prime[min(d_twin, max_val)])
                if twin_ok:
                    control_twin_pass += 1

        magic_ok = True
        if config.use_magic:
            magic_ok = False
            actual_val = int(pixels[r, col, 2])
            if abs(actual_val - config.magic_value) <= config.magic_tolerance:
                magic_ok = True
                control_magic_pass += 1

        if primary_ok and twin_ok and magic_ok:
            control_pass += 1

    # Statistics
    marker_rate = marker_pass / marker_total if marker_total > 0 else 0
    control_rate = control_pass / control_total if control_total > 0 else 0
    rate_ratio = marker_rate / control_rate if control_rate > 0 else float('inf')

    # Binomial test
    binom_p = 1.0
    if control_rate > 0 and control_rate < 1 and marker_total > 0:
        binom_p = float(sp_stats.binomtest(
            marker_pass, marker_total, control_rate,
            alternative='greater').pvalue)

    # Chi-squared contingency
    a, b = marker_pass, marker_total - marker_pass
    cc, d = control_pass, control_total - control_pass
    chi2_p = 1.0
    chi2_stat = 0.0
    if min(a + cc, b + d) > 0 and marker_total > 0 and control_total > 0:
        table = np.array([[a, b], [cc, d]])
        if a > 0 or cc > 0:  # At least some passes exist
            try:
                chi2_stat, chi2_p, _, _ = sp_stats.chi2_contingency(table, correction=True)
            except:
                pass

    return {
        "marker_total": marker_total,
        "marker_compound_pass": marker_pass,
        "marker_rate": marker_rate,
        "marker_primary_pass": marker_primary_pass,
        "marker_twin_pass": marker_twin_pass,
        "marker_magic_pass": marker_magic_pass,
        "control_total": control_total,
        "control_compound_pass": control_pass,
        "control_rate": control_rate,
        "control_primary_pass": control_primary_pass,
        "control_twin_pass": control_twin_pass,
        "control_magic_pass": control_magic_pass,
        "rate_ratio": rate_ratio,
        "chi2_pvalue": chi2_p,
        "binomial_pvalue": binom_p,
        "detected_chi2": chi2_p < 0.01 and marker_rate > control_rate,
        "detected_binom": binom_p < 0.01,
    }


# =============================================================================
# FULL TEST
# =============================================================================

def run_compound_test(output_dir: str):
    """Test all compound marker types across JPEG quality levels."""
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    pixels = _gen_synthetic_photo(512, 512, rng)

    jpeg_qualities = [None, 95, 85, 75, 60, 40]
    quality_labels = ["lossless", "Q95", "Q85", "Q75", "Q60", "Q40"]

    print("=" * 90)
    print("COMPOUND MARKER COMPARISON")
    print("=" * 90)

    all_results = {}

    for mtype_name, config in MARKER_TYPES.items():
        print(f"\n{'='*80}")
        print(f"Marker type: {config.name}")
        print(f"  {config.description}")
        print(f"  twins={config.use_twins}  magic={config.use_magic}"
              f"  rare_basket={config.use_rare_basket}")
        print(f"{'='*80}")

        # Build and show basket
        if config.use_rare_basket:
            basket = build_rare_basket(min_prime=config.min_prime,
                                        min_gap=config.rare_min_gap)
        else:
            all_p = sieve_of_eratosthenes(251)
            basket = all_p[all_p >= config.min_prime]
        basket = basket[basket <= 200]
        print(f"  Basket ({len(basket)} primes): "
              f"[{', '.join(str(p) for p in basket[:10])}{'...' if len(basket) > 10 else ''}]")

        # Embed
        try:
            embedded, markers = embed_compound(pixels, config, variable_offset=42)
        except ValueError as e:
            print(f"  EMBED FAILED: {e}")
            continue

        print(f"  Embedded: {len(markers)} markers")

        # Detect across quality levels
        type_results = {}
        print(f"\n  {'Quality':>8s}  {'M pass':>7s}  {'M rate':>7s}  "
              f"{'C pass':>7s}  {'C rate':>7s}  {'Ratio':>7s}  "
              f"{'χ² p':>10s}  {'Binom p':>10s}  {'Status':>10s}")
        print(f"  {'-'*85}")

        for q, label in zip(jpeg_qualities, quality_labels):
            if q is None:
                test_pixels = embedded
            else:
                tmp = os.path.join(output_dir, f"_tmp_{mtype_name}_q{q}.jpg")
                Image.fromarray(embedded).save(tmp, "JPEG", quality=q)
                test_pixels = np.array(Image.open(tmp).convert("RGB"))
                os.remove(tmp)

            det = detect_compound(test_pixels, markers, config)
            type_results[label] = det

            status = "DETECTED" if (det["detected_chi2"] or det["detected_binom"]) else "—"
            print(f"  {label:>8s}  {det['marker_compound_pass']:>5d}/{det['marker_total']:<3d}"
                  f"  {det['marker_rate']:>7.4f}"
                  f"  {det['control_compound_pass']:>5d}/{det['control_total']:<5d}"
                  f"  {det['control_rate']:>7.4f}"
                  f"  {det['rate_ratio']:>7.1f}"
                  f"  {det['chi2_pvalue']:>10.2e}"
                  f"  {det['binomial_pvalue']:>10.2e}"
                  f"  {status:>10s}")

        # Component survival breakdown for lossless
        lossless = type_results.get("lossless", {})
        if lossless and lossless["marker_total"] > 0:
            mt = lossless["marker_total"]
            print(f"\n  Component survival (lossless):")
            print(f"    Primary (prime gap):  {lossless['marker_primary_pass']:>4d}/{mt}"
                  f"  ({lossless['marker_primary_pass']/mt*100:.1f}%)")
            if config.use_twins:
                print(f"    Twin (adjacent prime): {lossless['marker_twin_pass']:>4d}/{mt}"
                      f"  ({lossless['marker_twin_pass']/mt*100:.1f}%)")
            if config.use_magic:
                print(f"    Magic (sentinel=42):  {lossless['marker_magic_pass']:>4d}/{mt}"
                      f"  ({lossless['marker_magic_pass']/mt*100:.1f}%)")
            print(f"    Full compound:        {lossless['marker_compound_pass']:>4d}/{mt}"
                  f"  ({lossless['marker_compound_pass']/mt*100:.1f}%)")

        # Component survival for Q75
        q75 = type_results.get("Q75", {})
        if q75 and q75["marker_total"] > 0:
            mt = q75["marker_total"]
            print(f"\n  Component survival (Q75 JPEG):")
            print(f"    Primary (prime gap):  {q75['marker_primary_pass']:>4d}/{mt}"
                  f"  ({q75['marker_primary_pass']/mt*100:.1f}%)")
            if config.use_twins:
                print(f"    Twin (adjacent prime): {q75['marker_twin_pass']:>4d}/{mt}"
                      f"  ({q75['marker_twin_pass']/mt*100:.1f}%)")
            if config.use_magic:
                print(f"    Magic (sentinel=42):  {q75['marker_magic_pass']:>4d}/{mt}"
                      f"  ({q75['marker_magic_pass']/mt*100:.1f}%)")
            print(f"    Full compound:        {q75['marker_compound_pass']:>4d}/{mt}"
                  f"  ({q75['marker_compound_pass']/mt*100:.1f}%)")

            # Control background rates for Q75
            ct = q75["control_total"]
            print(f"\n  Control background (Q75) — what nature produces:")
            print(f"    Primary: {q75['control_primary_pass']:>5d}/{ct}"
                  f"  ({q75['control_primary_pass']/ct*100:.4f}%)")
            if config.use_twins:
                print(f"    Twin:    {q75['control_twin_pass']:>5d}/{ct}"
                      f"  ({q75['control_twin_pass']/ct*100:.4f}%)")
            if config.use_magic:
                print(f"    Magic:   {q75['control_magic_pass']:>5d}/{ct}"
                      f"  ({q75['control_magic_pass']/ct*100:.4f}%)")
            print(f"    Compound:{q75['control_compound_pass']:>5d}/{ct}"
                  f"  ({q75['control_compound_pass']/ct*100:.4f}%)")

        all_results[mtype_name] = type_results

    # --- SUMMARY TABLE ---
    print(f"\n\n{'='*90}")
    print("SUMMARY — Detection (✓ = detected at α=0.01 by binomial test)")
    print(f"{'='*90}")
    print(f"\n{'Type':>20s}  {'Markers':>7s}  ", end="")
    for label in quality_labels:
        print(f"{'  ' + label:>10s}", end="")
    print()
    print("-" * 90)

    for mtype_name, type_results in all_results.items():
        n_markers = type_results.get("lossless", {}).get("marker_total", 0)
        line = f"{mtype_name:>20s}  {n_markers:>7d}  "
        for label in quality_labels:
            r = type_results.get(label, {})
            if r:
                det = "✓" if r.get("detected_binom", False) else "·"
                ratio = r.get("rate_ratio", 0)
                line += f"  {ratio:>5.1f}x {det}  "
            else:
                line += f"  {'—':>8s}  "
        print(line)

    print(f"\n  Ratio = marker_rate / control_rate (higher = better discrimination)")
    print(f"  ✓ = binomial p < 0.01  · = not significant")

    # --- BACKGROUND RATE COMPARISON ---
    print(f"\n\n{'='*90}")
    print("NATURAL BACKGROUND RATES — What the detector sees in clean images")
    print(f"{'='*90}")
    print(f"\n{'Type':>20s}  ", end="")
    for label in quality_labels:
        print(f"{'  ' + label:>10s}", end="")
    print()
    print("-" * 90)

    for mtype_name, type_results in all_results.items():
        line = f"{mtype_name:>20s}  "
        for label in quality_labels:
            r = type_results.get(label, {})
            cr = r.get("control_rate", 0)
            line += f"  {cr:>9.6f}"
        print(line)

    print(f"\n  Lower background rate = more discriminative marker type")
    print(f"  Compound markers should show dramatically lower background")

    # Save
    serializable = {}
    for mtype, results in all_results.items():
        serializable[mtype] = {}
        for q_label, data in results.items():
            serializable[mtype][q_label] = {
                k: v for k, v in data.items()
                if not isinstance(v, (np.integer, np.floating))
            }
    with open(os.path.join(output_dir, "compound_results.json"), "w") as f:
        json.dump(serializable, f, indent=2, default=str)

    return all_results


def plot_compound(results: dict, output_dir: str):
    """Visualize compound marker comparison."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)
    quality_labels = ["lossless", "Q95", "Q85", "Q75", "Q60", "Q40"]

    # Rate ratio comparison
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    for mtype_name, type_results in results.items():
        ratios = []
        for label in quality_labels:
            r = type_results.get(label, {})
            ratios.append(r.get("rate_ratio", 1.0))
        # Cap inf for display
        ratios = [min(r, 50) for r in ratios]
        axes[0].plot(range(len(quality_labels)), ratios, 'o-', linewidth=2,
                     markersize=7, label=mtype_name)

    axes[0].set_xticks(range(len(quality_labels)))
    axes[0].set_xticklabels(quality_labels, fontsize=10)
    axes[0].set_ylabel('Rate Ratio (marker / control)', fontsize=12)
    axes[0].set_title('Signal Discrimination by Marker Type', fontsize=14)
    axes[0].legend(fontsize=9)
    axes[0].set_yscale('log')
    axes[0].axhline(1.0, color='black', linewidth=0.5, linestyle='--', alpha=0.3)
    axes[0].grid(True, alpha=0.3)

    # Background rate comparison
    for mtype_name, type_results in results.items():
        bg_rates = []
        for label in quality_labels:
            r = type_results.get(label, {})
            bg_rates.append(r.get("control_rate", 0))
        axes[1].plot(range(len(quality_labels)), bg_rates, 'o-', linewidth=2,
                     markersize=7, label=mtype_name)

    axes[1].set_xticks(range(len(quality_labels)))
    axes[1].set_xticklabels(quality_labels, fontsize=10)
    axes[1].set_ylabel('Background Rate (control positions)', fontsize=12)
    axes[1].set_title('Natural Background — Lower = Better', fontsize=14)
    axes[1].legend(fontsize=9)
    axes[1].set_yscale('log')
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'compound_comparison.png'), dpi=150)
    plt.close()

    # Binomial p-value comparison
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    for mtype_name, type_results in results.items():
        pvals = []
        for label in quality_labels:
            r = type_results.get(label, {})
            pvals.append(-np.log10(max(r.get("binomial_pvalue", 1.0), 1e-300)))
        ax.plot(range(len(quality_labels)), pvals, 'o-', linewidth=2,
                markersize=7, label=mtype_name)

    ax.set_xticks(range(len(quality_labels)))
    ax.set_xticklabels(quality_labels, fontsize=10)
    ax.set_ylabel('-log₁₀(binomial p-value)', fontsize=12)
    ax.set_title('Detection Significance — Higher = More Confident', fontsize=14)
    ax.axhline(2, color='red', linewidth=1, linestyle='--', label='α=0.01')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'compound_significance.png'), dpi=150)
    plt.close()

    print(f"Compound plots saved to {output_dir}/")


if __name__ == "__main__":
    output_dir = "pgps_results/compound"
    results = run_compound_test(output_dir)
    plot_compound(results, os.path.join(output_dir, "plots"))
