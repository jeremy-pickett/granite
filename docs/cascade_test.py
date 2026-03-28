#!/usr/bin/env python3
"""
Cascade Compression Test — The Ingestion Pipeline
===================================================
Jeremy Pickett — Axiomatic Fictions Series

Real-world scenario: image is created, uploaded, scraped, re-hosted,
aggregated. Each step re-encodes. What survives at each generation?

Test matrix:
  - Start at Q95, Q85, Q75
  - Cascade down through each lower quality level
  - At each generation, measure ALL layers:
      Layer A: DQT primality (container)
      Layer B: Twin markers with rare basket (content, known positions)
      Layer C: Douglas Rule sentinel (content, known positions)
      Layer B+C: Compound detection
  - Also test the generational loss fingerprint (forensic residue)
"""

import os
import sys
import io
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import (
    sieve_of_eratosthenes, build_prime_lookup,
    sample_positions_grid, extract_distances, DEFAULT_CHANNEL_PAIRS,
    _gen_synthetic_photo,
)
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
    build_rare_basket, MAGIC_VALUE, MAGIC_TOLERANCE, PRIME_TOLERANCE,
)
from dqt_prime import (
    encode_prime_jpeg, detect_prime_dqt, extract_dqt_tables,
    analyze_qt_primality,
)


# =============================================================================
# CASCADE CONFIGURATION
# =============================================================================

# Starting quality levels
START_QUALITIES = [95, 85, 75]

# The pipeline: each step re-encodes at the next lower level
CASCADE_STEPS = [95, 85, 75, 60, 40]

# Marker configs to test at each step
MARKER_CONFIGS = {
    "twin": MarkerConfig(
        name="twin",
        description="Twin prime-gap markers",
        min_prime=53, use_twins=True, use_rare_basket=True,
        detection_prime_tolerance=2, n_markers=400,
    ),
    "magic": MarkerConfig(
        name="magic (Douglas Rule)",
        description="Magic sentinel (42) + prime gap",
        min_prime=53, use_magic=True, use_rare_basket=True,
        magic_value=42, magic_tolerance=2,
        detection_prime_tolerance=2, n_markers=400,
    ),
    "compound": MarkerConfig(
        name="compound",
        description="Twin + magic + rare basket",
        min_prime=53, use_twins=True, use_magic=True, use_rare_basket=True,
        magic_value=42, magic_tolerance=2,
        detection_prime_tolerance=2, n_markers=400,
    ),
}


# =============================================================================
# GENERATIONAL LOSS MEASUREMENT
# =============================================================================

def measure_generational_loss(original_pixels: np.ndarray,
                                current_pixels: np.ndarray) -> dict:
    """Measure cumulative degradation from original."""
    diff = current_pixels.astype(np.float64) - original_pixels.astype(np.float64)
    flat = diff.flatten()
    mse = float(np.mean(diff ** 2))
    psnr = 10 * np.log10(255**2 / mse) if mse > 0 else float('inf')

    return {
        "mse": mse,
        "psnr_db": psnr,
        "mean_abs_diff": float(np.mean(np.abs(flat))),
        "max_abs_diff": float(np.max(np.abs(flat))),
        "std_diff": float(np.std(flat)),
    }


# =============================================================================
# CASCADE TEST
# =============================================================================

