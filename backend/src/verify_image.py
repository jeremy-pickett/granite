#!/usr/bin/env python3
"""
Granite Verification Scanner
==============================
Scans an image for evidence of Granite provenance signals across all layers:
  - Layer 1: DQT Prime Tables (if JPEG)
  - Layer 2: Compound Markers (prime-gap enrichment at grid positions)
  - Layer 2+: Twin pairs (adjacent prime-gap — strongest blind signal)
  - Layer 2+: Magic sentinels (B≈42 + prime R-G)
  - Layer 3: Halo sentinel detection (radial lensing halos)
  - Structural: Mersenne sentinel continuity (corroborating only)

The embedder places markers at block-center positions (grid + 3px offset).
All grid-based checks scan BOTH the raw grid and the block-center grid to
ensure detection regardless of the embedding offset.

Outputs a JSON verification report.
"""

import os
import sys
import json
import hashlib
import time
import argparse
from dataclasses import dataclass, field
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid,
)
from compound_markers import (
    MARKER_TYPES, MERSENNE_BASKET, CANARY_WIDTH,
    build_rare_basket, WINDOW_W as EMBED_WINDOW,
    entropy_gate_positions, ENTROPY_GATE_THRESH, ENTROPY_BLOCK_SIZE,
)
from halo import detect_halo_centers, HaloState
from layer_h_ruler import (
    blind_scan_rulers, detect_all_rulers, RULER_TARGET, RULER_TOL,
    SEGMENT_THRESHOLD, BAND_WIDTH,
)


# =========================================================================
# VERIFY CONFIG — toggle experimental detection improvements
# =========================================================================

@dataclass
class VerifyConfig:
    """Configuration for verify_image detection parameters.

    All defaults preserve current (baseline) behavior.
    """
    # Idea 2: scan chains in both forward and reverse order
    # Default True — proven safe: +6 detections, zero false positives
    bidirectional: bool = True

    # Idea 3: scan all 64 grid phase combinations (8 row x 8 col)
    # instead of just phase0 and phase3
    all_phases: bool = False

    # Dynamic chain threshold: 0 = auto (adaptive to image content),
    # any positive int = fixed override
    chain_threshold: int = 0       # 0 = adaptive, >0 = fixed MIN_CHAIN_LEN

    # Idea 1: corroboration — chain just below threshold gets promoted
    # if another independent signal fires
    corroborate_weak: bool = False  # chain of (threshold-1) + another signal → detected

    # Experimental layers — require explicit opt-in via CLI flag
    check_dct: bool = False    # Layer DCT: frequency-domain prime embedding
    check_thermo: bool = False # Layer T: thermodynamic consensus detection


# Singleton default config — preserves baseline behavior everywhere
DEFAULT_CONFIG = VerifyConfig()


BIT_DEPTH = 8
WINDOW_W = 8
# The embedder offsets grid positions by +3 to land at JPEG block centers.
# We scan both phases to catch markers regardless.
BLOCK_CENTER_OFFSET = 3


def _entropy_gate_cached(entropy_map, grid_positions, h, w):
    """Filter positions using a precomputed entropy map (avoids recomputing)."""
    passed = []
    for pos in grid_positions:
        r, col = pos
        if entropy_map[min(r, h - 1), min(col, w - 1)] >= ENTROPY_GATE_THRESH:
            passed.append((r, col))
    return passed


# =========================================================================
# VERDICT TAXONOMY — detection thresholds and classification boundaries
# =========================================================================
#
# Each layer has a detection threshold.  All values are empirically
# calibrated: the threshold must sit between the NATURAL baseline
# (clean-image rate) and the EMBEDDED baseline (post-inject rate).
#
# Layer 1 — DQT Prime Tables
#   Natural DQT prime rate: ~22% (random quantization entries)
#   Embedded DQT prime rate: 100% (all entries replaced with primes)
DQT_PRIME_RATE_THRESH       = 0.55   # > 55% of DQT entries are prime

# Layer 2 — Prime Enrichment (relative detection via chi-squared)
#   Compares prime rate at entropy-gated positions vs control positions.
#   The image is its own control group — no fixed threshold needed.
#   With ~20K positions per group, even 1% enrichment gives p < 1e-10.
PRIME_ENRICHMENT_THRESH     = 0.01   # chi-squared p-value threshold

