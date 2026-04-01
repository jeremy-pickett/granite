#!/usr/bin/env python3
"""
Adversarial Test Harness
==========================
Embeds all layers into each DIV2K test image, then throws every attack
at it and records what survives.

Attack matrix per image:
  1. COMPRESSION  — verify at Q95, Q85, Q75, Q60, lossless PNG
  2. ROTATION     — 5°, 15°, 45°, 90°, 180°
  3. FLIP         — horizontal, vertical
  4. CROP         — 10% off each edge (left, right, top, bottom)
  5. SLICE        — cut into 4 unequal quadrants, verify each independently
  6. STITCH       — reassemble the 4 slices, verify the reconstruction

Usage:
    python backend/tests/adversarial_harness.py                    # all test images
    python backend/tests/adversarial_harness.py --images 0259 0487 # specific images
    python backend/tests/adversarial_harness.py --quick            # first 2 images only
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

from compound_markers import embed_compound, MARKER_TYPES, _pixel_luma
from halo import embed_halos_from_sentinels, HALO_RADIUS
from verify_image import verify_image

TEST_DIR = os.path.join(os.path.dirname(__file__), '..', 'test-images')


def psnr(a, b):
    d = a.astype(float) - b.astype(float)
    mse = np.mean(d ** 2)
    return 10 * np.log10(255 ** 2 / mse) if mse > 0 else float('inf')


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
    chains_info = [m for m in markers if isinstance(m, dict) and '_chains' in m]

    return np.array(mod_img), {
        'chain_links': len(chain_markers),
        'halos': len(hc),
        'chains': [c['length'] for c in chains_info[0]['_chains']] if chains_info else [],
    }


def verify_array(arr, suffix='.png', quality=None):
    """Save array to temp file and run verify_image. Returns the report dict."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        img = Image.fromarray(arr)
        if suffix == '.jpg' and quality:
            img.save(f.name, 'JPEG', quality=quality)
        else:
            img.save(f.name)
        report = verify_image(f.name)
        os.unlink(f.name)
    return report


def extract_verdict(report):
    """Pull key fields from a verify report."""
    pe = report['checks'].get('prime_enrichment', {})
    return {
        'verdict': report['verdict'],
        'signals': report['signal_count'],
        'chain': pe.get('longest_chain', 0),
        'chain_det': pe.get('detected', False),
        'dqt': report['checks'].get('dqt_primes', {}).get('detected', False),
    }


def run_compression(embedded, label_prefix=''):
    """Test across compression levels."""
    results = {}
    for q_label, suffix, quality in [
        ('lossless', '.png', None),
        ('Q95', '.jpg', 95),
        ('Q85', '.jpg', 85),
        ('Q75', '.jpg', 75),
        ('Q60', '.jpg', 60),
    ]:
        r = verify_array(embedded, suffix=suffix, quality=quality)
        v = extract_verdict(r)
        results[q_label] = v
    return results


def run_rotation(embedded):
    """Test rotation attacks."""
    results = {}
    img = Image.fromarray(embedded)
    for angle in [5, 15, 45, 90, 180]:
        rotated = np.array(img.rotate(angle, resample=Image.BILINEAR, expand=False))
        r = verify_array(rotated)
        results[f'{angle}deg'] = extract_verdict(r)
    return results


def run_flip(embedded):
    """Test horizontal and vertical flip."""
    results = {}
    img = Image.fromarray(embedded)

    flipped_h = np.array(img.transpose(Image.FLIP_LEFT_RIGHT))
    results['horizontal'] = extract_verdict(verify_array(flipped_h))

    flipped_v = np.array(img.transpose(Image.FLIP_TOP_BOTTOM))
    results['vertical'] = extract_verdict(verify_array(flipped_v))

    return results


def run_crop(embedded):
    """Crop 10% off each edge independently."""
    h, w = embedded.shape[:2]
    margin_x = int(w * 0.10)
    margin_y = int(h * 0.10)
    results = {}

    crops = {
        'left_10pct':   embedded[:, margin_x:, :],
        'right_10pct':  embedded[:, :w - margin_x, :],
        'top_10pct':    embedded[margin_y:, :, :],
        'bottom_10pct': embedded[:h - margin_y, :, :],
    }
    for name, cropped in crops.items():
        results[name] = extract_verdict(verify_array(cropped))
    return results


