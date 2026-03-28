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
#
# =============================================================================
# ASSUMPTION ZERO
# =============================================================================
# This project pursues PROVENANCE SIGNAL DETECTION, not watermarking,
# not steganography, and not DRM.
#
# The distinction is load-bearing:
#   - Watermarking encodes a mark and detects the mark.
#     This scheme encodes a relationship and detects a distribution.
#   - Steganography hides a payload for a keyed receiver.
#     This scheme hides nothing. The signal is a statistical property
#     detectable by anyone with public knowledge of prime gaps.
#   - DRM enforces access control.
#     This scheme enforces nothing. It produces measurements.
#     Humans and courts decide what measurements mean.
#
# Assumption Zero: whether provenance and attribution matter enough to
# shift corpus-scale economics is an empirical question we cannot answer.
# The technical contribution — a detectable, format-agnostic, infrastructure-
# free provenance signal that AMPLIFIES under lossy compression — stands
# independent of whether that assumption is true.
#
# The scheme proves participation. It does not judge what participation means.
# =============================================================================

"""
JPEG → WebP: The CDN Hop
==========================
Jeremy Pickett — Axiomatic Fictions Series

One question: what survives the codec boundary?

JPEG Q95 with all layers embedded → WebP at various quality levels.
Measure every layer. Report what lives and what dies.
"""

import os
import sys
import io
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    _gen_synthetic_photo,
)
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
)
from dqt_prime import encode_prime_jpeg, detect_prime_dqt, extract_dqt_tables
from div2k_harness import extract_twin_measurements, compare_twin_distributions


TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="Twin prime-gap markers",
    min_prime=53, use_twins=True, use_rare_basket=True,
    use_magic=False, detection_prime_tolerance=2, n_markers=400,
)

MAGIC_CONFIG = MarkerConfig(
    name="magic",
    description="Douglas Rule sentinel",
    min_prime=53, use_magic=True, use_rare_basket=True,
    use_twins=False, magic_value=42, magic_tolerance=2,
    detection_prime_tolerance=2, n_markers=400,
)

COMPOUND_CONFIG = MarkerConfig(
    name="compound",
    description="Twin + magic + rare",
    min_prime=53, use_twins=True, use_magic=True, use_rare_basket=True,
    magic_value=42, magic_tolerance=2,
    detection_prime_tolerance=2, n_markers=400,
)

WEBP_QUALITIES = [95, 85, 80, 75, 60, 40, 20]


