#!/usr/bin/env python3
"""
Injection Report Generator
============================
Produces heatmap + histogram visualizations showing what was injected where
across all Granite layers. Outputs to a public web directory.

Layer color scheme:
  Layer 1 (DQT Prime Tables)     — Cyan    (#00CED1)
  Layer 2 (Compound Markers)     — Magenta (#FF00FF)
  Layer 3 (Rare Basket / Seed)   — Gold    (#FFD700)
  Mersenne Sentinels             — Red     (#FF4444)
  Overlap                        — White   (#FFFFFF)
"""

import os
import sys
import json
import time
import hashlib
import numpy as np
from PIL import Image
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(__file__))

# Layer colors (RGB)
LAYER_COLORS = {
    "dqt":       (0, 206, 209),     # Cyan — Layer 1
    "compound":  (255, 0, 255),     # Magenta — Layer 2
    "rare":      (255, 215, 0),     # Gold — Layer 3
    "sentinel":  (255, 68, 68),     # Red — Mersenne sentinels
    "twin":      (0, 255, 128),     # Green — Twin markers
    "magic":     (128, 0, 255),     # Purple — Magic sentinels
}

LAYER_LABELS = {
    "dqt":       "Layer 1 — DQT Prime Tables",
    "compound":  "Layer 2 — Compound Markers",
    "rare":      "Layer 3 — Rare Basket",
    "sentinel":  "Mersenne Sentinels",
    "twin":      "Twin Markers",
    "magic":     "Magic Sentinels (B=42)",
}


@dataclass
class InjectionReport:
    """Metadata for a single injection run."""
    image_hash: str
    image_name: str
    width: int
    height: int
    timestamp: str
    profile: str
    layers_active: list
    total_markers: int
    total_sentinels: int
    basket_primes: list
    primes_used: dict
    mean_adjustment: float
    max_adjustment: int
    heatmap_path: str
    histogram_path: str
    report_json_path: str