def run_slice_and_stitch(embedded):
    """
    Slice into 4 unequal quadrants, verify each, then stitch back
    and verify the reconstruction.

    Split point: 40% width, 45% height (intentionally unequal).
    """
    h, w = embedded.shape[:2]
    sx = int(w * 0.40)  # 40% from left
    sy = int(h * 0.45)  # 45% from top

    # Four quadrants
    q_tl = embedded[:sy, :sx, :]        # top-left
    q_tr = embedded[:sy, sx:, :]        # top-right
    q_bl = embedded[sy:, :sx, :]        # bottom-left
    q_br = embedded[sy:, sx:, :]        # bottom-right

    results = {'slices': {}, 'stitch': {}}

    # Verify each slice independently
    for name, quad in [('top_left', q_tl), ('top_right', q_tr),
                       ('bottom_left', q_bl), ('bottom_right', q_br)]:
        qh, qw = quad.shape[:2]
        results['slices'][name] = {
            **extract_verdict(verify_array(quad)),
            'size': f'{qw}x{qh}',
        }

    # Stitch back together
    top_row = np.concatenate([q_tl, q_tr], axis=1)
    bottom_row = np.concatenate([q_bl, q_br], axis=1)
    stitched = np.concatenate([top_row, bottom_row], axis=0)

    results['stitch'] = {
        **extract_verdict(verify_array(stitched)),
        'matches_original': np.array_equal(stitched, embedded),
    }

    return results


def print_table(title, results, columns=None):
    """Print a results dict as a formatted table."""
    if not results:
        return
    if columns is None:
        columns = ['verdict', 'signals', 'chain', 'dqt']

    print(f"\n  {title}")
    header = f"    {'Attack':>16s}"
    for col in columns:
        header += f" | {col:>8s}"
    print(header)
    print(f"    {'-' * (len(header) - 4)}")

    for attack, vals in results.items():
        if isinstance(vals, dict) and 'verdict' in vals:
            row = f"    {attack:>16s}"
            for col in columns:
                v = vals.get(col, '')
                if isinstance(v, bool):
                    v = 'YES' if v else 'no'
                row += f" | {str(v):>8s}"
            print(row)


def run_image(image_name, output_dir=None):
    """Run the full adversarial suite on one image."""
    path = os.path.join(TEST_DIR, f'{image_name}.png')
    if not os.path.exists(path):
        print(f"  SKIP: {path} not found")
        return None

    img = Image.open(path).convert('RGB')
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    print(f"\n{'=' * 80}")
    print(f"IMAGE: {image_name}.png ({w}x{h})")
    print(f"{'=' * 80}")

    # Embed
    t0 = time.time()
    embedded, meta = embed_all_layers(pixels)
    embed_time = time.time() - t0
    p = psnr(pixels, embedded)
    print(f"  Embed: {meta['chain_links']} chain links, {meta['halos']} halos, "
          f"chains={meta['chains']}, PSNR={p:.1f} dB ({embed_time:.1f}s)")

    all_results = {'meta': {**meta, 'psnr': round(p, 1), 'size': f'{w}x{h}'}}

    # 1. Compression
    t0 = time.time()
    comp = run_compression(embedded)
    all_results['compression'] = comp
    print_table('COMPRESSION', comp)
    print(f"    ({time.time() - t0:.1f}s)")

    # 2. Rotation
    t0 = time.time()
    rot = run_rotation(embedded)
    all_results['rotation'] = rot
    print_table('ROTATION', rot)
    print(f"    ({time.time() - t0:.1f}s)")

    # 3. Flip
    t0 = time.time()
    flip = run_flip(embedded)
    all_results['flip'] = flip
    print_table('FLIP', flip)
    print(f"    ({time.time() - t0:.1f}s)")

    # 4. Crop
    t0 = time.time()
    crop = run_crop(embedded)
    all_results['crop'] = crop
    print_table('CROP', crop)
    print(f"    ({time.time() - t0:.1f}s)")

    # 5. Slice & Stitch
    t0 = time.time()
    ss = run_slice_and_stitch(embedded)
    all_results['slice_stitch'] = ss
    print_table('SLICES', ss['slices'], columns=['verdict', 'signals', 'chain', 'dqt', 'size'])
    print(f"\n    Stitch: {ss['stitch']['verdict']} "
          f"chain={ss['stitch']['chain']} "
          f"matches_original={ss['stitch']['matches_original']}")
    print(f"    ({time.time() - t0:.1f}s)")

    # Save results JSON
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, f'{image_name}_adversarial.json'), 'w') as f:
            json.dump(all_results, f, indent=2, default=str)

    return all_results


