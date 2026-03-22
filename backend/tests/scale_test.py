#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# See LICENSE file for full terms.
#
# Author:  Jeremy Pickett <jeremy.pickett@gmail.com>
# Project: Participation Over Permission — Provenance Signal Detection
# Co-developed with Claude (Anthropic). Human-directed, AI-assisted.
#
# ASSUMPTION ZERO: This is provenance signal detection, not watermarking.
# The scheme proves participation. It does not judge what participation means.
# =============================================================================
"""
Scale & Resize Testing — Finding the Floor
============================================
Jeremy Pickett — Axiomatic Fictions Series

Tests across four image sizes: small (512), medium (1024), large (2048),
huge (4096). For each size:

  1. CAPACITY: How many markers fit? What's the statistical power?
  2. CASCADE: Full JPEG compression cascade — does amplification hold?
  3. RESIZE: Large → smaller sizes. What survives spatial resampling?
  4. CROSS-CODEC + RESIZE: JPEG → resize → WebP (the real pipeline)
  5. FINGERPRINT STABILITY: Does the disruption map hold through transforms?
  6. SEED SEPARATION: Two seeds, same image — distinguishable?
"""

import os
import sys
import io
import json
import time
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
)
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
)
from div2k_harness import extract_twin_measurements, compare_twin_distributions


# =============================================================================
# CONFIG
# =============================================================================

SIZES = {
    "small_512":  512,
    "medium_1024": 1024,
    "large_2048": 2048,
    "huge_4096":  4096,
}

TWIN_CONFIG = MarkerConfig(
    name="twin", description="Twin prime-gap markers",
    min_prime=53, use_twins=True, use_rare_basket=True,
    use_magic=False, detection_prime_tolerance=2, n_markers=2000,
)

CASCADE_Q = [95, 85, 75, 60, 40]
WEBP_Q = [95, 80, 60]
RESIZE_TARGETS = [2048, 1024, 512, 256]


# =============================================================================
# SYNTHETIC IMAGE GENERATOR (scale-aware)
# =============================================================================

