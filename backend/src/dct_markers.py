#!/usr/bin/env python3
"""
dct_markers.py — Layer DCT: Frequency-Domain Prime Embedding
=============================================================
EXPERIMENTAL — requires --experimental-dct flag.

Instead of nudging pixel values and hoping they survive JPEG quantization,
embed primes directly into DCT coefficients.  JPEG preserves DCT structure
by design — the signal lives in the domain JPEG is built to keep.

Embedding:
    For each entropy-gated grid position, extract the 8x8 block,
    apply Type-II DCT, nudge a mid-frequency AC coefficient to the
    nearest prime, IDCT back.  The coefficient position is chosen to
    balance visibility (low-frequency = visible) against survival
    (high-frequency = quantized to zero).

Detection:
    For each grid position, DCT the 8x8 block, read the target
    coefficient, check if abs(round(coeff)) is prime.  Compare prime
    rate at gated positions vs control positions.  Binomial test.

The key insight: JPEG quantization divides coefficients by the quant
table entry and rounds.  If the coefficient is already a prime multiple
of the quant step, re-quantization at the same or lower quality
preserves the relationship.  The signal IS the quantization.
"""

import math
import numpy as np
from scipy.fft import dctn, idctn
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

# Zigzag-order position of the target AC coefficient.
# Position 10 = (1,3) in 8x8 block — mid-frequency, moderate energy.
# Lower positions (more energy) are more visible but survive better.
# Higher positions (less energy) are invisible but get quantized to 0.
ZIGZAG_POS = 10

# Zigzag order mapping: index → (row, col) in 8x8 block
_ZIGZAG = [
    (0,0),(0,1),(1,0),(2,0),(1,1),(0,2),(0,3),(1,2),
    (2,1),(3,0),(4,0),(3,1),(2,2),(1,3),(0,4),(0,5),
    (1,4),(2,3),(3,2),(4,1),(5,0),(6,0),(5,1),(4,2),
    (3,3),(2,4),(1,5),(0,6),(0,7),(1,6),(2,5),(3,4),
    (4,3),(5,2),(6,1),(7,0),(7,1),(6,2),(5,3),(4,4),
    (3,5),(2,6),(1,7),(2,7),(3,6),(4,5),(5,4),(6,3),
    (7,2),(7,3),(6,4),(5,5),(4,6),(3,7),(4,7),(5,6),
    (6,5),(7,4),(7,5),(6,6),(5,7),(6,7),(7,6),(7,7),
]

TARGET_ROW, TARGET_COL = _ZIGZAG[ZIGZAG_POS]

# Prime floor — ignore tiny primes that occur naturally in DCT coefficients
PRIME_FLOOR = 7

# Max nudge in DCT coefficient space (limits visual impact)
MAX_DCT_NUDGE = 4

# Build prime lookup at import time
_PRIME_LUT = np.zeros(512, dtype=bool)  # coefficients can exceed 255
for _p in range(2, 512):
    _is_prime = True
    if _p < 2:
        _is_prime = False
    else:
        for _d in range(2, int(_p**0.5) + 1):
            if _p % _d == 0:
                _is_prime = False
                break
    _PRIME_LUT[_p] = _is_prime


