#!/usr/bin/env python3
"""
Halo Detection Heatmap
========================
Visualises what the radial halo detector sees on any image (injected or clean).
Produces a heatmap overlay showing:
  - PRESENT centers (green circles with amplitude label)
  - VOID centers (red circles)
  - Inner density field (blue heat)
  - Outer density field (orange heat)

Used for debugging false positives and understanding natural image structure.
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))

from halo import (
    detect_halo_centers, HaloState,
    _abs_rg, _target_mask, _disk_density,
    INNER_TARGET, OUTER_TARGET, VOTE_TOL,
    INNER_RADIUS, HALO_RADIUS, INNER_THRESH, OUTER_THRESH,
)


def generate_halo_heatmap(image_path: str, output_path: str):
    """Generate a multi-panel halo detection heatmap."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from matplotlib.colors import Normalize

    img = Image.open(image_path).convert("RGB")
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    name = os.path.splitext(os.path.basename(image_path))[0]

    # Compute the density fields the detector uses
    rg = _abs_rg(img)
    inner_mask = _target_mask(rg, INNER_TARGET, VOTE_TOL)
    outer_mask = _target_mask(rg, OUTER_TARGET, VOTE_TOL)
    inner_density = _disk_density(inner_mask, INNER_RADIUS)
    outer_density = _disk_density(outer_mask, HALO_RADIUS)

    # Detect centers
    centers = detect_halo_centers(img)
    present = [c for c in centers if c.state == HaloState.PRESENT]
    void = [c for c in centers if c.state == HaloState.VOID]

    # --- Build figure ---
    fig, axes = plt.subplots(2, 2, figsize=(20, 14), dpi=120)
    fig.patch.set_facecolor('#07090F')
    fig.suptitle(
        f"Halo Detection Heatmap — {name} ({w}x{h})\n"
        f"PRESENT: {len(present)}   VOID: {len(void)}   Total: {len(centers)}",
        fontsize=16, color='white', fontweight='bold',
    )

    # Panel 1: Original image with detected centers overlaid
    ax = axes[0, 0]
    ax.imshow(pixels)
    for c in present:
        circ = Circle((c.col, c.row), HALO_RADIUS, fill=False,
                       edgecolor='#00FF80', linewidth=1.5, alpha=0.9)
        ax.add_patch(circ)
        ax.text(c.col + HALO_RADIUS + 3, c.row, f"{c.amplitude:.2f}",
                fontsize=6, color='#00FF80', va='center')
    for c in void:
        circ = Circle((c.col, c.row), HALO_RADIUS, fill=False,
                       edgecolor='#FF4444', linewidth=1.2, alpha=0.7)
        ax.add_patch(circ)
    ax.set_title("Detected Centers", color='white', fontsize=12)
    _style(ax)

    # Panel 2: Inner density field
    ax = axes[0, 1]
    im = ax.imshow(inner_density, cmap='inferno', vmin=0,
                   vmax=max(0.5, float(inner_density.max())))
    ax.axhline(y=0, color='none')  # dummy for layout
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(colors='#888', labelsize=8)
    cbar.set_label('density', color='#888', fontsize=9)
    # Mark threshold
    ax.set_title(
        f"Inner Density (target={INNER_TARGET}, thresh={INNER_THRESH})",
        color='white', fontsize=12,
    )
    _style(ax)

    # Panel 3: Outer density field
    ax = axes[1, 0]
    im = ax.imshow(outer_density, cmap='magma', vmin=0,
                   vmax=max(0.5, float(outer_density.max())))
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(colors='#888', labelsize=8)
    cbar.set_label('density', color='#888', fontsize=9)
    ax.set_title(
        f"Outer Density (target={OUTER_TARGET}, thresh={OUTER_THRESH})",
        color='white', fontsize=12,
    )
    _style(ax)

    # Panel 4: |R-G| distance field with target bands highlighted
    ax = axes[1, 1]
    # Show where |R-G| is near inner or outer target
    combined = np.zeros((h, w, 3), dtype=np.float32)
    # Inner target matches in cyan
    combined[:, :, 1] += inner_mask * 0.8  # green
    combined[:, :, 2] += inner_mask * 0.8  # blue → cyan
    # Outer target matches in orange
    combined[:, :, 0] += outer_mask * 0.9  # red
    combined[:, :, 1] += outer_mask * 0.4  # green → orange
    combined = np.clip(combined, 0, 1)
    ax.imshow(combined)
    ax.set_title(
        f"|R-G| target matches: cyan=inner({INNER_TARGET}±{VOTE_TOL})  "
        f"orange=outer({OUTER_TARGET}±{VOTE_TOL})",
        color='white', fontsize=11,
    )
    _style(ax)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor='#07090F', edgecolor='none')
    plt.close()

    print(f"Halo heatmap saved: {output_path}")
    print(f"  PRESENT: {len(present)}  VOID: {len(void)}")
    if present:
        amps = sorted([c.amplitude for c in present], reverse=True)
        print(f"  Top amplitudes: {[round(a, 3) for a in amps[:10]]}")


def _style(ax):
    ax.tick_params(colors='#666', labelsize=7)
    for spine in ax.spines.values():
        spine.set_color('#333')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate halo detection heatmap for any image"
    )
    parser.add_argument("image", help="Path to image")
    parser.add_argument("-o", "--output", default=None,
                        help="Output path (default: <name>_halo_heatmap.png)")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(args.image)[0]
        args.output = f"{base}_halo_heatmap.png"

    generate_halo_heatmap(args.image, args.output)
