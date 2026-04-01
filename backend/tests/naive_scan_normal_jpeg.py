#!/usr/bin/env python3
"""
Same naive scan but comparing encode_prime_jpeg vs normal Pillow JPEG save.
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MarkerConfig, build_rare_basket
from pgps_detector import sample_positions_grid, build_prime_lookup
from dqt_prime import encode_prime_jpeg

TEST_IMAGE = os.path.join(os.path.dirname(__file__), '..', 'test-images', '0538.png')
WINDOW_W = 8
MIN_PRIME = 53


def scan_jpeg(label, jpeg_pixels, pre_rg, all_injected, markers, prime_lookup, h, w):
    post_rg = np.abs(jpeg_pixels[:,:,0].astype(int) - jpeg_pixels[:,:,1].astype(int))
    total_pixels = h * w

    # Count primes
    post_prime_mask = np.zeros((h, w), dtype=bool)
    for r in range(h):
        for c in range(w):
            d = post_rg[r, c]
            if d <= 255 and prime_lookup[d]:
                post_prime_mask[r, c] = True
    post_prime_count = int(np.sum(post_prime_mask))

    # Survival at marker positions
    shifts = []
    survived_exact = 0
    survived_fuzzy2 = 0
    for r, c in all_injected:
        if 0 <= r < h and 0 <= c < w:
            pre_d = int(pre_rg[r, c])
            post_d = int(post_rg[r, c])
            shift = post_d - pre_d
            shifts.append(shift)
            if prime_lookup[min(post_d, 255)]:
                if pre_d == post_d:
                    survived_exact += 1
                elif abs(shift) <= 2:
                    survived_fuzzy2 += 1

    shifts = np.array(shifts)
    n = len(shifts)

    print(f"\n  {label}:")
    print(f"    Prime pixels in image:  {post_prime_count:>8,} / {total_pixels:,} ({post_prime_count/total_pixels*100:.4f}%)")
    print(f"    Survived exact:         {survived_exact:>8,} / {n:,} ({survived_exact/n*100:.1f}%)")
    print(f"    Survived fuzzy ±2:      {survived_fuzzy2:>8,} / {n:,} ({survived_fuzzy2/n*100:.1f}%)")
    print(f"    Total surviving:        {survived_exact+survived_fuzzy2:>8,} / {n:,} ({(survived_exact+survived_fuzzy2)/n*100:.1f}%)")
    print(f"    Mean shift:             {np.mean(shifts):+.1f}")
    print(f"    Std shift:              {np.std(shifts):.1f}")
    print(f"    Median shift:           {int(np.median(shifts)):+d}")


def run():
    img = Image.open(TEST_IMAGE).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape
    grid_size = len(sample_positions_grid(h, w, WINDOW_W))

    config = MarkerConfig(
        name="test", description="test",
        min_prime=53, use_twins=True, use_magic=True,
        use_rare_basket=True, n_markers=int(grid_size * 0.50),
    )

    modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)
    modified = np.clip(modified, 0, 255).astype(np.uint8)

    marker_positions = set((m["row"], m["col"]) for m in markers)
    twin_positions = set((m["row"], m["twin_col"]) for m in markers if "twin_col" in m)
    all_injected = marker_positions | twin_positions

    pre_rg = np.abs(modified[:,:,0].astype(int) - modified[:,:,1].astype(int))

    prime_lookup = build_prime_lookup(8)
    prime_lookup[:MIN_PRIME] = False

    print()
    print("=" * 90)
    print("PRIME JPEG vs NORMAL JPEG — Which one kills the markers?")
    print(f"  Image: {os.path.basename(TEST_IMAGE)} ({w}x{h})")
    print(f"  Injected positions: {len(all_injected):,}")
    print("=" * 90)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. encode_prime_jpeg Q95
        prime_path = os.path.join(tmpdir, "prime_q95.jpg")
        encode_prime_jpeg(modified, quality=95, output_path=prime_path)
        prime_pixels = np.array(Image.open(prime_path).convert("RGB"))

        # 2. Normal Pillow JPEG Q95
        normal_path = os.path.join(tmpdir, "normal_q95.jpg")
        Image.fromarray(modified).save(normal_path, "JPEG", quality=95)
        normal_pixels = np.array(Image.open(normal_path).convert("RGB"))

        # 3. Normal Pillow JPEG Q100
        q100_path = os.path.join(tmpdir, "normal_q100.jpg")
        Image.fromarray(modified).save(q100_path, "JPEG", quality=100)
        q100_pixels = np.array(Image.open(q100_path).convert("RGB"))

        # 4. PNG (lossless round-trip)
        png_path = os.path.join(tmpdir, "lossless.png")
        Image.fromarray(modified).save(png_path, "PNG")
        png_pixels = np.array(Image.open(png_path).convert("RGB"))

        # 5. Normal JPEG Q95 with 4:4:4 (no chroma subsampling)
        q95_444_path = os.path.join(tmpdir, "normal_q95_444.jpg")
        Image.fromarray(modified).save(q95_444_path, "JPEG", quality=95, subsampling=0)
        q95_444_pixels = np.array(Image.open(q95_444_path).convert("RGB"))

        # 6. Normal JPEG Q100 with 4:4:4
        q100_444_path = os.path.join(tmpdir, "normal_q100_444.jpg")
        Image.fromarray(modified).save(q100_444_path, "JPEG", quality=100, subsampling=0)
        q100_444_pixels = np.array(Image.open(q100_444_path).convert("RGB"))

        # 7. JPEG Q85 4:4:4
        q85_444_path = os.path.join(tmpdir, "normal_q85_444.jpg")
        Image.fromarray(modified).save(q85_444_path, "JPEG", quality=85, subsampling=0)
        q85_444_pixels = np.array(Image.open(q85_444_path).convert("RGB"))

        # 8. JPEG Q75 4:4:4
        q75_444_path = os.path.join(tmpdir, "normal_q75_444.jpg")
        Image.fromarray(modified).save(q75_444_path, "JPEG", quality=75, subsampling=0)
        q75_444_pixels = np.array(Image.open(q75_444_path).convert("RGB"))

        # File sizes
        print(f"\n  File sizes:")
        for label, path in [("Prime JPEG Q95", prime_path),
                            ("Normal JPEG Q95 (4:2:0)", normal_path),
                            ("Normal JPEG Q100 (4:2:0)", q100_path),
                            ("JPEG Q95  4:4:4", q95_444_path),
                            ("JPEG Q100 4:4:4", q100_444_path),
                            ("JPEG Q85  4:4:4", q85_444_path),
                            ("JPEG Q75  4:4:4", q75_444_path),
                            ("PNG lossless", png_path)]:
            sz = os.path.getsize(path)
            print(f"    {label:<25s}  {sz:>10,} bytes")

        scan_jpeg("Prime JPEG Q95 (encode_prime_jpeg)", prime_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("Normal JPEG Q95 (4:2:0 default)", normal_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("Normal JPEG Q100 (4:2:0 default)", q100_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("JPEG Q95  4:4:4 (no chroma sub)", q95_444_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("JPEG Q100 4:4:4 (no chroma sub)", q100_444_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("JPEG Q85  4:4:4 (no chroma sub)", q85_444_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("JPEG Q75  4:4:4 (no chroma sub)", q75_444_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)
        scan_jpeg("PNG lossless round-trip", png_pixels, pre_rg, all_injected, markers, prime_lookup, h, w)

    print()


if __name__ == "__main__":
    run()