def _nearest_prime(val, floor=PRIME_FLOOR, max_nudge=MAX_DCT_NUDGE):
    """Find the nearest prime to abs(val) that is >= floor, within max_nudge."""
    target = abs(int(round(val)))
    sign = 1 if val >= 0 else -1

    if target < floor:
        # Below floor — nudge up to floor's nearest prime
        for p in range(floor, floor + max_nudge + 1):
            if p < 512 and _PRIME_LUT[p]:
                return sign * p, abs(p - target)
        return None, None

    best_prime = None
    best_dist = max_nudge + 1

    for offset in range(0, max_nudge + 1):
        for candidate in [target + offset, target - offset]:
            if candidate >= floor and candidate < 512 and _PRIME_LUT[candidate]:
                if abs(candidate - target) < best_dist:
                    best_dist = abs(candidate - target)
                    best_prime = candidate

    if best_prime is not None:
        return sign * best_prime, best_dist
    return None, None


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_dct_primes(pixels, positions, channel=0):
    """
    Embed primes into DCT coefficients at the target AC position.

    Args:
        pixels: H x W x 3 numpy array (will be modified in-place)
        positions: list of (row, col) — top-left corner of each 8x8 block
        channel: which color channel to modify (0=R, default)

    Returns:
        (modified_pixels, metadata_dict)
    """
    h, w = pixels.shape[:2]
    modified = pixels.astype(np.float64)
    embedded = 0
    skipped = 0
    total_nudge = 0

    for r, c in positions:
        # Bounds check for full 8x8 block
        if r + 8 > h or c + 8 > w:
            skipped += 1
            continue

        # Extract block from target channel
        block = modified[r:r+8, c:c+8, channel].copy()

        # Forward DCT (Type II, orthonormalized)
        dct_block = dctn(block, type=2, norm='ortho')

        # Read the target coefficient
        coeff = dct_block[TARGET_ROW, TARGET_COL]

        # Nudge to nearest prime
        prime_val, nudge = _nearest_prime(coeff)
        if prime_val is None:
            skipped += 1
            continue

        # Apply
        dct_block[TARGET_ROW, TARGET_COL] = float(prime_val)

        # Inverse DCT back to pixel domain
        new_block = idctn(dct_block, type=2, norm='ortho')
        modified[r:r+8, c:c+8, channel] = new_block
        embedded += 1
        total_nudge += nudge

    modified = np.clip(modified, 0, 255).astype(np.uint8)

    meta = {
        'layer': 'dct',
        'embedded': embedded,
        'skipped': skipped,
        'total_positions': len(positions),
        'mean_nudge': round(total_nudge / embedded, 2) if embedded > 0 else 0,
        'zigzag_pos': ZIGZAG_POS,
        'target_rc': (TARGET_ROW, TARGET_COL),
        'channel': channel,
    }
    return modified, meta


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_dct_primes(pixels, gated_positions, control_positions, channel=0):
    """
    Detect prime enrichment in DCT coefficients.

    Compares prime rate at gated (marker candidate) positions vs
    control positions.  The image is its own control group.

    Args:
        pixels: H x W x 3 numpy array
        gated_positions: list of (row, col) — entropy-gated grid positions
        control_positions: list of (row, col) — non-gated positions for control
        channel: which color channel to read

    Returns:
        detection dict with p-value and rates
    """
    h, w = pixels.shape[:2]
    arr = pixels.astype(np.float64)

    def _read_coefficients(positions):
        """Read the target DCT coefficient at each position."""
        coeffs = []
        for r, c in positions:
            if r + 8 > h or c + 8 > w:
                continue
            block = arr[r:r+8, c:c+8, channel]
            dct_block = dctn(block, type=2, norm='ortho')
            coeff = dct_block[TARGET_ROW, TARGET_COL]
            coeffs.append(abs(int(round(coeff))))
        return coeffs

    marker_coeffs = _read_coefficients(gated_positions)
    control_coeffs = _read_coefficients(control_positions)

    if len(marker_coeffs) < 10 or len(control_coeffs) < 10:
        return {"detected": False, "reason": "Too few positions"}

    # Count primes at each group
    marker_primes = sum(1 for c in marker_coeffs
                        if PRIME_FLOOR <= c < 512 and _PRIME_LUT[c])
    control_primes = sum(1 for c in control_coeffs
                         if PRIME_FLOOR <= c < 512 and _PRIME_LUT[c])

    marker_rate = marker_primes / len(marker_coeffs)
    control_rate = control_primes / len(control_coeffs)

    # Chi-squared test on 2x2 contingency table
    a = marker_primes
    b = len(marker_coeffs) - marker_primes
    c = control_primes
    d = len(control_coeffs) - control_primes

    contingency = np.array([[a, b], [c, d]])
    if min(a, b, c, d) > 5:
        chi2, pvalue, _, _ = sp_stats.chi2_contingency(contingency)
    elif (a + b) > 0 and (c + d) > 0:
        _, pvalue = sp_stats.fisher_exact(contingency, alternative='greater')
        chi2 = 0
    else:
        chi2, pvalue = 0, 1.0

    # Detection: significant enrichment at marker positions
    detected = (pvalue < 0.01 and marker_rate > control_rate)

    return {
        "detected": detected,
        "marker_positions": len(marker_coeffs),
        "control_positions": len(control_coeffs),
        "marker_prime_rate": round(marker_rate, 4),
        "control_prime_rate": round(control_rate, 4),
        "rate_ratio": round(marker_rate / control_rate, 3) if control_rate > 0 else float('inf'),
        "chi2_pvalue": float(pvalue),
        "zigzag_pos": ZIGZAG_POS,
    }
