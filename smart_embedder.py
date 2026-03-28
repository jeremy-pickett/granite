#!/usr/bin/env python3
"""
Profile-Aware Prime-Gap Embedder
==================================
Jeremy Pickett — Axiomatic Fictions Series

The injector does the homework so the detector doesn't have to.

Architecture:
  - File type profiles define: quantization grids to avoid, distance zones
    to avoid, position selection strategy, basket filtering
  - The embedder at creation time has perfect knowledge of the file
  - The detector downstream stays dumb and general

Profiles:
  - JPEG: avoid standard quantization table multiples, embed in
    mid-entropy regions, prefer inter-block positions
  - PNG: lossless baseline, embed freely, avoid d=0 zone
  - WEBP: similar to JPEG with VP8 quantization tables
  - AUDIO_PCM: amplitude domain, avoid silence/clipping zones
  - GENERIC: conservative defaults

This is not a product. It's proof that a smarter injector fixes the
false positive problem without making the detector content-aware.
"""

import os
import sys
import json
import time
import numpy as np
from PIL import Image
from dataclasses import dataclass, field, asdict
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup, build_prime_set,
    sample_positions_grid, sample_positions_random,
    extract_distances, DEFAULT_CHANNEL_PAIRS,
    load_and_decode, analyze_distances,
    _gen_synthetic_photo,
)
from fp_forensics import full_distance_forensics
from prime_floor_sweep import analyze_distances_at_floor


# =============================================================================
# JPEG QUANTIZATION TABLES (standard)
# =============================================================================

# ITU-T T.81 Annex K — standard luminance quantization table
JPEG_LUMA_QUANT = np.array([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68,109,103, 77,
    24, 35, 55, 64, 81,104,113, 92,
    49, 64, 78, 87,103,121,120,101,
    72, 92, 95, 98,112,100,103, 99,
], dtype=int)

# ITU-T T.81 — standard chrominance quantization table
JPEG_CHROMA_QUANT = np.array([
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
], dtype=int)


def jpeg_quant_at_quality(base_table: np.ndarray, quality: int) -> np.ndarray:
    """Scale quantization table by JPEG quality factor (libjpeg formula)."""
    if quality < 50:
        scale = 5000 // quality
    else:
        scale = 200 - 2 * quality
    table = (base_table * scale + 50) // 100
    table = np.clip(table, 1, 255)
    return table


def get_jpeg_grid_multiples(quality: int = 75, max_val: int = 255) -> set:
    """
    Get the set of all distance values that are multiples of any entry
    in the JPEG quantization tables at the given quality level.
    These are the values JPEG snaps to — our embedder must AVOID them.
    """
    luma = jpeg_quant_at_quality(JPEG_LUMA_QUANT, quality)
    chroma = jpeg_quant_at_quality(JPEG_CHROMA_QUANT, quality)

    # Unique quantization step sizes
    all_steps = set(luma.tolist()) | set(chroma.tolist())

    # All multiples of those steps in [0, max_val]
    grid_multiples = set()
    for step in all_steps:
        if step > 1:  # skip step=1, everything is a multiple of 1
            for m in range(0, max_val + 1, step):
                grid_multiples.add(m)

    return grid_multiples


# =============================================================================
# FILE TYPE PROFILES
# =============================================================================

@dataclass
class EmbedProfile:
    """
    File type profile for the smart embedder.
    Defines what to avoid and where to embed.
    """
    name: str
    description: str

    # Basket filtering
    min_prime: int = 43                  # Validated operating point (floor sweep, March 2026)
    max_prime: int = 251                 # Stay in 8-bit
    avoid_distances: set = field(default_factory=set)  # Distance values to avoid

    # Position selection
    prefer_high_entropy: bool = True     # Prefer high local entropy positions
    avoid_edges: bool = False            # Avoid strong edge positions
    min_channel_value: int = 16          # Avoid near-black (clipping zone)
    max_channel_value: int = 240         # Avoid near-white (clipping zone)
    block_alignment: int = 1             # 8 for JPEG (avoid block boundaries)

    # Embedding parameters
    target_channel_pair: tuple = (0, 1)  # R-G by default
    window_w: int = 8                    # Sampling window
    n_markers: int = 0                   # 0 = caller must set per-image:
                                         # ceil(grid_capacity(h, w) * 0.08)
                                         # Validated density: 8% of eligible
                                         # grid positions (~465 markers per
                                         # 1024px image, 40.98dB PSNR, 90%
                                         # blind detection after Q40)

    # Survival hints
    expected_quality_range: tuple = (60, 95)  # Expected JPEG quality range
    expected_value_shift: int = 5        # Expected max per-channel shift


