#!/usr/bin/env python3
"""
Debug: What does the verifier actually see at each grid phase?
Breaks down prime hit rate by phase0 vs phase3 positions.
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MarkerConfig
from pgps_detector import sample_positions_grid, build_prime_lookup
from verify_image import _grid_positions_both_phases
from dqt_prime import encode_prime_jpeg

TEST_IMAGE = os.path.join(os.path.dirname(__file__), '..', 'test-images', '0538.png')
WINDOW_W = 8


def debug():
    img = Image.open(TEST_IMAGE).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape

    # Inject at 50% density
    grid_size = len(sample_positions_grid(h, w, WINDOW_W))
    config = MarkerConfig(
        name="compound_debug",
        description="Debug",
        min_prime=53,
        use_twins=True,
        use_magic=True,
        use_rare_basket=True,
        n_markers=int(grid_size * 0.50),
    )

    modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)
    placed = len(markers)
    marker_positions = set((m["row"], m["col"]) for m in markers)
    twin_positions = set((m["row"], m["twin_col"]) for m in markers if "twin_col" in m)
    all_injected = marker_positions | twin_positions

    # Save as JPEG and reload (what the verifier gets)
    modified_clipped = np.clip(modified, 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as tmpdir:
        jpeg_path = os.path.join(tmpdir, "debug.jpg")
        encode_prime_jpeg(modified_clipped, quality=95, output_path=jpeg_path)
        jpeg_pixels = np.array(Image.open(jpeg_path).convert("RGB"))

    prime_lookup = build_prime_lookup(8)
    prime_lookup[:37] = False

    # Get verifier grids
    phase0, phase3 = _grid_positions_both_phases(h, w)

    print()
    print("=" * 90)
    print("DEBUG — What the verifier sees at each grid phase")
    print(f"  Image: {os.path.basename(TEST_IMAGE)} ({w}x{h})")
    print(f"  Markers placed: {placed} (requested {config.n_markers})")
    print(f"  All injected positions (markers+twins): {len(all_injected)}")
    print("=" * 90)

    # For each phase, check:
    # 1. How many verifier positions overlap with injected positions?
    # 2. What's the prime hit rate at overlapping vs non-overlapping?
    for phase_name, positions in [("Phase 0 (raw grid)", phase0),
                                   ("Phase 3 (block center +3)", phase3)]:
        pos_set = set(positions)
        overlap = pos_set & all_injected
        non_overlap = pos_set - all_injected

        # On the pre-JPEG modified image
        def prime_rate_at(pos_list, px):
            hits = 0
            total = 0
            for r, c in pos_list:
                if 0 <= r < h and 0 <= c < w:
                    total += 1
                    d = abs(int(px[r, c, 0]) - int(px[r, c, 1]))
                    if d <= 255 and prime_lookup[d]:
                        hits += 1
            return hits, total

        # Pre-JPEG
        ov_hits_pre, ov_total_pre = prime_rate_at(overlap, modified_clipped)
        no_hits_pre, no_total_pre = prime_rate_at(non_overlap, modified_clipped)
        all_hits_pre, all_total_pre = prime_rate_at(positions, modified_clipped)

        # Post-JPEG
        ov_hits_post, ov_total_post = prime_rate_at(overlap, jpeg_pixels)
        no_hits_post, no_total_post = prime_rate_at(non_overlap, jpeg_pixels)
        all_hits_post, all_total_post = prime_rate_at(positions, jpeg_pixels)

        print(f"\n  {phase_name}:")
        print(f"    Total positions:    {len(positions)}")
        print(f"    Overlap w/markers:  {len(overlap)} ({len(overlap)/len(positions)*100:.1f}%)")
        print(f"    Non-overlap:        {len(non_overlap)}")
        print()
        print(f"    {'':30s}  {'Pre-JPEG':>10s}  {'Post-JPEG Q95':>14s}")
        print(f"    {'Overlap prime rate':30s}  {ov_hits_pre/ov_total_pre if ov_total_pre else 0:>10.4f}  {ov_hits_post/ov_total_post if ov_total_post else 0:>14.4f}")
        print(f"    {'Non-overlap prime rate':30s}  {no_hits_pre/no_total_pre if no_total_pre else 0:>10.4f}  {no_hits_post/no_total_post if no_total_post else 0:>14.4f}")
        print(f"    {'COMBINED (what verifier sees)':30s}  {all_hits_pre/all_total_pre if all_total_pre else 0:>10.4f}  {all_hits_post/all_total_post if all_total_post else 0:>14.4f}")
        print(f"    {'Threshold':30s}  {'0.2000':>10s}  {'0.2000':>14s}")

    # Also check: what do markers look like on the JPEG image?
    print(f"\n  AT ACTUAL MARKER POSITIONS (not grid-aligned):")
    hits_pre = sum(1 for r, c in all_injected
                   if 0 <= r < h and 0 <= c < w
                   and abs(int(modified_clipped[r, c, 0]) - int(modified_clipped[r, c, 1])) <= 255
                   and prime_lookup[abs(int(modified_clipped[r, c, 0]) - int(modified_clipped[r, c, 1]))])
    hits_post = sum(1 for r, c in all_injected
                    if 0 <= r < h and 0 <= c < w
                    and abs(int(jpeg_pixels[r, c, 0]) - int(jpeg_pixels[r, c, 1])) <= 255
                    and prime_lookup[abs(int(jpeg_pixels[r, c, 0]) - int(jpeg_pixels[r, c, 1]))])
    print(f"    Pre-JPEG:  {hits_pre}/{len(all_injected)} = {hits_pre/len(all_injected):.4f}")
    print(f"    Post-JPEG: {hits_post}/{len(all_injected)} = {hits_post/len(all_injected):.4f}")

    print()


if __name__ == "__main__":
    debug()