def _generate_heatmap(pixels: np.ndarray, markers: list, sentinels: list,
                      output_path: str, alpha: float = 0.80):
    """
    Render a bold heatmap overlay showing injection sites on the image.

    Uses large, opaque markers in high-contrast complementary colors so
    injection positions are immediately obvious at any zoom level.
    Draws directly with PIL for crisp output, then composites with matplotlib
    for the legend.
    """
    from PIL import ImageDraw, ImageFont
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    h, w = pixels.shape[:2]

    # Scale marker radius to image size — visible at any resolution
    # Minimum 4px, scales up with image diagonal
    diag = (h * h + w * w) ** 0.5
    base_radius = max(4, int(diag / 180))
    sentinel_radius = max(6, int(base_radius * 1.6))

    # Complementary high-contrast colors (RGBA with strong alpha)
    marker_alpha = int(alpha * 255)
    COLORS_RGBA = {
        "rare":     (*LAYER_COLORS["rare"],     marker_alpha),  # Gold
        "compound": (*LAYER_COLORS["compound"], marker_alpha),  # Magenta
        "twin":     (*LAYER_COLORS["twin"],     marker_alpha),  # Green
        "magic":    (*LAYER_COLORS["magic"],    marker_alpha),  # Purple
        "sentinel": (*LAYER_COLORS["sentinel"], marker_alpha),  # Red
    }

    # Start with the image as base
    base = Image.fromarray(pixels).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # --- Draw primary / compound markers as filled circles ---
    for m in markers:
        if "row" not in m or "col" not in m:
            continue
        r, c = m["row"], m["col"]
        if not (0 <= r < h and 0 <= c < w):
            continue

        layer = "rare" if m.get("type") == "primary" else "rare"
        color = COLORS_RGBA[layer]
        draw.ellipse(
            [c - base_radius, r - base_radius,
             c + base_radius, r + base_radius],
            fill=color,
            outline=(255, 255, 255, 180),
            width=1,
        )

        # Twin marker — connected with a line
        if "twin_col" in m:
            tc = m["twin_col"]
            if 0 <= tc < w:
                twin_color = COLORS_RGBA["twin"]
                draw.ellipse(
                    [tc - base_radius, r - base_radius,
                     tc + base_radius, r + base_radius],
                    fill=twin_color,
                    outline=(255, 255, 255, 180),
                    width=1,
                )
                # Connect twin pair with a line
                draw.line(
                    [(c, r), (tc, r)],
                    fill=(*LAYER_COLORS["twin"], 140),
                    width=max(1, base_radius // 2),
                )

        # Magic sentinel — diamond shape over the marker
        if "magic_value" in m:
            magic_color = COLORS_RGBA["magic"]
            mr = base_radius + 2
            draw.polygon(
                [(c, r - mr), (c + mr, r), (c, r + mr), (c - mr, r)],
                fill=magic_color,
                outline=(255, 255, 255, 200),
            )

    # --- Mersenne sentinels — large bold X marks ---
    for s in sentinels:
        r, c = s["row"], s["col"]
        if not (0 <= r < h and 0 <= c < w):
            continue
        if not s.get("placed"):
            continue

        sr = sentinel_radius
        sentinel_color = COLORS_RGBA["sentinel"]

        # Bold X
        line_w = max(2, sr // 2)
        draw.line([(c - sr, r - sr), (c + sr, r + sr)],
                  fill=sentinel_color, width=line_w)
        draw.line([(c - sr, r + sr), (c + sr, r - sr)],
                  fill=sentinel_color, width=line_w)
        # Outer ring
        draw.ellipse(
            [c - sr - 1, r - sr - 1, c + sr + 1, r + sr + 1],
            outline=(*LAYER_COLORS["sentinel"], 220),
            width=max(2, line_w // 2),
        )

    # Composite overlay onto base
    composite = Image.alpha_composite(base, overlay).convert("RGB")
    composite_arr = np.array(composite)

    # --- Render with matplotlib for legend ---
    fig_w = max(12, w / 80)
    fig_h = max(8, h / 80)
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=150)
    ax.imshow(composite_arr)
    ax.set_axis_off()
    ax.set_title("Granite Injection Heatmap", fontsize=14, color='white',
                 fontweight='bold', pad=10)

    # Legend
    legend_elements = []
    active_layers = set()
    for m in markers:
        active_layers.add("rare")
        if "twin_col" in m:
            active_layers.add("twin")
        if "magic_value" in m:
            active_layers.add("magic")
    if sentinels and any(s.get("placed") for s in sentinels):
        active_layers.add("sentinel")

    for key in ["rare", "twin", "magic", "sentinel"]:
        if key in active_layers:
            c = tuple(v / 255.0 for v in LAYER_COLORS[key])
            legend_elements.append(Patch(facecolor=c, label=LAYER_LABELS[key]))

    if legend_elements:
        ax.legend(handles=legend_elements, loc='upper right',
                  fontsize=max(9, int(fig_w * 0.7)),
                  framealpha=0.85,
                  facecolor='#101424', edgecolor='#6A8FD8',
                  labelcolor='white')

    fig.patch.set_facecolor('#07090F')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='#07090F', edgecolor='none')
    plt.close()


def _generate_histogram(markers: list, sentinels: list, output_path: str):
    """
    Generate histogram showing distribution of injected primes by layer type.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # Collect primes by category
    primary_primes = [m["prime"] for m in markers if "prime" in m]
    twin_primes = [m["twin_prime"] for m in markers if "twin_prime" in m]
    sentinel_mersennes = [s["mersenne"] for s in sentinels if s.get("placed")]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor('#07090F')
    fig.suptitle("Granite Injection Histogram", fontsize=16, color='white',
                 fontweight='bold')

    style = dict(edgecolor='white', linewidth=0.5)

    # 1. Primary prime distribution
    ax = axes[0, 0]
    if primary_primes:
        bins = range(min(primary_primes), max(primary_primes) + 5, 4)
        ax.hist(primary_primes, bins=bins,
                color=tuple(v / 255 for v in LAYER_COLORS["rare"]), **style)
    ax.set_title("Primary Marker Primes", color='white', fontsize=11)
    ax.set_xlabel("Prime value", color='#aaa', fontsize=9)
    ax.set_ylabel("Count", color='#aaa', fontsize=9)
    _style_ax(ax)

    # 2. Twin prime distribution
    ax = axes[0, 1]
    if twin_primes:
        bins = range(min(twin_primes), max(twin_primes) + 5, 4)
        ax.hist(twin_primes, bins=bins,
                color=tuple(v / 255 for v in LAYER_COLORS["twin"]), **style)
    else:
        ax.text(0.5, 0.5, "No twins", transform=ax.transAxes,
                ha='center', va='center', color='#666', fontsize=12)
    ax.set_title("Twin Marker Primes", color='white', fontsize=11)
    ax.set_xlabel("Prime value", color='#aaa', fontsize=9)
    ax.set_ylabel("Count", color='#aaa', fontsize=9)
    _style_ax(ax)

    # 3. Adjustment magnitude distribution
    ax = axes[1, 0]
    adjustments = []
    for m in markers:
        if "adjustment" in m:
            adjustments.append(m["adjustment"])
    if adjustments:
        ax.hist(adjustments, bins=30,
                color=tuple(v / 255 for v in LAYER_COLORS["compound"]), **style)
    ax.set_title("Channel Adjustment Magnitude", color='white', fontsize=11)
    ax.set_xlabel("Pixel value change", color='#aaa', fontsize=9)
    ax.set_ylabel("Count", color='#aaa', fontsize=9)
    _style_ax(ax)

    # 4. Spatial distribution (row histogram)
    ax = axes[1, 1]
    rows = [m["row"] for m in markers if "row" in m]
    if rows:
        ax.hist(rows, bins=50,
                color=tuple(v / 255 for v in LAYER_COLORS["sentinel"]), **style)
    sentinel_rows = [s["row"] for s in sentinels if s.get("placed")]
    if sentinel_rows:
        ax.hist(sentinel_rows, bins=50, alpha=0.6,
                color=tuple(v / 255 for v in LAYER_COLORS["sentinel"]), **style)
    ax.set_title("Injection Row Distribution", color='white', fontsize=11)
    ax.set_xlabel("Image row", color='#aaa', fontsize=9)
    ax.set_ylabel("Count", color='#aaa', fontsize=9)
    _style_ax(ax)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='#07090F', edgecolor='none')
    plt.close()


def _style_ax(ax):
    """Apply dark theme to a matplotlib axis."""
    ax.set_facecolor('#0B0E18')
    ax.tick_params(colors='#888', labelsize=8)
    ax.spines['bottom'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color='#6A8FD8')


def generate_injection_report(
    image_path: str,
    output_dir: str,
    profile_name: str = "compound",
    variable_offset: int = 42,
    enable_dct: bool = False,
    enable_thermo: bool = False,
) -> InjectionReport:
    """
    Run the full injection pipeline on an image and produce:
      1. Heatmap overlay (PNG)
      2. Histogram (PNG)
      3. JSON report

    Args:
        image_path: Path to source image
        output_dir: Directory to write outputs (should be web-public)
        profile_name: Marker config name from MARKER_TYPES
        variable_offset: Seed for position selection

    Returns:
        InjectionReport with paths to all outputs
    """
    from compound_markers import embed_compound, MARKER_TYPES
    from halo import embed_halos_from_sentinels, HALO_RADIUS
    from dqt_prime import encode_prime_jpeg

    img = Image.open(image_path).convert("RGB")
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    # Hash for unique identification
    img_hash = hashlib.sha256(pixels.tobytes()).hexdigest()[:16]
    img_name = os.path.splitext(os.path.basename(image_path))[0]
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    os.makedirs(output_dir, exist_ok=True)

    # ── Layer 2: Compound markers ──
    config = MARKER_TYPES[profile_name]
    modified, markers, sentinels = embed_compound(pixels, config, variable_offset)

    # Compute adjustment stats (luma domain: may modify R+G)
    adjustments = []
    for m in markers:
        adj = m.get("adjustment", 0)
        adjustments.append(adj)

    primes_used = {}
    for m in markers:
        p = m.get("prime")
        if p is not None:
            primes_used[p] = primes_used.get(p, 0) + 1

    basket_primes = sorted(set(m["prime"] for m in markers if "prime" in m))

    # ── Layer 3: Radial halos at Mersenne sentinel positions ──
    placed_sentinels = [s for s in sentinels if s.get("placed")]
    halo_centers = []
    for s in placed_sentinels:
        r, c = s["row"], s["col"]
        # Only place halos where there's room for the full disk
        if (HALO_RADIUS <= r < h - HALO_RADIUS and
                HALO_RADIUS <= c < w - HALO_RADIUS):
            halo_centers.append((r, c))

    n_halos = 0
    if halo_centers:
        modified_img = Image.fromarray(
            np.clip(modified, 0, 255).astype(np.uint8))
        modified_img = embed_halos_from_sentinels(modified_img, halo_centers)
        modified = np.array(modified_img)
        n_halos = len(halo_centers)

    # ── Layer H: Spatial Rulers — DISABLED pending perceptual tuning ──
    # Ruler bands (|R-G|=198) are visually loud.  Disabled until band
    # intensity can be reduced to imperceptible levels.
    n_rulers = 0

    # ── EXPERIMENTAL: Layer DCT — frequency-domain primes ──
    n_dct = 0
    if enable_dct:
        from dct_markers import embed_dct_primes
        from compound_markers import entropy_gate_positions, ENTROPY_BLOCK_SIZE
        from smart_embedder import compute_local_entropy_fast
        from pgps_detector import sample_positions_grid

        h_cur, w_cur = modified.shape[:2]
        emap = compute_local_entropy_fast(
            np.clip(modified, 0, 255).astype(np.uint8),
            block_size=ENTROPY_BLOCK_SIZE)
        raw_grid = sample_positions_grid(h_cur, w_cur, 8)
        grid_positions = [(int(r) + 3, int(c) + 3) for r, c in raw_grid
                          if int(r) + 3 < h_cur and int(c) + 3 < w_cur]
        from verify_image import _entropy_gate_cached, ENTROPY_GATE_THRESH
        gated_dct = _entropy_gate_cached(emap, grid_positions, h_cur, w_cur)
        # Align to 8x8 block origins
        dct_blocks = list(set(
            (r - r % 8, c - c % 8) for r, c in gated_dct
            if r - r % 8 + 8 <= h_cur and c - c % 8 + 8 <= w_cur
        ))
        mod_clipped = np.clip(modified, 0, 255).astype(np.uint8)
        mod_clipped, dct_meta = embed_dct_primes(mod_clipped, dct_blocks)
        modified = mod_clipped.astype(modified.dtype)
        n_dct = dct_meta['embedded']

    # ── EXPERIMENTAL: Layer T — thermodynamic consensus ──
    n_thermo = 0
    if enable_thermo:
        from thermo_markers import embed_thermodynamic
        from compound_markers import entropy_gate_positions, ENTROPY_BLOCK_SIZE
        from smart_embedder import compute_local_entropy_fast
        from pgps_detector import sample_positions_grid

        h_cur, w_cur = modified.shape[:2]
        mod_u8 = np.clip(modified, 0, 255).astype(np.uint8)
        emap = compute_local_entropy_fast(mod_u8, block_size=ENTROPY_BLOCK_SIZE)
        raw_grid = sample_positions_grid(h_cur, w_cur, 8)
        grid_positions = [(int(r) + 3, int(c) + 3) for r, c in raw_grid
                          if int(r) + 3 < h_cur and int(c) + 3 + 1 < w_cur]
        from verify_image import _entropy_gate_cached, ENTROPY_GATE_THRESH
        gated_thermo = _entropy_gate_cached(emap, grid_positions, h_cur, w_cur)
        mod_u8, thermo_meta = embed_thermodynamic(mod_u8, gated_thermo)
        modified = mod_u8.astype(modified.dtype)
        n_thermo = thermo_meta['embedded']

    # Determine active layers
    layers_active = ["compound"]
    if any("twin_col" in m for m in markers):
        layers_active.append("twin")
    if any("magic_value" in m for m in markers):
        layers_active.append("magic")
    if placed_sentinels:
        layers_active.append("sentinel")
    if n_halos > 0:
        layers_active.append("halo")
    if n_rulers > 0:
        layers_active.append("ruler")
    if n_dct > 0:
        layers_active.append("dct")
    if n_thermo > 0:
        layers_active.append("thermo")

    # File paths (relative for web serving)
    slug = f"{img_name}_{img_hash}"
    heatmap_file = f"{slug}_heatmap.png"
    histogram_file = f"{slug}_histogram.png"
    report_file = f"{slug}_report.json"

    heatmap_path = os.path.join(output_dir, heatmap_file)
    histogram_path = os.path.join(output_dir, histogram_file)
    report_json_path = os.path.join(output_dir, report_file)

    # Generate visualizations
    _generate_heatmap(pixels, markers, sentinels, heatmap_path)
    _generate_histogram(markers, sentinels, histogram_path)

    # ── Layer 1: DQT prime quantization tables (JPEG output) ──
    # Save as JPEG with prime-shifted quantization tables so Layer 1 is active.
    # Also save a lossless PNG copy for pixel-perfect archival.
    modified_clipped = np.clip(modified, 0, 255).astype(np.uint8)

    embedded_jpeg_file = f"{slug}_embedded.jpg"
    embedded_jpeg_path = os.path.join(output_dir, embedded_jpeg_file)
    dqt_jpeg_data, dqt_meta = encode_prime_jpeg(
        modified_clipped, quality=95, output_path=embedded_jpeg_path)
    layers_active.append("dqt")

    # Also save lossless PNG
    embedded_png_file = f"{slug}_embedded.png"
    embedded_png_path = os.path.join(output_dir, embedded_png_file)
    Image.fromarray(modified_clipped).save(embedded_png_path)

    # Build report
    report = InjectionReport(
        image_hash=img_hash,
        image_name=img_name,
        width=w,
        height=h,
        timestamp=timestamp,
        profile=profile_name,
        layers_active=layers_active,
        total_markers=len(markers),
        total_sentinels=len(placed_sentinels),
        basket_primes=basket_primes,
        primes_used=primes_used,
        mean_adjustment=float(np.mean(adjustments)) if adjustments else 0,
        max_adjustment=int(max(adjustments)) if adjustments else 0,
        heatmap_path=heatmap_file,
        histogram_path=histogram_file,
        report_json_path=report_file,
    )

    # Save JSON report
    report_dict = asdict(report)
    report_dict["markers"] = markers
    report_dict["sentinels"] = sentinels
    report_dict["halo_centers"] = len(halo_centers)
    report_dict["n_rulers"] = n_rulers
    report_dict["dqt_tables"] = dqt_meta.get("n_tables", 0)
    report_dict["dqt_quality"] = 95
    report_dict["embedded_jpeg"] = embedded_jpeg_file
    report_dict["embedded_png"] = embedded_png_file
    with open(report_json_path, "w") as f:
        json.dump(report_dict, f, indent=2, default=str)

    return report


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Granite injection heatmap + histogram report"
    )
    parser.add_argument("image", help="Path to source image")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory (default: public reports dir)")
    parser.add_argument("-p", "--profile", default="compound",
                        choices=["single_basic", "single_rare", "twin",
                                 "magic", "compound"],
                        help="Marker config profile")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Variable offset / seed")
    parser.add_argument("--experimental-dct", action="store_true",
                        help="Enable experimental DCT-domain prime embedding")
    parser.add_argument("--experimental-thermo", action="store_true",
                        help="Enable experimental thermodynamic consensus embedding")
    args = parser.parse_args()

    # Default output: website public reports directory
    if args.output is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.output = os.path.join(script_dir, "..", "..", "website", "public",
                                   "reports")

    report = generate_injection_report(
        args.image, args.output, args.profile, args.seed,
        enable_dct=args.experimental_dct,
        enable_thermo=args.experimental_thermo,
    )

    print(f"\nInjection Report Generated")
    print(f"  Image:      {report.image_name} ({report.width}x{report.height})")
    print(f"  Hash:       {report.image_hash}")
    print(f"  Profile:    {report.profile}")
    print(f"  Markers:    {report.total_markers}")
    print(f"  Sentinels:  {report.total_sentinels}")
    print(f"  Layers:     {', '.join(report.layers_active)}")
    print(f"  Mean adj:   {report.mean_adjustment:.1f}")
    print(f"  Max adj:    {report.max_adjustment}")
    print(f"  Heatmap:    {report.heatmap_path}")
    print(f"  Histogram:  {report.histogram_path}")
    print(f"  Report:     {report.report_json_path}")
