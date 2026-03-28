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
# Author:  Jeremy Pickett <jeremy@signaldelta.com>
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
Relational Signal Analysis — The Slope Hypothesis
===================================================
Jeremy Pickett — Axiomatic Fictions Series

The absolute values move under JPEG. Does the RELATIONSHIP survive?

Three relational measurements at twin marker positions:
  1. RATIO:      d1/d2 between twin distances (scale-invariant)
  2. DIFFERENCE:  d1-d2 between twin distances (shift-invariant)
  3. SLOPE:      channel value gradient across the twin pair

Hypothesis: DCT quantization within an 8x8 block applies correlated
error. Two adjacent pixels shift together. The ratio between their
prime-gap distances may be a more robust signal than the primality
of either distance alone.

If true, this changes the detection question from "are these distances
prime?" to "does this pair of distances have a relationship consistent
with having BEEN prime before compression?"
"""

import os
import sys
import io
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, _gen_synthetic_photo,
)
from compound_markers import (
    MarkerConfig, embed_compound, build_rare_basket,
)
from dqt_prime import encode_prime_jpeg


TWIN_CONFIG = MarkerConfig(
    name="twin",
    description="Twin prime-gap markers for relational analysis",
    min_prime=53, use_twins=True, use_rare_basket=True,
    use_magic=False,
    detection_prime_tolerance=2, n_markers=400,
)


def extract_twin_relations(pixels: np.ndarray, markers: list,
                            channel_pair: tuple = (0, 1)) -> dict:
    """
    Extract relational measurements at twin marker positions and
    at control (non-marker) positions.

    At each twin position (r, c) and (r, c+1):
      d1 = |R-G| at (r, c)       — primary distance
      d2 = |R-G| at (r, c+1)     — twin distance
      ratio = d1 / d2
      diff = d1 - d2
      slope_R = R(r,c+1) - R(r,c)  — red channel gradient
      slope_G = G(r,c+1) - G(r,c)  — green channel gradient
      slope_d = d2 - d1             — distance gradient
    """
    h, w, _ = pixels.shape
    ch_a, ch_b = channel_pair

    # Marker positions
    marker_set = set()
    marker_data = []
    for m in markers:
        r, c = m["row"], m["col"]
        tc = m.get("twin_col", c + 1)
        if r >= h or c >= w or tc >= w:
            continue
        marker_set.add((r, c))
        marker_set.add((r, tc))

        va_1 = int(pixels[r, c, ch_a])
        vb_1 = int(pixels[r, c, ch_b])
        va_2 = int(pixels[r, tc, ch_a])
        vb_2 = int(pixels[r, tc, ch_b])

        d1 = abs(va_1 - vb_1)
        d2 = abs(va_2 - vb_2)

        marker_data.append({
            "row": r, "col": c, "twin_col": tc,
            "d1": d1, "d2": d2,
            "ratio": d1 / d2 if d2 > 0 else float('inf'),
            "diff": d1 - d2,
            "abs_diff": abs(d1 - d2),
            "slope_a": va_2 - va_1,  # channel A gradient
            "slope_b": vb_2 - vb_1,  # channel B gradient
            "slope_d": d2 - d1,      # distance gradient
            "va_1": va_1, "vb_1": vb_1,
            "va_2": va_2, "vb_2": vb_2,
        })

    # Control positions: non-marker grid positions with same twin structure
    all_positions = sample_positions_grid(h, w, 8)
    control_data = []
    for pos in all_positions:
        r, c = int(pos[0]), int(pos[1])
        # Offset into block center like the embedder does
        r = min(r + 3, h - 1)
        c = min(c + 3, w - 2)
        tc = c + 1

        if (r, c) in marker_set or (r, tc) in marker_set:
            continue
        if r >= h or tc >= w:
            continue

        va_1 = int(pixels[r, c, ch_a])
        vb_1 = int(pixels[r, c, ch_b])
        va_2 = int(pixels[r, tc, ch_a])
        vb_2 = int(pixels[r, tc, ch_b])

        d1 = abs(va_1 - vb_1)
        d2 = abs(va_2 - vb_2)

        control_data.append({
            "d1": d1, "d2": d2,
            "ratio": d1 / d2 if d2 > 0 else float('inf'),
            "diff": d1 - d2,
            "abs_diff": abs(d1 - d2),
            "slope_a": va_2 - va_1,
            "slope_b": vb_2 - vb_1,
            "slope_d": d2 - d1,
        })

    return {"marker": marker_data, "control": control_data}


def compare_relations(gen0_relations: dict, current_relations: dict,
                       label: str = "") -> dict:
    """
    Compare relational measurements between generation 0 (embedded)
    and current generation (after compression).

    The key question: how well are the ORIGINAL relationships preserved?
    """
    gen0_markers = gen0_relations["marker"]
    curr_markers = current_relations["marker"]
    curr_controls = current_relations["control"]

    n = min(len(gen0_markers), len(curr_markers))
    if n == 0:
        return {"error": "no markers"}

    # Pair up gen0 and current markers (same positions)
    # Compute preservation metrics
    ratio_preserved = []      # |current_ratio - gen0_ratio| / gen0_ratio
    diff_preserved = []       # |current_diff - gen0_diff|
    slope_a_preserved = []    # |current_slope_a - gen0_slope_a|
    slope_b_preserved = []
    slope_d_preserved = []

    # Raw values for distribution comparison
    gen0_ratios = []
    curr_marker_ratios = []
    curr_control_ratios = []
    gen0_diffs = []
    curr_marker_diffs = []
    curr_control_diffs = []
    gen0_slopes_d = []
    curr_marker_slopes_d = []
    curr_control_slopes_d = []

    for i in range(n):
        g = gen0_markers[i]
        c = curr_markers[i]

        # Ratio preservation
        if g["ratio"] != float('inf') and c["ratio"] != float('inf'):
            gen0_ratios.append(g["ratio"])
            curr_marker_ratios.append(c["ratio"])
            if g["ratio"] > 0:
                ratio_preserved.append(abs(c["ratio"] - g["ratio"]) / g["ratio"])

        # Difference preservation
        gen0_diffs.append(g["diff"])
        curr_marker_diffs.append(c["diff"])
        diff_preserved.append(abs(c["diff"] - g["diff"]))

        # Slope preservation
        slope_a_preserved.append(abs(c["slope_a"] - g["slope_a"]))
        slope_b_preserved.append(abs(c["slope_b"] - g["slope_b"]))

        gen0_slopes_d.append(g["slope_d"])
        curr_marker_slopes_d.append(c["slope_d"])
        slope_d_preserved.append(abs(c["slope_d"] - g["slope_d"]))

    # Control distributions
    for c in curr_controls:
        if c["ratio"] != float('inf'):
            curr_control_ratios.append(c["ratio"])
        curr_control_diffs.append(c["diff"])
        curr_control_slopes_d.append(c["slope_d"])

    # Statistical tests: are marker relationships more like gen0 than controls are?

    # Ratio correlation: gen0 ratio vs current ratio at same positions
    ratio_corr = 0.0
    ratio_corr_p = 1.0
    if len(gen0_ratios) > 10 and len(curr_marker_ratios) > 10:
        # Filter inf/nan
        valid = [(g, c) for g, c in zip(gen0_ratios, curr_marker_ratios)
                 if np.isfinite(g) and np.isfinite(c) and g < 100 and c < 100]
        if len(valid) > 10:
            gs, cs = zip(*valid)
            ratio_corr, ratio_corr_p = sp_stats.pearsonr(gs, cs)

    # Difference correlation
    diff_corr = 0.0
    diff_corr_p = 1.0
    if len(gen0_diffs) > 10:
        diff_corr, diff_corr_p = sp_stats.pearsonr(gen0_diffs[:n], curr_marker_diffs[:n])

    # Slope correlation
    slope_corr = 0.0
    slope_corr_p = 1.0
    if len(gen0_slopes_d) > 10:
        slope_corr, slope_corr_p = sp_stats.pearsonr(
            gen0_slopes_d[:n], curr_marker_slopes_d[:n]
        )

    # KS test: do marker ratios come from a different distribution than control?
    ks_ratio_stat, ks_ratio_p = 0.0, 1.0
    if len(curr_marker_ratios) > 5 and len(curr_control_ratios) > 5:
        # Filter extremes
        m_filt = [r for r in curr_marker_ratios if np.isfinite(r) and r < 50]
        c_filt = [r for r in curr_control_ratios if np.isfinite(r) and r < 50]
        if len(m_filt) > 5 and len(c_filt) > 5:
            ks_ratio_stat, ks_ratio_p = sp_stats.ks_2samp(m_filt, c_filt)

    ks_diff_stat, ks_diff_p = 0.0, 1.0
    if len(curr_marker_diffs) > 5 and len(curr_control_diffs) > 5:
        ks_diff_stat, ks_diff_p = sp_stats.ks_2samp(
            curr_marker_diffs, curr_control_diffs
        )

    ks_slope_stat, ks_slope_p = 0.0, 1.0
    if len(curr_marker_slopes_d) > 5 and len(curr_control_slopes_d) > 5:
        ks_slope_stat, ks_slope_p = sp_stats.ks_2samp(
            curr_marker_slopes_d, curr_control_slopes_d
        )

    return {
        "label": label,
        "n_pairs": n,
        "n_controls": len(curr_controls),

        # Preservation from gen0
        "ratio_mean_error": float(np.mean(ratio_preserved)) if ratio_preserved else 0,
        "ratio_median_error": float(np.median(ratio_preserved)) if ratio_preserved else 0,
        "diff_mean_error": float(np.mean(diff_preserved)) if diff_preserved else 0,
        "diff_median_error": float(np.median(diff_preserved)) if diff_preserved else 0,
        "slope_a_mean_error": float(np.mean(slope_a_preserved)) if slope_a_preserved else 0,
        "slope_b_mean_error": float(np.mean(slope_b_preserved)) if slope_b_preserved else 0,
        "slope_d_mean_error": float(np.mean(slope_d_preserved)) if slope_d_preserved else 0,

        # Correlations with gen0 (memory of original relationship)
        "ratio_correlation": ratio_corr,
        "ratio_correlation_p": ratio_corr_p,
        "diff_correlation": diff_corr,
        "diff_correlation_p": diff_corr_p,
        "slope_d_correlation": slope_corr,
        "slope_d_correlation_p": slope_corr_p,

        # KS: marker vs control distribution difference
        "ks_ratio_stat": ks_ratio_stat,
        "ks_ratio_p": ks_ratio_p,
        "ks_diff_stat": ks_diff_stat,
        "ks_diff_p": ks_diff_p,
        "ks_slope_stat": ks_slope_stat,
        "ks_slope_p": ks_slope_p,

        # Distributional summaries
        "marker_ratio_mean": float(np.mean([r for r in curr_marker_ratios if np.isfinite(r) and r < 50])) if curr_marker_ratios else 0,
        "control_ratio_mean": float(np.mean([r for r in curr_control_ratios if np.isfinite(r) and r < 50])) if curr_control_ratios else 0,
        "marker_diff_std": float(np.std(curr_marker_diffs)) if curr_marker_diffs else 0,
        "control_diff_std": float(np.std(curr_control_diffs)) if curr_control_diffs else 0,
        "marker_slope_std": float(np.std(curr_marker_slopes_d)) if curr_marker_slopes_d else 0,
        "control_slope_std": float(np.std(curr_control_slopes_d)) if curr_control_slopes_d else 0,
    }


def run_relational_test(output_dir: str):
    """Full relational signal test through compression cascade."""
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    source_pixels = _gen_synthetic_photo(512, 512, rng)

    print("=" * 90)
    print("RELATIONAL SIGNAL ANALYSIS — THE SLOPE HYPOTHESIS")
    print("=" * 90)

    # Create prime JPEG with twin markers at Q95
    prime_data, _ = encode_prime_jpeg(source_pixels, quality=95,
                                       min_prime=2, preserve_dc=True)
    prime_pixels = np.array(Image.open(io.BytesIO(prime_data)).convert("RGB"))

    embedded_pixels, markers = embed_compound(prime_pixels, TWIN_CONFIG, seed=42)
    print(f"\nEmbedded {len(markers)} twin markers into 512x512 image")

    # Generation 0: re-encode marked pixels as Q95
    buf = io.BytesIO()
    Image.fromarray(embedded_pixels).save(buf, format='JPEG', quality=95)
    gen0_data = buf.getvalue()
    gen0_pixels = np.array(Image.open(io.BytesIO(gen0_data)).convert("RGB"))

    # Extract gen0 relations (the "truth" we're tracking)
    gen0_relations = extract_twin_relations(gen0_pixels, markers)
    print(f"  Gen0: {len(gen0_relations['marker'])} marker pairs,"
          f" {len(gen0_relations['control'])} control pairs")

    # Show what the gen0 relationships look like
    m_ratios = [m["ratio"] for m in gen0_relations["marker"]
                if m["ratio"] != float('inf') and m["ratio"] < 50]
    c_ratios = [c["ratio"] for c in gen0_relations["control"]
                if c["ratio"] != float('inf') and c["ratio"] < 50]
    print(f"\n  Gen0 ratio distributions:")
    print(f"    Markers: mean={np.mean(m_ratios):.3f}  std={np.std(m_ratios):.3f}"
          f"  median={np.median(m_ratios):.3f}")
    print(f"    Control: mean={np.mean(c_ratios):.3f}  std={np.std(c_ratios):.3f}"
          f"  median={np.median(c_ratios):.3f}")

    m_diffs = [m["diff"] for m in gen0_relations["marker"]]
    c_diffs = [c["diff"] for c in gen0_relations["control"]]
    print(f"\n  Gen0 difference distributions:")
    print(f"    Markers: mean={np.mean(m_diffs):.1f}  std={np.std(m_diffs):.1f}")
    print(f"    Control: mean={np.mean(c_diffs):.1f}  std={np.std(c_diffs):.1f}")

    m_slopes = [m["slope_d"] for m in gen0_relations["marker"]]
    c_slopes = [c["slope_d"] for c in gen0_relations["control"]]
    print(f"\n  Gen0 distance-slope distributions:")
    print(f"    Markers: mean={np.mean(m_slopes):.1f}  std={np.std(m_slopes):.1f}")
    print(f"    Control: mean={np.mean(c_slopes):.1f}  std={np.std(c_slopes):.1f}")

    # Cascade through quality levels
    cascade_qualities = [95, 85, 75, 60, 40]
    current_pixels = gen0_pixels.copy()
    results = []

    print(f"\n\n{'='*90}")
    print("CASCADE — Relational Signal Through Compression Pipeline")
    print(f"{'='*90}")
    print(f"\n  {'Gen':>4s} {'Q':>4s}  "
          f"{'r_corr':>7s} {'r_p':>10s}  "
          f"{'d_corr':>7s} {'d_p':>10s}  "
          f"{'s_corr':>7s} {'s_p':>10s}  "
          f"{'KS_r_p':>10s} {'KS_d_p':>10s} {'KS_s_p':>10s}  "
          f"{'Signal'}")
    print(f"  {'-'*115}")

    for gen_idx, q in enumerate(cascade_qualities):
        if gen_idx == 0:
            test_pixels = gen0_pixels
        else:
            buf = io.BytesIO()
            Image.fromarray(current_pixels).save(buf, format='JPEG', quality=q)
            test_pixels = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))

        current_relations = extract_twin_relations(test_pixels, markers)
        comparison = compare_relations(gen0_relations, current_relations,
                                        f"Gen{gen_idx}_Q{q}")

        # What's the strongest signal?
        signals = []
        if comparison["ratio_correlation_p"] < 0.01 and comparison["ratio_correlation"] > 0.1:
            signals.append(f"ratio(r={comparison['ratio_correlation']:.3f})")
        if comparison["diff_correlation_p"] < 0.01 and comparison["diff_correlation"] > 0.1:
            signals.append(f"diff(r={comparison['diff_correlation']:.3f})")
        if comparison["slope_d_correlation_p"] < 0.01 and comparison["slope_d_correlation"] > 0.1:
            signals.append(f"slope(r={comparison['slope_d_correlation']:.3f})")
        if comparison["ks_ratio_p"] < 0.01:
            signals.append(f"KS_ratio")
        if comparison["ks_diff_p"] < 0.01:
            signals.append(f"KS_diff")
        if comparison["ks_slope_p"] < 0.01:
            signals.append(f"KS_slope")

        signal_str = " + ".join(signals) if signals else "—"

        print(f"  {gen_idx:>4d} Q{q:>3d}  "
              f"{comparison['ratio_correlation']:>7.3f} {comparison['ratio_correlation_p']:>10.2e}  "
              f"{comparison['diff_correlation']:>7.3f} {comparison['diff_correlation_p']:>10.2e}  "
              f"{comparison['slope_d_correlation']:>7.3f} {comparison['slope_d_correlation_p']:>10.2e}  "
              f"{comparison['ks_ratio_p']:>10.2e} {comparison['ks_diff_p']:>10.2e} {comparison['ks_slope_p']:>10.2e}  "
              f"{signal_str}")

        comparison["generation"] = gen_idx
        comparison["quality"] = q
        results.append(comparison)

        current_pixels = test_pixels

    # Detailed breakdown
    print(f"\n\n{'='*90}")
    print("DETAIL — Correlation Survival (memory of original relationship)")
    print(f"{'='*90}")
    print(f"\n  The correlation between gen0 values and current values")
    print(f"  measures how much 'memory' the relationship has after compression.")
    print(f"  r > 0.3 = meaningful memory.  r > 0.5 = strong memory.")
    print(f"  r < 0.1 = noise.")

    for r in results:
        print(f"\n  Gen {r['generation']} (Q{r['quality']}):")
        print(f"    Ratio correlation:    r={r['ratio_correlation']:>7.4f}"
              f"  p={r['ratio_correlation_p']:>10.2e}"
              f"  {'*** SIGNAL ***' if r['ratio_correlation'] > 0.3 and r['ratio_correlation_p'] < 0.01 else ''}")
        print(f"    Difference corr:      r={r['diff_correlation']:>7.4f}"
              f"  p={r['diff_correlation_p']:>10.2e}"
              f"  {'*** SIGNAL ***' if r['diff_correlation'] > 0.3 and r['diff_correlation_p'] < 0.01 else ''}")
        print(f"    Distance-slope corr:  r={r['slope_d_correlation']:>7.4f}"
              f"  p={r['slope_d_correlation_p']:>10.2e}"
              f"  {'*** SIGNAL ***' if r['slope_d_correlation'] > 0.3 and r['slope_d_correlation_p'] < 0.01 else ''}")
        print(f"    Ratio mean error:     {r['ratio_mean_error']:.4f}")
        print(f"    Diff mean error:      {r['diff_mean_error']:.1f}")

    print(f"\n\n{'='*90}")
    print("DETAIL — Distribution Separation (marker vs control at each gen)")
    print(f"{'='*90}")
    print(f"\n  KS test: are marker pair relationships distinguishable from")
    print(f"  control pair relationships at the current generation?")

    for r in results:
        print(f"\n  Gen {r['generation']} (Q{r['quality']}):")
        print(f"    Ratio KS:    D={r['ks_ratio_stat']:.4f}  p={r['ks_ratio_p']:.4e}"
              f"  {'*** SEPARATED ***' if r['ks_ratio_p'] < 0.01 else ''}")
        print(f"    Diff KS:     D={r['ks_diff_stat']:.4f}  p={r['ks_diff_p']:.4e}"
              f"  {'*** SEPARATED ***' if r['ks_diff_p'] < 0.01 else ''}")
        print(f"    Slope KS:    D={r['ks_slope_stat']:.4f}  p={r['ks_slope_p']:.4e}"
              f"  {'*** SEPARATED ***' if r['ks_slope_p'] < 0.01 else ''}")

    # Save
    with open(os.path.join(output_dir, "relational_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


def plot_relational(results: list, output_dir: str):
    """Visualize relational signal survival."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    gens = [r["generation"] for r in results]
    quals = [f"G{r['generation']}:Q{r['quality']}" for r in results]

    # Correlation survival
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    metrics = [
        ("ratio_correlation", "ratio_correlation_p", "Ratio d₁/d₂", '#E85D3A'),
        ("diff_correlation", "diff_correlation_p", "Difference d₁−d₂", '#2C5F8A'),
        ("slope_d_correlation", "slope_d_correlation_p", "Distance Slope", '#4CAF50'),
    ]

    for idx, (corr_key, p_key, label, color) in enumerate(metrics):
        corrs = [r[corr_key] for r in results]
        pvals = [r[p_key] for r in results]

        axes[idx].bar(range(len(gens)), corrs, color=color, alpha=0.7, edgecolor='black')
        for i, (c, p) in enumerate(zip(corrs, pvals)):
            marker = "***" if p < 0.01 and c > 0.1 else ""
            axes[idx].text(i, c + 0.02, f"{c:.3f}\n{marker}", ha='center',
                          fontsize=9, fontweight='bold' if marker else 'normal')

        axes[idx].set_xticks(range(len(quals)))
        axes[idx].set_xticklabels(quals, fontsize=9)
        axes[idx].set_ylabel('Pearson r (vs Gen0)', fontsize=11)
        axes[idx].set_title(f'{label} Correlation', fontsize=13)
        axes[idx].axhline(0.3, color='red', linewidth=1, linestyle='--', alpha=0.5,
                          label='Signal threshold')
        axes[idx].axhline(0, color='black', linewidth=0.5, alpha=0.3)
        axes[idx].set_ylim(-0.3, 1.05)
        axes[idx].legend(fontsize=9)

    plt.suptitle('Relational Signal Memory Through Compression Cascade', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'relational_correlation.png'), dpi=150)
    plt.close()

    # KS separation
    fig, ax = plt.subplots(1, 1, figsize=(12, 5))

    for corr_key, p_key, label, color in [
        ("ks_ratio_stat", "ks_ratio_p", "Ratio", '#E85D3A'),
        ("ks_diff_stat", "ks_diff_p", "Difference", '#2C5F8A'),
        ("ks_slope_stat", "ks_slope_p", "Slope", '#4CAF50'),
    ]:
        neg_log_p = [-np.log10(max(r[p_key], 1e-300)) for r in results]
        ax.plot(range(len(gens)), neg_log_p, 'o-', linewidth=2,
                markersize=8, color=color, label=label)

    ax.axhline(2, color='red', linewidth=1, linestyle='--', label='α=0.01')
    ax.set_xticks(range(len(quals)))
    ax.set_xticklabels(quals, fontsize=10)
    ax.set_ylabel('-log₁₀(KS p-value)', fontsize=12)
    ax.set_title('Marker vs Control Distribution Separation (KS test)', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'relational_ks.png'), dpi=150)
    plt.close()

    print(f"Relational plots saved to {output_dir}/")


if __name__ == "__main__":
    output_dir = "pgps_results/relational"
    results = run_relational_test(output_dir)
    plot_relational(results, os.path.join(output_dir, "plots"))
