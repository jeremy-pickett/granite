#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
#
# Copyright (c) 2026, Jeremy Pickett
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
# THE POSSIBILITY OF SUCH DAMAGE.
# =============================================================================
#
# Author:  Jeremy Pickett <jeremy.pickett@gmail.com>
# Project: Participation Over Permission — Provenance Signal Detection
#          Axiomatic Fictions Series
# Date:    March 2026
#
# Co-developed with Claude (Anthropic). Human-directed, AI-assisted.
# =============================================================================
"""
GEOMETRIC ATTACK: Rotations and Flips
=======================================
Jeremy Pickett — Axiomatic Fictions Series

The scary attack. Arbitrary rotation forces interpolation.
Interpolation blends pixel values with neighbors.
Does the perturbation survive blending?
"""

import os
import sys
import io
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import MarkerConfig, embed_compound, detect_compound
from div2k_harness import extract_twin_measurements, compare_twin_distributions

TWIN_CONFIG = MarkerConfig(
    name="twin", description="Rotation attack test",
    min_prime=53, use_twins=True, use_rare_basket=True,
    use_magic=False, detection_prime_tolerance=2, n_markers=1000,
)


def gen_photo(size, seed=42):
    rng = np.random.RandomState(seed)
    h = w = size
    img = np.zeros((h, w, 3), dtype=np.float64)
    for _ in range(max(10, size // 50)):
        cy, cx = rng.randint(0, h), rng.randint(0, w)
        sy, sx = rng.uniform(size*0.04, size*0.3), rng.uniform(size*0.04, size*0.3)
        color = rng.uniform(50, 220, 3)
        yy, xx = np.ogrid[:h, :w]
        mask = np.exp(-0.5*(((yy-cy)/sy)**2 + ((xx-cx)/sx)**2))
        for c in range(3):
            img[:,:,c] += mask * color[c]
    img = np.clip(img, 0, 255)
    noise = rng.normal(0, 3, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


def to_jpeg(pixels, q=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=q)
    return buf.getvalue()

def decode(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


def disruption_map(pixels, markers, config):
    prime_lookup = build_prime_lookup(8, min_prime=config.min_prime)
    tol = config.detection_prime_tolerance
    max_val = 255
    h, w, _ = pixels.shape

    fuzzy_prime = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for offset in range(-tol, tol + 1):
            check = d + offset
            if 0 <= check <= max_val and prime_lookup[check]:
                fuzzy_prime[d] = True
                break

    bitmap = []
    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc >= w:
            bitmap.append(0)
            continue
        d1 = abs(int(pixels[r, c, 0]) - int(pixels[r, c, 1]))
        d2 = abs(int(pixels[r, tc, 0]) - int(pixels[r, tc, 1]))
        p1 = bool(fuzzy_prime[min(d1, max_val)])
        p2 = bool(fuzzy_prime[min(d2, max_val)])
        bitmap.append(1 if (p1 and p2) else 0)
    return np.array(bitmap, dtype=np.uint8)


def transform_positions(markers, transform, img_size):
    """Apply a geometric transform to marker positions."""
    h, w = img_size
    transformed = []
    for m in markers:
        r, c = float(m["row"]), float(m["col"])
        tc = float(m.get("twin_col", c + 1))

        if transform == "flip_h":
            c = w - 1 - c
            tc = w - 1 - tc
            # Swap twin_col ordering if flipped
            if tc > c:
                pass  # normal
            else:
                c, tc = tc, c
        elif transform == "flip_v":
            r = h - 1 - r
        elif transform == "flip_hv":
            c = w - 1 - c
            tc = w - 1 - tc
            r = h - 1 - r
            if tc > c:
                pass
            else:
                c, tc = tc, c
        elif transform.startswith("rotate_"):
            angle = float(transform.split("_")[1])
            rad = np.radians(angle)
            cy, cx = h / 2, w / 2
            # Rotate position around center
            nr = (r - cy) * np.cos(rad) - (c - cx) * np.sin(rad) + cy
            nc = (r - cy) * np.sin(rad) + (c - cx) * np.cos(rad) + cx
            ntc = (r - cy) * np.sin(rad) + (tc - cx) * np.cos(rad) + cx
            r, c, tc = nr, nc, ntc

        r, c, tc = int(round(r)), int(round(c)), int(round(tc))
        if 0 <= r < h and 0 <= c < w and 0 <= tc < w:
            transformed.append({"row": r, "col": c, "twin_col": tc})
    return transformed


def apply_transform(pixels, transform):
    """Apply a geometric transform to an image."""
    img = Image.fromarray(pixels)
    if transform == "flip_h":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif transform == "flip_v":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    elif transform == "flip_hv":
        img = img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)
    elif transform.startswith("rotate_"):
        angle = float(transform.split("_")[1])
        # Use BICUBIC for realistic rotation interpolation
        # expand=False keeps same dimensions (crops corners)
        img = img.rotate(-angle, resample=Image.BICUBIC, expand=False)
    return np.array(img)


def run_test():
    SIZE = 1024

    print("=" * 90)
    print("GEOMETRIC ATTACK: ROTATIONS AND FLIPS")
    print("=" * 90)

    # Generate and embed
    print(f"\n[1] Generating {SIZE}x{SIZE} image and embedding...")
    pixels = gen_photo(SIZE)
    embedded, markers = embed_compound(pixels, TWIN_CONFIG, seed=42)
    print(f"    {len(markers)} markers embedded")

    # JPEG encode baseline
    gen0_data = to_jpeg(embedded, 95)
    gen0_px = decode(gen0_data)

    # Baseline
    det_base = detect_compound(gen0_px, markers, TWIN_CONFIG)
    map_base = disruption_map(gen0_px, markers, TWIN_CONFIG)
    gen0_twins = extract_twin_measurements(gen0_px, markers)

    print(f"    Baseline: {det_base['marker_compound_pass']}/{det_base['marker_total']}"
          f" ratio={det_base['rate_ratio']:.1f}x p={det_base['binomial_pvalue']:.2e}")

    # =========================================================================
    # FLIPS (lossless coordinate transforms)
    # =========================================================================
    print(f"\n\n{'='*90}")
    print("PART 1: FLIPS (no interpolation, pure coordinate remap)")
    print(f"{'='*90}")

    print(f"\n  {'Transform':>20s}  {'Markers':>8s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"  {'-'*80}")

    for flip in ["flip_h", "flip_v", "flip_hv"]:
        flipped_px = apply_transform(gen0_px, flip)
        flipped_markers = transform_positions(markers, flip, (SIZE, SIZE))

        det = detect_compound(flipped_px, flipped_markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {flip:>20s}  {len(flipped_markers):>6d}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # What if detector doesn't know about the flip? (scan at original positions)
    print(f"\n  What if the detector doesn't know the image was flipped?")
    print(f"  (scanning at original positions on a flipped image)")
    print(f"  {'Transform':>20s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"  {'-'*70}")

    for flip in ["flip_h", "flip_v", "flip_hv"]:
        flipped_px = apply_transform(gen0_px, flip)
        # Use ORIGINAL markers on FLIPPED image
        det = detect_compound(flipped_px, markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {flip:>20s}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # =========================================================================
    # SMALL ROTATIONS (the scary part)
    # =========================================================================
    print(f"\n\n{'='*90}")
    print("PART 2: SMALL ROTATIONS (interpolation required)")
    print(f"{'='*90}")

    angles = [1, 2, 3, 5, 7, 10, 15, 45, 90]

    # With corrected positions
    print(f"\n  WITH corrected marker positions:")
    print(f"  {'Angle':>8s}  {'Markers':>8s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Jaccard':>8s}  {'Status'}")
    print(f"  {'-'*85}")

    for angle in angles:
        rotated_px = apply_transform(gen0_px, f"rotate_{angle}")
        rotated_markers = transform_positions(markers, f"rotate_{angle}", (SIZE, SIZE))

        if len(rotated_markers) < 20:
            print(f"  {angle:>6d}\u00b0  Too few markers survived coordinate transform ({len(rotated_markers)})")
            continue

        det = detect_compound(rotated_px, rotated_markers, TWIN_CONFIG)

        # Fingerprint comparison
        rot_map = disruption_map(rotated_px, rotated_markers, TWIN_CONFIG)
        # Can't directly compare maps since positions changed; use pass rate as proxy
        n = min(len(map_base), len(rot_map))
        if n > 0:
            intersection = int(np.sum(map_base[:n] & rot_map[:n]))
            union = int(np.sum(map_base[:n] | rot_map[:n]))
            jaccard = intersection / union if union > 0 else 0
        else:
            jaccard = 0

        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {angle:>6d}\u00b0  {len(rotated_markers):>6d}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {jaccard:>8.4f}"
              f"  {status}")

    # Without corrected positions (blind detection on rotated image)
    print(f"\n  WITHOUT corrected positions (original markers on rotated image):")
    print(f"  {'Angle':>8s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"  {'-'*65}")

    for angle in angles:
        rotated_px = apply_transform(gen0_px, f"rotate_{angle}")
        det = detect_compound(rotated_px, markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {angle:>6d}\u00b0"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # =========================================================================
    # THE FULL ATTACK CHAIN
    # =========================================================================
    print(f"\n\n{'='*90}")
    print("PART 3: THE FULL CHAIN — rotate 5\u00b0, flip H, rotate 7\u00b0, flip V")
    print(f"{'='*90}")

    current_px = gen0_px.copy()
    current_markers = [dict(m) for m in markers]
    current_size = (SIZE, SIZE)

    steps = [
        ("rotate_5", "Rotate 5\u00b0"),
        ("flip_h", "Flip horizontal"),
        ("rotate_7", "Rotate 7\u00b0"),
        ("flip_v", "Flip vertical"),
    ]

    print(f"\n  Step-by-step with corrected positions:")
    print(f"  {'Step':>25s}  {'Markers':>8s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"  {'-'*85}")

    for transform, label in steps:
        current_px = apply_transform(current_px, transform)
        current_markers = transform_positions(current_markers, transform, current_size)

        if len(current_markers) < 10:
            print(f"  {label:>25s}  {len(current_markers):>6d}  — Too few markers")
            continue

        det = detect_compound(current_px, current_markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {label:>25s}  {len(current_markers):>6d}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # Now: what if the attacker also JPEG re-encodes at the end?
    print(f"\n  After full chain + JPEG Q85 re-encode:")
    reenc_data = to_jpeg(current_px, 85)
    reenc_px = decode(reenc_data)
    if len(current_markers) >= 10:
        det = detect_compound(reenc_px, current_markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {'Chain + Q85':>25s}  {len(current_markers):>6d}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # =========================================================================
    # THE INVERSE: Can the attacker undo the rotation?
    # =========================================================================
    print(f"\n\n{'='*90}")
    print("PART 4: INVERSE — Apply chain, then reverse it exactly")
    print(f"{'='*90}")

    # Forward: rotate 5, flip H, rotate 7, flip V
    fwd = gen0_px.copy()
    fwd = apply_transform(fwd, "rotate_5")
    fwd = apply_transform(fwd, "flip_h")
    fwd = apply_transform(fwd, "rotate_7")
    fwd = apply_transform(fwd, "flip_v")

    # Reverse: flip V, rotate -7, flip H, rotate -5
    rev = fwd.copy()
    rev = apply_transform(rev, "flip_v")
    rev = apply_transform(rev, "rotate_-7")
    rev = apply_transform(rev, "flip_h")
    rev = apply_transform(rev, "rotate_-5")

    # Detect with ORIGINAL markers
    print(f"\n  Detection on inverse-transformed image (original markers):")
    det_rev = detect_compound(rev, markers, TWIN_CONFIG)
    map_rev = disruption_map(rev, markers, TWIN_CONFIG)

    n = min(len(map_base), len(map_rev))
    intersection = int(np.sum(map_base[:n] & map_rev[:n]))
    union = int(np.sum(map_base[:n] | map_rev[:n]))
    jaccard = intersection / union if union > 0 else 0

    print(f"    Compound pass: {det_rev['marker_compound_pass']}/{det_rev['marker_total']}")
    print(f"    Rate ratio:    {det_rev['rate_ratio']:.1f}x")
    print(f"    Binom p:       {det_rev['binomial_pvalue']:.2e}")
    print(f"    Detected:      {'YES' if det_rev['detected_binom'] else 'NO'}")
    print(f"    Fingerprint:   Jaccard = {jaccard:.4f} vs intact ({'matchable' if jaccard > 0.3 else 'NOT matchable'})")

    # Pixel-level damage from the round trip
    pixel_diff = np.abs(gen0_px.astype(float) - rev.astype(float))
    print(f"\n  Pixel damage from rotation round-trip:")
    print(f"    Mean absolute diff:  {np.mean(pixel_diff):.2f}")
    print(f"    Max diff:            {np.max(pixel_diff):.0f}")
    print(f"    % pixels changed:    {np.mean(pixel_diff > 0)*100:.1f}%")
    print(f"    PSNR:                {10 * np.log10(255**2 / np.mean(pixel_diff**2)):.1f} dB")

    # =========================================================================
    # 90 DEGREE ROTATION (the lossless case)
    # =========================================================================
    print(f"\n\n{'='*90}")
    print("PART 5: 90\u00b0 ROTATION (no interpolation, pure remap)")
    print(f"{'='*90}")

    for angle in [90, 180, 270]:
        rot_px = apply_transform(gen0_px, f"rotate_{angle}")
        rot_markers = transform_positions(markers, f"rotate_{angle}", (SIZE, SIZE))

        if len(rot_markers) < 20:
            print(f"\n  {angle}\u00b0: Too few markers ({len(rot_markers)})")
            continue

        det = detect_compound(rot_px, rot_markers, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"\n  {angle}\u00b0 with corrected positions:"
              f" {det['marker_compound_pass']}/{det['marker_total']}"
              f" ratio={det['rate_ratio']:.1f}x"
              f" p={det['binomial_pvalue']:.2e}"
              f" {status}")

    # =========================================================================
    print(f"\n\n{'='*90}")
    print("SUMMARY")
    print(f"{'='*90}")
    print(f"""
  FLIPS:
    Pure coordinate remap. No interpolation. No value damage.
    With corrected positions: detection identical to baseline.
    Without corrected positions: detection fails (positions wrong).
    Search space: 4 flip states. Trivially enumerable.

  SMALL ROTATIONS (1-15 degrees):
    Interpolation required. Pixel values blended with neighbors.
    With corrected positions: check results above.
    Without corrected positions: detection fails (positions shifted).
    The key question: does the variance anomaly survive interpolation?

  THE FULL CHAIN (rotate 5, flip H, rotate 7, flip V):
    Two interpolation passes plus two coordinate remaps.
    Check results above.

  THE INVERSE (forward chain then exact reverse):
    Two MORE interpolation passes. Four total.
    Check results above.
    The round-trip introduces interpolation damage even if angles cancel.

  90-DEGREE ROTATIONS:
    No interpolation. Pure coordinate remap (like flips).
    With corrected positions: detection should be identical to baseline.
""")


if __name__ == "__main__":
    run_test()