def run_jpeg_to_webp(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    source = _gen_synthetic_photo(512, 512, rng)

    print("=" * 80)
    print("JPEG Q95 \u2192 WebP: THE CDN HOP")
    print("=" * 80)

    # Step 1: Create prime JPEG at Q95 with twin markers
    prime_data, _ = encode_prime_jpeg(source, quality=95, min_prime=2, preserve_dc=True)
    prime_pixels = np.array(Image.open(io.BytesIO(prime_data)).convert("RGB"))

    # Embed twins
    twin_pixels, twin_markers = embed_compound(prime_pixels, TWIN_CONFIG, variable_offset=42)
    print(f"Embedded {len(twin_markers)} twin markers")

    # Embed magic (separate image for independent measurement)
    magic_pixels, magic_markers = embed_compound(prime_pixels, MAGIC_CONFIG, variable_offset=42)
    print(f"Embedded {len(magic_markers)} magic markers")

    # Embed compound
    comp_pixels, comp_markers = embed_compound(prime_pixels, COMPOUND_CONFIG, variable_offset=42)
    print(f"Embedded {len(comp_markers)} compound markers")

    # Re-encode as JPEG Q95 (generation 0)
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

    # Baselines: JPEG Q95 versions
    twin_jpeg = to_jpeg(twin_pixels)
    twin_jpeg_px = decode(twin_jpeg)

    magic_jpeg = to_jpeg(magic_pixels)
    magic_jpeg_px = decode(magic_jpeg)

    comp_jpeg = to_jpeg(comp_pixels)
    comp_jpeg_px = decode(comp_jpeg)

    # Gen0 relations for relational signal
    gen0_twins = extract_twin_measurements(twin_jpeg_px, twin_markers)

    print(f"\n\n{'='*80}")
    print("LAYER A — DQT Primality")
    print(f"{'='*80}")
    print(f"\n  JPEG Q95 (source): ", end="")
    # Re-encode with prime tables for DQT test
    prime_jpeg_data, _ = encode_prime_jpeg(twin_pixels, quality=95, min_prime=2, preserve_dc=True)
    dqt_jpeg = detect_prime_dqt(prime_jpeg_data)
    print(f"prime_rate={dqt_jpeg['overall_prime_rate']:.3f}  "
          f"{'DETECTED' if dqt_jpeg['detected'] else 'not detected'}")

    print(f"\n  WebP has no DQT segment. Layer A is definitionally absent in WebP.")
    print(f"  This is expected. Layer A is a JPEG container signal.")
    print(f"  The CDN hop from JPEG to WebP transitions from State B to State C.")

    # =========================================================================
    print(f"\n\n{'='*80}")
    print("LAYER B — Twin Markers (Primality Detection)")
    print(f"{'='*80}")

    print(f"\n  {'Format':>12s}  {'Quality':>7s}  {'M_pass':>7s}  {'M_rate':>7s}  "
          f"{'C_rate':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Status'}")
    print(f"  {'-'*80}")

    # JPEG baseline
    det = detect_compound(twin_jpeg_px, twin_markers, TWIN_CONFIG)
    print(f"  {'JPEG':>12s}  {'Q95':>7s}  {det['marker_compound_pass']:>4d}/{det['marker_total']:<3d}"
          f"  {det['marker_rate']:>7.4f}  {det['control_rate']:>7.4f}"
          f"  {det['rate_ratio']:>6.1f}  {det['binomial_pvalue']:>10.2e}"
          f"  {'DETECTED' if det['detected_binom'] else '\u2014'}")

    # WebP at each quality
    for wq in WEBP_QUALITIES:
        webp_data = to_webp(twin_pixels, q=wq)
        webp_px = decode(webp_data)
        det = detect_compound(webp_px, twin_markers, TWIN_CONFIG)
        detected = "DETECTED" if det["detected_binom"] else "\u2014"
        print(f"  {'WebP':>12s}  {'Q'+str(wq):>7s}  {det['marker_compound_pass']:>4d}/{det['marker_total']:<3d}"
              f"  {det['marker_rate']:>7.4f}  {det['control_rate']:>7.4f}"
              f"  {det['rate_ratio']:>6.1f}  {det['binomial_pvalue']:>10.2e}"
              f"  {detected}")

    # Component survival breakdown
    print(f"\n  Component survival (twin markers):")
    print(f"  {'Format':>12s}  {'Quality':>7s}  {'Primary':>12s}  {'Twin':>12s}  {'Compound':>12s}")
    print(f"  {'-'*60}")

    det = detect_compound(twin_jpeg_px, twin_markers, TWIN_CONFIG)
    mt = det['marker_total']
    print(f"  {'JPEG':>12s}  {'Q95':>7s}"
          f"  {det['marker_primary_pass']:>4d} ({det['marker_primary_pass']/mt*100:>5.1f}%)"
          f"  {det['marker_twin_pass']:>4d} ({det['marker_twin_pass']/mt*100:>5.1f}%)"
          f"  {det['marker_compound_pass']:>4d} ({det['marker_compound_pass']/mt*100:>5.1f}%)")

    for wq in WEBP_QUALITIES:
        webp_px = decode(to_webp(twin_pixels, q=wq))
        det = detect_compound(webp_px, twin_markers, TWIN_CONFIG)
        mt = det['marker_total']
        print(f"  {'WebP':>12s}  {'Q'+str(wq):>7s}"
              f"  {det['marker_primary_pass']:>4d} ({det['marker_primary_pass']/mt*100:>5.1f}%)"
              f"  {det['marker_twin_pass']:>4d} ({det['marker_twin_pass']/mt*100:>5.1f}%)"
              f"  {det['marker_compound_pass']:>4d} ({det['marker_compound_pass']/mt*100:>5.1f}%)")

    # =========================================================================
    print(f"\n\n{'='*80}")
    print("LAYER C — Douglas Rule (Magic Byte = 42)")
    print(f"{'='*80}")

    print(f"\n  {'Format':>12s}  {'Quality':>7s}  {'Magic Pass':>10s}  {'Magic Rate':>10s}  "
          f"{'Control':>10s}  {'Status'}")
    print(f"  {'-'*70}")

    det = detect_compound(magic_jpeg_px, magic_markers, MAGIC_CONFIG)
    mt = det['marker_total']
    print(f"  {'JPEG':>12s}  {'Q95':>7s}"
          f"  {det['marker_magic_pass']:>5d}/{mt:<3d}"
          f"  {det['marker_magic_pass']/mt*100:>9.1f}%"
          f"  {det['control_magic_pass']}/{det['control_total']}"
          f"  {'ALIVE' if det['marker_magic_pass'] > 0 else 'DEAD'}")

    for wq in WEBP_QUALITIES:
        webp_px = decode(to_webp(magic_pixels, q=wq))
        det = detect_compound(webp_px, magic_markers, MAGIC_CONFIG)
        mt = det['marker_total']
        status = "ALIVE" if det['marker_magic_pass'] > 0 else "DEAD"
        print(f"  {'WebP':>12s}  {'Q'+str(wq):>7s}"
              f"  {det['marker_magic_pass']:>5d}/{mt:<3d}"
              f"  {det['marker_magic_pass']/mt*100:>9.1f}%"
              f"  {det['control_magic_pass']}/{det['control_total']}"
              f"  {status}")

    # =========================================================================
    print(f"\n\n{'='*80}")
    print("RELATIONAL SIGNAL — The Granite Test Across Codec Boundary")
    print(f"{'='*80}")

    print(f"\n  {'Format':>12s}  {'Quality':>7s}  "
          f"{'r_corr':>7s}  {'d_corr':>7s}  {'s_corr':>7s}  "
          f"{'KS_r_p':>10s}  {'KS_d_p':>10s}  {'KS_s_p':>10s}  "
          f"{'VarRatio':>8s}  {'Signal'}")
    print(f"  {'-'*100}")

    # JPEG baseline
    curr = extract_twin_measurements(twin_jpeg_px, twin_markers)
    rel = compare_twin_distributions(gen0_twins, curr)
    signals = []
    if rel['ks_ratio_p'] < 0.01: signals.append("KS_r")
    if rel['ks_diff_p'] < 0.01: signals.append("KS_d")
    if rel['ks_slope_p'] < 0.01: signals.append("KS_s")
    sig_str = "+".join(signals) if signals else "\u2014"
    print(f"  {'JPEG':>12s}  {'Q95':>7s}"
          f"  {rel['ratio_corr']:>7.3f}  {rel['diff_corr']:>7.3f}  {rel['slope_corr']:>7.3f}"
          f"  {rel['ks_ratio_p']:>10.2e}  {rel['ks_diff_p']:>10.2e}  {rel['ks_slope_p']:>10.2e}"
          f"  {rel['variance_ratio']:>8.3f}  {sig_str}")

    # WebP at each quality
    for wq in WEBP_QUALITIES:
        webp_px = decode(to_webp(twin_pixels, q=wq))
        curr = extract_twin_measurements(webp_px, twin_markers)
        rel = compare_twin_distributions(gen0_twins, curr)
        signals = []
        if rel['ks_ratio_p'] < 0.01: signals.append("KS_r")
        if rel['ks_diff_p'] < 0.01: signals.append("KS_d")
        if rel['ks_slope_p'] < 0.01: signals.append("KS_s")
        sig_str = "+".join(signals) if signals else "\u2014"
        print(f"  {'WebP':>12s}  {'Q'+str(wq):>7s}"
              f"  {rel['ratio_corr']:>7.3f}  {rel['diff_corr']:>7.3f}  {rel['slope_corr']:>7.3f}"
              f"  {rel['ks_ratio_p']:>10.2e}  {rel['ks_diff_p']:>10.2e}  {rel['ks_slope_p']:>10.2e}"
              f"  {rel['variance_ratio']:>8.3f}  {sig_str}")

    # =========================================================================
    # Also test: JPEG Q95 → WebP → back to JPEG (the full roundtrip)
    print(f"\n\n{'='*80}")
    print("ROUNDTRIP: JPEG Q95 \u2192 WebP Q80 \u2192 JPEG Q85 (CDN \u2192 scraper)")
    print(f"{'='*80}")

    webp_intermediate = to_webp(twin_pixels, q=80)
    webp_px = decode(webp_intermediate)
    jpeg_final = to_jpeg(webp_px, q=85)
    jpeg_final_px = decode(jpeg_final)

    print(f"\n  Twin marker detection:")
    det = detect_compound(jpeg_final_px, twin_markers, TWIN_CONFIG)
    mt = det['marker_total']
    print(f"    Pass: {det['marker_compound_pass']}/{mt}"
          f"  Rate: {det['marker_rate']:.4f}"
          f"  Control: {det['control_rate']:.4f}"
          f"  Ratio: {det['rate_ratio']:.1f}"
          f"  p={det['binomial_pvalue']:.2e}"
          f"  {'DETECTED' if det['detected_binom'] else 'not detected'}")

    print(f"\n  Relational signal:")
    curr = extract_twin_measurements(jpeg_final_px, twin_markers)
    rel = compare_twin_distributions(gen0_twins, curr)
    print(f"    Ratio corr:  {rel['ratio_corr']:.4f}")
    print(f"    Diff corr:   {rel['diff_corr']:.4f}")
    print(f"    Slope corr:  {rel['slope_corr']:.4f}")
    print(f"    KS ratio p:  {rel['ks_ratio_p']:.4e}")
    print(f"    KS diff p:   {rel['ks_diff_p']:.4e}")
    print(f"    KS slope p:  {rel['ks_slope_p']:.4e}")
    print(f"    Var ratio:   {rel['variance_ratio']:.3f}")

    signals = []
    if rel['ks_ratio_p'] < 0.01: signals.append("KS_ratio")
    if rel['ks_diff_p'] < 0.01: signals.append("KS_diff")
    if rel['ks_slope_p'] < 0.01: signals.append("KS_slope")
    if det['detected_binom']: signals.append("twins")
    print(f"    Signals: {', '.join(signals) if signals else 'NONE'}")

    # =========================================================================
    print(f"\n\n{'='*80}")
    print("PIXEL-LEVEL: What WebP Does vs What JPEG Does")
    print(f"{'='*80}")

    for wq in [95, 80, 60, 40]:
        webp_px = decode(to_webp(twin_pixels, q=wq))
        jpeg_eq = decode(to_jpeg(twin_pixels, q=wq))

        diff_webp = webp_px.astype(float) - twin_pixels.astype(float)
        diff_jpeg = jpeg_eq.astype(float) - twin_pixels.astype(float)

        print(f"\n  Quality {wq}:")
        print(f"    WebP: mean_abs={np.mean(np.abs(diff_webp)):.2f}"
              f"  std={np.std(diff_webp):.2f}"
              f"  max={np.max(np.abs(diff_webp)):.0f}")
        print(f"    JPEG: mean_abs={np.mean(np.abs(diff_jpeg)):.2f}"
              f"  std={np.std(diff_jpeg):.2f}"
              f"  max={np.max(np.abs(diff_jpeg)):.0f}")

    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"""
  Layer A (DQT):       DEAD in WebP. Expected. JPEG container signal only.
  Layer C (Douglas):   Check results above.
  Layer B (Twins):     Check results above.
  Relational signal:   Check results above.

  The question: does the perturbation survive the codec boundary?
  VP8 uses 4x4 integer DCT. JPEG uses 8x8 floating-point DCT.
  Different block sizes. Different quantization grids. Different transform.
  Same principle: block-based coding that penalizes local complexity.
""")


if __name__ == "__main__":
    run_jpeg_to_webp("pgps_results/jpeg_to_webp")
