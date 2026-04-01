#!/usr/bin/env python3
"""
Density Sweep — Blind detection vs marker density (10%-90% of grid)
====================================================================
Uses one DIV2K image. For each density level:
  1. Inject with embed_compound at that density
  2. Save as JPEG (with DQT)
  3. Blind verify with verify_image
  4. Report all signal checks
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MarkerConfig, MARKER_TYPES, build_rare_basket
from pgps_detector import sample_positions_grid
from dqt_prime import encode_prime_jpeg
from verify_image import verify_image

TEST_IMAGE = os.path.join(os.path.dirname(__file__), '..', 'test-images', '0538.png')
WINDOW_W = 8


def run_density_sweep():
    img = Image.open(TEST_IMAGE).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape

    grid_size = len(sample_positions_grid(h, w, WINDOW_W))

    print()
    print("=" * 130)
    print(f"DENSITY SWEEP — Blind Detection vs Marker Density")
    print(f"  Image:     {os.path.basename(TEST_IMAGE)} ({w}x{h})")
    print(f"  Grid size: {grid_size} positions (window={WINDOW_W})")
    print("=" * 130)
    print()
    print(f"  {'Density':>7s}  {'n_mark':>6s}  {'Placed':>6s}  "
          f"{'Verdict':<14s}  {'Sigs':>4s}  "
          f"{'DQT':>5s}  {'PrimeRate':>9s}  {'TwinRate':>9s}  "
          f"{'MagicRate':>9s}  {'PrEnrich':>8s}  {'Twins':>5s}  {'Magic':>5s}")
    print("  " + "-" * 120)

    densities = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]

    with tempfile.TemporaryDirectory() as tmpdir:
        for density in densities:
            n_markers = int(grid_size * density)

            config = MarkerConfig(
                name=f"compound_d{int(density*100)}",
                description=f"Compound at {density:.0%} density",
                min_prime=53,
                use_twins=True,
                use_magic=True,
                use_rare_basket=True,
                rare_min_gap=4,
                n_markers=n_markers,
            )

            try:
                modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)
            except Exception as e:
                print(f"  {density:>6.0%}  {n_markers:>6d}  {'FAIL':>6s}  {str(e)}")
                continue

            placed = len(markers)

            # Save as JPEG with DQT
            modified_clipped = np.clip(modified, 0, 255).astype(np.uint8)
            jpeg_path = os.path.join(tmpdir, f"sweep_{int(density*100)}.jpg")
            encode_prime_jpeg(modified_clipped, quality=95, output_path=jpeg_path)

            # Blind verify
            vr = verify_image(jpeg_path)
            ck = vr["checks"]

            dqt_yn = "YES" if ck["dqt_primes"].get("detected") else "no"
            pr = ck["prime_enrichment"].get("prime_hit_rate", 0)
            tr = ck["twin_pairs"].get("twin_rate", 0)
            mr = ck["magic_sentinels"].get("magic_rate", 0)
            pe_yn = "YES" if ck["prime_enrichment"].get("detected") else "no"
            tw_yn = "YES" if ck["twin_pairs"].get("detected") else "no"
            mg_yn = "YES" if ck["magic_sentinels"].get("detected") else "no"

            print(f"  {density:>6.0%}  {n_markers:>6d}  {placed:>6d}  "
                  f"{vr['verdict']:<14s}  {vr['signal_count']:>4d}  "
                  f"{dqt_yn:>5s}  {pr:>9.4f}  {tr:>9.6f}  "
                  f"{mr:>9.6f}  {pe_yn:>8s}  {tw_yn:>5s}  {mg_yn:>5s}")

    print()
    print("  Thresholds: PrimeEnrich > 0.20 | TwinRate > 0.04 | MagicRate > 0.008")
    print()


if __name__ == "__main__":
    run_density_sweep()
