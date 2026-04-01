#!/usr/bin/env python3
"""
Grid Alignment Diagnostic
===========================
Shows exactly where the injector places markers vs where the verifier looks.
Quantifies the overlap (or lack thereof).
"""

import os
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MARKER_TYPES
from verify_image import _grid_positions_both_phases, WINDOW_W
from pgps_detector import sample_positions_grid, build_prime_lookup

TEST_IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'test-images')


def diagnose_one_image(img_path: str):
    img = Image.open(img_path).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape
    name = os.path.basename(img_path)

    # ── INJECT ──
    config = MARKER_TYPES["compound"]
    modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)

    # Injected marker positions
    injected_positions = set((m["row"], m["col"]) for m in markers)
    twin_positions = set()
    for m in markers:
        if "twin_col" in m:
            twin_positions.add((m["row"], m["twin_col"]))

    all_injected = injected_positions | twin_positions

    # ── VERIFIER GRID ──
    phase0, phase3 = _grid_positions_both_phases(h, w)
    phase0_set = set(phase0)
    phase3_set = set(phase3)
    verifier_all = phase0_set | phase3_set

    # ── OVERLAP ──
    on_phase0 = all_injected & phase0_set
    on_phase3 = all_injected & phase3_set
    on_either = all_injected & verifier_all
    missed = all_injected - verifier_all

    # ── What does the verifier see at marker positions? ──
    prime_lookup = build_prime_lookup(8)
    prime_lookup[:37] = False

    # Check R-G distances at injected positions on the MODIFIED image
    marker_prime_hits = 0
    for r, c in all_injected:
        if 0 <= r < h and 0 <= c < w:
            d = abs(int(modified[r, c, 0]) - int(modified[r, c, 1]))
            if d <= 255 and prime_lookup[d]:
                marker_prime_hits += 1

    # Check R-G distances at ALL verifier grid positions on the MODIFIED image
    verifier_prime_hits = 0
    verifier_total = 0
    for r, c in phase3:  # phase3 is the one that should match
        if 0 <= r < h and 0 <= c < w:
            verifier_total += 1
            d = abs(int(modified[r, c, 0]) - int(modified[r, c, 1]))
            if d <= 255 and prime_lookup[d]:
                verifier_prime_hits += 1

    return {
        "name": name,
        "h": h, "w": w,
        "n_markers": len(markers),
        "n_twins": len(twin_positions),
        "n_all_injected": len(all_injected),
        "n_phase0": len(phase0),
        "n_phase3": len(phase3),
        "n_verifier_all": len(verifier_all),
        "on_phase0": len(on_phase0),
        "on_phase3": len(on_phase3),
        "on_either": len(on_either),
        "missed": len(missed),
        "overlap_pct": len(on_either) / len(all_injected) * 100 if all_injected else 0,
        "marker_prime_hits": marker_prime_hits,
        "marker_prime_rate": marker_prime_hits / len(all_injected) if all_injected else 0,
        "verifier_prime_hits": verifier_prime_hits,
        "verifier_prime_rate": verifier_prime_hits / verifier_total if verifier_total else 0,
        "dilution_factor": len(verifier_all) / len(on_either) if on_either else float('inf'),
    }


def main():
    images = sorted(f for f in os.listdir(TEST_IMAGES_DIR) if f.endswith('.png'))

    print()
    print("=" * 110)
    print("GRID ALIGNMENT DIAGNOSTIC — Where does the injector place vs where does the verifier look?")
    print("=" * 110)

    print(f"\n  POSITION OVERLAP")
    print(f"  {'Image':<12s}  {'Injected':>8s}  {'Verifier':>8s}  "
          f"{'On Grid':>7s}  {'Missed':>6s}  {'Overlap%':>8s}  {'Dilution':>8s}")
    print("  " + "-" * 80)

    results = []
    for img_name in images:
        r = diagnose_one_image(os.path.join(TEST_IMAGES_DIR, img_name))
        results.append(r)
        print(f"  {r['name']:<12s}  {r['n_all_injected']:>8d}  {r['n_verifier_all']:>8d}  "
              f"{r['on_either']:>7d}  {r['missed']:>6d}  {r['overlap_pct']:>7.1f}%  "
              f"{r['dilution_factor']:>7.1f}x")

    # Prime rate comparison
    print(f"\n  PRIME HIT RATES (on modified image)")
    print(f"  {'Image':<12s}  {'At markers':>10s}  {'Verifier grid':>13s}  {'Ratio':>7s}  {'Threshold':>9s}  {'Would detect':>12s}")
    print("  " + "-" * 80)

    for r in results:
        ratio = r['marker_prime_rate'] / r['verifier_prime_rate'] if r['verifier_prime_rate'] > 0 else float('inf')
        would_detect = "YES" if r['verifier_prime_rate'] > 0.20 else "no"
        print(f"  {r['name']:<12s}  {r['marker_prime_rate']:>10.4f}  {r['verifier_prime_rate']:>13.4f}  "
              f"{ratio:>7.1f}x  {'>0.20':>9s}  {would_detect:>12s}")

    # Summary
    avg_overlap = np.mean([r['overlap_pct'] for r in results])
    avg_dilution = np.mean([r['dilution_factor'] for r in results])
    avg_marker_rate = np.mean([r['marker_prime_rate'] for r in results])
    avg_verifier_rate = np.mean([r['verifier_prime_rate'] for r in results])

    print(f"\n  DIAGNOSIS:")
    print(f"    Average overlap:       {avg_overlap:.1f}% of injected markers land on verifier grid positions")
    print(f"    Average dilution:      {avg_dilution:.1f}x — each marker signal diluted by this many non-marker positions")
    print(f"    Prime rate at markers: {avg_marker_rate:.4f} (what the signal actually is)")
    print(f"    Prime rate at grid:    {avg_verifier_rate:.4f} (what the verifier sees)")
    print(f"    Detection threshold:   0.20")
    print()

    if avg_verifier_rate < 0.20:
        gap = 0.20 / avg_verifier_rate if avg_verifier_rate > 0 else float('inf')
        print(f"    CONCLUSION: The verifier grid rate is {gap:.0f}x below threshold.")
        print(f"    The signal IS there at marker positions ({avg_marker_rate:.4f}).")
        print(f"    But the verifier drowns it by scanning {avg_dilution:.0f}x more non-marker positions.")

    if avg_overlap < 100:
        print(f"    Additionally, {100 - avg_overlap:.1f}% of markers are COMPLETELY INVISIBLE to the verifier grid.")

    print()


if __name__ == "__main__":
    main()