# Layer 2+ — Twin Pairs (consecutive luma-pair primes)
#   Natural twin rate: ~0%
#   Embedded: ~10% lossless, ~0.5% after Q85
TWIN_PAIR_RATE_THRESH       = 0.003  # > 0.3% of grid positions are twin pairs

# Layer 2+ — Magic Sentinels (B≈42 AND prime luma-diff)
#   Natural rate: ~0%
#   Embedded: ~11% lossless; fragile under JPEG (B channel shifts)
MAGIC_SENTINEL_RATE_THRESH  = 0.002  # > 0.2% of grid positions are magic

# Layer G — Radial Halos
#   Natural strong-PRESENT count: 0 (synthetic), 0-5 (some DIV2K textures)
#   Embedded: 100+ PRESENT (lossless), 40+ (Q85)
HALO_AMPLITUDE_THRESH       = 0.15   # inner-outer density diff for "strong"
HALO_STRONG_COUNT_THRESH    = 20     # need ≥20 strong PRESENT centers

# Layer H — Spatial Rulers
#   Natural valid-ruler count: 0 (no bands with matching payload)
#   Embedded: 6 rulers (3 col + 3 row) on 512px
RULER_VALID_COUNT_THRESH    = 2      # need ≥2 rulers with valid decoded payload
RULER_BAND_ELEVATION_THRESH = 20     # band mean must exceed natural (~15)

# Overall verdict thresholds (number of independent signals detected)
VERDICT_CONFIRMED_THRESH    = 3      # ≥3 signals → CONFIRMED (high confidence)
VERDICT_PROBABLE_THRESH     = 2      # ≥2 signals → PROBABLE  (medium)
VERDICT_PARTIAL_THRESH      = 1      # ≥1 signal  → PARTIAL   (low)


def _pixel_luma(pixels, r, c):
    """Integer luma Y for pixel at (r, c).  BT.601 weights."""
    return int(round(0.299 * float(pixels[r, c, 0]) +
                     0.587 * float(pixels[r, c, 1]) +
                     0.114 * float(pixels[r, c, 2])))


def _make_prime_lookup(min_prime: int = 37) -> np.ndarray:
    """Build a prime lookup array with a floor."""
    pl = build_prime_lookup(BIT_DEPTH)
    for i in range(min_prime):
        pl[i] = False
    return pl


def _grid_positions_both_phases(h: int, w: int) -> list[tuple[str, list]]:
    """
    Return named phase lists for grid scanning.

    Baseline: two phases (raw grid + block-center offset).
    """
    raw = sample_positions_grid(h, w, WINDOW_W)
    phase0 = [(int(r), int(c)) for r, c in raw if int(c) + 1 < w]
    phase3 = []
    for r, c in raw:
        r3 = min(int(r) + BLOCK_CENTER_OFFSET, h - 1)
        c3 = min(int(c) + BLOCK_CENTER_OFFSET, w - 2)
        if c3 + 1 < w:
            phase3.append((r3, c3))
    return [("block_center", phase3), ("raw", phase0)]


def _grid_positions_all_phases(h: int, w: int) -> list[tuple[str, list]]:
    """
    Return all 64 grid phase combinations (8 row offsets x 8 col offsets).

    Idea 3: after crop or rotation the grid phase shifts. Scanning all
    phases recovers the alignment. The caller short-circuits once a
    chain is found, so cost is only paid on otherwise-missed images.
    """
    raw = sample_positions_grid(h, w, WINDOW_W)
    phases = []
    # block_center (phase 3,3) first — most likely to match
    for r_off in [3, 0, 1, 2, 4, 5, 6, 7]:
        for c_off in [3, 0, 1, 2, 4, 5, 6, 7]:
            name = f"phase_{r_off}_{c_off}"
            positions = []
            for r, c in raw:
                rr = min(int(r) + r_off, h - 1)
                cc = min(int(c) + c_off, w - 2)
                if cc + 1 < w:
                    positions.append((rr, cc))
            if positions:
                phases.append((name, positions))
    return phases


