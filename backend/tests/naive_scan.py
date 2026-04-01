#!/usr/bin/env python3
"""
Naive full-image scan: where ARE the prime R-G distances after JPEG?
=====================================================================
1. Inject at 50% density
2. Save as JPEG Q95
3. Scan EVERY pixel for |R-G| that's prime >= 53
4. Compare: are primes at marker positions? Near marker positions? Random?
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MarkerConfig, build_rare_basket
from pgps_detector import sample_positions_grid, build_prime_lookup, sieve_of_eratosthenes
from dqt_prime import encode_prime_jpeg

TEST_IMAGE = os.path.join(os.path.dirname(__file__), '..', 'test-images', '0538.png')
WINDOW_W = 8
MIN_PRIME = 53


def run():
    img = Image.open(TEST_IMAGE).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape

    grid_size = len(sample_positions_grid(h, w, WINDOW_W))

    # Inject at 50% density
    config = MarkerConfig(
        name="naive_scan",
        description="Debug",
        min_prime=53,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        n_markers=int(grid_size * 0.50),
    )

    modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)
    modified = np.clip(modified, 0, 255).astype(np.uint8)

    marker_positions = set((m["row"], m["col"]) for m in markers)
    twin_positions = set((m["row"], m["twin_col"]) for m in markers if "twin_col" in m)
    all_injected = marker_positions | twin_positions

    # What primes did we inject?
    injected_primes = Counter()
    for m in markers:
        injected_primes[m["prime"]] += 1
        if "twin_prime" in m:
            injected_primes[m["twin_prime"]] += 1

    # Save as JPEG Q95 and reload
    with tempfile.TemporaryDirectory() as tmpdir:
        jpeg_path = os.path.join(tmpdir, "test.jpg")
        encode_prime_jpeg(modified, quality=95, output_path=jpeg_path)
        jpeg_pixels = np.array(Image.open(jpeg_path).convert("RGB"))

    prime_lookup = build_prime_lookup(8)
    prime_lookup[:MIN_PRIME] = False

    basket = build_rare_basket(min_prime=53)
    basket_set = set(int(p) for p in basket)

    # ── NAIVE SCAN: every pixel in pre-JPEG vs post-JPEG ──
    print()
    print("=" * 100)
    print(f"NAIVE FULL-IMAGE SCAN")
    print(f"  Image: {os.path.basename(TEST_IMAGE)} ({w}x{h} = {h*w:,} pixels)")
    print(f"  Markers placed: {len(markers)} + {len(twin_positions)} twins = {len(all_injected)} positions")
    print("=" * 100)

    # Compute |R-G| for every pixel
    pre_rg = np.abs(modified[:,:,0].astype(int) - modified[:,:,1].astype(int))
    post_rg = np.abs(jpeg_pixels[:,:,0].astype(int) - jpeg_pixels[:,:,1].astype(int))

    # Count primes everywhere
    pre_prime_mask = np.zeros_like(pre_rg, dtype=bool)
    post_prime_mask = np.zeros_like(post_rg, dtype=bool)
    for r_idx in range(h):
        for c_idx in range(w):
            d = pre_rg[r_idx, c_idx]
            if d <= 255 and prime_lookup[d]:
                pre_prime_mask[r_idx, c_idx] = True
            d = post_rg[r_idx, c_idx]
            if d <= 255 and prime_lookup[d]:
                post_prime_mask[r_idx, c_idx] = True

    pre_prime_count = int(np.sum(pre_prime_mask))
    post_prime_count = int(np.sum(post_prime_mask))
    total_pixels = h * w

    print(f"\n  1. PRIME PIXEL COUNTS (|R-G| is prime >= {MIN_PRIME}):")
    print(f"     Pre-JPEG:  {pre_prime_count:>8,} / {total_pixels:,} ({pre_prime_count/total_pixels*100:.2f}%)")
    print(f"     Post-JPEG: {post_prime_count:>8,} / {total_pixels:,} ({post_prime_count/total_pixels*100:.2f}%)")

    # ── WHERE are the post-JPEG primes relative to marker positions? ──
    # Build marker mask
    marker_mask = np.zeros((h, w), dtype=bool)
    for r, c in all_injected:
        if 0 <= r < h and 0 <= c < w:
            marker_mask[r, c] = True

    # Exact match
    post_prime_at_markers = int(np.sum(post_prime_mask & marker_mask))
    post_prime_not_markers = int(np.sum(post_prime_mask & ~marker_mask))

    print(f"\n  2. POST-JPEG PRIMES — WHERE ARE THEY?")
    print(f"     At exact marker positions:     {post_prime_at_markers:>8,} ({post_prime_at_markers/post_prime_count*100:.1f}% of all post-JPEG primes)")
    print(f"     At non-marker positions:       {post_prime_not_markers:>8,} ({post_prime_not_markers/post_prime_count*100:.1f}%)")

    # Near markers (within 1-3 pixels)
    for radius in [1, 2, 3, 4]:
        near_mask = np.zeros((h, w), dtype=bool)
        for r, c in all_injected:
            r_lo, r_hi = max(0, r - radius), min(h, r + radius + 1)
            c_lo, c_hi = max(0, c - radius), min(w, c + radius + 1)
            near_mask[r_lo:r_hi, c_lo:c_hi] = True
        near_mask = near_mask & ~marker_mask  # exclude exact matches
        near_count = int(np.sum(post_prime_mask & near_mask))
        print(f"     Within {radius}px of marker (not exact):  {near_count:>8,}")

    # ── WHAT HAPPENED TO THE INJECTED DISTANCES? ──
    print(f"\n  3. WHAT HAPPENED TO INJECTED DISTANCES AFTER JPEG?")

    # For each marker, compare pre vs post R-G distance
    shifts = []
    survived_exact = 0
    survived_fuzzy1 = 0
    survived_fuzzy2 = 0
    destroyed = 0

    for r, c in all_injected:
        if 0 <= r < h and 0 <= c < w:
            pre_d = pre_rg[r, c]
            post_d = post_rg[r, c]
            shift = post_d - pre_d
            shifts.append(shift)

            if pre_d == post_d:
                survived_exact += 1
            elif abs(shift) <= 1 and post_d <= 255 and prime_lookup[post_d]:
                survived_fuzzy1 += 1
            elif abs(shift) <= 2 and post_d <= 255 and prime_lookup[post_d]:
                survived_fuzzy2 += 1
            else:
                destroyed += 1

    shifts = np.array(shifts)
    n = len(shifts)

    print(f"     Survived exact (same prime):   {survived_exact:>8,} ({survived_exact/n*100:.1f}%)")
    print(f"     Survived fuzzy ±1 (still prime): {survived_fuzzy1:>8,} ({survived_fuzzy1/n*100:.1f}%)")
    print(f"     Survived fuzzy ±2 (still prime): {survived_fuzzy2:>8,} ({survived_fuzzy2/n*100:.1f}%)")
    print(f"     Destroyed (no longer prime):   {destroyed:>8,} ({destroyed/n*100:.1f}%)")

    print(f"\n     Distance shift distribution:")
    print(f"       Mean shift:   {np.mean(shifts):+.2f}")
    print(f"       Median shift: {int(np.median(shifts)):+d}")
    print(f"       Std shift:    {np.std(shifts):.2f}")
    print(f"       Min/Max:      {int(np.min(shifts)):+d} / {int(np.max(shifts)):+d}")

    # Histogram of shifts
    shift_counts = Counter(shifts.tolist())
    print(f"\n     Top shift values:")
    for shift_val, count in sorted(shift_counts.items(), key=lambda x: -x[1])[:15]:
        pct = count / n * 100
        bar = "#" * int(pct)
        print(f"       {int(shift_val):+4d}: {count:>6,} ({pct:>5.1f}%) {bar}")

    # ── PER-PRIME SURVIVAL ──
    print(f"\n  4. PER-PRIME SURVIVAL AFTER JPEG:")
    print(f"     {'Prime':>6s}  {'Injected':>8s}  {'Survived':>8s}  {'Rate':>6s}  {'Post-JPEG dist':>14s}")
    print(f"     " + "-" * 55)

    for prime in sorted(basket_set):
        prime_markers = [(m["row"], m["col"]) for m in markers if m["prime"] == prime]
        prime_twins = [(m["row"], m["twin_col"]) for m in markers
                       if "twin_prime" in m and m["twin_prime"] == prime and "twin_col" in m]
        positions_for_prime = prime_markers + prime_twins

        if not positions_for_prime:
            continue

        survived = 0
        post_dists = []
        for r, c in positions_for_prime:
            if 0 <= r < h and 0 <= c < w:
                post_d = post_rg[r, c]
                post_dists.append(post_d)
                if post_d <= 255 and prime_lookup[post_d]:
                    survived += 1

        rate = survived / len(positions_for_prime) if positions_for_prime else 0
        avg_post = np.mean(post_dists) if post_dists else 0
        print(f"     {prime:>6d}  {len(positions_for_prime):>8d}  {survived:>8d}  {rate:>5.1%}  {avg_post:>14.1f}")

    # ── CLEAN IMAGE BASELINE ──
    print(f"\n  5. CLEAN IMAGE BASELINE (no injection):")
    clean_rg = np.abs(pixels[:,:,0].astype(int) - pixels[:,:,1].astype(int))
    clean_prime_count = 0
    for r_idx in range(h):
        for c_idx in range(w):
            d = clean_rg[r_idx, c_idx]
            if d <= 255 and prime_lookup[d]:
                clean_prime_count += 1
    print(f"     Pixels with prime |R-G| >= {MIN_PRIME}: {clean_prime_count:,} ({clean_prime_count/total_pixels*100:.2f}%)")
    print(f"     Post-injection (pre-JPEG):          {pre_prime_count:,} ({pre_prime_count/total_pixels*100:.2f}%)")
    print(f"     Post-JPEG:                          {post_prime_count:,} ({post_prime_count/total_pixels*100:.2f}%)")

    print()


if __name__ == "__main__":
    run()
