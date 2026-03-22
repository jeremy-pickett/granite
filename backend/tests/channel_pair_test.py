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
RGB Channel Pair Independence Test
====================================
Is the free lunch real?

Embed twin markers in (R,G) pair only.
Measure detection in all three pairs: (R,G), (R,B), (G,B).
If they're independent, (R,B) and (G,B) should show NO signal.
Then embed in all three pairs. Do they interfere?
"""

import os, sys, io
import numpy as np
from PIL import Image
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import build_prime_lookup, sieve_of_eratosthenes
from compound_markers import MarkerConfig, embed_compound, detect_compound


def gen_photo(size, seed=42):
    rng = np.random.RandomState(seed)
    h = w = size
    img = np.zeros((h, w, 3), dtype=np.float64)
    for _ in range(20):
        cy, cx = rng.randint(0, h), rng.randint(0, w)
        sy, sx = rng.uniform(size*0.04, size*0.3), rng.uniform(size*0.04, size*0.3)
        color = rng.uniform(50, 220, 3)
        yy, xx = np.ogrid[:h, :w]
        mask = np.exp(-0.5*(((yy-cy)/sy)**2 + ((xx-cx)/sx)**2))
        for c in range(3):
            img[:,:,c] += mask * color[c]
    return np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)


def to_jpeg(pixels, q=95):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format='JPEG', quality=q)
    return buf.getvalue()

def decode(data):
    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


def measure_channel_pair(pixels, markers, ch_a, ch_b, config):
    """Manually measure prime-gap enrichment for a specific channel pair."""
    h, w, _ = pixels.shape
    primes = build_prime_lookup(8, min_prime=config.min_prime)
    tol = config.detection_prime_tolerance
    max_val = 255

    fuzzy = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for off in range(-tol, tol + 1):
            check = d + off
            if 0 <= check <= max_val and primes[check]:
                fuzzy[d] = True
                break

    # Marker positions
    m_pass = 0
    m_total = 0
    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc >= w:
            continue
        m_total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]:
            m_pass += 1

    # Control positions (offset grid)
    from pgps_detector import sample_positions_grid
    marker_set = set()
    for m in markers:
        marker_set.add((m["row"], m["col"]))
        marker_set.add((m["row"], m.get("twin_col", m["col"]+1)))

    all_pos = sample_positions_grid(h, w, 8)
    c_pass = 0
    c_total = 0
    for pos in all_pos:
        r, c = int(pos[0]) + 3, int(pos[1]) + 3
        tc = c + 1
        if (r, c) in marker_set or (r, tc) in marker_set:
            continue
        if r >= h or c >= w or tc >= w:
            continue
        c_total += 1
        d1 = abs(int(pixels[r, c, ch_a]) - int(pixels[r, c, ch_b]))
        d2 = abs(int(pixels[r, tc, ch_a]) - int(pixels[r, tc, ch_b]))
        if fuzzy[min(d1, max_val)] and fuzzy[min(d2, max_val)]:
            c_pass += 1

    m_rate = m_pass / m_total if m_total > 0 else 0
    c_rate = c_pass / c_total if c_total > 0 else 0
    ratio = m_rate / c_rate if c_rate > 0 else float('inf')

    if m_total > 0 and c_total > 0:
        from scipy.stats import binomtest
        result = binomtest(m_pass, m_total, c_rate, alternative='greater')
        p = result.pvalue
    else:
        p = 1.0

    return {
        "ch_pair": f"({ch_a},{ch_b})",
        "m_pass": m_pass, "m_total": m_total, "m_rate": m_rate,
        "c_pass": c_pass, "c_total": c_total, "c_rate": c_rate,
        "ratio": ratio, "p": p,
    }


def embed_specific_pair(pixels, markers, ch_a, ch_b, config, seed=42):
    """
    Embed prime-gap twin markers using a specific channel pair.
    Modifies pixels in-place at marker positions so |ch_a - ch_b| is prime.
    """
    h, w, _ = pixels.shape
    result = pixels.copy()
    primes_list = sorted([p for p in sieve_of_eratosthenes(255) if p >= config.min_prime])
    rng = np.random.RandomState(seed)

    embedded = 0
    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc >= w:
            continue

        for pos_c in [c, tc]:
            va = int(result[r, pos_c, ch_a])
            vb = int(result[r, pos_c, ch_b])
            target_prime = rng.choice(primes_list)

            # Adjust ch_b to create target distance
            if va >= target_prime:
                new_vb = va - target_prime
            else:
                new_vb = va + target_prime

            if 0 <= new_vb <= 255:
                result[r, pos_c, ch_b] = new_vb
            elif 0 <= (va + target_prime) <= 255:
                result[r, pos_c, ch_b] = va + target_prime
            elif 0 <= (va - target_prime) <= 255:
                result[r, pos_c, ch_b] = va - target_prime

        embedded += 1

    return result, embedded


SIZE = 1024
PAIR_NAMES = {(0,1): "R-G", (0,2): "R-B", (1,2): "G-B"}

config = MarkerConfig(
    name="twin", description="Channel pair test",
    min_prime=53, use_twins=True, use_rare_basket=True,
    use_magic=False, detection_prime_tolerance=2, n_markers=500,
)

print("=" * 90)
print("RGB CHANNEL PAIR INDEPENDENCE TEST")
print("=" * 90)

pixels = gen_photo(SIZE)
_, markers = embed_compound(pixels, config, variable_offset=42)
print(f"\n{SIZE}x{SIZE} image, {len(markers)} marker positions")

# =========================================================================
print(f"\n\n{'='*90}")
print("TEST 1: Embed in R-G only. Measure all three pairs.")
print("If independent, R-B and G-B should show NO enrichment.")
print(f"{'='*90}")

# Standard embed uses (0,1) = R-G
embedded_rg, _ = embed_compound(pixels, config, variable_offset=42)
jpeg_rg = decode(to_jpeg(embedded_rg, 95))

print(f"\n  {'Pair':>8s}  {'M_pass':>8s}  {'M_rate':>8s}  {'C_rate':>8s}  "
      f"{'Ratio':>8s}  {'p-value':>12s}  {'Signal?'}")
print(f"  {'-'*70}")

for pair in [(0,1), (0,2), (1,2)]:
    r = measure_channel_pair(jpeg_rg, markers, pair[0], pair[1], config)
    sig = "YES" if r["p"] < 0.01 else "no"
    print(f"  {PAIR_NAMES[pair]:>8s}  {r['m_pass']:>4d}/{r['m_total']:<3d}"
          f"  {r['m_rate']:>8.4f}  {r['c_rate']:>8.4f}"
          f"  {r['ratio']:>8.2f}  {r['p']:>12.2e}  {sig}")

# =========================================================================
print(f"\n\n{'='*90}")
print("TEST 2: Embed in all three pairs independently. Measure each.")
print(f"{'='*90}")

# Embed R-G
img_all = pixels.copy()
img_all, n1 = embed_specific_pair(img_all, markers, 0, 1, config, seed=42)
img_all, n2 = embed_specific_pair(img_all, markers, 0, 2, config, seed=43)
img_all, n3 = embed_specific_pair(img_all, markers, 1, 2, config, seed=44)

print(f"  Embedded: R-G={n1}, R-B={n2}, G-B={n3}")

jpeg_all = decode(to_jpeg(img_all, 95))

print(f"\n  After JPEG Q95:")
print(f"  {'Pair':>8s}  {'M_pass':>8s}  {'M_rate':>8s}  {'C_rate':>8s}  "
      f"{'Ratio':>8s}  {'p-value':>12s}  {'Signal?'}")
print(f"  {'-'*70}")

for pair in [(0,1), (0,2), (1,2)]:
    r = measure_channel_pair(jpeg_all, markers, pair[0], pair[1], config)
    sig = "YES" if r["p"] < 0.01 else "no"
    print(f"  {PAIR_NAMES[pair]:>8s}  {r['m_pass']:>4d}/{r['m_total']:<3d}"
          f"  {r['m_rate']:>8.4f}  {r['c_rate']:>8.4f}"
          f"  {r['ratio']:>8.2f}  {r['p']:>12.2e}  {sig}")

# =========================================================================
print(f"\n\n{'='*90}")
print("TEST 3: Do the pairs INTERFERE? Embed R-G, then embed R-B.")
print("Does R-B embedding damage R-G signal?")
print(f"{'='*90}")

# First embed R-G alone
img_rg_only = pixels.copy()
img_rg_only, _ = embed_specific_pair(img_rg_only, markers, 0, 1, config, seed=42)
jpeg_rg_only = decode(to_jpeg(img_rg_only, 95))
r_rg_before = measure_channel_pair(jpeg_rg_only, markers, 0, 1, config)

# Now embed R-G then R-B (R-B changes B channel, might affect R-G? No - R-G only uses R and G)
img_rg_then_rb = pixels.copy()
img_rg_then_rb, _ = embed_specific_pair(img_rg_then_rb, markers, 0, 1, config, seed=42)
img_rg_then_rb, _ = embed_specific_pair(img_rg_then_rb, markers, 0, 2, config, seed=43)
jpeg_rg_then_rb = decode(to_jpeg(img_rg_then_rb, 95))
r_rg_after = measure_channel_pair(jpeg_rg_then_rb, markers, 0, 1, config)

print(f"\n  R-G signal BEFORE R-B embedding:")
print(f"    Rate: {r_rg_before['m_rate']:.4f}  Ratio: {r_rg_before['ratio']:.2f}  p: {r_rg_before['p']:.2e}")

print(f"\n  R-G signal AFTER R-B embedding:")
print(f"    Rate: {r_rg_after['m_rate']:.4f}  Ratio: {r_rg_after['ratio']:.2f}  p: {r_rg_after['p']:.2e}")

# But wait - JPEG converts to YCbCr. R, G, B are mixed.
# Does the YCbCr conversion create cross-talk?
print(f"\n  Ratio change: {r_rg_after['ratio'] / r_rg_before['ratio']:.3f}x")
if abs(r_rg_after['ratio'] - r_rg_before['ratio']) / r_rg_before['ratio'] < 0.1:
    print(f"  VERDICT: Less than 10% change. Channels are INDEPENDENT through JPEG.")
elif r_rg_after['ratio'] < r_rg_before['ratio'] * 0.5:
    print(f"  VERDICT: Significant degradation. YCbCr conversion creates CROSS-TALK.")
    print(f"  The free lunch has a cost.")
else:
    print(f"  VERDICT: Moderate interaction. Partial independence.")

# =========================================================================
print(f"\n\n{'='*90}")
print("TEST 4: Cascade survival per channel pair")
print(f"{'='*90}")

# Embed all three pairs
img_cascade = pixels.copy()
img_cascade, _ = embed_specific_pair(img_cascade, markers, 0, 1, config, seed=42)
img_cascade, _ = embed_specific_pair(img_cascade, markers, 0, 2, config, seed=43)
img_cascade, _ = embed_specific_pair(img_cascade, markers, 1, 2, config, seed=44)

qualities = [95, 85, 75, 60, 40]
current = img_cascade.copy()

print(f"\n  {'Q':>5s}", end="")
for pair in [(0,1), (0,2), (1,2)]:
    print(f"  {'':>4s}{PAIR_NAMES[pair]:>4s} ratio  {PAIR_NAMES[pair]:>4s} p-val", end="")
print()
print(f"  {'-'*75}")

for q in qualities:
    jpeg_data = to_jpeg(current, q)
    test_px = decode(jpeg_data)

    print(f"  Q{q:>3d}", end="")
    for pair in [(0,1), (0,2), (1,2)]:
        r = measure_channel_pair(test_px, markers, pair[0], pair[1], config)
        sig = "*" if r["p"] < 0.01 else " "
        print(f"  {r['ratio']:>10.2f}  {r['p']:>10.2e}{sig}", end="")
    print()

    current = test_px

# =========================================================================
print(f"\n\n{'='*90}")
print("SUMMARY")
print(f"{'='*90}")
print(f"""
  Question 1: Does embedding in R-G leak into R-B or G-B?
  Question 2: Does embedding all three pairs produce three independent signals?
  Question 3: Does JPEG's YCbCr conversion create cross-talk between pairs?
  Question 4: Do all three pairs survive the compression cascade?

  If all four answers are favorable: three independent channels.
  If cross-talk exists: partially independent channels with reduced capacity.
  If only one pair survives: no free lunch. Back to single-channel.

  The data is above. Read it honestly.
""")