def _check_dqt_primes(image_path: str) -> dict:
    """Layer 1: Check JPEG DQT for prime entries (only works on JPEG files)."""
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in ('.jpg', '.jpeg'):
        return {"applicable": False, "reason": "Not a JPEG file"}

    try:
        from dqt_prime import extract_dqt_tables
        with open(image_path, 'rb') as f:
            jpeg_data = f.read()
        tables = extract_dqt_tables(jpeg_data)
        if not tables:
            return {"applicable": True, "detected": False, "reason": "No DQT tables found"}

        total_entries = 0
        prime_entries = 0
        primes = sieve_of_eratosthenes(255)
        prime_set = set(primes.tolist())

        for table in tables:
            for val in table["entries"].flatten():
                total_entries += 1
                if int(val) in prime_set:
                    prime_entries += 1

        prime_rate = prime_entries / total_entries if total_entries > 0 else 0
        detected = prime_rate > DQT_PRIME_RATE_THRESH

        return {
            "applicable": True,
            "detected": detected,
            "total_entries": total_entries,
            "prime_entries": prime_entries,
            "prime_rate": round(prime_rate, 4),
            "tables_found": len(tables),
        }
    except Exception as e:
        return {"applicable": True, "detected": False, "error": str(e)}


def _scan_chains_one_direction(diffs, basket_set, n_gated, min_chain_len):
    """Scan for longest chain in a single direction through diffs list."""
    longest_chain = 0
    longest_start = -1
    scanned = 0

    for start_idx in range(n_gated):
        d = diffs[start_idx]
        if d not in basket_set:
            continue

        cursor = start_idx
        chain_len = 0
        while cursor < n_gated:
            d = diffs[cursor]
            if d not in basket_set:
                break
            chain_len += 1
            next_cursor = cursor + d
            if next_cursor >= n_gated:
                break
            cursor = next_cursor

        if chain_len > longest_chain:
            longest_chain = chain_len
            longest_start = start_idx

        scanned += 1

        if longest_chain > min_chain_len:
            break

    return longest_chain, longest_start, scanned


def _adaptive_chain_threshold(n_gated: int, prime_rate: float) -> int:
    """
    Compute the minimum chain length needed for detection, adaptive to
    both image size (n_gated positions) and content (natural prime rate).

    Formula: ceil(log(n_gated) / log(1 / prime_rate)) + 1

    log(n_gated) / log(1/p) is the expected longest natural chain in an
    image with n_gated positions where each has probability p of being
    prime.  The +2 margin ensures we require a chain clearly ABOVE the
    natural maximum, giving P(false positive) ≈ p^2 / n_gated ≈ 0.

    Validated on 5 DIV2K clean images: zero false positives.
    On embedded images: 80% detection (fails only on extremely
    high-texture images where signal is indistinguishable from noise).

    Floor of 6: even a tiny image needs at least 6 links.
    """
    import math
    if prime_rate <= 0 or prime_rate >= 1 or n_gated < 6:
        return 6
    threshold = math.ceil(math.log(n_gated) / math.log(1.0 / prime_rate)) + 2
    return max(6, threshold)


