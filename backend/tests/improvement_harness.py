#!/usr/bin/env python3
"""
Improvement Comparison Harness
================================
Runs the adversarial attack suite with different VerifyConfig flag
combinations and produces a side-by-side comparison matrix.

Configurations tested:
  baseline      — current behavior (no flags)
  bidir         — bidirectional chain following
  allphase      — all 64 grid phase combinations
  lowthresh     — chain threshold 5 + corroboration
  combined      — all three improvements together

Usage:
    python backend/tests/improvement_harness.py                          # default 5 images
    python backend/tests/improvement_harness.py --images 0057 0348 0588  # specific images
    python backend/tests/improvement_harness.py -o /tmp/results          # save JSON
"""

import sys
import os
import time
import json
import argparse
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import embed_compound, MARKER_TYPES
from halo import embed_halos_from_sentinels, HALO_RADIUS
from verify_image import verify_image, VerifyConfig

TEST_DIR = os.path.join(os.path.dirname(__file__), '..', 'test-images')

# =========================================================================
# CONFIG PRESETS
# =========================================================================

CONFIGS = {
    "baseline": VerifyConfig(),
    "bidir": VerifyConfig(bidirectional=True),
    "allphase": VerifyConfig(all_phases=True),
    "lowthresh": VerifyConfig(chain_threshold=5, corroborate_weak=True),
    "combined": VerifyConfig(
        bidirectional=True,
        all_phases=True,
        chain_threshold=5,
        corroborate_weak=True,
    ),
}

# =========================================================================
# ATTACK SUITE (same as adversarial_harness.py)
# =========================================================================

def embed_all_layers(pixels):
    """Embed Layer 2 (chains) + Layer G (halos)."""
    h, w = pixels.shape[:2]
    config = MARKER_TYPES['compound']
    modified, markers, sentinels = embed_compound(pixels, config)
    l2 = np.clip(modified, 0, 255).astype(np.uint8)

    placed = [s for s in sentinels if s.get('placed')]
    hc = [(s['row'], s['col']) for s in placed
          if HALO_RADIUS <= s['row'] < h - HALO_RADIUS
          and HALO_RADIUS <= s['col'] < w - HALO_RADIUS]
    mod_img = embed_halos_from_sentinels(Image.fromarray(l2), hc)

    chain_markers = [m for m in markers
                     if isinstance(m, dict) and m.get('type') == 'chain_link']

    return np.array(mod_img), {
        'chain_links': len(chain_markers),
        'halos': len(hc),
    }


def psnr(a, b):
    d = a.astype(float) - b.astype(float)
    mse = np.mean(d ** 2)
    return 10 * np.log10(255 ** 2 / mse) if mse > 0 else float('inf')


