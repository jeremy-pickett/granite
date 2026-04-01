#!/usr/bin/env python3
"""
Manifest-based detection accuracy across all encoding variants.
The question: if you HAVE the manifest, does detection work?
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MarkerConfig
from pgps_detector import sample_positions_grid, build_prime_lookup
from layer2_detect import layer2_detect
from dqt_prime import encode_prime_jpeg

TEST_IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'test-images')
WINDOW_W = 8


def test_one_image(img_path, tmpdir):
    img = Image.open(img_path).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape
    name = os.path.basename(img_path)

    grid_size = len(sample_positions_grid(h, w, WINDOW_W))
    config = MarkerConfig(
        name="compound", description="compound",
        min_prime=53, use_twins=True, use_magic=True,
        use_rare_basket=True, n_markers=int(grid_size * 0.50),
    )

    modified, markers, sentinels = embed_compound(pixels, config, variable_offset=42)
    modified = np.clip(modified, 0, 255).astype(np.uint8)

    # Build encoding variants
    variants = {}

    # PNG lossless
    p = os.path.join(tmpdir, f"{name}_png.png")
    Image.fromarray(modified).save(p, "PNG")
    variants["PNG lossless"] = np.array(Image.open(p).convert("RGB"))

    # JPEG 4:2:0 (Pillow default)
    for q in [100, 95, 85, 75]:
        p = os.path.join(tmpdir, f"{name}_420_q{q}.jpg")
        Image.fromarray(modified).save(p, "JPEG", quality=q)
        variants[f"JPEG Q{q} 4:2:0"] = np.array(Image.open(p).convert("RGB"))

    # JPEG 4:4:4
    for q in [100, 95, 85, 75]:
        p = os.path.join(tmpdir, f"{name}_444_q{q}.jpg")
        Image.fromarray(modified).save(p, "JPEG", quality=q, subsampling=0)
        variants[f"JPEG Q{q} 4:4:4"] = np.array(Image.open(p).convert("RGB"))

    # encode_prime_jpeg
    p = os.path.join(tmpdir, f"{name}_prime_q95.jpg")
    encode_prime_jpeg(modified, quality=95, output_path=p)
    variants["Prime JPEG Q95"] = np.array(Image.open(p).convert("RGB"))

    results = {}
    for label, px in variants.items():
        det = layer2_detect(px, markers, min_prime=53, channel_pair=(0, 1))
        results[label] = det

    return name, len(markers), results


def main():
    images = sorted(f for f in os.listdir(TEST_IMAGES_DIR) if f.endswith('.png'))

    print()
    print("=" * 130)
    print("MANIFEST-BASED DETECTION — How accurate is verify when you HAVE the marker positions?")
    print("=" * 130)

    # Run all images, collect results per variant
    variant_order = [
        "PNG lossless",
        "JPEG Q100 4:4:4", "JPEG Q95 4:4:4", "JPEG Q85 4:4:4", "JPEG Q75 4:4:4",
        "JPEG Q100 4:2:0", "JPEG Q95 4:2:0", "JPEG Q85 4:2:0", "JPEG Q75 4:2:0",
        "Prime JPEG Q95",
    ]

    all_results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for img_name in images:
            path = os.path.join(TEST_IMAGES_DIR, img_name)
            name, n_markers, results = test_one_image(path, tmpdir)
            all_results.append((name, n_markers, results))

    # Per-image table
    print(f"\n  {'Encoding':<22s}  ", end="")
    for name, _, _ in all_results:
        print(f"{name[:8]:>10s}", end="")
    print(f"  {'Avg':>8s}")
    print("  " + "-" * (24 + 10 * len(all_results) + 10))

    for variant in variant_order:
        print(f"  {variant:<22s}  ", end="")
        rates = []
        for name, n_markers, results in all_results:
            det = results[variant]
            detected = det["detected"]
            ratio = det["rate_ratio"]
            sym = f"{ratio:.1f}x" if detected else f"({ratio:.1f})"
            print(f"{sym:>10s}", end="")
            rates.append(ratio)
        avg = np.mean(rates)
        print(f"  {avg:>7.1f}x")

    # Detection rate summary
    print(f"\n  DETECTION RATE (detected=True at α=0.01):")
    print(f"  {'Encoding':<22s}  {'Detected':>8s}  {'Rate':>6s}  "
          f"{'Avg marker ρ':>12s}  {'Avg control ρ':>13s}  {'Avg ratio':>9s}  {'Avg χ² p':>10s}")
    print("  " + "-" * 95)

    for variant in variant_order:
        detected_count = 0
        marker_rates = []
        control_rates = []
        ratios = []
        pvals = []
        for name, n_markers, results in all_results:
            det = results[variant]
            if det["detected"]:
                detected_count += 1
            marker_rates.append(det["marker_hit_rate"])
            control_rates.append(det["control_hit_rate"])
            ratios.append(det["rate_ratio"])
            pvals.append(det["chi2_pvalue"])

        n = len(all_results)
        avg_p = np.mean(pvals)
        print(f"  {variant:<22s}  {detected_count:>4d}/{n:<3d}  {detected_count/n:>5.0%}  "
              f"{np.mean(marker_rates):>12.4f}  {np.mean(control_rates):>13.4f}  "
              f"{np.mean(ratios):>9.1f}x  {avg_p:>10.2e}")

    print()


if __name__ == "__main__":
    main()