def _check_prime_enrichment(pixels: np.ndarray, min_prime: int = 7,
                            config: VerifyConfig = None,
                            entropy_map: np.ndarray = None) -> dict:
    """
    Layer 2: Chain-following blind detection.

    The injector embeds chains where each marker's prime value = step
    count to the next marker in the entropy-gated grid.  The verifier
    reconstructs the same grid, scans for chain starts, and follows.

    Chain threshold is adaptive: computed from the image's own prime rate
    and grid size.  Threshold = ceil(log(n_gated) / log(1/prime_rate)),
    floored at 5.  This adapts to image content:
      - Smooth image (8% prime rate, 5K positions)  → threshold 4-5
      - Textured image (21% prime rate, 43K positions) → threshold 7-8
      - Medium (14%, 20K positions)                    → threshold 6

    Config flags:
      bidirectional: also scan chains in reverse order
      all_phases: scan all 64 grid phases instead of just 2
      chain_threshold: 0 = adaptive (default), >0 = fixed override
    """
    if config is None:
        config = DEFAULT_CONFIG

    h, w, _ = pixels.shape
    prime_lookup = _make_prime_lookup(min_prime)

    from pgps_detector import sieve_of_eratosthenes
    all_p = sieve_of_eratosthenes(127)
    basket_set = set(int(p) for p in all_p if p >= min_prime)  # same as injector

    # Idea 3: all 64 phases or just the original 2
    if config.all_phases:
        phase_list = _grid_positions_all_phases(h, w)
    else:
        phase_list = _grid_positions_both_phases(h, w)

    best_chain = 0
    best_result = None
    best_threshold = 6  # for reporting

    for phase_name, positions in phase_list:
        if len(positions) == 0:
            continue

        # Reconstruct the same entropy-gated grid the injector used
        if entropy_map is not None:
            gated = _entropy_gate_cached(entropy_map, positions, h, w)
        else:
            gated = entropy_gate_positions(pixels, positions, h, w)
        gated.sort(key=lambda x: (x[0], x[1]))
        n_gated = len(gated)
        if n_gated < 5:
            continue

        # Read luma-diff at every gated position (once)
        diffs = []
        for r, c in gated:
            d = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
            diffs.append(d)

        # Measure this image's natural prime rate at these positions
        prime_hits = sum(1 for d in diffs if d in basket_set)
        prime_rate = prime_hits / n_gated

        # Compute adaptive threshold from this image's statistics
        if config.chain_threshold > 0:
            min_chain_len = config.chain_threshold  # fixed override
        else:
            min_chain_len = _adaptive_chain_threshold(n_gated, prime_rate)

        if n_gated < min_chain_len:
            continue

        # Forward scan
        longest_chain, longest_start, scanned = _scan_chains_one_direction(
            diffs, basket_set, n_gated, min_chain_len)

        # Idea 2: reverse scan (catches vertical flip, 180° rotation)
        if config.bidirectional and longest_chain < min_chain_len:
            rev_diffs = list(reversed(diffs))
            rev_chain, rev_start, rev_scanned = _scan_chains_one_direction(
                rev_diffs, basket_set, n_gated, min_chain_len)
            scanned += rev_scanned
            if rev_chain > longest_chain:
                longest_chain = rev_chain
                longest_start = n_gated - 1 - rev_start  # map back to forward index

        if longest_chain > best_chain:
            best_chain = longest_chain
            best_threshold = min_chain_len
            best_result = {
                "n_gated": n_gated,
                "longest_chain": longest_chain,
                "chain_start_index": longest_start,
                "positions_scanned": scanned,
                "grid_phase": phase_name,
                "prime_hit_rate": round(prime_rate, 4),
                "adaptive_threshold": min_chain_len,
            }

            if best_chain > min_chain_len:
                break  # no need to check other phases

    if best_result is None:
        return {"detected": False, "reason": "Image too small",
                "longest_chain": 0, "adaptive_threshold": best_threshold}

    best_result["detected"] = (best_result["longest_chain"] >
                               best_result["adaptive_threshold"])
    return best_result


def _check_twin_pairs(pixels: np.ndarray, min_prime: int = 37,
                      config: VerifyConfig = None,
                      entropy_map: np.ndarray = None) -> dict:
    """
    Blind twin-pair detection in the luma domain.

    A "twin" is two consecutive luma-pair distances that are both prime:
      |Y(r,c) - Y(r,c+1)| is prime  AND  |Y(r,c+1) - Y(r,c+2)| is prime.

    Natural probability of both being prime is ~1-2%.  Embedded compound
    markers with twins push this to 5-15%+ at marker grid positions.
    """
    if config is None:
        config = DEFAULT_CONFIG
    h, w, _ = pixels.shape
    prime_lookup = _make_prime_lookup(min_prime)

    if config.all_phases:
        phase_list = _grid_positions_all_phases(h, w)
    else:
        phase_list = _grid_positions_both_phases(h, w)

    best = None
    for phase_name, positions in phase_list:
        if entropy_map is not None:
            gated = _entropy_gate_cached(entropy_map, positions, h, w)
        else:
            gated = entropy_gate_positions(pixels, positions, h, w)
        twin_hits = 0
        total = 0

        for r, c in gated:
            if c + 2 >= w:
                continue
            total += 1
            d1 = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
            d2 = abs(_pixel_luma(pixels, r, c + 1) - _pixel_luma(pixels, r, c + 2))
            if d1 <= 255 and prime_lookup[d1] and d2 <= 255 and prime_lookup[d2]:
                twin_hits += 1

        if total == 0:
            continue
        twin_rate = twin_hits / total

        if best is None or twin_rate > best["twin_rate"]:
            best = {
                "twin_hits": twin_hits,
                "total_checked": total,
                "twin_rate": round(twin_rate, 6),
                "grid_phase": phase_name,
            }

    if best is None:
        return {"detected": False, "reason": "Image too small"}

    best["detected"] = best["twin_rate"] > TWIN_PAIR_RATE_THRESH
    return best


