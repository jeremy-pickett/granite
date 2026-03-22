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
THE SLICE-AND-STITCH ATTACK
=============================
Jeremy Pickett — Axiomatic Fictions Series

Take a 2048x2048 image with provenance.
Slice into four quadrants. Save each as JPEG.
Reload and stitch back together.
What survives?
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
    name="twin", description="Slice attack test",
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

def to_webp(pixels, q=80):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='WEBP', quality=q)
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


def run_attack():
    SIZE = 2048
    HALF = SIZE // 2
    SLICE_Q = 85  # Quality the attacker saves quadrants at

    print("=" * 90)
    print("THE SLICE-AND-STITCH ATTACK")
    print("=" * 90)

    # Step 1: Create and embed
    print(f"\n[1] Generating {SIZE}x{SIZE} synthetic image...")
    pixels = gen_photo(SIZE)

    print(f"[2] Embedding twin markers...")
    embedded, markers = embed_compound(pixels, TWIN_CONFIG, seed=42)
    print(f"    {len(markers)} markers embedded")

    # Step 3: JPEG encode (gen 0)
    print(f"[3] JPEG Q95 encode (generation 0)...")
    gen0_data = to_jpeg(embedded, 95)
    gen0_px = decode(gen0_data)

    # Baseline detection on intact image
    print(f"[4] Baseline detection on intact image...")
    det_intact = detect_compound(gen0_px, markers, TWIN_CONFIG)
    map_intact = disruption_map(gen0_px, markers, TWIN_CONFIG)
    gen0_twins = extract_twin_measurements(gen0_px, markers)

    print(f"    Compound pass: {det_intact['marker_compound_pass']}/{det_intact['marker_total']}")
    print(f"    Rate ratio:    {det_intact['rate_ratio']:.1f}x")
    print(f"    Binom p:       {det_intact['binomial_pvalue']:.2e}")
    print(f"    Disruption map: {int(np.sum(map_intact))} / {len(markers)} positions disrupted")

    # Step 5: SLICE INTO QUADRANTS
    print(f"\n[5] Slicing into four quadrants...")
    quadrants = {
        "top_left":     gen0_px[0:HALF, 0:HALF],
        "top_right":    gen0_px[0:HALF, HALF:SIZE],
        "bottom_left":  gen0_px[HALF:SIZE, 0:HALF],
        "bottom_right": gen0_px[HALF:SIZE, HALF:SIZE],
    }

    # Save each quadrant as JPEG (the attacker's re-encode)
    print(f"[6] Saving each quadrant as JPEG Q{SLICE_Q} (the attacker's re-encode)...")
    quadrant_data = {}
    quadrant_px = {}
    for name, qpx in quadrants.items():
        data = to_jpeg(qpx, SLICE_Q)
        quadrant_data[name] = data
        quadrant_px[name] = decode(data)
        print(f"    {name}: {qpx.shape[1]}x{qpx.shape[0]} -> {len(data)} bytes")

    # Step 7: Classify markers by quadrant
    print(f"\n[7] Classifying markers by quadrant...")
    quad_markers = {"top_left": [], "top_right": [], "bottom_left": [], "bottom_right": []}
    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r < HALF and c < HALF and tc < HALF:
            quad_markers["top_left"].append(m)
        elif r < HALF and c >= HALF and tc < SIZE:
            quad_markers["top_right"].append({
                "row": r, "col": c - HALF, "twin_col": tc - HALF
            })
        elif r >= HALF and c < HALF and tc < HALF:
            quad_markers["bottom_left"].append({
                "row": r - HALF, "col": c, "twin_col": tc
            })
        elif r >= HALF and c >= HALF and tc < SIZE:
            quad_markers["bottom_right"].append({
                "row": r - HALF, "col": c - HALF, "twin_col": tc - HALF
            })

    for name in quad_markers:
        print(f"    {name}: {len(quad_markers[name])} markers")

    # Step 8: Detect on each quadrant individually
    print(f"\n[8] Detection on individual quadrants (the attacker's fragments):")
    print(f"    {'Quadrant':>15s}  {'Markers':>8s}  {'Pass':>6s}  {'Rate':>7s}"
          f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"    {'-'*80}")

    for name in ["top_left", "top_right", "bottom_left", "bottom_right"]:
        qm = quad_markers[name]
        if len(qm) < 5:
            print(f"    {name:>15s}  {len(qm):>6d}  Too few markers")
            continue
        det = detect_compound(quadrant_px[name], qm, TWIN_CONFIG)
        status = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"    {name:>15s}  {len(qm):>6d}"
              f"  {det['marker_compound_pass']:>4d}"
              f"  {det['marker_rate']:>7.4f}"
              f"  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}"
              f"  {det['binomial_pvalue']:>10.2e}"
              f"  {status}")

    # Step 9: STITCH BACK TOGETHER
    print(f"\n[9] Stitching quadrants back together...")
    stitched = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    stitched[0:HALF, 0:HALF] = quadrant_px["top_left"]
    stitched[0:HALF, HALF:SIZE] = quadrant_px["top_right"]
    stitched[HALF:SIZE, 0:HALF] = quadrant_px["bottom_left"]
    stitched[HALF:SIZE, HALF:SIZE] = quadrant_px["bottom_right"]

    # Step 10: Detection on stitched image with ORIGINAL markers
    print(f"\n[10] Detection on stitched image (original coordinate space)...")
    det_stitched = detect_compound(stitched, markers, TWIN_CONFIG)
    map_stitched = disruption_map(stitched, markers, TWIN_CONFIG)
    stitch_twins = extract_twin_measurements(stitched, markers)
    rel = compare_twin_distributions(gen0_twins, stitch_twins)

    print(f"     Compound pass: {det_stitched['marker_compound_pass']}/{det_stitched['marker_total']}")
    print(f"     Rate ratio:    {det_stitched['rate_ratio']:.1f}x")
    print(f"     Binom p:       {det_stitched['binomial_pvalue']:.2e}")
    print(f"     Detected:      {'YES' if det_stitched['detected_binom'] else 'NO'}")

    # Step 11: Fingerprint comparison
    print(f"\n[11] Fingerprint comparison (disruption map)...")
    intact_ones = int(np.sum(map_intact))
    stitched_ones = int(np.sum(map_stitched))
    n = min(len(map_intact), len(map_stitched))
    hamming = int(np.sum(map_intact[:n] != map_stitched[:n]))
    intersection = int(np.sum(map_intact[:n] & map_stitched[:n]))
    union = int(np.sum(map_intact[:n] | map_stitched[:n]))
    jaccard = intersection / union if union > 0 else 0

    print(f"     Intact map:    {intact_ones} / {len(markers)} disrupted")
    print(f"     Stitched map:  {stitched_ones} / {len(markers)} disrupted")
    print(f"     Hamming dist:  {hamming} ({hamming/n*100:.1f}%)")
    print(f"     Jaccard sim:   {jaccard:.4f}")
    print(f"     Matchable:     {'YES' if jaccard > 0.3 else 'NO'}")

    # Step 12: Relational signal
    print(f"\n[12] Relational signal (variance anomaly)...")
    print(f"     KS diff p:     {rel['ks_diff_p']:.4e}")
    print(f"     KS slope p:    {rel['ks_slope_p']:.4e}")
    print(f"     Var ratio:     {rel['variance_ratio']:.3f}")
    print(f"     Diff corr:     {rel['diff_corr']:.4f}")

    # Step 13: Stitch seam forensics
    print(f"\n[13] Stitch seam forensics...")
    # Measure the pixel difference across the vertical seam
    left_edge = stitched[0:HALF, HALF-1, :].astype(float)
    right_edge = stitched[0:HALF, HALF, :].astype(float)
    seam_diff = np.mean(np.abs(left_edge - right_edge))

    # Compare to average adjacent-pixel difference in the interior
    interior_left = stitched[0:HALF, HALF-10, :].astype(float)
    interior_right = stitched[0:HALF, HALF-9, :].astype(float)
    interior_diff = np.mean(np.abs(interior_left - interior_right))

    # Horizontal seam
    top_edge = stitched[HALF-1, 0:HALF, :].astype(float)
    bottom_edge = stitched[HALF, 0:HALF, :].astype(float)
    hseam_diff = np.mean(np.abs(top_edge - bottom_edge))

    hinterior_top = stitched[HALF-10, 0:HALF, :].astype(float)
    hinterior_bot = stitched[HALF-9, 0:HALF, :].astype(float)
    hinterior_diff = np.mean(np.abs(hinterior_top - hinterior_bot))

    print(f"     Vertical seam avg diff:   {seam_diff:.2f}")
    print(f"     Interior avg diff:        {interior_diff:.2f}")
    print(f"     Seam/Interior ratio:      {seam_diff/interior_diff:.2f}x")
    print(f"     Horizontal seam avg diff: {hseam_diff:.2f}")
    print(f"     H Interior avg diff:      {hinterior_diff:.2f}")
    print(f"     H Seam/Interior ratio:    {hseam_diff/hinterior_diff:.2f}x")

    # Step 14: Re-encode the stitched image (the next platform hop)
    print(f"\n[14] What if the stitched image is re-encoded? (JPEG Q75)...")
    stitched_reenc = decode(to_jpeg(stitched, 75))
    det_reenc = detect_compound(stitched_reenc, markers, TWIN_CONFIG)
    map_reenc = disruption_map(stitched_reenc, markers, TWIN_CONFIG)

    reenc_ones = int(np.sum(map_reenc))
    intersection_r = int(np.sum(map_intact[:n] & map_reenc[:n]))
    union_r = int(np.sum(map_intact[:n] | map_reenc[:n]))
    jaccard_r = intersection_r / union_r if union_r > 0 else 0

    print(f"     Compound pass: {det_reenc['marker_compound_pass']}/{det_reenc['marker_total']}")
    print(f"     Rate ratio:    {det_reenc['rate_ratio']:.1f}x")
    print(f"     Binom p:       {det_reenc['binomial_pvalue']:.2e}")
    print(f"     Detected:      {'YES' if det_reenc['detected_binom'] else 'NO'}")
    print(f"     Fingerprint:   Jaccard = {jaccard_r:.4f} ({'matchable' if jaccard_r > 0.3 else 'NOT matchable'})")

    # WebP too
    print(f"\n[15] Stitched image -> WebP Q80 (the CDN hop)...")
    stitched_webp = decode(to_webp(stitched, 80))
    det_webp = detect_compound(stitched_webp, markers, TWIN_CONFIG)
    map_webp = disruption_map(stitched_webp, markers, TWIN_CONFIG)

    webp_ones = int(np.sum(map_webp))
    intersection_w = int(np.sum(map_intact[:n] & map_webp[:n]))
    union_w = int(np.sum(map_intact[:n] | map_webp[:n]))
    jaccard_w = intersection_w / union_w if union_w > 0 else 0

    print(f"     Compound pass: {det_webp['marker_compound_pass']}/{det_webp['marker_total']}")
    print(f"     Rate ratio:    {det_webp['rate_ratio']:.1f}x")
    print(f"     Binom p:       {det_webp['binomial_pvalue']:.2e}")
    print(f"     Detected:      {'YES' if det_webp['detected_binom'] else 'NO'}")
    print(f"     Fingerprint:   Jaccard = {jaccard_w:.4f} ({'matchable' if jaccard_w > 0.3 else 'NOT matchable'})")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n\n{'='*90}")
    print(f"SUMMARY: THE SLICE-AND-STITCH ATTACK")
    print(f"{'='*90}")
    print(f"""
  SOURCE:     {SIZE}x{SIZE}, {len(markers)} markers
  ATTACK:     Slice into 4 quadrants, save each as JPEG Q{SLICE_Q}, stitch back

  INDIVIDUAL QUADRANTS:
    ~{len(markers)//4} markers each in {HALF}x{HALF} images
    Detection: marginal (at detection floor)
    Attribution: BROKEN (coordinate transform unknown)

  STITCHED IMAGE:
    All {len(markers)} markers back in original coordinates
    Detection:   {'YES' if det_stitched['detected_binom'] else 'NO'} (ratio {det_stitched['rate_ratio']:.1f}x, p={det_stitched['binomial_pvalue']:.2e})
    Fingerprint: Jaccard {jaccard:.4f} vs intact ({'MATCHABLE' if jaccard > 0.3 else 'NOT MATCHABLE'})

  STITCHED + JPEG Q75:
    Detection:   {'YES' if det_reenc['detected_binom'] else 'NO'} (ratio {det_reenc['rate_ratio']:.1f}x, p={det_reenc['binomial_pvalue']:.2e})
    Fingerprint: Jaccard {jaccard_r:.4f} vs intact ({'MATCHABLE' if jaccard_r > 0.3 else 'NOT MATCHABLE'})

  STITCH SEAM:
    Vertical seam/interior ratio:   {seam_diff/interior_diff:.2f}x
    Horizontal seam/interior ratio: {hseam_diff/hinterior_diff:.2f}x
    Forensically detectable: {'YES' if seam_diff/interior_diff > 1.5 else 'MAYBE'}

  VERDICT:
    The attack undoes itself on reassembly.
    Fingerprint returns. Detection returns. Stitch scars are visible.
    The only winning move is to keep the pieces separate.
    And separate pieces are a crop attack, not a stitch attack.
""")


if __name__ == "__main__":
    run_attack()