def print_summary(all_results):
    """Print a cross-image summary matrix."""
    print(f"\n\n{'=' * 80}")
    print("SUMMARY MATRIX")
    print(f"{'=' * 80}")

    attacks = []
    # Compression
    for q in ['lossless', 'Q95', 'Q85', 'Q75', 'Q60']:
        attacks.append(('comp', q))
    # Rotation
    for a in ['5deg', '15deg', '45deg', '90deg', '180deg']:
        attacks.append(('rot', a))
    # Flip
    for f in ['horizontal', 'vertical']:
        attacks.append(('flip', f))
    # Crop
    for c in ['left_10pct', 'right_10pct', 'top_10pct', 'bottom_10pct']:
        attacks.append(('crop', c))
    # Slice
    for s in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
        attacks.append(('slice', s))
    attacks.append(('stitch', 'reassembled'))

    images = list(all_results.keys())

    # Header
    header = f"{'Attack':>20s}"
    for img in images:
        header += f" | {img:>8s}"
    print(f"\n{header}")
    print("-" * len(header))

    for category, attack in attacks:
        row = f"{category + '/' + attack:>20s}"
        for img in images:
            res = all_results[img]
            if category == 'comp':
                v = res.get('compression', {}).get(attack, {})
            elif category == 'rot':
                v = res.get('rotation', {}).get(attack, {})
            elif category == 'flip':
                v = res.get('flip', {}).get(attack, {})
            elif category == 'crop':
                v = res.get('crop', {}).get(attack, {})
            elif category == 'slice':
                v = res.get('slice_stitch', {}).get('slices', {}).get(attack, {})
            elif category == 'stitch':
                v = res.get('slice_stitch', {}).get('stitch', {})
            else:
                v = {}

            if isinstance(v, dict) and 'chain' in v:
                # Show chain length and whether DQT detected
                c = v.get('chain', 0)
                d = 'D' if v.get('dqt') else '.'
                det = '*' if v.get('chain_det') else ' '
                cell = f"c{c}{det}{d}"
            else:
                cell = '--'
            row += f" | {cell:>8s}"
        print(row)

    print(f"\n  Legend: cN = chain length, * = chain detected, D = DQT detected, . = no DQT")


def main():
    parser = argparse.ArgumentParser(description='Adversarial test harness')
    parser.add_argument('--images', nargs='*', default=None,
                        help='Specific image names (without .png)')
    parser.add_argument('--quick', action='store_true',
                        help='Run on first 2 images only')
    parser.add_argument('-o', '--output', default=None,
                        help='Output directory for JSON results')
    args = parser.parse_args()

    # Find test images
    if args.images:
        image_names = args.images
    else:
        image_names = sorted([
            f.replace('.png', '') for f in os.listdir(TEST_DIR)
            if f.endswith('.png')
        ])

    if args.quick:
        image_names = image_names[:2]

    print("=" * 80)
    print(f"ADVERSARIAL TEST HARNESS — {len(image_names)} images")
    print(f"Attacks: compression(5) + rotation(5) + flip(2) + crop(4) + slice(4) + stitch(1)")
    print(f"Total tests: {len(image_names) * 21} verifications")
    print("=" * 80)

    t_start = time.time()
    all_results = {}

    for name in image_names:
        result = run_image(name, args.output)
        if result:
            all_results[name] = result

    print_summary(all_results)

    elapsed = time.time() - t_start
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed / 60:.1f} min)")

    # Save combined results
    if args.output:
        with open(os.path.join(args.output, 'adversarial_summary.json'), 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"  Results saved to {args.output}/")


if __name__ == "__main__":
    main()