def _check_magic_sentinels(pixels: np.ndarray,
                           config: VerifyConfig = None,
                           entropy_map: np.ndarray = None) -> dict:
    """
    Check for magic sentinel pattern: B channel ≈ 42 at a position where
    the luma-pair distance |Y(r,c) - Y(r,c+1)| is also prime.
    Scans grid phases per config.
    """
    if config is None:
        config = DEFAULT_CONFIG
    h, w, _ = pixels.shape
    prime_lookup = _make_prime_lookup(37)
    magic_value = 42
    tolerance = 2

    if config.all_phases:
        phase_list = _grid_positions_all_phases(h, w)
    else:
        phase_list = _grid_positions_both_phases(h, w)

    best = None
    for phase_name, positions in phase_list:
        if entropy_map is not None:
            gated = _entropy_gate_cached(entropy_map, positions, h, w)
        else:
            gated = entropy_gate_positions(pixels, positions, h, w)
        magic_hits = 0
        total_checked = 0

        for r, c in gated:
            total_checked += 1
            b_val = int(pixels[r, c, 2])
            if abs(b_val - magic_value) <= tolerance:
                d = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
                if d <= 255 and prime_lookup[d]:
                    magic_hits += 1

        if total_checked == 0:
            continue
        magic_rate = magic_hits / total_checked

        if best is None or magic_rate > best["magic_rate"]:
            best = {
                "magic_hits": magic_hits,
                "total_checked": total_checked,
                "magic_rate": round(magic_rate, 6),
                "grid_phase": phase_name,
            }

    if best is None:
        return {"detected": False, "reason": "Image too small"}

    best["detected"] = best["magic_rate"] > MAGIC_SENTINEL_RATE_THRESH
    return best


def _check_mersenne_sentinels(pixels: np.ndarray) -> dict:
    """
    Structural: Scan for Mersenne sentinel patterns.

    Corroborating only — Mersenne values (3, 7, 31, 127) occur naturally
    at high rates. Cannot stand alone for blind detection.
    """
    h, w, _ = pixels.shape
    mersenne_set = set(MERSENNE_BASKET)
    prime_lookup = _make_prime_lookup(37)

    phase_list = _grid_positions_both_phases(h, w)
    all_positions = []
    for _name, positions in phase_list:
        all_positions.extend(positions)

    mersenne_hits = []
    for r, c in all_positions:
        d = abs(int(pixels[r, c, 0]) - int(pixels[r, c, 1]))
        if d in mersenne_set:
            mersenne_hits.append({"row": r, "col": c, "distance": d, "mersenne": d})

    # Pair analysis
    hit_by_row = {}
    for hit in mersenne_hits:
        hit_by_row.setdefault(hit["row"], []).append(hit)

    structural_pairs = 0
    distinct_mersenne = set()
    for row_hits in hit_by_row.values():
        for i, h1 in enumerate(row_hits):
            for h2 in row_hits[i + 1:]:
                if h1["mersenne"] != h2["mersenne"]:
                    continue
                col_diff = abs(h1["col"] - h2["col"])
                if col_diff < WINDOW_W or col_diff > WINDOW_W * 20:
                    continue
                has_prime_neighbour = False
                for hit in (h1, h2):
                    for dc in (-WINDOW_W, WINDOW_W):
                        nc = hit["col"] + dc
                        nr = hit["row"]
                        if 0 <= nr < h and 0 <= nc < w:
                            nd = abs(int(pixels[nr, nc, 0]) - int(pixels[nr, nc, 1]))
                            if nd <= 255 and prime_lookup[nd]:
                                has_prime_neighbour = True
                                break
                    if has_prime_neighbour:
                        break
                if has_prime_neighbour:
                    structural_pairs += 1
                    distinct_mersenne.add(h1["mersenne"])

    # Corroborating only — always False for blind scan
    detected = False

    return {
        "detected": detected,
        "total_mersenne_hits": len(mersenne_hits),
        "structural_pairs": structural_pairs,
        "distinct_mersenne_count": len(distinct_mersenne),
        "mersenne_values_found": sorted(set(h["mersenne"] for h in mersenne_hits)),
        "sample_positions": mersenne_hits[:20],
    }