def verify_array(arr, config, suffix='.png', quality=None):
    """Save array to temp file and run verify_image with given config."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        img = Image.fromarray(arr)
        if suffix == '.jpg' and quality:
            img.save(f.name, 'JPEG', quality=quality)
        else:
            img.save(f.name)
        report = verify_image(f.name, config=config)
        os.unlink(f.name)
    return report


def extract_verdict(report):
    pe = report['checks'].get('prime_enrichment', {})
    return {
        'verdict': report['verdict'],
        'signals': report['signal_count'],
        'chain': pe.get('longest_chain', 0),
        'chain_det': pe.get('detected', False),
        'corroborated': pe.get('corroborated', False),
        'dqt': report['checks'].get('dqt_primes', {}).get('detected', False),
        'halos': report['checks'].get('radial_halos', {}).get('detected', False),
    }

# =========================================================================
# ATTACK DEFINITIONS
# =========================================================================

def gen_attacks(embedded):
    """Yield (attack_name, pixel_array, save_suffix, jpeg_quality) tuples."""
    h, w = embedded.shape[:2]
    img = Image.fromarray(embedded)

    # Compression
    for q_label, suffix, quality in [
        ('comp/lossless', '.png', None),
        ('comp/Q95', '.jpg', 95),
        ('comp/Q85', '.jpg', 85),
        ('comp/Q75', '.jpg', 75),
        ('comp/Q60', '.jpg', 60),
    ]:
        yield q_label, embedded, suffix, quality

    # Rotation
    for angle in [5, 15, 45, 90, 180]:
        rotated = np.array(img.rotate(angle, resample=Image.BILINEAR, expand=False))
        yield f'rot/{angle}deg', rotated, '.png', None

    # Flip
    yield 'flip/horizontal', np.array(img.transpose(Image.FLIP_LEFT_RIGHT)), '.png', None
    yield 'flip/vertical', np.array(img.transpose(Image.FLIP_TOP_BOTTOM)), '.png', None

    # Crop
    margin_x = int(w * 0.10)
    margin_y = int(h * 0.10)
    yield 'crop/left_10pct', embedded[:, margin_x:, :], '.png', None
    yield 'crop/right_10pct', embedded[:, :w - margin_x, :], '.png', None
    yield 'crop/top_10pct', embedded[margin_y:, :, :], '.png', None
    yield 'crop/bottom_10pct', embedded[:h - margin_y, :, :], '.png', None

    # Slice quadrants
    sx = int(w * 0.40)
    sy = int(h * 0.45)
    yield 'slice/top_left', embedded[:sy, :sx, :], '.png', None
    yield 'slice/top_right', embedded[:sy, sx:, :], '.png', None
    yield 'slice/bottom_left', embedded[sy:, :sx, :], '.png', None
    yield 'slice/bottom_right', embedded[sy:, sx:, :], '.png', None


# =========================================================================
# MAIN HARNESS
# =========================================================================

def run_one_image(image_name, config_names=None):
    """Run all attacks x all configs on one image. Returns results dict."""
    path = os.path.join(TEST_DIR, f'{image_name}.png')
    if not os.path.exists(path):
        print(f"  SKIP: {path} not found")
        return None

    img = Image.open(path).convert('RGB')
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    # Embed
    t0 = time.time()
    embedded, meta = embed_all_layers(pixels)
    embed_time = time.time() - t0
    p = psnr(pixels, embedded)
    print(f"\n  {image_name}.png ({w}x{h}) — {meta['chain_links']} chains, "
          f"{meta['halos']} halos, PSNR={p:.1f} dB ({embed_time:.1f}s)")

    if config_names is None:
        config_names = list(CONFIGS.keys())

    # Pre-generate attacks (pixels are shared across configs)
    attacks = list(gen_attacks(embedded))

    results = {}
    for cfg_name in config_names:
        cfg = CONFIGS[cfg_name]
        cfg_results = {}
        t0 = time.time()

        for attack_name, arr, suffix, quality in attacks:
            report = verify_array(arr, cfg, suffix=suffix, quality=quality)
            cfg_results[attack_name] = extract_verdict(report)

        elapsed = time.time() - t0
        results[cfg_name] = cfg_results
        print(f"    {cfg_name:>12s}: {elapsed:.0f}s")

    return results


def score_config(results):
    """Count detections across all attacks for one config."""
    detected = sum(1 for v in results.values() if v['chain_det'])
    confirmed = sum(1 for v in results.values() if v['verdict'] == 'CONFIRMED')
    probable = sum(1 for v in results.values() if v['verdict'] == 'PROBABLE')
    partial = sum(1 for v in results.values() if v['verdict'] == 'PARTIAL')
    not_det = sum(1 for v in results.values() if v['verdict'] == 'NOT DETECTED')
    return {
        'chain_detected': detected,
        'CONFIRMED': confirmed,
        'PROBABLE': probable,
        'PARTIAL': partial,
        'NOT_DETECTED': not_det,
        'total': len(results),
    }


def print_comparison(all_results, config_names):
    """Print side-by-side comparison matrix."""
    # Collect all attack names from first image
    first_img = next(iter(all_results.values()))
    attack_names = list(first_img[config_names[0]].keys())

    print(f"\n{'=' * 120}")
    print("IMPROVEMENT COMPARISON MATRIX")
    print(f"{'=' * 120}")

    # Per-image comparison
    for img_name, img_results in all_results.items():
        print(f"\n  IMAGE: {img_name}")
        print(f"  {'Attack':>22s}", end='')
        for cfg in config_names:
            print(f" | {cfg:>12s}", end='')
        print()
        print(f"  {'-' * (22 + 15 * len(config_names))}")

        for attack in attack_names:
            row = f"  {attack:>22s}"
            for cfg in config_names:
                v = img_results[cfg][attack]
                c = v['chain']
                det = '*' if v['chain_det'] else ' '
                d = 'D' if v['dqt'] else '.'
                h_flag = 'H' if v['halos'] else '.'
                cor = '+' if v.get('corroborated') else ' '
                cell = f"c{c}{det}{cor}{d}{h_flag}"
                row += f" | {cell:>12s}"
            print(row)

    # Aggregate scores
    print(f"\n{'=' * 120}")
    print("AGGREGATE SCORES (across all images)")
    print(f"{'=' * 120}")

    totals = {cfg: {'chain_detected': 0, 'CONFIRMED': 0, 'PROBABLE': 0,
                     'PARTIAL': 0, 'NOT_DETECTED': 0, 'total': 0}
              for cfg in config_names}

    for img_name, img_results in all_results.items():
        for cfg in config_names:
            s = score_config(img_results[cfg])
            for k in totals[cfg]:
                totals[cfg][k] += s[k]

    print(f"\n  {'Metric':>20s}", end='')
    for cfg in config_names:
        print(f" | {cfg:>12s}", end='')
    print()
    print(f"  {'-' * (20 + 15 * len(config_names))}")

    for metric in ['chain_detected', 'CONFIRMED', 'PROBABLE', 'PARTIAL', 'NOT_DETECTED', 'total']:
        row = f"  {metric:>20s}"
        for cfg in config_names:
            val = totals[cfg][metric]
            if metric == 'total':
                row += f" | {val:>12d}"
            else:
                pct = val / totals[cfg]['total'] * 100 if totals[cfg]['total'] > 0 else 0
                row += f" | {val:>5d} ({pct:4.1f}%)"
            print(row, end='')
            row = ''
        print()

    # Delta from baseline
    if 'baseline' in config_names:
        print(f"\n  DELTA vs BASELINE (chain_detected):")
        base = totals['baseline']['chain_detected']
        for cfg in config_names:
            if cfg == 'baseline':
                continue
            delta = totals[cfg]['chain_detected'] - base
            sign = '+' if delta >= 0 else ''
            print(f"    {cfg:>12s}: {sign}{delta} detections "
                  f"({base} → {totals[cfg]['chain_detected']})")

    print(f"\n  Legend: cN = chain length, * = chain detected, + = corroborated,")
    print(f"          D = DQT detected, H = halo detected, . = not detected")


def main():
    parser = argparse.ArgumentParser(description='Improvement comparison harness')
    parser.add_argument('--images', nargs='*', default=None,
                        help='Specific image names (without .png)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output directory for JSON results')
    parser.add_argument('--configs', nargs='*', default=None,
                        choices=list(CONFIGS.keys()),
                        help='Which configs to test (default: all)')
    args = parser.parse_args()

    # Default: 5 images spanning weak-to-strong
    if args.images:
        image_names = args.images
    else:
        image_names = ['0057', '0185', '0348', '0588', '0710']

    config_names = args.configs or list(CONFIGS.keys())

    n_attacks = 21  # compression(5) + rotation(5) + flip(2) + crop(4) + slice(4)
    total_verifications = len(image_names) * len(config_names) * n_attacks

    print("=" * 120)
    print(f"IMPROVEMENT COMPARISON HARNESS")
    print(f"  Images: {len(image_names)} | Configs: {len(config_names)} | "
          f"Attacks: {n_attacks} | Total verifications: {total_verifications}")
    print(f"  Configs: {', '.join(config_names)}")
    print("=" * 120)

    t_start = time.time()
    all_results = {}

    for name in image_names:
        result = run_one_image(name, config_names)
        if result:
            all_results[name] = result

    print_comparison(all_results, config_names)

    elapsed = time.time() - t_start
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed / 60:.1f} min)")

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, 'improvement_comparison.json'), 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"  Results saved to {args.output}/")


if __name__ == "__main__":
    main()