def gen_photo(size, seed=42):
    """Generate a synthetic photograph at given size."""
    rng = np.random.RandomState(seed)
    h = w = size
    img = np.zeros((h, w, 3), dtype=np.float64)
    n_blobs = max(10, size // 50)
    for _ in range(n_blobs):
        cy, cx = rng.randint(0, h), rng.randint(0, w)
        sy, sx = rng.uniform(size * 0.04, size * 0.3), rng.uniform(size * 0.04, size * 0.3)
        color = rng.uniform(50, 220, 3)
        yy, xx = np.ogrid[:h, :w]
        mask = np.exp(-0.5 * (((yy - cy) / sy)**2 + ((xx - cx) / sx)**2))
        for c in range(3):
            img[:, :, c] += mask * color[c]
    img = np.clip(img, 0, 255)
    noise = rng.normal(0, 3, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


# =============================================================================
# HELPERS
# =============================================================================

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

def resize(pixels, target_size):
    img = Image.fromarray(pixels)
    img = img.resize((target_size, target_size), Image.LANCZOS)
    return np.array(img)


def detect_and_report(pixels, markers, config):
    """Run compound detection and return summary dict."""
    det = detect_compound(pixels, markers, config)
    return {
        "marker_total": det["marker_total"],
        "marker_pass": det["marker_compound_pass"],
        "marker_rate": det["marker_rate"],
        "control_rate": det["control_rate"],
        "rate_ratio": det["rate_ratio"],
        "binom_p": det["binomial_pvalue"],
        "detected": det["detected_binom"],
        "primary_pass": det["marker_primary_pass"],
        "twin_pass": det["marker_twin_pass"],
    }


def disruption_map(pixels, markers, config):
    """
    Extract binary disruption map: which marker positions show anomalous
    variance relative to neighbors.
    """
    h, w, _ = pixels.shape
    prime_lookup = build_prime_lookup(8, min_prime=config.min_prime)
    tol = config.detection_prime_tolerance
    max_val = 255

    # Build fuzzy prime lookup
    fuzzy_prime = np.zeros(max_val + 1, dtype=bool)
    for d in range(max_val + 1):
        for offset in range(-tol, tol + 1):
            check = d + offset
            if 0 <= check <= max_val and prime_lookup[check]:
                fuzzy_prime[d] = True
                break

    # For each marker position: is the twin compound satisfied?
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


def hamming_distance(a, b):
    """Hamming distance between two binary arrays."""
    n = min(len(a), len(b))
    return int(np.sum(a[:n] != b[:n]))


# =============================================================================
# TEST 1: CAPACITY AND CASCADE PER SIZE
# =============================================================================

def test_capacity_and_cascade(output_dir):
    """How many markers fit at each size? Does amplification hold?"""
    print("\n" + "=" * 90)
    print("TEST 1: CAPACITY AND CASCADE BY IMAGE SIZE")
    print("=" * 90)

    results = {}

    for name, size in SIZES.items():
        print(f"\n{'='*70}")
        print(f"  {name} ({size}x{size})")
        print(f"{'='*70}")

        t0 = time.time()
        pixels = gen_photo(size)

        # Adjust marker count to image size
        config = MarkerConfig(
            name="twin", description="Scale test",
            min_prime=53, use_twins=True, use_rare_basket=True,
            use_magic=False, detection_prime_tolerance=2,
            n_markers=min(2000, (size * size) // 500),
        )

        try:
            embedded, markers = embed_compound(pixels, config, variable_offset=42)
        except ValueError as e:
            print(f"  EMBED FAILED: {e}")
            continue

        n_eligible = len(sample_positions_grid(size, size, 8))
        saturation = len(markers) / n_eligible if n_eligible > 0 else 0

        print(f"  Eligible positions: {n_eligible}")
        print(f"  Markers embedded:   {len(markers)}")
        print(f"  Saturation:         {saturation:.1%}")
        print(f"  Gen time:           {time.time()-t0:.1f}s")

        # JPEG cascade
        buf = io.BytesIO()
        Image.fromarray(embedded).save(buf, format='JPEG', quality=95)
        gen0_data = buf.getvalue()
        gen0_px = decode(gen0_data)
        gen0_twins = extract_twin_measurements(gen0_px, markers)

        print(f"\n  {'Gen':>4s} {'Q':>4s}  {'Compound':>10s}  {'Rate':>7s}"
              f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}"
              f"  {'KS_diff_p':>10s}  {'VarRatio':>8s}  {'Signal'}")
        print(f"  {'-'*95}")

        current = gen0_px.copy()
        size_results = []

        for gen_idx, q in enumerate(CASCADE_Q):
            if gen_idx == 0:
                test_px = gen0_px
            else:
                test_px = decode(to_jpeg(current, q))

            det = detect_and_report(test_px, markers, config)

            curr_twins = extract_twin_measurements(test_px, markers)
            rel = compare_twin_distributions(gen0_twins, curr_twins)

            signals = []
            if det["detected"]: signals.append("TWIN")
            if rel["ks_diff_p"] < 0.01: signals.append("KS")
            sig = "+".join(signals) if signals else "\u2014"

            print(f"  {gen_idx:>4d} Q{q:>3d}"
                  f"  {det['marker_pass']:>4d}/{det['marker_total']:<4d}"
                  f"  {det['marker_rate']:>7.4f}"
                  f"  {det['control_rate']:>7.4f}"
                  f"  {det['rate_ratio']:>6.1f}"
                  f"  {det['binom_p']:>10.2e}"
                  f"  {rel['ks_diff_p']:>10.2e}"
                  f"  {rel['variance_ratio']:>8.3f}"
                  f"  {sig}")

            size_results.append({
                "gen": gen_idx, "q": q,
                **det, **{f"rel_{k}": v for k, v in rel.items()},
            })

            current = test_px

        results[name] = {
            "size": size,
            "n_eligible": n_eligible,
            "n_markers": len(markers),
            "saturation": saturation,
            "cascade": size_results,
        }

    return results


# =============================================================================
# TEST 2: RESIZE SURVIVAL
# =============================================================================

def test_resize(output_dir):
    """What happens when images are resized?"""
    print("\n\n" + "=" * 90)
    print("TEST 2: RESIZE SURVIVAL")
    print("=" * 90)

    # Start with large and huge, resize down
    source_sizes = [("large_2048", 2048), ("huge_4096", 4096)]
    results = {}

    for name, size in source_sizes:
        print(f"\n{'='*70}")
        print(f"  Source: {name} ({size}x{size})")
        print(f"{'='*70}")

        pixels = gen_photo(size)
        config = MarkerConfig(
            name="twin", description="Resize test",
            min_prime=53, use_twins=True, use_rare_basket=True,
            use_magic=False, detection_prime_tolerance=2,
            n_markers=min(2000, (size * size) // 500),
        )

        try:
            embedded, markers = embed_compound(pixels, config, variable_offset=42)
        except ValueError as e:
            print(f"  EMBED FAILED: {e}")
            continue

        # JPEG Q95 as starting point
        gen0_px = decode(to_jpeg(embedded, 95))
        gen0_twins = extract_twin_measurements(gen0_px, markers)

        print(f"  Embedded {len(markers)} markers")
        print(f"\n  {'Target':>8s}  {'Scale':>6s}  {'Compound':>10s}  {'Rate':>7s}"
              f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}"
              f"  {'KS_diff_p':>10s}  {'VarRatio':>8s}  {'Signal'}")
        print(f"  {'-'*95}")

        size_results = []

        for target in RESIZE_TARGETS:
            if target >= size:
                continue

            scale = target / size

            # Resize the embedded pixels
            resized = resize(gen0_px, target)

            # Scale marker positions to new coordinates
            scaled_markers = []
            for m in markers:
                new_r = int(m["row"] * scale)
                new_c = int(m["col"] * scale)
                new_tc = int(m.get("twin_col", m["col"] + 1) * scale)
                if new_r < target and new_c < target and new_tc < target:
                    scaled_markers.append({
                        "row": new_r, "col": new_c, "twin_col": new_tc,
                    })

            if len(scaled_markers) < 20:
                print(f"  {target:>6d}px  {scale:>5.2f}x  Too few markers after scaling ({len(scaled_markers)})")
                continue

            det = detect_and_report(resized, scaled_markers, config)

            # Relational signal (compare against gen0 at same scaled positions)
            curr_twins = extract_twin_measurements(resized, scaled_markers)
            # Build a gen0 measurement at the same scaled positions for fair comparison
            gen0_at_scaled = extract_twin_measurements(gen0_px, markers)
            rel = compare_twin_distributions(gen0_at_scaled, curr_twins)

            signals = []
            if det["detected"]: signals.append("TWIN")
            if rel["ks_diff_p"] < 0.01: signals.append("KS")
            sig = "+".join(signals) if signals else "\u2014"

            print(f"  {target:>6d}px  {scale:>5.2f}x"
                  f"  {det['marker_pass']:>4d}/{det['marker_total']:<4d}"
                  f"  {det['marker_rate']:>7.4f}"
                  f"  {det['control_rate']:>7.4f}"
                  f"  {det['rate_ratio']:>6.1f}"
                  f"  {det['binom_p']:>10.2e}"
                  f"  {rel['ks_diff_p']:>10.2e}"
                  f"  {rel['variance_ratio']:>8.3f}"
                  f"  {sig}")

            size_results.append({
                "target": target, "scale": scale,
                "n_scaled_markers": len(scaled_markers),
                **det, **{f"rel_{k}": v for k, v in rel.items()},
            })

        # Resize + re-encode (the real pipeline)
        print(f"\n  Resize + JPEG re-encode (the platform pipeline):")
        print(f"  {'Target':>8s}  {'Q':>4s}  {'Compound':>10s}  {'Rate':>7s}"
              f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Signal'}")
        print(f"  {'-'*75}")

        for target in [1024, 512]:
            if target >= size:
                continue
            scale = target / size
            resized = resize(gen0_px, target)

            scaled_markers = []
            for m in markers:
                new_r = int(m["row"] * scale)
                new_c = int(m["col"] * scale)
                new_tc = int(m.get("twin_col", m["col"] + 1) * scale)
                if new_r < target and new_c < target and new_tc < target:
                    scaled_markers.append({
                        "row": new_r, "col": new_c, "twin_col": new_tc,
                    })

            if len(scaled_markers) < 20:
                continue

            for q in [85, 75, 60]:
                reencoded = decode(to_jpeg(resized, q))
                det = detect_and_report(reencoded, scaled_markers, config)
                sig = "DETECTED" if det["detected"] else "\u2014"
                print(f"  {target:>6d}px  Q{q:>3d}"
                      f"  {det['marker_pass']:>4d}/{det['marker_total']:<4d}"
                      f"  {det['marker_rate']:>7.4f}"
                      f"  {det['control_rate']:>7.4f}"
                      f"  {det['rate_ratio']:>6.1f}"
                      f"  {det['binom_p']:>10.2e}"
                      f"  {sig}")

        # Resize + WebP (the CDN pipeline)
        print(f"\n  Resize + WebP (the CDN pipeline):")
        print(f"  {'Target':>8s}  {'Q':>4s}  {'Compound':>10s}  {'Rate':>7s}"
              f"  {'Ctrl':>7s}  {'Ratio':>6s}  {'Binom_p':>10s}  {'Signal'}")
        print(f"  {'-'*75}")

        for target in [1024, 512]:
            if target >= size:
                continue
            scale = target / size
            resized = resize(gen0_px, target)

            scaled_markers = []
            for m in markers:
                new_r = int(m["row"] * scale)
                new_c = int(m["col"] * scale)
                new_tc = int(m.get("twin_col", m["col"] + 1) * scale)
                if new_r < target and new_c < target and new_tc < target:
                    scaled_markers.append({
                        "row": new_r, "col": new_c, "twin_col": new_tc,
                    })

            if len(scaled_markers) < 20:
                continue

            for q in [95, 80, 60]:
                reencoded = decode(to_webp(resized, q))
                det = detect_and_report(reencoded, scaled_markers, config)
                sig = "DETECTED" if det["detected"] else "\u2014"
                print(f"  {target:>6d}px  WQ{q:>2d}"
                      f"  {det['marker_pass']:>4d}/{det['marker_total']:<4d}"
                      f"  {det['marker_rate']:>7.4f}"
                      f"  {det['control_rate']:>7.4f}"
                      f"  {det['rate_ratio']:>6.1f}"
                      f"  {det['binom_p']:>10.2e}"
                      f"  {sig}")

        results[name] = size_results

    return results


# =============================================================================
# TEST 3: FINGERPRINT STABILITY
# =============================================================================

def test_fingerprint_stability(output_dir):
    """Does the disruption map remain matchable through transforms?"""
    print("\n\n" + "=" * 90)
    print("TEST 3: FINGERPRINT (DISRUPTION MAP) STABILITY")
    print("=" * 90)

    size = 1024
    pixels = gen_photo(size)
    config = MarkerConfig(
        name="twin", description="Fingerprint test",
        min_prime=53, use_twins=True, use_rare_basket=True,
        use_magic=False, detection_prime_tolerance=2,
        n_markers=800,
    )

    embedded, markers = embed_compound(pixels, config, variable_offset=42)
    gen0_px = decode(to_jpeg(embedded, 95))

    # Reference disruption map
    ref_map = disruption_map(gen0_px, markers, config)
    n_markers = len(markers)
    ref_ones = int(np.sum(ref_map))

    print(f"\n  Image: {size}x{size}, {len(markers)} markers")
    print(f"  Reference map: {ref_ones}/{n_markers} positions disrupted ({ref_ones/n_markers*100:.1f}%)")

    print(f"\n  {'Transform':>30s}  {'Ones':>6s}  {'Hamming':>8s}  {'Hamming%':>8s}  {'Jaccard':>8s}  {'Match?'}")
    print(f"  {'-'*80}")

    transforms = [
        ("JPEG Q95 (identity)", lambda px: decode(to_jpeg(px, 95))),
        ("JPEG Q85", lambda px: decode(to_jpeg(px, 85))),
        ("JPEG Q75", lambda px: decode(to_jpeg(px, 75))),
        ("JPEG Q60", lambda px: decode(to_jpeg(px, 60))),
        ("JPEG Q40", lambda px: decode(to_jpeg(px, 40))),
        ("WebP Q95", lambda px: decode(to_webp(px, 95))),
        ("WebP Q80", lambda px: decode(to_webp(px, 80))),
        ("WebP Q60", lambda px: decode(to_webp(px, 60))),
        ("JPEG Q85 \u2192 WebP Q80", lambda px: decode(to_webp(decode(to_jpeg(px, 85)), 80))),
        ("JPEG Q75 \u2192 WebP Q60", lambda px: decode(to_webp(decode(to_jpeg(px, 75)), 60))),
        ("JPEG Q95 \u2192 Q85 \u2192 Q75", lambda px: decode(to_jpeg(decode(to_jpeg(decode(to_jpeg(px, 95)), 85)), 75))),
    ]

    results = []
    for name, transform_fn in transforms:
        transformed = transform_fn(embedded)
        t_map = disruption_map(transformed, markers, config)
        t_ones = int(np.sum(t_map))

        hd = hamming_distance(ref_map, t_map)
        hd_pct = hd / n_markers * 100

        # Jaccard similarity (intersection / union of disrupted positions)
        intersection = int(np.sum(ref_map & t_map))
        union = int(np.sum(ref_map | t_map))
        jaccard = intersection / union if union > 0 else 0

        # Is this a usable match?
        match = "YES" if jaccard > 0.3 else "marginal" if jaccard > 0.15 else "NO"

        print(f"  {name:>30s}  {t_ones:>4d}  {hd:>6d}  {hd_pct:>7.1f}%  {jaccard:>8.3f}  {match}")

        results.append({
            "transform": name, "ones": t_ones,
            "hamming": hd, "hamming_pct": hd_pct,
            "jaccard": jaccard, "matchable": match,
        })

    return results


# =============================================================================
# TEST 4: SEED SEPARATION
# =============================================================================

def test_seed_separation(output_dir):
    """Two seeds, same image. Are the fingerprints distinguishable?"""
    print("\n\n" + "=" * 90)
    print("TEST 4: SEED SEPARATION — TWO CREATORS, SAME IMAGE")
    print("=" * 90)

    size = 1024
    pixels = gen_photo(size, seed=99)

    config = MarkerConfig(
        name="twin", description="Seed separation test",
        min_prime=53, use_twins=True, use_rare_basket=True,
        use_magic=False, detection_prime_tolerance=2,
        n_markers=500,
    )

    # Embed with two different seeds
    emb_a, markers_a = embed_compound(pixels, config, variable_offset=42)
    emb_b, markers_b = embed_compound(pixels, config, variable_offset=137)

    print(f"\n  Image: {size}x{size}")
    print(f"  Seed A (42):  {len(markers_a)} markers")
    print(f"  Seed B (137): {len(markers_b)} markers")

    # Position overlap
    set_a = set((m["row"], m["col"]) for m in markers_a)
    set_b = set((m["row"], m["col"]) for m in markers_b)
    overlap = len(set_a & set_b)
    total = len(set_a | set_b)
    jaccard = overlap / total if total > 0 else 0

    print(f"\n  Position overlap: {overlap} / {len(set_a)} (Jaccard: {jaccard:.4f})")

    # Disruption maps
    gen0_a = decode(to_jpeg(emb_a, 95))
    gen0_b = decode(to_jpeg(emb_b, 95))

    map_a = disruption_map(gen0_a, markers_a, config)
    map_b = disruption_map(gen0_b, markers_b, config)

    # Can we tell which seed produced a given image?
    # Test: scan image A with markers from seed A vs markers from seed B
    det_aa = detect_and_report(gen0_a, markers_a, config)  # Correct seed
    det_ab = detect_and_report(gen0_a, markers_b, config)  # Wrong seed

    det_bb = detect_and_report(gen0_b, markers_b, config)  # Correct seed
    det_ba = detect_and_report(gen0_b, markers_a, config)  # Wrong seed

    print(f"\n  Cross-detection matrix:")
    print(f"  {'':>20s}  {'Markers A':>15s}  {'Markers B':>15s}")
    print(f"  {'Image A (seed 42)':>20s}"
          f"  {det_aa['rate_ratio']:>5.1f}x p={det_aa['binom_p']:.1e}"
          f"  {det_ab['rate_ratio']:>5.1f}x p={det_ab['binom_p']:.1e}")
    print(f"  {'Image B (seed 137)':>20s}"
          f"  {det_ba['rate_ratio']:>5.1f}x p={det_ba['binom_p']:.1e}"
          f"  {det_bb['rate_ratio']:>5.1f}x p={det_bb['binom_p']:.1e}")

    correct_detected = det_aa["detected"] and det_bb["detected"]
    wrong_not_detected = not det_ab["detected"] and not det_ba["detected"]
    clean_separation = correct_detected and wrong_not_detected

    print(f"\n  Correct seed detected: A\u2192A={'YES' if det_aa['detected'] else 'NO'}"
          f"  B\u2192B={'YES' if det_bb['detected'] else 'NO'}")
    print(f"  Wrong seed rejected:  A\u2192B={'YES' if not det_ab['detected'] else 'NO'}"
          f"  B\u2192A={'YES' if not det_ba['detected'] else 'NO'}")
    print(f"  Clean separation: {'YES' if clean_separation else 'NO'}")

    # After JPEG compression
    print(f"\n  After JPEG Q75:")
    comp_a = decode(to_jpeg(gen0_a, 75))
    comp_b = decode(to_jpeg(gen0_b, 75))

    det_aa_c = detect_and_report(comp_a, markers_a, config)
    det_ab_c = detect_and_report(comp_a, markers_b, config)
    det_bb_c = detect_and_report(comp_b, markers_b, config)
    det_ba_c = detect_and_report(comp_b, markers_a, config)

    print(f"  {'':>20s}  {'Markers A':>15s}  {'Markers B':>15s}")
    print(f"  {'Image A + Q75':>20s}"
          f"  {det_aa_c['rate_ratio']:>5.1f}x p={det_aa_c['binom_p']:.1e}"
          f"  {det_ab_c['rate_ratio']:>5.1f}x p={det_ab_c['binom_p']:.1e}")
    print(f"  {'Image B + Q75':>20s}"
          f"  {det_ba_c['rate_ratio']:>5.1f}x p={det_ba_c['binom_p']:.1e}"
          f"  {det_bb_c['rate_ratio']:>5.1f}x p={det_bb_c['binom_p']:.1e}")

    return {
        "position_overlap": overlap,
        "jaccard": jaccard,
        "clean_separation_gen0": clean_separation,
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    output_dir = "pgps_results/scale_test"
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 90)
    print("SCALE & RESIZE TESTING \u2014 FINDING THE FLOOR")
    print("=" * 90)

    t_start = time.time()

    # Test 1
    capacity_results = test_capacity_and_cascade(output_dir)

    # Test 2
    try:
        resize_results = test_resize(output_dir)
    except Exception as e:
        print(f"\nTest 2 error: {e}")
        resize_results = {}

    # Test 3
    try:
        fingerprint_results = test_fingerprint_stability(output_dir)
    except Exception as e:
        print(f"\nTest 3 error: {e}")
        fingerprint_results = []

    # Test 4
    try:
        seed_results = test_seed_separation(output_dir)
    except Exception as e:
        print(f"\nTest 4 error: {e}")
        seed_results = {}

    total = time.time() - t_start
    print(f"\n\n{'='*90}")
    print(f"ALL TESTS COMPLETE \u2014 {total:.0f}s total")
    print(f"{'='*90}")

    # Save
    summary = {
        "capacity": {k: {"size": v["size"], "markers": v["n_markers"],
                         "saturation": v["saturation"]}
                     for k, v in capacity_results.items()},
        "fingerprint_stability": fingerprint_results,
        "seed_separation": seed_results,
    }
    with open(os.path.join(output_dir, "scale_results.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