def run_cascade(output_dir: str):
    """Run the full cascade compression test."""
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    source_pixels = _gen_synthetic_photo(512, 512, rng)

    print("=" * 90)
    print("CASCADE COMPRESSION TEST — THE INGESTION PIPELINE")
    print("=" * 90)

    all_results = {}

    for start_q in START_QUALITIES:
        print(f"\n\n{'#' * 90}")
        print(f"# STARTING QUALITY: Q{start_q}")
        print(f"{'#' * 90}")

        # Step 1: Create the prime-table JPEG with embedded markers
        print(f"\n--- Creating prime JPEG at Q{start_q} with all marker layers ---")

        # First, encode with prime quantization tables
        prime_data, dqt_meta = encode_prime_jpeg(
            source_pixels, quality=start_q, min_prime=2, preserve_dc=True
        )

        # Decode the prime JPEG to get the pixel-space starting point
        prime_pixels = np.array(Image.open(io.BytesIO(prime_data)).convert("RGB"))

        # Now embed pixel-space markers into those pixels
        marker_results = {}
        for mname, mconfig in MARKER_CONFIGS.items():
            try:
                embedded_pixels, markers = embed_compound(prime_pixels, mconfig, seed=42)
                marker_results[mname] = {
                    "pixels": embedded_pixels,
                    "markers": markers,
                    "n_embedded": len(markers),
                }
                print(f"  {mname}: {len(markers)} markers embedded")
            except ValueError as e:
                print(f"  {mname}: FAILED — {e}")
                marker_results[mname] = None

        # Re-encode the marked pixels as prime JPEG at start_q
        # This is generation 0: the file as the creator ships it
        gen0_results = {}
        for mname, mdata in marker_results.items():
            if mdata is None:
                continue
            gen0_data, _ = encode_prime_jpeg(
                mdata["pixels"], quality=start_q, min_prime=2, preserve_dc=True
            )
            gen0_results[mname] = {
                "jpeg_data": gen0_data,
                "markers": mdata["markers"],
            }

        # Now run the cascade
        # Build the quality ladder starting from start_q downward
        cascade = [q for q in CASCADE_STEPS if q <= start_q]

        cascade_key = f"start_Q{start_q}"
        all_results[cascade_key] = {}

        for mname in MARKER_CONFIGS:
            if mname not in gen0_results:
                continue

            mconfig = MARKER_CONFIGS[mname]
            markers = gen0_results[mname]["markers"]

            print(f"\n{'='*80}")
            print(f"  Marker: {mname} | Start: Q{start_q} | {len(markers)} markers")
            print(f"{'='*80}")

            print(f"\n  {'Gen':>4s}  {'Quality':>7s}  "
                  f"{'DQT%':>6s}  {'DQT':>8s}  "
                  f"{'M_pass':>7s}  {'M_rate':>7s}  {'C_rate':>7s}  {'Ratio':>6s}  "
                  f"{'Binom_p':>10s}  {'PSNR':>7s}  {'Status'}")
            print(f"  {'-'*100}")

            # Generation 0: the original prime JPEG
            current_data = gen0_results[mname]["jpeg_data"]
            current_pixels = np.array(
                Image.open(io.BytesIO(current_data)).convert("RGB")
            )
            original_marked_pixels = current_pixels.copy()

            generation = 0
            gen_results = []

            for step_idx, target_q in enumerate(cascade):
                if generation == 0:
                    # Gen 0 is the original file at start_q
                    test_data = current_data
                    test_pixels = current_pixels
                else:
                    # Re-encode current pixels at target quality (normal encoder)
                    buf = io.BytesIO()
                    Image.fromarray(current_pixels).save(
                        buf, format='JPEG', quality=target_q
                    )
                    test_data = buf.getvalue()
                    test_pixels = np.array(
                        Image.open(io.BytesIO(test_data)).convert("RGB")
                    )

                # --- Layer A: DQT detection ---
                dqt_det = detect_prime_dqt(test_data)
                dqt_rate = dqt_det["overall_prime_rate"]
                dqt_status = "PRIME" if dqt_det["detected"] else "natural"

                # --- Layer B+C: Compound marker detection ---
                compound_det = detect_compound(test_pixels, markers, mconfig)

                # --- Generational loss ---
                gen_loss = measure_generational_loss(
                    original_marked_pixels, test_pixels
                )

                # Detection summary
                marker_detected = compound_det["detected_binom"]
                either_detected = dqt_det["detected"] or marker_detected

                status_parts = []
                if dqt_det["detected"]:
                    status_parts.append("DQT")
                if marker_detected:
                    status_parts.append("MARKERS")
                status = "+".join(status_parts) if status_parts else "—"

                result = {
                    "generation": generation,
                    "quality": target_q,
                    "dqt_prime_rate": dqt_rate,
                    "dqt_detected": dqt_det["detected"],
                    "marker_total": compound_det["marker_total"],
                    "marker_pass": compound_det["marker_compound_pass"],
                    "marker_rate": compound_det["marker_rate"],
                    "control_rate": compound_det["control_rate"],
                    "rate_ratio": compound_det["rate_ratio"],
                    "binom_p": compound_det["binomial_pvalue"],
                    "marker_detected": marker_detected,
                    "psnr": gen_loss["psnr_db"],
                    "mean_abs_diff": gen_loss["mean_abs_diff"],
                    "any_detected": either_detected,
                    "marker_primary_pass": compound_det["marker_primary_pass"],
                    "marker_twin_pass": compound_det.get("marker_twin_pass", 0),
                    "marker_magic_pass": compound_det.get("marker_magic_pass", 0),
                }
                gen_results.append(result)

                mt = compound_det["marker_total"]
                mp = compound_det["marker_compound_pass"]
                mr = compound_det["marker_rate"]
                cr = compound_det["control_rate"]
                rr = compound_det["rate_ratio"]
                bp = compound_det["binomial_pvalue"]
                psnr = gen_loss["psnr_db"]

                print(f"  {generation:>4d}  Q{target_q:>5d}  "
                      f"{dqt_rate:>5.1%}  {dqt_status:>8s}  "
                      f"{mp:>4d}/{mt:<3d}  {mr:>7.4f}  {cr:>7.4f}  {rr:>6.1f}  "
                      f"{bp:>10.2e}  {psnr:>6.1f}  {status}")

                # Advance to next generation
                current_data = test_data
                current_pixels = test_pixels
                generation += 1

            # Component breakdown at each generation
            print(f"\n  Component survival breakdown:")
            print(f"  {'Gen':>4s}  {'Q':>4s}  {'Primary':>10s}  {'Twin':>10s}  "
                  f"{'Magic':>10s}  {'Compound':>10s}")
            for r in gen_results:
                mt = r["marker_total"]
                if mt > 0:
                    pp = r["marker_primary_pass"]
                    tp = r["marker_twin_pass"]
                    mp_val = r["marker_magic_pass"]
                    cp = r["marker_pass"]
                    print(f"  {r['generation']:>4d}  Q{r['quality']:>3d}"
                          f"  {pp:>4d} ({pp/mt*100:>4.1f}%)"
                          f"  {tp:>4d} ({tp/mt*100:>4.1f}%)"
                          f"  {mp_val:>4d} ({mp_val/mt*100:>4.1f}%)"
                          f"  {cp:>4d} ({cp/mt*100:>4.1f}%)")

            all_results[cascade_key][mname] = gen_results

    # --- GRAND SUMMARY ---
    print(f"\n\n{'='*90}")
    print("GRAND SUMMARY — What Survives the Pipeline")
    print(f"{'='*90}")

    print(f"\n  Layer A (DQT primality):")
    print(f"  {'':>30s}  ", end="")
    for start_q in START_QUALITIES:
        print(f"  Start Q{start_q}", end="")
    print()

    # For DQT, all marker types produce the same result
    for gen_idx in range(len(CASCADE_STEPS)):
        q = CASCADE_STEPS[gen_idx] if gen_idx < len(CASCADE_STEPS) else "—"
        line = f"  {'Gen ' + str(gen_idx) + ' (Q' + str(q) + ')':>30s}  "
        for start_q in START_QUALITIES:
            cascade_key = f"start_Q{start_q}"
            if cascade_key in all_results:
                # Use first available marker type
                for mname in MARKER_CONFIGS:
                    if mname in all_results[cascade_key]:
                        results = all_results[cascade_key][mname]
                        if gen_idx < len(results):
                            r = results[gen_idx]
                            flag = "✓" if r["dqt_detected"] else "·"
                            line += f"  {r['dqt_prime_rate']:>5.1%} {flag}    "
                        else:
                            line += f"  {'—':>10s}    "
                        break
            else:
                line += f"  {'—':>10s}    "
        print(line)

    print(f"\n  Layer B (Twin markers) — rate ratio at each generation:")
    for mname in ["twin", "compound"]:
        print(f"\n  {mname}:")
        print(f"  {'':>30s}  ", end="")
        for start_q in START_QUALITIES:
            print(f"  Start Q{start_q}", end="")
        print()

        for gen_idx in range(len(CASCADE_STEPS)):
            q = CASCADE_STEPS[gen_idx] if gen_idx < len(CASCADE_STEPS) else "—"
            line = f"  {'Gen ' + str(gen_idx) + ' (Q' + str(q) + ')':>30s}  "
            for start_q in START_QUALITIES:
                cascade_key = f"start_Q{start_q}"
                if cascade_key in all_results and mname in all_results[cascade_key]:
                    results = all_results[cascade_key][mname]
                    if gen_idx < len(results):
                        r = results[gen_idx]
                        flag = "✓" if r["marker_detected"] else "·"
                        rr = r["rate_ratio"]
                        if rr == float('inf'):
                            line += f"    inf {flag}    "
                        else:
                            line += f"  {rr:>5.1f}x {flag}    "
                    else:
                        line += f"  {'—':>10s}    "
                else:
                    line += f"  {'—':>10s}    "
            print(line)

    print(f"\n  Key:")
    print(f"    ✓ = detected at α=0.01")
    print(f"    · = not detected")
    print(f"    Layer A survives until re-encode (generation 1)")
    print(f"    Layer B survives through compression cascade")
    print(f"    The two layers are independent — either is sufficient")

    # Save
    serializable = {}
    for ck, markers in all_results.items():
        serializable[ck] = {}
        for mname, gens in markers.items():
            serializable[ck][mname] = [
                {k: v for k, v in g.items() if k != "pixels"}
                for g in gens
            ]
    with open(os.path.join(output_dir, "cascade_results.json"), "w") as f:
        json.dump(serializable, f, indent=2, default=str)

    return all_results


