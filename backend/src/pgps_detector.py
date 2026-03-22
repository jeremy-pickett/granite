#!/usr/bin/env python3
"""
Prime-Gap Provenance Signal Detector & Null Hypothesis Characterizer
====================================================================
Jeremy Pickett — Axiomatic Fictions Series

Measures prime-gap structure in decoded pixel space across binary media.
Establishes empirical null hypothesis for natural (unmodified) images.
Reports ρ, statistical tests, and false positive characterization.

Usage:
    # Characterize null hypothesis against a directory of natural images:
    python pgps_detector.py --mode baseline --input /path/to/natural/images --output results/

    # Detect provenance signal in a single file:
    python pgps_detector.py --mode detect --input /path/to/file.png --output results/

    # Generate synthetic test corpus and run full characterization:
    python pgps_detector.py --mode synthetic --output results/

    # Embed test markers and validate detection roundtrip:
    python pgps_detector.py --mode roundtrip --input /path/to/file.png --output results/
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from scipy import stats as sp_stats


# =============================================================================
# PRIME UTILITIES
# =============================================================================

def sieve_of_eratosthenes(limit: int) -> np.ndarray:
    """Return all primes up to `limit` inclusive."""
    is_prime = np.ones(limit + 1, dtype=bool)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if is_prime[i]:
            is_prime[i*i::i] = False
    return np.where(is_prime)[0]


def build_prime_set(bit_depth: int = 8) -> set:
    """Build the set of primes in the measurement domain [0, 2^bit_depth - 1]."""
    max_val = (1 << bit_depth) - 1
    primes = sieve_of_eratosthenes(max_val)
    return set(primes.tolist())


def build_prime_lookup(bit_depth: int = 8, min_prime: int = 0) -> np.ndarray:
    """Boolean array: index d -> True if d is prime and >= min_prime."""
    max_val = (1 << bit_depth) - 1
    lookup = np.zeros(max_val + 1, dtype=bool)
    for p in sieve_of_eratosthenes(max_val):
        if p >= min_prime:
            lookup[p] = True
    return lookup


def nearest_prime_distance(value: int, prime_set: set, max_val: int = 255) -> int:
    """Return the distance from `value` to the nearest prime."""
    if value in prime_set:
        return 0
    for d in range(1, max_val + 1):
        if (value - d) in prime_set or (value + d) in prime_set:
            return d
    return max_val


# =============================================================================
# SAMPLING STRATEGIES
# =============================================================================

def sample_positions_grid(height: int, width: int, window_w: int) -> np.ndarray:
    """Grid-based sampling at interval W. Returns array of (row, col) positions."""
    rows = np.arange(0, height, window_w)
    cols = np.arange(0, width, window_w)
    grid = np.array(np.meshgrid(rows, cols, indexing='ij')).reshape(2, -1).T
    return grid


def sample_positions_random(height: int, width: int, n_samples: int,
                            seed: int = 42) -> np.ndarray:
    """Random sampling of n positions. Deterministic given seed."""
    rng = np.random.RandomState(seed)
    rows = rng.randint(0, height, size=n_samples)
    cols = rng.randint(0, width, size=n_samples)
    return np.column_stack([rows, cols])


# =============================================================================
# DISTANCE EXTRACTION
# =============================================================================

@dataclass
class ChannelPairConfig:
    """Defines which channel pairs to measure distances between."""
    name: str
    ch_high: int  # channel index for high-order value
    ch_low: int   # channel index for low-order value


# The three natural channel pairs in RGB decoded space
DEFAULT_CHANNEL_PAIRS = [
    ChannelPairConfig("R-G", 0, 1),
    ChannelPairConfig("R-B", 0, 2),
    ChannelPairConfig("G-B", 1, 2),
]


def extract_distances(pixels: np.ndarray, positions: np.ndarray,
                      channel_pairs: list[ChannelPairConfig]) -> dict[str, np.ndarray]:
    """
    Extract absolute distances between channel pairs at sampled positions.

    Args:
        pixels: decoded image as (H, W, C) uint8 array
        positions: (N, 2) array of (row, col) sample positions
        channel_pairs: list of ChannelPairConfig defining measurement pairs

    Returns:
        dict mapping pair name to array of absolute distances
    """
    results = {}
    rows, cols = positions[:, 0], positions[:, 1]

    for pair in channel_pairs:
        high_vals = pixels[rows, cols, pair.ch_high].astype(np.int16)
        low_vals = pixels[rows, cols, pair.ch_low].astype(np.int16)
        distances = np.abs(high_vals - low_vals)
        results[pair.name] = distances.astype(np.uint16)

    # Also compute combined (all pairs concatenated)
    results["ALL"] = np.concatenate(list(results.values()))
    return results


def extract_adjacent_distances(pixels: np.ndarray, positions: np.ndarray,
                                channel: int = 0) -> np.ndarray:
    """
    Extract distances between same-channel values at adjacent pixel positions.
    This measures spatial prime-gap structure within a single channel.

    For each sampled position (r, c), measure |pixel[r,c,ch] - pixel[r,c+1,ch]|.
    """
    h, w, _ = pixels.shape
    # Filter positions where c+1 is still in bounds
    valid = positions[:, 1] < (w - 1)
    pos = positions[valid]
    rows, cols = pos[:, 0], pos[:, 1]

    val_a = pixels[rows, cols, channel].astype(np.int16)
    val_b = pixels[rows, cols + 1, channel].astype(np.int16)
    return np.abs(val_a - val_b).astype(np.uint16)


# =============================================================================
# STATISTICAL ANALYSIS
# =============================================================================

@dataclass
class PrimeGapStats:
    """Statistical characterization of prime-gap structure at sampled positions."""
    n_samples: int = 0
    n_prime_hits: int = 0
    prime_hit_rate: float = 0.0
    expected_hit_rate_uniform: float = 0.0  # what uniform random would produce
    rho: float = 0.0                         # detection metric
    chi2_statistic: float = 0.0
    chi2_pvalue: float = 1.0
    ks_statistic: float = 0.0
    ks_pvalue: float = 1.0
    distance_histogram: list = field(default_factory=list)
    prime_distance_histogram: list = field(default_factory=list)
    mean_distance: float = 0.0
    std_distance: float = 0.0
    median_distance: float = 0.0


def analyze_distances(distances: np.ndarray, prime_lookup: np.ndarray,
                      bit_depth: int = 8) -> PrimeGapStats:
    """
    Full statistical analysis of distance distribution against prime-gap prior.

    The null hypothesis: distances at sampled positions in natural images
    show no excess clustering at prime values relative to the empirical
    distance distribution's expected prime overlap.
    """
    max_val = (1 << bit_depth) - 1
    stats = PrimeGapStats()
    stats.n_samples = len(distances)

    if stats.n_samples == 0:
        return stats

    # Basic descriptives
    stats.mean_distance = float(np.mean(distances))
    stats.std_distance = float(np.std(distances))
    stats.median_distance = float(np.median(distances))

    # Full distance histogram (0 through max_val)
    hist, _ = np.histogram(distances, bins=np.arange(0, max_val + 2) - 0.5)
    stats.distance_histogram = hist.tolist()

    # Prime hit analysis
    # Clamp distances to lookup range
    clamped = np.minimum(distances, max_val)
    prime_hits = prime_lookup[clamped]
    stats.n_prime_hits = int(np.sum(prime_hits))
    stats.prime_hit_rate = stats.n_prime_hits / stats.n_samples

    # Expected prime hit rate under uniform distance distribution
    n_primes_in_range = int(np.sum(prime_lookup))
    stats.expected_hit_rate_uniform = n_primes_in_range / (max_val + 1)

    # Prime-only histogram
    prime_hist = hist.copy()
    non_prime_mask = ~prime_lookup[:len(prime_hist)]
    prime_hist[non_prime_mask] = 0
    stats.prime_distance_histogram = prime_hist.tolist()

    # ρ metric: observed prime density normalized by file metric
    # For null hypothesis characterization, ρ = prime_hit_rate
    # (In production, ρ = M_detected / F with F as file size normalization)
    stats.rho = stats.prime_hit_rate

    # --- Chi-squared test ---
    # Bin distances into prime vs non-prime
    # Observed: [prime_hits, non_prime_hits]
    # Expected under the empirical marginal distribution:
    #   For each observed distance d, probability it's prime = prime_lookup[d]
    #   Expected prime count = sum over all samples of P(d is prime | d's bin)
    #
    # More rigorous: given the OBSERVED distance distribution, how many prime
    # hits would we expect if "prime-ness" were independent of the process
    # generating these distances?
    #
    # Expected prime hits = sum_d [ count(d) * prime_lookup[d] ]
    # But that's circular — it just counts primes.
    #
    # The right test: does the distance distribution show EXCESS prime structure
    # relative to a smooth version of itself?
    #
    # Approach: bin the distance histogram into prime bins and composite bins.
    # Compare observed counts in prime bins vs expected from a smoothed
    # (moving-average) version of the histogram.

    # Smoothed histogram (moving average, window=5)
    kernel_size = 5
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(hist.astype(float), kernel, mode='same')
    # Avoid division by zero
    smoothed = np.maximum(smoothed, 1e-10)

    # Expected counts under smoothed model
    total_observed = hist.sum()
    total_smoothed = smoothed.sum()
    expected = smoothed * (total_observed / total_smoothed)

    # Chi-squared on prime bins only: do prime-valued distances show excess?
    prime_indices = np.where(prime_lookup[:len(hist)])[0]
    if len(prime_indices) > 1:
        obs_prime_bins = hist[prime_indices].astype(float)
        exp_prime_bins = expected[prime_indices]
        # Filter out bins where expected is too small
        valid = exp_prime_bins > 5
        if np.sum(valid) > 2:
            obs_v = obs_prime_bins[valid]
            exp_v = exp_prime_bins[valid]
            # Normalize expected to match observed total (required by chisquare)
            exp_v = exp_v * (obs_v.sum() / exp_v.sum())
            chi2, p = sp_stats.chisquare(obs_v, exp_v)
            stats.chi2_statistic = float(chi2)
            stats.chi2_pvalue = float(p)

    # --- KS test ---
    # Compare the empirical CDF of distances at prime values vs non-prime values
    # If embedding occurred, prime-valued distances should be over-represented
    prime_distances = distances[prime_hits]
    nonprime_distances = distances[~prime_hits]
    if len(prime_distances) > 10 and len(nonprime_distances) > 10:
        ks_stat, ks_p = sp_stats.ks_2samp(prime_distances, nonprime_distances)
        stats.ks_statistic = float(ks_stat)
        stats.ks_pvalue = float(ks_p)

    return stats


# =============================================================================
# FUZZY TOLERANCE ANALYSIS
# =============================================================================

def analyze_with_tolerance(distances: np.ndarray, prime_lookup: np.ndarray,
                           tolerance_n: int, bit_depth: int = 8) -> dict:
    """
    Analyze prime-gap hit rates under fuzzy tolerance N.
    A distance d is a "fuzzy prime hit" if any value in [d-N, d+N] is prime.

    Returns dict with hit rate and degeneracy analysis.
    """
    max_val = (1 << bit_depth) - 1

    # Build fuzzy lookup: for each distance d, is there a prime within ±N?
    fuzzy_lookup = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for offset in range(-tolerance_n, tolerance_n + 1):
            check = d + offset
            if 0 <= check <= max_val and prime_lookup[check]:
                fuzzy_lookup[d] = True
                break

    # Degeneracy: what fraction of ALL possible distances are fuzzy-prime?
    degeneracy = float(np.sum(fuzzy_lookup)) / (max_val + 1)

    # Apply to observed distances
    clamped = np.minimum(distances, max_val)
    fuzzy_hits = fuzzy_lookup[clamped]
    fuzzy_hit_rate = float(np.sum(fuzzy_hits)) / len(distances) if len(distances) > 0 else 0.0

    return {
        "tolerance_N": tolerance_n,
        "degeneracy": degeneracy,
        "fuzzy_hit_rate": fuzzy_hit_rate,
        "n_fuzzy_hits": int(np.sum(fuzzy_hits)),
        "n_samples": len(distances),
        "specificity_ratio": fuzzy_hit_rate / degeneracy if degeneracy > 0 else 0.0,
    }


# =============================================================================
# IMAGE PROCESSING
# =============================================================================

def load_and_decode(filepath: str) -> Optional[np.ndarray]:
    """Load image, decode to RGB pixel space. Returns (H, W, 3) uint8 array."""
    try:
        img = Image.open(filepath).convert("RGB")
        return np.array(img, dtype=np.uint8)
    except Exception as e:
        print(f"  [SKIP] Cannot decode {filepath}: {e}", file=sys.stderr)
        return None


@dataclass
class ImageAnalysis:
    """Complete analysis results for a single image."""
    filepath: str
    width: int = 0
    height: int = 0
    n_pixels: int = 0
    n_samples: int = 0
    window_w: int = 0
    channel_pair_stats: dict = field(default_factory=dict)
    adjacent_stats: Optional[PrimeGapStats] = None
    tolerance_analysis: list = field(default_factory=list)
    processing_time_ms: float = 0.0


def analyze_image(filepath: str, window_w: int = 8,
                  bit_depth: int = 8,
                  max_tolerance: int = 5) -> Optional[ImageAnalysis]:
    """
    Full prime-gap analysis of a single image.

    Args:
        filepath: path to image file
        window_w: sampling interval (pixels)
        bit_depth: color depth (8 for standard RGB)
        max_tolerance: max fuzzy tolerance N to analyze
    """
    t0 = time.perf_counter()

    pixels = load_and_decode(filepath)
    if pixels is None:
        return None

    h, w, c = pixels.shape
    result = ImageAnalysis(filepath=filepath, height=h, width=w,
                           n_pixels=h * w, window_w=window_w)

    prime_lookup = build_prime_lookup(bit_depth)

    # Sample positions
    positions = sample_positions_grid(h, w, window_w)
    result.n_samples = len(positions)

    # Channel-pair distance analysis
    pair_distances = extract_distances(pixels, positions, DEFAULT_CHANNEL_PAIRS)
    for pair_name, dists in pair_distances.items():
        result.channel_pair_stats[pair_name] = asdict(
            analyze_distances(dists, prime_lookup, bit_depth)
        )

    # Adjacent-pixel same-channel analysis (R channel)
    adj_dists = extract_adjacent_distances(pixels, positions, channel=0)
    result.adjacent_stats = asdict(analyze_distances(adj_dists, prime_lookup, bit_depth))

    # Fuzzy tolerance sweep
    all_dists = pair_distances["ALL"]
    for n in range(0, max_tolerance + 1):
        result.tolerance_analysis.append(
            analyze_with_tolerance(all_dists, prime_lookup, n, bit_depth)
        )

    result.processing_time_ms = (time.perf_counter() - t0) * 1000
    return result


# =============================================================================
# SYNTHETIC TEST CORPUS GENERATION
# =============================================================================

def generate_synthetic_corpus(output_dir: str, n_per_class: int = 10,
                              size: tuple = (512, 512)) -> list[str]:
    """
    Generate synthetic images spanning natural image statistics classes.
    Returns list of file paths.

    Classes:
    - gradient: smooth gradients (low spatial frequency)
    - noise_uniform: uniform random noise (maximum entropy)
    - noise_gaussian: gaussian noise (natural-ish distribution)
    - texture_regular: regular patterns (brick wall analog — named failure mode)
    - photo_synthetic: synthetic "photo-like" (smooth regions + edges)
    - low_contrast: low dynamic range (clustered channel values)
    - high_contrast: high dynamic range (spread channel values)
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    rng = np.random.RandomState(2026)
    h, w = size

    classes = {
        "gradient": lambda: _gen_gradient(h, w, rng),
        "noise_uniform": lambda: rng.randint(0, 256, (h, w, 3)).astype(np.uint8),
        "noise_gaussian": lambda: np.clip(
            rng.normal(128, 40, (h, w, 3)), 0, 255).astype(np.uint8),
        "texture_regular": lambda: _gen_regular_texture(h, w, rng),
        "photo_synthetic": lambda: _gen_synthetic_photo(h, w, rng),
        "low_contrast": lambda: np.clip(
            rng.normal(128, 10, (h, w, 3)), 0, 255).astype(np.uint8),
        "high_contrast": lambda: np.clip(
            rng.normal(128, 80, (h, w, 3)), 0, 255).astype(np.uint8),
    }

    for class_name, generator in classes.items():
        for i in range(n_per_class):
            pixels = generator()
            fname = f"{class_name}_{i:03d}.png"
            fpath = os.path.join(output_dir, fname)
            Image.fromarray(pixels).save(fpath)
            paths.append(fpath)

    return paths