def _check_halos(image: Image.Image, config: VerifyConfig = None) -> dict:
    """Layer 3: Detect radial lensing halos."""
    if config is None:
        config = DEFAULT_CONFIG
    centers = detect_halo_centers(image)

    present = [c for c in centers if c.state == HaloState.PRESENT]
    void = [c for c in centers if c.state == HaloState.VOID]

    strong_present = [c for c in present if c.amplitude >= HALO_AMPLITUDE_THRESH]
    # Nearest-prime halos produce prime density indistinguishable from
    # natural texture on real images.  Halo detection is corroborating
    # only until a discriminative detection model is implemented.
    # With corroborate_weak, we allow halos as a weak signal that can
    # promote a chain-of-(threshold-1) to detected.
    detected = (config.corroborate_weak and
                len(strong_present) >= HALO_STRONG_COUNT_THRESH)

    center_details = []
    for c in centers[:30]:
        center_details.append({
            "row": c.row,
            "col": c.col,
            "state": c.state.name,
            "inner_density": round(c.inner_density, 4),
            "outer_density": round(c.outer_density, 4),
            "amplitude": round(c.amplitude, 4),
        })

    return {
        "detected": detected,
        "total_centers": len(centers),
        "present_count": len(present),
        "void_count": len(void),
        "strong_present": len(strong_present),
        "centers": center_details,
    }


def _check_rulers(image: Image.Image) -> dict:
    """
    Layer H: Detect spatial ruler bands for crop/stitch forensics.

    Uses detect_all_rulers (expected positions) first, then blind_scan for
    cropped images.  A ruler is valid if its decoded payload contains a
    dimension estimate that approximately matches the image.
    """
    W, H = image.size
    try:
        # Try expected positions first (fast, works on uncropped images)
        detections = detect_all_rulers(image)
        # Also run blind scan for cropped images
        blind = blind_scan_rulers(image)
        # Merge blind results that aren't already found
        det_positions = set((d.at_pixel, d.is_col) for d in detections)
        for b in blind:
            if (b.at_pixel, b.is_col) not in det_positions:
                detections.append(b)
    except Exception as e:
        return {"detected": False, "error": str(e)}

    col_rulers = [d for d in detections if d.is_col]
    row_rulers = [d for d in detections if not d.is_col]

    ruler_details = []
    valid_rulers = []
    for d in detections:
        if not d.payload or d.payload.bits_read < 4:
            continue
        has_signal = d.band_mean > RULER_BAND_ELEVATION_THRESH
        if not has_signal:
            continue

        p = d.payload
        ref_dim = W if d.is_col else H

        # Validation path 1: dim_orig matches current dimensions
        dim_ok = (p.dim_orig is not None and
                  0.5 * ref_dim <= p.dim_orig <= 2.0 * ref_dim)
        # Validation path 2 (small images): position matches at_pixel
        pos_ok = (p.position is not None and
                  abs(p.position - d.at_pixel) <= BAND_WIDTH)
        # Validation path 3 (standard mode): fraction matches position
        frac_ok = False
        if p.fraction is not None:
            n, den = p.fraction
            expected_pos = int(round(ref_dim * n / den))
            frac_ok = abs(expected_pos - d.at_pixel) <= BAND_WIDTH

        if dim_ok or pos_ok or frac_ok:
            valid_rulers.append(d)

        ruler_details.append({
            "at_pixel": d.at_pixel,
            "is_col": d.is_col,
            "band_mean": round(d.band_mean, 2),
            "n_segments": d.n_segments,
            "payload_bits": d.payload.bits_read if d.payload else 0,
            "dim_orig": d.payload.dim_orig if d.payload else None,
        })

    detected = len(valid_rulers) >= RULER_VALID_COUNT_THRESH

    return {
        "detected": detected,
        "col_rulers": len(col_rulers),
        "row_rulers": len(row_rulers),
        "total_rulers": len(detections),
        "valid_rulers": len(valid_rulers),
        "rulers": ruler_details,
    }


