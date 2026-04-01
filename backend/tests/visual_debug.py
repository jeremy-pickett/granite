#!/usr/bin/env python3
"""
Visual Debug: entropy map, chain overlay, diff amplification
==============================================================
Uses DIV2K test images only.  All heatmaps normalized to 0-255.
"""

import sys
import os
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import (
    embed_compound, MARKER_TYPES, _pixel_luma,
    entropy_gate_positions, ENTROPY_BLOCK_SIZE,
)
from smart_embedder import compute_local_entropy_fast
from halo import embed_halos_from_sentinels, HALO_RADIUS
from pgps_detector import sample_positions_grid


def normalize_to_uint8(arr):
    """Normalize any float array to 0-255 uint8."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-10:
        return np.zeros_like(arr, dtype=np.uint8)
    return ((arr - mn) / (mx - mn) * 255).astype(np.uint8)


def run(image_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(image_path))[0]

    img = Image.open(image_path).convert('RGB')
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    print(f"Image: {name} ({w}x{h})")

    # --- 1. Entropy heatmap (normalized to 0-255) ---
    entropy_map = compute_local_entropy_fast(pixels, block_size=ENTROPY_BLOCK_SIZE)
    entropy_vis = normalize_to_uint8(entropy_map)
    Image.fromarray(entropy_vis, mode='L').save(
        os.path.join(output_dir, f'{name}_entropy.png'))
    print(f"  Entropy: min={entropy_map.min():.1f} max={entropy_map.max():.1f} "
          f"mean={entropy_map.mean():.1f}")

    # --- 2. Entropy gate visualization ---
    # Green = gated (will embed), Red = rejected (flat/face)
    all_pos = sample_positions_grid(h, w, 8)
    bc = [(min(int(p[0]) + 3, h - 1), min(int(p[1]) + 3, w - 2))
          for p in all_pos if int(p[1]) + 4 < w]
    gated = entropy_gate_positions(pixels, bc, h, w)
    gated_set = set(gated)
    rejected = [(r, c) for r, c in bc if (r, c) not in gated_set]

    gate_overlay = pixels.copy()
    for r, c in gated:
        gate_overlay[r, c] = [0, 200, 0]  # green dot
    for r, c in rejected:
        gate_overlay[r, c] = [200, 0, 0]  # red dot
    Image.fromarray(gate_overlay).save(
        os.path.join(output_dir, f'{name}_entropy_gate.png'))
    print(f"  Gate: {len(gated)} passed (green), {len(rejected)} rejected (red)")

    # --- 3. Embed and save ---
    config = MARKER_TYPES['compound']
    modified, markers, sentinels = embed_compound(pixels, config)
    l2 = np.clip(modified, 0, 255).astype(np.uint8)

    chain_markers = [m for m in markers
                     if isinstance(m, dict) and m.get('type') == 'chain_link']
    chains_info = [m for m in markers if isinstance(m, dict) and '_chains' in m]
    chain_lengths = [c['length'] for c in chains_info[0]['_chains']] if chains_info else []

    # Halos
    placed = [s for s in sentinels if s.get('placed')]
    hc = [(s['row'], s['col']) for s in placed
          if HALO_RADIUS <= s['row'] < h - HALO_RADIUS
          and HALO_RADIUS <= s['col'] < w - HALO_RADIUS]
    mod_img = embed_halos_from_sentinels(Image.fromarray(l2), hc)
    embedded = np.array(mod_img)

    def psnr(a, b):
        d = a.astype(float) - b.astype(float)
        mse = np.mean(d ** 2)
        return 10 * np.log10(255 ** 2 / mse) if mse > 0 else float('inf')

    print(f"  Embedded: {len(chain_markers)} chain links, chains={chain_lengths}, "
          f"{len(hc)} halos, PSNR={psnr(pixels, embedded):.1f} dB")

    # Save original and embedded side by side
    img.save(os.path.join(output_dir, f'{name}_original.png'))
    mod_img.save(os.path.join(output_dir, f'{name}_embedded.png'))

    # --- 4. Difference map (30x amplified, normalized) ---
    diff = embedded.astype(np.int16) - pixels.astype(np.int16)
    diff_abs = np.abs(diff).astype(float)
    # Per-channel amplified diff centered at 128
    diff_vis = np.clip(diff * 30 + 128, 0, 255).astype(np.uint8)
    Image.fromarray(diff_vis).save(
        os.path.join(output_dir, f'{name}_diff_30x.png'))

    # Also save normalized absolute diff (shows WHERE changes are)
    diff_magnitude = np.sqrt(np.sum(diff.astype(float) ** 2, axis=2))
    diff_norm = normalize_to_uint8(diff_magnitude)
    Image.fromarray(diff_norm, mode='L').save(
        os.path.join(output_dir, f'{name}_diff_magnitude.png'))

    # --- 5. Chain overlay ---
    # Draw chain links as colored lines on the image
    chain_overlay = pixels.copy()
    draw_img = Image.fromarray(chain_overlay)
    draw = ImageDraw.Draw(draw_img)
    chain_colors = [(255, 50, 50), (50, 255, 50), (50, 50, 255)]

    for m in chain_markers:
        cid = m.get('chain_id', 0)
        r, c = m['row'], m['col']
        color = chain_colors[cid % len(chain_colors)]
        draw.rectangle([c - 1, r - 1, c + 1, r + 1], fill=color)

    draw_img.save(os.path.join(output_dir, f'{name}_chains.png'))

    # --- 6. Adjustment histogram ---
    if chain_markers:
        adjs = [m['adjustment'] for m in chain_markers]
        print(f"  Adjustments: mean={np.mean(adjs):.1f} median={np.median(adjs):.0f} "
              f"max={max(adjs)} adj<=3: {sum(1 for a in adjs if a <= 3)} "
              f"adj<=5: {sum(1 for a in adjs if a <= 5)}")

    print(f"  Saved to {output_dir}/")
    return embedded, markers, chain_markers


if __name__ == "__main__":
    out = '/tmp/granite_visual_debug'
    for name in ['0057', '0185', '0259', '0348', '0487']:
        path = f'backend/test-images/{name}.png'
        if os.path.exists(path):
            run(path, out)
            print()