def build_jpeg_profile(quality: int = 75) -> EmbedProfile:
    """
    JPEG-aware profile. Avoids quantization grid multiples,
    low-distance natural concentration zone, and block boundaries.
    """
    grid = get_jpeg_grid_multiples(quality)

    # Also avoid low distances (d < 43) — natural concentration zone
    # confirmed by forensics: JPEG collapses distances toward zero
    low_zone = set(range(0, 43))

    profile = EmbedProfile(
        name=f"jpeg_q{quality}",
        description=f"JPEG-aware profile optimized for quality ~{quality}",
        min_prime=43,
        avoid_distances=grid | low_zone,
        prefer_high_entropy=True,
        avoid_edges=True,
        min_channel_value=20,
        max_channel_value=235,
        block_alignment=8,  # Avoid straddling 8x8 DCT block boundaries
        expected_quality_range=(max(40, quality - 20), min(100, quality + 10)),
        expected_value_shift=max(3, (100 - quality) // 10),
    )
    return profile


def build_png_profile() -> EmbedProfile:
    """
    PNG lossless profile. Generous — no lossy pipeline to worry about.
    Still avoid d=0 zone (natural concentration) and clipping.
    """
    return EmbedProfile(
        name="png_lossless",
        description="PNG lossless — maximum embedding freedom",
        min_prime=43,
        avoid_distances=set(range(0, 20)),
        prefer_high_entropy=False,  # Doesn't matter for lossless
        avoid_edges=False,
        min_channel_value=5,
        max_channel_value=250,
        block_alignment=1,
        expected_value_shift=0,
    )


def build_generic_profile() -> EmbedProfile:
    """
    Conservative generic profile for unknown downstream pipeline.
    Assumes worst case: aggressive JPEG somewhere in the chain.
    """
    grid = get_jpeg_grid_multiples(60)  # Assume aggressive compression
    low_zone = set(range(0, 43))

    return EmbedProfile(
        name="generic",
        description="Conservative defaults — assumes hostile pipeline",
        min_prime=43,
        avoid_distances=grid | low_zone,
        prefer_high_entropy=True,
        avoid_edges=True,
        min_channel_value=25,
        max_channel_value=230,
        block_alignment=8,
        expected_value_shift=8,
    )


PROFILES = {
    "jpeg_95": build_jpeg_profile(95),
    "jpeg_85": build_jpeg_profile(85),
    "jpeg_75": build_jpeg_profile(75),
    "jpeg_60": build_jpeg_profile(60),
    "png": build_png_profile(),
    "generic": build_generic_profile(),
}


# =============================================================================
# SMART BASKET CONSTRUCTION
# =============================================================================

def build_smart_basket(profile: EmbedProfile) -> np.ndarray:
    """
    Build a basket of primes that avoids quantization grids and
    natural distance concentration zones.
    """
    all_primes = sieve_of_eratosthenes(profile.max_prime)
    basket = all_primes[all_primes >= profile.min_prime]

    # Filter out primes that collide with avoid set
    clean_basket = np.array([p for p in basket if p not in profile.avoid_distances])

    return clean_basket


def score_basket_prime(prime: int, profile: EmbedProfile) -> float:
    """
    Score a prime for embedding quality. Higher = better.
    Factors: distance from quantization grid, distance from natural
    concentration zones, survival likelihood.
    """
    score = 1.0

    # Penalize proximity to quantization grid
    for d in profile.avoid_distances:
        dist = abs(prime - d)
        if dist == 0:
            return 0.0  # Hard exclude
        elif dist <= profile.expected_value_shift:
            score *= 0.5 ** (1.0 / dist)  # Soft penalty

    # Prefer primes in the mid-range (better survival)
    # Sweet spot: 40-180 (not too small, not too close to 255 clipping)
    if 50 <= prime <= 180:
        score *= 1.2
    elif prime > 200:
        score *= 0.7  # Requires large channel gap, harder to achieve

    return score


# =============================================================================
# SMART POSITION SELECTION
# =============================================================================

def compute_local_entropy(pixels: np.ndarray, block_size: int = 8) -> np.ndarray:
    """
    Compute local entropy map. High entropy = textured regions = better
    hiding spots. Low entropy = smooth regions = modifications more visible
    and more vulnerable to quantization.
    """
    h, w, c = pixels.shape
    entropy_map = np.zeros((h, w), dtype=float)

    # Use luminance for entropy estimation
    luma = 0.299 * pixels[:,:,0].astype(float) + \
           0.587 * pixels[:,:,1].astype(float) + \
           0.114 * pixels[:,:,2].astype(float)

    half = block_size // 2
    for r in range(half, h - half):
        for col in range(half, w - half):
            block = luma[r-half:r+half, col-half:col+half]
            std = np.std(block)
            entropy_map[r, col] = std

    return entropy_map


def compute_local_entropy_fast(pixels: np.ndarray, block_size: int = 8) -> np.ndarray:
    """Fast local entropy via uniform filter (approximation)."""
    from scipy.ndimage import uniform_filter

    luma = (0.299 * pixels[:,:,0].astype(float) +
            0.587 * pixels[:,:,1].astype(float) +
            0.114 * pixels[:,:,2].astype(float))

    # Local mean and local mean of squares
    local_mean = uniform_filter(luma, size=block_size, mode='reflect')
    local_sq_mean = uniform_filter(luma**2, size=block_size, mode='reflect')
    # Local variance = E[X²] - E[X]²
    local_var = np.maximum(local_sq_mean - local_mean**2, 0)
    return np.sqrt(local_var)


def select_smart_positions(pixels: np.ndarray, profile: EmbedProfile,
                            n_positions: int, seed: int = 42) -> np.ndarray:
    """
    Select embedding positions based on profile criteria.
    Returns (N, 2) array of (row, col).
    """
    h, w, c = pixels.shape
    rng = np.random.RandomState(seed)

    # Start with grid positions
    all_positions = sample_positions_grid(h, w, profile.window_w)

    # Filter by channel value range (avoid clipping zones)
    valid_mask = np.ones(len(all_positions), dtype=bool)
    for i, (r, col) in enumerate(all_positions):
        ch_a = pixels[r, col, profile.target_channel_pair[0]]
        ch_b = pixels[r, col, profile.target_channel_pair[1]]
        if (ch_a < profile.min_channel_value or ch_a > profile.max_channel_value or
            ch_b < profile.min_channel_value or ch_b > profile.max_channel_value):
            valid_mask[i] = False

    # Filter by block alignment (for JPEG: avoid positions near block boundaries)
    if profile.block_alignment > 1:
        for i, (r, col) in enumerate(all_positions):
            r_in_block = r % profile.block_alignment
            c_in_block = col % profile.block_alignment
            # Prefer positions near center of 8x8 blocks
            if r_in_block < 2 or r_in_block > 5 or c_in_block < 2 or c_in_block > 5:
                valid_mask[i] = False

    valid_positions = all_positions[valid_mask]

    if len(valid_positions) == 0:
        # Fallback: just use all positions
        valid_positions = all_positions

    # Score by local entropy if requested
    if profile.prefer_high_entropy and len(valid_positions) > n_positions:
        entropy_map = compute_local_entropy_fast(pixels, block_size=8)
        scores = np.array([entropy_map[r, col] for r, col in valid_positions])

        # Weighted random selection favoring high entropy
        if scores.sum() > 0:
            probs = scores / scores.sum()
            # Blend with uniform to avoid total exclusion of lower-entropy regions
            probs = 0.7 * probs + 0.3 * (np.ones_like(probs) / len(probs))
            probs = probs / probs.sum()
            indices = rng.choice(len(valid_positions), size=min(n_positions, len(valid_positions)),
                                 replace=False, p=probs)
        else:
            indices = rng.choice(len(valid_positions), size=min(n_positions, len(valid_positions)),
                                 replace=False)
        return valid_positions[indices]
    elif len(valid_positions) > n_positions:
        indices = rng.choice(len(valid_positions), size=n_positions, replace=False)
        return valid_positions[indices]
    else:
        return valid_positions


# =============================================================================
# SMART EMBEDDER
# =============================================================================

@dataclass
class EmbedResult:
    """Complete embedding metadata."""
    profile_name: str
    n_markers_requested: int
    n_markers_embedded: int
    n_positions_available: int
    n_positions_after_filter: int
    basket_size: int
    basket_primes: list
    primes_used: dict  # prime -> count
    mean_channel_adjustment: float
    max_channel_adjustment: int
    positions: list  # list of {row, col, prime, adjustment}
    embed_time_ms: float


def smart_embed(pixels: np.ndarray, profile: EmbedProfile,
                seed: int = 42) -> tuple[np.ndarray, EmbedResult]:
    """
    Profile-aware embedding. The embedder does the homework.

    Returns (modified_pixels, metadata).
    """
    t0 = time.perf_counter()
    h, w, c = pixels.shape

    if profile.n_markers == 0:
        import math
        from pgps_detector import sample_positions_grid as _spg
        cap = len(_spg(h, w, profile.window_w))
        profile.n_markers = max(10, math.ceil(cap * 0.08))

    modified = pixels.copy().astype(np.int16)
    rng = np.random.RandomState(seed)

    # Build smart basket
    basket = build_smart_basket(profile)
    if len(basket) == 0:
        raise ValueError(f"Empty basket for profile {profile.name} — "
                         f"all primes filtered by avoid set")

    # Score primes
    scored = [(p, score_basket_prime(p, profile)) for p in basket]
    scored = [(p, s) for p, s in scored if s > 0]
    if not scored:
        raise ValueError("All primes scored zero")

    primes_available = np.array([p for p, s in scored])
    prime_weights = np.array([s for p, s in scored])
    prime_weights = prime_weights / prime_weights.sum()

    # Select positions
    positions = select_smart_positions(pixels, profile, profile.n_markers, seed)
    n_available = len(positions)

    # Embed
    ch_a_idx, ch_b_idx = profile.target_channel_pair
    markers = []
    primes_used = {}
    adjustments = []

    for pos in positions:
        r, col = pos
        val_a = int(modified[r, col, ch_a_idx])
        val_b = int(modified[r, col, ch_b_idx])

        # Select a prime weighted by score
        target_prime = int(rng.choice(primes_available, p=prime_weights))

        # Compute adjustment: make |val_a - val_b_new| = target_prime
        # Choose direction that minimizes adjustment magnitude
        option1 = val_a - target_prime  # new_b = val_a - prime
        option2 = val_a + target_prime  # new_b = val_a + prime

        candidates = []
        for new_b in [option1, option2]:
            if profile.min_channel_value <= new_b <= profile.max_channel_value:
                candidates.append((new_b, abs(new_b - val_b)))

        if not candidates:
            # Can't embed here without clipping — skip
            continue

        # Pick smallest adjustment
        best_b, adjustment = min(candidates, key=lambda x: x[1])
        modified[r, col, ch_b_idx] = best_b
        adjustments.append(adjustment)

        primes_used[target_prime] = primes_used.get(target_prime, 0) + 1
        markers.append({
            "row": int(r), "col": int(col),
            "prime": target_prime,
            "adjustment": adjustment,
            "original_b": val_b,
            "new_b": best_b,
        })

    modified = np.clip(modified, 0, 255).astype(np.uint8)

    result = EmbedResult(
        profile_name=profile.name,
        n_markers_requested=profile.n_markers,
        n_markers_embedded=len(markers),
        n_positions_available=len(sample_positions_grid(h, w, profile.window_w)),
        n_positions_after_filter=n_available,
        basket_size=len(primes_available),
        basket_primes=primes_available.tolist(),
        primes_used=primes_used,
        mean_channel_adjustment=float(np.mean(adjustments)) if adjustments else 0,
        max_channel_adjustment=int(max(adjustments)) if adjustments else 0,
        positions=markers,
        embed_time_ms=(time.perf_counter() - t0) * 1000,
    )
    return modified, result


# =============================================================================
# ROUNDTRIP VALIDATION
# =============================================================================

def run_profile_comparison(output_dir: str):
    """
    Compare dumb embedder vs smart profile-aware embedder across
    JPEG quality levels. The main question: does the smart embedder
    produce better signal survival?
    """
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    pixels = _gen_synthetic_photo(512, 512, rng)

    print("=" * 80)
    print("PROFILE-AWARE EMBEDDER vs DUMB EMBEDDER — ROUNDTRIP COMPARISON")
    print("=" * 80)

    h, w, _ = pixels.shape
    positions_grid = sample_positions_grid(h, w, 8)
    prime_lookup_37 = build_prime_lookup(8, min_prime=37)

    # Baseline clean analysis
    clean_dists = extract_distances(pixels, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
    clean_stats = analyze_distances_at_floor(clean_dists, 37)
    print(f"\nClean image baseline: ρ = {clean_stats['rho']:.4f}")

    # --- DUMB EMBEDDER (from pgps_detector) ---
    print(f"\n{'='*60}")
    print("DUMB EMBEDDER (floor=37, no profile awareness)")
    print(f"{'='*60}")

    from pgps_detector import embed_prime_gap_markers
    dumb_modified, dumb_meta = embed_prime_gap_markers(
        pixels, n_markers=500, window_w=8, seed=99, min_prime=37
    )

    dumb_dists = extract_distances(dumb_modified, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
    dumb_stats = analyze_distances_at_floor(dumb_dists, 37)
    print(f"Embedded: ρ = {dumb_stats['rho']:.4f}  (Δ = {dumb_stats['rho'] - clean_stats['rho']:+.4f})")

    dumb_jpeg = {}
    for q in [95, 85, 75, 60, 40]:
        tmp = os.path.join(output_dir, f"_tmp_dumb_q{q}.jpg")
        Image.fromarray(dumb_modified).save(tmp, "JPEG", quality=q)
        jp = np.array(Image.open(tmp).convert("RGB"))
        os.remove(tmp)
        jd = extract_distances(jp, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
        js = analyze_distances_at_floor(jd, 37)
        delta = js['rho'] - clean_stats['rho']
        dumb_jpeg[q] = {"rho": js['rho'], "delta": delta}
        detected = "SIGNAL" if delta > 0.005 else "noise"
        print(f"  Q{q:3d}: ρ={js['rho']:.4f}  Δ={delta:+.4f}  [{detected}]")

    # --- SMART EMBEDDER — each profile ---
    smart_results = {}

    for profile_name in ["jpeg_95", "jpeg_75", "jpeg_60", "generic", "png"]:
        profile = PROFILES[profile_name]
        print(f"\n{'='*60}")
        print(f"SMART EMBEDDER — profile: {profile_name}")
        print(f"  {profile.description}")
        print(f"{'='*60}")

        try:
            smart_modified, smart_meta = smart_embed(pixels, profile, seed=42)
        except ValueError as e:
            print(f"  FAILED: {e}")
            continue

        basket_str = ", ".join(str(p) for p in smart_meta.basket_primes[:10])
        if len(smart_meta.basket_primes) > 10:
            basket_str += f"... ({len(smart_meta.basket_primes)} total)"
        print(f"  Basket: [{basket_str}]")
        print(f"  Markers: {smart_meta.n_markers_embedded} / {smart_meta.n_markers_requested}"
              f" ({smart_meta.n_positions_after_filter} positions available)")
        print(f"  Mean adjustment: {smart_meta.mean_channel_adjustment:.1f}"
              f"  Max: {smart_meta.max_channel_adjustment}")
        print(f"  Embed time: {smart_meta.embed_time_ms:.0f}ms")

        # Top primes used
        top_primes = sorted(smart_meta.primes_used.items(), key=lambda x: -x[1])[:5]
        print(f"  Top primes used: " +
              ", ".join(f"{p}(×{c})" for p, c in top_primes))

        # Measure embedded
        sm_dists = extract_distances(smart_modified, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
        sm_stats = analyze_distances_at_floor(sm_dists, 37)
        delta_emb = sm_stats['rho'] - clean_stats['rho']
        print(f"  Embedded ρ: {sm_stats['rho']:.4f}  (Δ = {delta_emb:+.4f})")

        # JPEG roundtrip
        profile_jpeg = {}
        for q in [95, 85, 75, 60, 40]:
            tmp = os.path.join(output_dir, f"_tmp_smart_{profile_name}_q{q}.jpg")
            Image.fromarray(smart_modified).save(tmp, "JPEG", quality=q)
            jp = np.array(Image.open(tmp).convert("RGB"))
            os.remove(tmp)
            jd = extract_distances(jp, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
            js = analyze_distances_at_floor(jd, 37)
            delta = js['rho'] - clean_stats['rho']

            # Also check what the clean image looks like after this JPEG quality
            tmp2 = os.path.join(output_dir, f"_tmp_clean_q{q}.jpg")
            Image.fromarray(pixels).save(tmp2, "JPEG", quality=q)
            clean_jp = np.array(Image.open(tmp2).convert("RGB"))
            os.remove(tmp2)
            clean_jd = extract_distances(clean_jp, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
            clean_js = analyze_distances_at_floor(clean_jd, 37)
            # True signal: embedded-after-JPEG minus clean-after-JPEG
            true_delta = js['rho'] - clean_js['rho']

            profile_jpeg[q] = {
                "rho": js['rho'],
                "delta_vs_clean_orig": delta,
                "clean_after_jpeg_rho": clean_js['rho'],
                "delta_vs_clean_after_jpeg": true_delta,
            }
            detected = "SIGNAL" if true_delta > 0.003 else "noise"
            print(f"  Q{q:3d}: ρ={js['rho']:.4f}"
                  f"  clean_jpeg_ρ={clean_js['rho']:.4f}"
                  f"  TRUE Δ={true_delta:+.4f}  [{detected}]")

        smart_results[profile_name] = {
            "meta": asdict(smart_meta),
            "embedded_rho": sm_stats['rho'],
            "embedded_delta": delta_emb,
            "jpeg_survival": profile_jpeg,
        }

    # --- COMPARISON TABLE ---
    print(f"\n\n{'='*80}")
    print("COMPARISON: TRUE SIGNAL (embedded_jpeg ρ - clean_jpeg ρ)")
    print(f"{'='*80}")
    print(f"\n{'Method':>20s}  {'Emb Δ':>7s}  {'Q95':>7s}  {'Q85':>7s}  "
          f"{'Q75':>7s}  {'Q60':>7s}  {'Q40':>7s}")
    print("-" * 80)

    # Dumb embedder comparison against clean JPEG baselines
    dumb_true = {}
    for q in [95, 85, 75, 60, 40]:
        tmp = os.path.join(output_dir, f"_tmp_clean_q{q}.jpg")
        Image.fromarray(pixels).save(tmp, "JPEG", quality=q)
        clean_jp = np.array(Image.open(tmp).convert("RGB"))
        os.remove(tmp)
        clean_jd = extract_distances(clean_jp, positions_grid, DEFAULT_CHANNEL_PAIRS)["ALL"]
        clean_js = analyze_distances_at_floor(clean_jd, 37)
        dumb_true[q] = dumb_jpeg[q]["rho"] - clean_js['rho']

    dumb_delta = dumb_stats['rho'] - clean_stats['rho']
    dumb_line = f"{'dumb (floor=37)':>20s}  {dumb_delta:>+7.4f}"
    for q in [95, 85, 75, 60, 40]:
        dumb_line += f"  {dumb_true[q]:>+7.4f}"
    print(dumb_line)

    for pname, sdata in smart_results.items():
        line = f"{pname:>20s}  {sdata['embedded_delta']:>+7.4f}"
        for q in [95, 85, 75, 60, 40]:
            d = sdata['jpeg_survival'].get(q, {}).get('delta_vs_clean_after_jpeg', 0)
            line += f"  {d:>+7.4f}"
        print(line)

    print(f"\n  TRUE Δ > 0 means the signal is distinguishable from JPEG artifacts.")
    print(f"  TRUE Δ = embedded_after_JPEG ρ - clean_after_JPEG ρ")
    print(f"  This controls for JPEG's own distance redistribution.")

    # Save results
    with open(os.path.join(output_dir, "profile_comparison.json"), "w") as f:
        # Can't serialize sets, so convert
        serializable = {
            "clean_rho": clean_stats['rho'],
            "dumb_embedded_rho": dumb_stats['rho'],
            "dumb_jpeg": {str(k): v for k, v in dumb_jpeg.items()},
            "dumb_true_delta": {str(k): v for k, v in dumb_true.items()},
            "smart_results": {
                name: {
                    "embedded_rho": data["embedded_rho"],
                    "embedded_delta": data["embedded_delta"],
                    "jpeg_survival": {str(k): v for k, v in data["jpeg_survival"].items()},
                }
                for name, data in smart_results.items()
            },
        }
        json.dump(serializable, f, indent=2)

    return smart_results


# =============================================================================
# VISUALIZATION
# =============================================================================

def plot_comparison(smart_results: dict, output_dir: str):
    """Plot dumb vs smart embedder survival curves."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    qualities = [95, 85, 75, 60, 40]
    x = range(len(qualities))

    for pname, data in smart_results.items():
        deltas = [data["jpeg_survival"].get(q, {}).get("delta_vs_clean_after_jpeg", 0)
                  for q in qualities]
        ax.plot(x, deltas, 'o-', linewidth=2, markersize=7, label=f'smart: {pname}')

    ax.axhline(0, color='black', linewidth=1, alpha=0.3, linestyle='--')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Q{q}' for q in qualities], fontsize=11)
    ax.set_xlabel('JPEG Quality', fontsize=12)
    ax.set_ylabel('TRUE Δρ (embedded−clean, both after JPEG)', fontsize=12)
    ax.set_title('Signal Survival: Smart Embedder Profiles', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'smart_vs_dumb_survival.png'), dpi=150)
    plt.close()

    print(f"Comparison plot saved to {output_dir}/")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    output_dir = "pgps_results/smart_embed"
    os.makedirs(output_dir, exist_ok=True)

    # Show basket composition per profile
    print("BASKET COMPOSITION BY PROFILE")
    print("=" * 60)
    for pname, profile in PROFILES.items():
        basket = build_smart_basket(profile)
        grid_multiples = get_jpeg_grid_multiples(75)
        collisions = sum(1 for p in basket if p in grid_multiples)
        print(f"  {pname:>12s}: {len(basket):>2d} primes,"
              f" {collisions} collide with Q75 grid,"
              f" [{', '.join(str(p) for p in basket[:8])}{'...' if len(basket) > 8 else ''}]")
    print()

    # Run comparison
    smart_results = run_profile_comparison(output_dir)

    # Plot
    plot_comparison(smart_results, os.path.join(output_dir, "plots"))