def _check_dct_primes(pixels: np.ndarray, entropy_map: np.ndarray = None) -> dict:
    """
    EXPERIMENTAL Layer DCT: Check for prime enrichment in DCT coefficients.

    Control group: entropy-gated positions from a DIFFERENT grid phase,
    so both groups have similar texture levels.  The signal (if present)
    is only at the embedding phase (block_center = phase 3,3).
    """
    from dct_markers import detect_dct_primes

    h, w = pixels.shape[:2]
    phase_list = _grid_positions_both_phases(h, w)

    # Marker candidates: block_center phase (where embedder places signal)
    _, marker_positions = phase_list[0]
    # Control: raw phase (phase 0,0) — same texture, no signal
    _, control_positions = phase_list[1]

    if entropy_map is not None:
        gated = _entropy_gate_cached(entropy_map, marker_positions, h, w)
        control = _entropy_gate_cached(entropy_map, control_positions, h, w)
    else:
        gated = entropy_gate_positions(pixels, marker_positions, h, w)
        control = entropy_gate_positions(pixels, control_positions, h, w)

    # Align to 8x8 block origins for DCT
    gated_blocks = list(set(
        (r - r % 8, c - c % 8) for r, c in gated
        if r - r % 8 + 8 <= h and c - c % 8 + 8 <= w))
    control_blocks = list(set(
        (r - r % 8, c - c % 8) for r, c in control
        if r - r % 8 + 8 <= h and c - c % 8 + 8 <= w))

    return detect_dct_primes(pixels, gated_blocks, control_blocks)


def _check_thermodynamic(pixels: np.ndarray,
                         entropy_map: np.ndarray = None) -> dict:
    """
    EXPERIMENTAL Layer T: Thermodynamic consensus detection.

    Control group: entropy-gated positions from a DIFFERENT grid phase,
    so both groups have similar texture/prime-rate baseline.
    """
    from thermo_markers import detect_thermodynamic

    h, w = pixels.shape[:2]
    phase_list = _grid_positions_both_phases(h, w)

    _, marker_positions = phase_list[0]  # block_center (embedded)
    _, control_positions = phase_list[1]  # raw phase (not embedded)

    if entropy_map is not None:
        gated = _entropy_gate_cached(entropy_map, marker_positions, h, w)
        control = _entropy_gate_cached(entropy_map, control_positions, h, w)
    else:
        gated = entropy_gate_positions(pixels, marker_positions, h, w)
        control = entropy_gate_positions(pixels, control_positions, h, w)

    return detect_thermodynamic(pixels, gated, control)