# =============================================================================
# VISUALIZATION
# =============================================================================

def plot_cascade(results: dict, output_dir: str):
    """Visualize cascade survival."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    for cascade_key, marker_data in results.items():
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # Top: DQT survival
        for mname, gens in marker_data.items():
            generations = [g["generation"] for g in gens]
            dqt_rates = [g["dqt_prime_rate"] for g in gens]
            qualities = [f"G{g['generation']}:Q{g['quality']}" for g in gens]
            axes[0].plot(generations, dqt_rates, 'o-', linewidth=2,
                        markersize=8, label=f'{mname}')
            break  # DQT is same for all marker types

        axes[0].axhline(0.60, color='red', linewidth=1, linestyle='--',
                        label='Detection threshold')
        axes[0].axhline(0.23, color='gray', linewidth=1, linestyle=':',
                        label='Natural baseline')
        axes[0].set_ylabel('DQT Prime Rate', fontsize=12)
        axes[0].set_title(f'{cascade_key} — Layer A: DQT Primality', fontsize=14)
        axes[0].legend(fontsize=10)
        axes[0].set_ylim(-0.05, 1.05)
        axes[0].grid(True, alpha=0.3)
        if gens:
            axes[0].set_xticks(generations)
            axes[0].set_xticklabels(
                [f"G{g['generation']}\nQ{g['quality']}" for g in gens], fontsize=9
            )

        # Bottom: Marker rate ratio
        for mname, gens in marker_data.items():
            generations = [g["generation"] for g in gens]
            ratios = [min(g["rate_ratio"], 50) for g in gens]
            axes[1].plot(generations, ratios, 'o-', linewidth=2,
                        markersize=8, label=mname)

        axes[1].axhline(1.0, color='black', linewidth=0.5, linestyle='--', alpha=0.3)
        axes[1].set_ylabel('Rate Ratio (marker/control)', fontsize=12)
        axes[1].set_xlabel('Generation', fontsize=12)
        axes[1].set_title(f'{cascade_key} — Layer B+C: Marker Detection', fontsize=14)
        axes[1].legend(fontsize=10)
        axes[1].set_yscale('log')
        axes[1].grid(True, alpha=0.3)
        if gens:
            axes[1].set_xticks(generations)
            axes[1].set_xticklabels(
                [f"G{g['generation']}\nQ{g['quality']}" for g in gens], fontsize=9
            )

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'cascade_{cascade_key}.png'), dpi=150)
        plt.close()

    print(f"Cascade plots saved to {output_dir}/")


if __name__ == "__main__":
    output_dir = "pgps_results/cascade"
    results = run_cascade(output_dir)
    plot_cascade(results, os.path.join(output_dir, "plots"))
