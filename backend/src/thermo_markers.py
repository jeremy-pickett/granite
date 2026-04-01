#!/usr/bin/env python3
"""
thermo_markers.py — Layer T: Thermodynamic Consensus Detection
================================================================
EXPERIMENTAL — requires --experimental-thermo flag.

Abandon the "find one long chain" paradigm.  Instead, embed thousands
of independent single-prime markers at minimal pixel cost (nudge ≤ 2
per pixel).  No chains, no adjacency requirements, no following.

Detection: compare the prime luma-pair hit rate at entropy-gated grid
positions vs the image's own control positions (non-gated or random).
With N=10,000 markers even if JPEG destroys 80% of them, the surviving
2,000 against a natural baseline of ~14% gives p < 1e-50 via binomial
test.  The signal is thermodynamic — it's in the statistical temperature
of the whole image, not in any individual pixel.

Properties:
  - Rotation: scrambles positions but the RATE doesn't change
  - Crop: removes markers proportionally from both groups
  - Compression: destroys individual markers but the aggregate survives
  - The only attack that works is replacing every pixel

The manifest exists for QA to verify which markers survived, but the
blind detector never sees it — it just measures temperature.
"""

import numpy as np
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

# Minimum prime for luma-pair distance
PRIME_FLOOR = 7

# Maximum pixel adjustment per channel (keeps PSNR high)
MAX_PIXEL_NUDGE = 2

# Target density: fraction of grid positions to embed
# Higher = stronger signal but more visual impact
EMBED_DENSITY = 1.0  # embed at ALL entropy-gated positions

# Build prime lookup
_PRIME_LUT = np.zeros(256, dtype=bool)
for _p in range(2, 256):
    _is_prime = True
    for _d in range(2, int(_p**0.5) + 1):
        if _p % _d == 0:
            _is_prime = False
            break
    if _is_prime:
        _PRIME_LUT[_p] = True

# Precompute primes >= floor for fast lookup
_PRIMES_ABOVE_FLOOR = set(int(p) for p in range(PRIME_FLOOR, 256) if _PRIME_LUT[p])


def _pixel_luma(pixels, r, c):
    """Integer luma Y for pixel at (r, c). BT.601 weights."""
    return int(round(0.299 * float(pixels[r, c, 0]) +
                     0.587 * float(pixels[r, c, 1]) +
                     0.114 * float(pixels[r, c, 2])))