def verify_image(image_path: str, output_dir: str = None,
                 config: VerifyConfig = None) -> dict:
    """
    Run all verification checks on an image.

    Returns a comprehensive verification report.
    """
    if config is None:
        config = DEFAULT_CONFIG

    img = Image.open(image_path).convert("RGB")
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    img_hash = hashlib.sha256(pixels.tobytes()).hexdigest()[:16]
    img_name = os.path.splitext(os.path.basename(image_path))[0]
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Compute entropy map ONCE — shared across all phase scans
    from smart_embedder import compute_local_entropy_fast
    emap = compute_local_entropy_fast(pixels, block_size=ENTROPY_BLOCK_SIZE)

    # Run all checks — thread config and cached entropy map through each layer
    dqt_result = _check_dqt_primes(image_path)
    prime_result = _check_prime_enrichment(pixels, config=config, entropy_map=emap)
    twin_result = _check_twin_pairs(pixels, config=config, entropy_map=emap)
    magic_result = _check_magic_sentinels(pixels, config=config, entropy_map=emap)
    mersenne_result = _check_mersenne_sentinels(pixels)
    halo_result = _check_halos(img, config=config)
    ruler_result = _check_rulers(img)

    # Experimental layers — only run when explicitly enabled
    dct_result = (_check_dct_primes(pixels, entropy_map=emap)
                  if config.check_dct else {"detected": False, "enabled": False})
    thermo_result = (_check_thermodynamic(pixels, entropy_map=emap)
                     if config.check_thermo else {"detected": False, "enabled": False})

    # Compute overall verdict
    signals_detected = []
    if dqt_result.get("detected"):
        signals_detected.append("DQT Prime Tables")
    if prime_result.get("detected"):
        signals_detected.append("Prime Enrichment")
    if twin_result.get("detected"):
        signals_detected.append("Twin Pairs")
    if magic_result.get("detected"):
        signals_detected.append("Magic Sentinels")
    if mersenne_result.get("detected"):
        signals_detected.append("Mersenne Sentinels")
    if halo_result.get("detected"):
        signals_detected.append("Radial Halos")
    if ruler_result.get("detected"):
        signals_detected.append("Spatial Rulers")
    if dct_result.get("detected"):
        signals_detected.append("DCT Primes")
    if thermo_result.get("detected"):
        signals_detected.append("Thermodynamic Consensus")

    # Idea 1: corroboration — a chain just below threshold gets promoted
    # if at least one other independent signal fired
    if config.corroborate_weak and not prime_result.get("detected"):
        adaptive_thresh = prime_result.get("adaptive_threshold", 6)
        chain_len = prime_result.get("longest_chain", 0)
        if chain_len >= adaptive_thresh - 1:
            other_signals = len(signals_detected)  # signals already found (excl prime)
            if other_signals >= 1:
                signals_detected.append("Prime Enrichment (corroborated)")
                prime_result["detected"] = True
                prime_result["corroborated"] = True

    n_signals = len(signals_detected)
    if n_signals >= VERDICT_CONFIRMED_THRESH:
        verdict = "CONFIRMED"
        confidence = "high"
    elif n_signals >= VERDICT_PROBABLE_THRESH:
        verdict = "PROBABLE"
        confidence = "medium"
    elif n_signals >= VERDICT_PARTIAL_THRESH:
        verdict = "PARTIAL"
        confidence = "low"
    else:
        verdict = "NOT DETECTED"
        confidence = "none"

    report = {
        "image_name": img_name,
        "image_hash": img_hash,
        "width": w,
        "height": h,
        "timestamp": timestamp,
        "verdict": verdict,
        "confidence": confidence,
        "signals_detected": signals_detected,
        "signal_count": n_signals,
        "checks": {
            "dqt_primes": dqt_result,
            "prime_enrichment": prime_result,
            "twin_pairs": twin_result,
            "magic_sentinels": magic_result,
            "mersenne_sentinels": mersenne_result,
            "radial_halos": halo_result,
            "spatial_rulers": ruler_result,
            "dct_primes": dct_result,
            "thermodynamic": thermo_result,
        },
    }

    # Save report if output directory specified
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        slug = f"{img_name}_{img_hash}"
        report_path = os.path.join(output_dir, f"{slug}_verify.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        report["report_path"] = f"{slug}_verify.json"

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify Granite provenance signals in an image"
    )
    parser.add_argument("image", help="Path to image to verify")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory for verification report")
    parser.add_argument("--experimental-dct", action="store_true",
                        help="Enable experimental DCT-domain prime detection")
    parser.add_argument("--experimental-thermo", action="store_true",
                        help="Enable experimental thermodynamic consensus detection")
    args = parser.parse_args()

    config = VerifyConfig(
        check_dct=args.experimental_dct,
        check_thermo=args.experimental_thermo,
    )
    report = verify_image(args.image, args.output, config=config)

    print(f"\nGranite Verification Report")
    print(f"  Image:      {report['image_name']} ({report['width']}x{report['height']})")
    print(f"  Hash:       {report['image_hash']}")
    print(f"  Verdict:    {report['verdict']} ({report['confidence']} confidence)")
    print(f"  Signals:    {', '.join(report['signals_detected']) or 'none'}")
    print()
    for check_name, result in report["checks"].items():
        if result.get("enabled") is False:
            status = "disabled (use --experimental flag)"
        elif result.get("applicable") is False:
            status = "n/a"
        elif result.get("detected"):
            status = "DETECTED"
        else:
            status = "not detected"
        print(f"  {check_name:25s} {status}")

    if args.output:
        print(f"\n  Report saved to: {report.get('report_path', 'N/A')}")