def _gen_gradient(h, w, rng):
    """Smooth color gradient."""
    angle = rng.uniform(0, 2 * np.pi)
    x = np.linspace(0, 1, w)
    y = np.linspace(0, 1, h)
    xx, yy = np.meshgrid(x, y)
    t = xx * np.cos(angle) + yy * np.sin(angle)
    t = (t - t.min()) / (t.max() - t.min() + 1e-10)
    r = (t * 255).astype(np.uint8)
    g = ((1 - t) * 200 + rng.uniform(0, 55)).astype(np.uint8)
    b = ((0.5 + 0.5 * np.sin(t * np.pi * 2)) * 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def _gen_regular_texture(h, w, rng):
    """Regular repeating pattern — the brick wall failure mode."""
    period = rng.randint(8, 32)
    x = np.arange(w) % period
    y = np.arange(h) % period
    xx, yy = np.meshgrid(x, y)
    base = ((xx + yy) % period * (255 // period)).astype(np.uint8)
    noise = rng.randint(-5, 6, (h, w)).astype(np.int16)
    r = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    g = np.clip(base.astype(np.int16) + noise + 30, 0, 255).astype(np.uint8)
    b = np.clip(base.astype(np.int16) + noise - 20, 0, 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _gen_synthetic_photo(h, w, rng):
    """Synthetic photo-like: smooth blobs with edges."""
    img = np.zeros((h, w, 3), dtype=np.float64)
    n_blobs = rng.randint(5, 15)
    for _ in range(n_blobs):
        cy, cx = rng.randint(0, h), rng.randint(0, w)
        sy, sx = rng.uniform(20, h // 3), rng.uniform(20, w // 3)
        color = rng.uniform(50, 220, 3)
        yy, xx = np.ogrid[:h, :w]
        mask = np.exp(-0.5 * (((yy - cy) / sy)**2 + ((xx - cx) / sx)**2))
        for c in range(3):
            img[:, :, c] += mask * color[c]
    img = np.clip(img, 0, 255)
    noise = rng.normal(0, 3, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


# =============================================================================
# EMBEDDING (for roundtrip validation)
# =============================================================================

def embed_prime_gap_markers(pixels: np.ndarray, n_markers: int = 200,
                            window_w: int = 8, seed: int = 99,
                            bit_depth: int = 8) -> tuple[np.ndarray, dict]:
    """
    Embed prime-gap markers into a copy of the image.
    Returns (modified_pixels, embedding_metadata).

    This is a reference implementation for roundtrip validation.
    The embedding modifies pixel channel values such that the distance
    between two channels at each marker position is a prime number.
    """
    h, w, c = pixels.shape
    modified = pixels.copy().astype(np.int16)
    rng = np.random.RandomState(seed)
    primes = sieve_of_eratosthenes((1 << bit_depth) - 1)

    # Select marker positions (subset of grid positions)
    all_positions = sample_positions_grid(h, w, window_w)
    if n_markers > len(all_positions):
        n_markers = len(all_positions)
    indices = rng.choice(len(all_positions), size=n_markers, replace=False)
    marker_positions = all_positions[indices]

    # Embed: make |R - G| at each marker position equal to a prime
    embedded_markers = []
    for pos in marker_positions:
        r, col = pos
        target_prime = int(rng.choice(primes[primes <= 127]))  # keep adjustments small
        current_r = int(modified[r, col, 0])
        current_g = int(modified[r, col, 1])
        current_diff = abs(current_r - current_g)

        # Adjust G channel to make |R - G| = target_prime
        if current_r >= target_prime:
            new_g = current_r - target_prime
        else:
            new_g = current_r + target_prime

        new_g = np.clip(new_g, 0, 255)
        actual_diff = abs(current_r - int(new_g))

        modified[r, col, 1] = new_g
        embedded_markers.append({
            "row": int(r), "col": int(col),
            "target_prime": target_prime,
            "actual_diff": actual_diff,
            "channel_pair": "R-G",
        })

    modified = np.clip(modified, 0, 255).astype(np.uint8)

    metadata = {
        "n_markers": n_markers,
        "n_embedded": len(embedded_markers),
        "window_w": window_w,
        "seed": seed,
        "markers": embedded_markers,
    }
    return modified, metadata


# =============================================================================
# CORPUS-LEVEL ANALYSIS
# =============================================================================

@dataclass
class CorpusStats:
    """Aggregate statistics across a corpus of images."""
    n_images: int = 0
    n_failed: int = 0
    mean_rho: float = 0.0
    std_rho: float = 0.0
    min_rho: float = 0.0
    max_rho: float = 0.0
    median_rho: float = 0.0
    p95_rho: float = 0.0
    p99_rho: float = 0.0
    mean_prime_hit_rate: float = 0.0
    std_prime_hit_rate: float = 0.0
    mean_chi2_pvalue: float = 0.0
    fp_rate_at_alpha_05: float = 0.0
    fp_rate_at_alpha_01: float = 0.0
    fp_rate_at_alpha_001: float = 0.0
    per_class_stats: dict = field(default_factory=dict)
    tolerance_degeneracy_curve: list = field(default_factory=list)
    total_processing_time_ms: float = 0.0


def analyze_corpus(image_paths: list[str], window_w: int = 8,
                   bit_depth: int = 8,
                   max_tolerance: int = 10) -> tuple[CorpusStats, list[ImageAnalysis]]:
    """
    Run full analysis across a corpus. Returns aggregate stats and per-image results.
    """
    corpus = CorpusStats()
    results = []
    rho_values = []
    hit_rates = []
    chi2_pvalues = []

    # Per-class tracking
    class_rhos = {}

    for path in image_paths:
        fname = os.path.basename(path)
        print(f"  Analyzing: {fname}", end="", flush=True)

        analysis = analyze_image(path, window_w=window_w,
                                 bit_depth=bit_depth,
                                 max_tolerance=max_tolerance)
        if analysis is None:
            corpus.n_failed += 1
            print(" [FAILED]")
            continue

        results.append(analysis)

        # Extract ALL-pairs stats
        all_stats = analysis.channel_pair_stats.get("ALL", {})
        rho = all_stats.get("rho", 0.0)
        rho_values.append(rho)
        hit_rates.append(all_stats.get("prime_hit_rate", 0.0))
        chi2_pvalues.append(all_stats.get("chi2_pvalue", 1.0))

        # Track by image class (from filename prefix)
        class_name = fname.rsplit("_", 1)[0] if "_" in fname else "unknown"
        if class_name not in class_rhos:
            class_rhos[class_name] = []
        class_rhos[class_name].append(rho)

        corpus.total_processing_time_ms += analysis.processing_time_ms
        print(f"  ρ={rho:.4f}  p={all_stats.get('chi2_pvalue', 1.0):.4f}"
              f"  [{analysis.processing_time_ms:.0f}ms]")

    corpus.n_images = len(results)

    if rho_values:
        rho_arr = np.array(rho_values)
        corpus.mean_rho = float(np.mean(rho_arr))
        corpus.std_rho = float(np.std(rho_arr))
        corpus.min_rho = float(np.min(rho_arr))
        corpus.max_rho = float(np.max(rho_arr))
        corpus.median_rho = float(np.median(rho_arr))
        corpus.p95_rho = float(np.percentile(rho_arr, 95))
        corpus.p99_rho = float(np.percentile(rho_arr, 99))

        corpus.mean_prime_hit_rate = float(np.mean(hit_rates))
        corpus.std_prime_hit_rate = float(np.std(hit_rates))
        corpus.mean_chi2_pvalue = float(np.mean(chi2_pvalues))

        pvals = np.array(chi2_pvalues)
        corpus.fp_rate_at_alpha_05 = float(np.mean(pvals < 0.05))
        corpus.fp_rate_at_alpha_01 = float(np.mean(pvals < 0.01))
        corpus.fp_rate_at_alpha_001 = float(np.mean(pvals < 0.001))

    # Per-class stats
    for cls, rhos in class_rhos.items():
        arr = np.array(rhos)
        corpus.per_class_stats[cls] = {
            "n": len(rhos),
            "mean_rho": float(np.mean(arr)),
            "std_rho": float(np.std(arr)),
            "min_rho": float(np.min(arr)),
            "max_rho": float(np.max(arr)),
        }

    # Tolerance degeneracy curve (from first image's analysis)
    if results and results[0].tolerance_analysis:
        corpus.tolerance_degeneracy_curve = results[0].tolerance_analysis

    return corpus, results


# =============================================================================
# REPORTING
# =============================================================================

def print_corpus_report(corpus: CorpusStats):
    """Print human-readable corpus analysis report."""
    print("\n" + "=" * 72)
    print("PRIME-GAP PROVENANCE SIGNAL — NULL HYPOTHESIS CHARACTERIZATION")
    print("=" * 72)

    print(f"\nCorpus: {corpus.n_images} images analyzed"
          f" ({corpus.n_failed} failed)")
    print(f"Processing time: {corpus.total_processing_time_ms:.0f}ms total"
          f" ({corpus.total_processing_time_ms / max(corpus.n_images, 1):.0f}ms/image)")

    print(f"\n--- ρ Distribution (Prime Hit Rate) ---")
    print(f"  Mean:   {corpus.mean_rho:.6f}")
    print(f"  Std:    {corpus.std_rho:.6f}")
    print(f"  Min:    {corpus.min_rho:.6f}")
    print(f"  Max:    {corpus.max_rho:.6f}")
    print(f"  Median: {corpus.median_rho:.6f}")
    print(f"  P95:    {corpus.p95_rho:.6f}")
    print(f"  P99:    {corpus.p99_rho:.6f}")

    n_primes_8bit = len(build_prime_set(8))
    expected_uniform = n_primes_8bit / 256
    print(f"\n--- Baseline Comparison ---")
    print(f"  Primes in [0,255]:         {n_primes_8bit} / 256"
          f" = {expected_uniform:.4f}")
    print(f"  Observed mean hit rate:    {corpus.mean_prime_hit_rate:.6f}")
    print(f"  Deviation from uniform:    {corpus.mean_prime_hit_rate - expected_uniform:+.6f}")

    print(f"\n--- False Positive Rates (Chi-squared on prime bins) ---")
    print(f"  FP rate at α=0.05:  {corpus.fp_rate_at_alpha_05:.4f}"
          f"  ({corpus.fp_rate_at_alpha_05 * 100:.1f}%)")
    print(f"  FP rate at α=0.01:  {corpus.fp_rate_at_alpha_01:.4f}"
          f"  ({corpus.fp_rate_at_alpha_01 * 100:.1f}%)")
    print(f"  FP rate at α=0.001: {corpus.fp_rate_at_alpha_001:.4f}"
          f"  ({corpus.fp_rate_at_alpha_001 * 100:.1f}%)")

    if corpus.per_class_stats:
        print(f"\n--- Per-Class ρ ---")
        for cls, st in sorted(corpus.per_class_stats.items()):
            print(f"  {cls:25s}  n={st['n']:3d}"
                  f"  ρ={st['mean_rho']:.6f} ± {st['std_rho']:.6f}"
                  f"  [{st['min_rho']:.6f}, {st['max_rho']:.6f}]")

    if corpus.tolerance_degeneracy_curve:
        print(f"\n--- Fuzzy Tolerance Degeneracy Curve ---")
        print(f"  {'N':>4s}  {'Degeneracy':>11s}  {'Hit Rate':>10s}  {'Specificity':>12s}")
        for t in corpus.tolerance_degeneracy_curve:
            print(f"  {t['tolerance_N']:4d}  {t['degeneracy']:11.4f}"
                  f"  {t['fuzzy_hit_rate']:10.4f}  {t['specificity_ratio']:12.4f}")

    print("\n" + "=" * 72)
    print("INTERPRETATION NOTES")
    print("=" * 72)
    print("""
  ρ represents the prime-hit rate in the channel-pair distance domain.
  Under uniform random distances, expected ρ ≈ 0.2109 (54 primes / 256).
  Natural images will deviate from this due to spatial correlation and
  non-uniform value distributions.

  The FALSE POSITIVE RATE is the key number. It answers: how often does
  a natural, unmodified image produce a chi-squared p-value below the
  detection threshold? This is the number the paper's legal instrument
  claim depends on.

  The DEGENERACY CEILING for fuzzy tolerance N: as N increases, the
  fraction of ALL distances that qualify as "near-prime" approaches 1.0.
  At that point the test has no specificity. The degeneracy column shows
  where this collapse occurs. N must be chosen below the knee of this
  curve.

  All numbers are from synthetic test images. Run against DIV2K, COCO,
  and MIRFLICKR for publication-grade null hypothesis characterization.
""")


def generate_plots(corpus: CorpusStats, results: list[ImageAnalysis],
                   output_dir: str):
    """Generate matplotlib visualizations."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    # --- Plot 1: ρ distribution across corpus ---
    fig, ax = plt.subplots(1, 1, figsize=(10, 5))
    rhos = [r.channel_pair_stats["ALL"]["rho"] for r in results
            if "ALL" in r.channel_pair_stats]
    ax.hist(rhos, bins=30, edgecolor='black', alpha=0.7, color='#2C5F8A')
    expected = len(build_prime_set(8)) / 256
    ax.axvline(expected, color='red', linestyle='--', linewidth=2,
               label=f'Uniform expected: {expected:.4f}')
    ax.axvline(np.mean(rhos), color='orange', linestyle='-', linewidth=2,
               label=f'Observed mean: {np.mean(rhos):.4f}')
    ax.set_xlabel('ρ (Prime Hit Rate)', fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title('Null Hypothesis: ρ Distribution in Natural Images', fontsize=14)
    ax.legend(fontsize=11)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'rho_distribution.png'), dpi=150)
    plt.close()

    # --- Plot 2: Distance histogram (first image, ALL pairs) ---
    if results:
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        first = results[0]
        all_stats = first.channel_pair_stats.get("ALL", {})
        dist_hist = all_stats.get("distance_histogram", [])
        prime_hist = all_stats.get("prime_distance_histogram", [])

        if dist_hist:
            x = np.arange(len(dist_hist))
            axes[0].bar(x, dist_hist, width=1.0, color='#2C5F8A', alpha=0.6,
                        label='All distances')
            if prime_hist:
                axes[0].bar(x, prime_hist, width=1.0, color='#E85D3A', alpha=0.8,
                            label='Prime distances')
            axes[0].set_xlabel('Distance', fontsize=11)
            axes[0].set_ylabel('Count', fontsize=11)
            axes[0].set_title(f'Distance Distribution — {os.path.basename(first.filepath)}',
                              fontsize=13)
            axes[0].legend(fontsize=10)
            axes[0].set_xlim(-1, 256)

            # Zoomed view: distances 0-50
            if len(dist_hist) > 50:
                axes[1].bar(x[:51], dist_hist[:51], width=1.0, color='#2C5F8A',
                            alpha=0.6, label='All distances')
                if prime_hist and len(prime_hist) > 50:
                    axes[1].bar(x[:51], prime_hist[:51], width=1.0,
                                color='#E85D3A', alpha=0.8, label='Prime distances')
                # Mark primes on x-axis
                prime_lookup = build_prime_lookup(8)
                for p in range(51):
                    if prime_lookup[p]:
                        axes[1].axvline(p, color='red', alpha=0.15, linewidth=0.8)
                axes[1].set_xlabel('Distance (zoomed 0-50)', fontsize=11)
                axes[1].set_ylabel('Count', fontsize=11)
                axes[1].set_title('Distance Distribution (Zoomed) — Prime Values Highlighted',
                                  fontsize=13)
                axes[1].legend(fontsize=10)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'distance_histogram.png'), dpi=150)
        plt.close()

    # --- Plot 3: Per-class ρ comparison ---
    if corpus.per_class_stats:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        classes = sorted(corpus.per_class_stats.keys())
        means = [corpus.per_class_stats[c]["mean_rho"] for c in classes]
        stds = [corpus.per_class_stats[c]["std_rho"] for c in classes]
        x = np.arange(len(classes))
        ax.bar(x, means, yerr=stds, capsize=4, color='#2C5F8A', alpha=0.7,
               edgecolor='black')
        ax.axhline(expected, color='red', linestyle='--', linewidth=1.5,
                   label=f'Uniform expected: {expected:.4f}')
        ax.set_xticks(x)
        ax.set_xticklabels(classes, rotation=35, ha='right', fontsize=9)
        ax.set_ylabel('ρ (Prime Hit Rate)', fontsize=12)
        ax.set_title('ρ by Image Class — Null Hypothesis Baseline', fontsize=14)
        ax.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'rho_by_class.png'), dpi=150)
        plt.close()

    # --- Plot 4: Tolerance degeneracy curve ---
    if corpus.tolerance_degeneracy_curve:
        fig, ax1 = plt.subplots(1, 1, figsize=(10, 5))
        ns = [t["tolerance_N"] for t in corpus.tolerance_degeneracy_curve]
        degens = [t["degeneracy"] for t in corpus.tolerance_degeneracy_curve]
        hits = [t["fuzzy_hit_rate"] for t in corpus.tolerance_degeneracy_curve]
        specs = [t["specificity_ratio"] for t in corpus.tolerance_degeneracy_curve]

        ax1.plot(ns, degens, 'o-', color='#E85D3A', linewidth=2, markersize=6,
                 label='Degeneracy (fraction of space)')
        ax1.plot(ns, hits, 's-', color='#2C5F8A', linewidth=2, markersize=6,
                 label='Fuzzy hit rate')
        ax1.set_xlabel('Fuzzy Tolerance N', fontsize=12)
        ax1.set_ylabel('Rate', fontsize=12)
        ax1.set_title('Fuzzy Tolerance N: Degeneracy Ceiling Analysis', fontsize=14)
        ax1.legend(loc='upper left', fontsize=11)
        ax1.set_ylim(0, 1.05)

        ax2 = ax1.twinx()
        ax2.plot(ns, specs, '^--', color='#4CAF50', linewidth=1.5, markersize=6,
                 label='Specificity ratio')
        ax2.set_ylabel('Specificity Ratio (hit/degeneracy)', fontsize=12,
                       color='#4CAF50')
        ax2.legend(loc='upper right', fontsize=11)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'tolerance_degeneracy.png'), dpi=150)
        plt.close()

    # --- Plot 5: Chi-squared p-value distribution ---
    pvals = [r.channel_pair_stats["ALL"]["chi2_pvalue"] for r in results
             if "ALL" in r.channel_pair_stats]
    if pvals:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        ax.hist(pvals, bins=20, edgecolor='black', alpha=0.7, color='#2C5F8A')
        ax.axvline(0.05, color='red', linestyle='--', linewidth=2,
                   label='α = 0.05')
        ax.axvline(0.01, color='orange', linestyle='--', linewidth=2,
                   label='α = 0.01')
        fp_05 = sum(1 for p in pvals if p < 0.05) / len(pvals)
        ax.set_xlabel('Chi-squared p-value', fontsize=12)
        ax.set_ylabel('Count', fontsize=12)
        ax.set_title(f'Chi-squared p-value Distribution — FP rate at α=0.05: {fp_05:.1%}',
                     fontsize=14)
        ax.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'chi2_pvalues.png'), dpi=150)
        plt.close()

    print(f"\nPlots saved to {output_dir}/")


# =============================================================================
# ROUNDTRIP VALIDATION
# =============================================================================

def run_roundtrip(filepath: str, output_dir: str, n_markers: int = 200,
                  window_w: int = 8):
    """
    Embed markers, detect, compare before/after.
    This validates the detector can distinguish embedded from natural.
    """
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*72}")
    print(f"ROUNDTRIP VALIDATION")
    print(f"{'='*72}")

    pixels = load_and_decode(filepath)
    if pixels is None:
        print("Failed to load image.")
        return

    print(f"\nSource: {filepath} ({pixels.shape[1]}x{pixels.shape[0]})")
    print(f"Embedding {n_markers} markers at window W={window_w}...")

    # Analyze BEFORE embedding
    print("\n--- BEFORE Embedding ---")
    before = analyze_image(filepath, window_w=window_w)
    if before:
        before_rho = before.channel_pair_stats["ALL"]["rho"]
        before_p = before.channel_pair_stats["ALL"]["chi2_pvalue"]
        print(f"  ρ = {before_rho:.6f}  chi2 p = {before_p:.6f}")

    # Embed
    modified, metadata = embed_prime_gap_markers(pixels, n_markers=n_markers,
                                                  window_w=window_w)

    # Save modified image
    mod_path = os.path.join(output_dir, "roundtrip_embedded.png")
    Image.fromarray(modified).save(mod_path)

    # Analyze AFTER embedding
    print("\n--- AFTER Embedding ---")
    after = analyze_image(mod_path, window_w=window_w)
    if after:
        after_rho = after.channel_pair_stats["ALL"]["rho"]
        after_p = after.channel_pair_stats["ALL"]["chi2_pvalue"]
        print(f"  ρ = {after_rho:.6f}  chi2 p = {after_p:.6f}")

    # Report delta
    if before and after:
        delta_rho = after_rho - before_rho
        print(f"\n--- DELTA ---")
        print(f"  Δρ = {delta_rho:+.6f}")
        print(f"  p-value shift: {before_p:.6f} → {after_p:.6f}")
        print(f"  Detection: {'DETECTED' if after_p < 0.01 else 'NOT DETECTED'}"
              f" at α=0.01")

        # JPEG survival test
        print(f"\n--- JPEG SURVIVAL TEST ---")
        for quality in [95, 85, 75, 60, 40]:
            jpeg_path = os.path.join(output_dir, f"roundtrip_q{quality}.jpg")
            Image.fromarray(modified).save(jpeg_path, "JPEG", quality=quality)
            # Re-open as PNG for analysis (decode JPEG to pixel space)
            reopened = np.array(Image.open(jpeg_path).convert("RGB"))
            reopen_path = os.path.join(output_dir, f"roundtrip_q{quality}_decoded.png")
            Image.fromarray(reopened).save(reopen_path)
            jpeg_analysis = analyze_image(reopen_path, window_w=window_w)
            if jpeg_analysis:
                j_rho = jpeg_analysis.channel_pair_stats["ALL"]["rho"]
                j_p = jpeg_analysis.channel_pair_stats["ALL"]["chi2_pvalue"]
                detected = "DETECTED" if j_p < 0.01 else "not detected"
                print(f"  Q{quality:3d}: ρ={j_rho:.6f}  p={j_p:.6f}  [{detected}]")

    # Save metadata
    meta_path = os.path.join(output_dir, "roundtrip_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"\nArtifacts saved to {output_dir}/")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Prime-Gap Provenance Signal Detector & Null Hypothesis Characterizer"
    )
    parser.add_argument("--mode", choices=["baseline", "detect", "synthetic", "roundtrip"],
                        default="synthetic",
                        help="Operating mode")
    parser.add_argument("--input", "-i", type=str, default=None,
                        help="Input file or directory")
    parser.add_argument("--output", "-o", type=str, default="pgps_results",
                        help="Output directory")
    parser.add_argument("--window", "-w", type=int, default=8,
                        help="Sampling window W (pixels)")
    parser.add_argument("--markers", "-m", type=int, default=200,
                        help="Number of markers for roundtrip mode")
    parser.add_argument("--max-tolerance", type=int, default=10,
                        help="Maximum fuzzy tolerance N to analyze")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip plot generation")

    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    if args.mode == "synthetic":
        print("Generating synthetic test corpus...")
        corpus_dir = os.path.join(args.output, "synthetic_corpus")
        paths = generate_synthetic_corpus(corpus_dir, n_per_class=10)
        print(f"Generated {len(paths)} images in {corpus_dir}/\n")
        print("Running null hypothesis characterization...")
        corpus, results = analyze_corpus(paths, window_w=args.window,
                                         max_tolerance=args.max_tolerance)
        print_corpus_report(corpus)
        if not args.no_plots:
            generate_plots(corpus, results, os.path.join(args.output, "plots"))

        # Save raw stats
        with open(os.path.join(args.output, "corpus_stats.json"), "w") as f:
            json.dump(asdict(corpus), f, indent=2, default=str)

    elif args.mode == "baseline":
        if not args.input:
            print("ERROR: --input required for baseline mode (directory of images)")
            sys.exit(1)
        paths = sorted([
            os.path.join(args.input, f) for f in os.listdir(args.input)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'))
        ])
        print(f"Found {len(paths)} images in {args.input}\n")
        corpus, results = analyze_corpus(paths, window_w=args.window,
                                         max_tolerance=args.max_tolerance)
        print_corpus_report(corpus)
        if not args.no_plots:
            generate_plots(corpus, results, os.path.join(args.output, "plots"))
        with open(os.path.join(args.output, "corpus_stats.json"), "w") as f:
            json.dump(asdict(corpus), f, indent=2, default=str)

    elif args.mode == "detect":
        if not args.input:
            print("ERROR: --input required for detect mode")
            sys.exit(1)
        result = analyze_image(args.input, window_w=args.window,
                               max_tolerance=args.max_tolerance)
        if result:
            all_stats = result.channel_pair_stats.get("ALL", {})
            print(f"\nFile: {args.input}")
            print(f"Size: {result.width}x{result.height}")
            print(f"Samples: {result.n_samples}")
            print(f"ρ = {all_stats.get('rho', 0):.6f}")
            print(f"Chi² p = {all_stats.get('chi2_pvalue', 1):.6f}")
            print(f"Prime hit rate: {all_stats.get('prime_hit_rate', 0):.6f}")
            print(f"Time: {result.processing_time_ms:.0f}ms")

            with open(os.path.join(args.output, "detection_result.json"), "w") as f:
                json.dump(asdict(result), f, indent=2, default=str)

    elif args.mode == "roundtrip":
        if not args.input:
            # Generate a test image
            print("No input specified, generating synthetic test image...")
            rng = np.random.RandomState(42)
            pixels = _gen_synthetic_photo(512, 512, rng)
            test_path = os.path.join(args.output, "roundtrip_source.png")
            Image.fromarray(pixels).save(test_path)
            args.input = test_path

        run_roundtrip(args.input, args.output,
                      n_markers=args.markers, window_w=args.window)


if __name__ == "__main__":
    main()