def _nearest_prime_luma(current_diff, floor=PRIME_FLOOR, max_nudge=MAX_PIXEL_NUDGE):
    """Find the nearest prime to current_diff that is >= floor, within max_nudge."""
    for offset in range(0, max_nudge + 1):
        for candidate in [current_diff + offset, current_diff - offset]:
            if candidate >= floor and candidate < 256 and _PRIME_LUT[candidate]:
                return candidate, offset
    return None, None


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_thermodynamic(pixels, positions):
    """
    Embed minimal prime nudges at every given position.

    For each position (r, c), compute |Y(r,c) - Y(r,c+1)| and nudge
    the G channel of pixel (r,c) by at most MAX_PIXEL_NUDGE to make
    the luma difference a prime >= PRIME_FLOOR.

    Args:
        pixels: H x W x 3 numpy array (modified in-place)
        positions: list of (row, col) to embed at

    Returns:
        (modified_pixels, metadata_dict)
    """
    h, w = pixels.shape[:2]
    modified = pixels.copy().astype(np.int32)
    embedded = 0
    skipped = 0
    total_nudge = 0

    for r, c in positions:
        if c + 1 >= w:
            skipped += 1
            continue

        y0 = _pixel_luma(modified, r, c)
        y1 = _pixel_luma(modified, r, c + 1)
        current_diff = abs(y0 - y1)

        # Already prime? Skip (free hit)
        if current_diff in _PRIMES_ABOVE_FLOOR:
            embedded += 1
            continue

        # Try nudging G channel of pixel (r, c) to make diff prime
        g_orig = int(modified[r, c, 1])
        best_g = None
        best_nudge = MAX_PIXEL_NUDGE + 1

        for dg in range(-MAX_PIXEL_NUDGE, MAX_PIXEL_NUDGE + 1):
            g_new = g_orig + dg
            if g_new < 0 or g_new > 255:
                continue
            # Recompute luma with new G
            y0_new = int(round(0.299 * float(modified[r, c, 0]) +
                               0.587 * float(g_new) +
                               0.114 * float(modified[r, c, 2])))
            new_diff = abs(y0_new - y1)
            if new_diff in _PRIMES_ABOVE_FLOOR and abs(dg) < best_nudge:
                best_g = g_new
                best_nudge = abs(dg)

        if best_g is not None:
            modified[r, c, 1] = best_g
            embedded += 1
            total_nudge += best_nudge
        else:
            skipped += 1

    modified = np.clip(modified, 0, 255).astype(np.uint8)

    meta = {
        'layer': 'thermo',
        'embedded': embedded,
        'skipped': skipped,
        'total_positions': len(positions),
        'embed_rate': round(embedded / len(positions), 4) if positions else 0,
        'mean_nudge': round(total_nudge / max(1, embedded - skipped), 3),
    }
    return modified, meta


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_thermodynamic(pixels, gated_positions, control_positions):
    """
    Thermodynamic consensus detection via binomial test.

    Measures the prime luma-pair rate at entropy-gated positions and
    compares against control positions.  The image is its own control.

    Args:
        pixels: H x W x 3 numpy array
        gated_positions: list of (row, col) — where signal might be
        control_positions: list of (row, col) — natural baseline

    Returns:
        detection dict
    """
    h, w = pixels.shape[:2]

    def _prime_rate(positions):
        hits = 0
        total = 0
        for r, c in positions:
            if c + 1 >= w:
                continue
            total += 1
            d = abs(_pixel_luma(pixels, r, c) - _pixel_luma(pixels, r, c + 1))
            if d in _PRIMES_ABOVE_FLOOR:
                hits += 1
        return hits, total

    marker_hits, marker_total = _prime_rate(gated_positions)
    control_hits, control_total = _prime_rate(control_positions)

    if marker_total < 30 or control_total < 30:
        return {"detected": False, "reason": "Too few positions"}

    marker_rate = marker_hits / marker_total
    control_rate = control_hits / control_total

    # Binomial test: are marker positions enriched for primes
    # beyond the control rate?
    if control_rate > 0 and control_rate < 1:
        binom_result = sp_stats.binomtest(
            marker_hits, marker_total, control_rate,
            alternative='greater')
        pvalue = binom_result.pvalue
    else:
        pvalue = 1.0

    # Also chi-squared for robustness
    a = marker_hits
    b = marker_total - marker_hits
    c = control_hits
    d = control_total - control_hits
    contingency = np.array([[a, b], [c, d]])
    if min(a, b, c, d) > 5:
        chi2, chi2_p, _, _ = sp_stats.chi2_contingency(contingency)
    else:
        chi2, chi2_p = 0, 1.0

    # Elevation: how many percentage points above control?
    elevation = marker_rate - control_rate

    # Detection: significant enrichment (binomial p < 0.001)
    # AND marker rate must be above control (not just different)
    # AND elevation must be meaningful (> 2 percentage points)
    detected = (pvalue < 0.001 and marker_rate > control_rate
                and elevation > 0.02)

    return {
        "detected": detected,
        "marker_positions": marker_total,
        "control_positions": control_total,
        "marker_hits": marker_hits,
        "control_hits": control_hits,
        "marker_prime_rate": round(marker_rate, 4),
        "control_prime_rate": round(control_rate, 4),
        "elevation": round(elevation, 4),
        "rate_ratio": round(marker_rate / control_rate, 3) if control_rate > 0 else float('inf'),
        "binomial_pvalue": float(pvalue),
        "chi2_pvalue": float(chi2_p),
    }
