#!/usr/bin/env python3
"""
Stress Test: inject → blind detect → manifest detect → rotation → splice
==========================================================================
Runs all five test images through the full pipeline across four compression
levels.  Reports per-image, per-quality results in a summary table.
"""

import sys
import os
import time
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from compound_markers import (
    embed_compound, MARKER_TYPES, _pixel_luma,
    entropy_gate_positions, _find_channel_for_luma_dist,
)
from halo import (
    embed_halos_from_sentinels, detect_halo_centers,
    HaloState, HALO_RADIUS,
)
from verify_image import verify_image
from pgps_detector import sieve_of_eratosthenes, sample_positions_grid

TEST_IMAGES = ['0057', '0185', '0259', '0348', '0487']
QUALITIES = [None, 95, 85, 75]  # None = lossless PNG
ROTATION_ANGLES = [0, 5, 15, 45, 90]
BASKET_SET = set(int(p) for p in sieve_of_eratosthenes(127) if p >= 7)


def psnr(a, b):
    d = a.astype(float) - b.astype(float)
    mse = np.mean(d ** 2)
    return 10 * np.log10(255 ** 2 / mse) if mse > 0 else float('inf')


def embed_all_layers(pixels):
    """Embed Layer 2 (chains) + Layer G (halos).  Returns (modified, markers, sentinels, halo_centers)."""
    h, w = pixels.shape[:2]
    config = MARKER_TYPES['compound']
    modified, markers, sentinels = embed_compound(pixels, config)
    l2 = np.clip(modified, 0, 255).astype(np.uint8)

    placed = [s for s in sentinels if s.get('placed')]
    hc = [(s['row'], s['col']) for s in placed
          if HALO_RADIUS <= s['row'] < h - HALO_RADIUS
          and HALO_RADIUS <= s['col'] < w - HALO_RADIUS]
    mod_img = embed_halos_from_sentinels(Image.fromarray(l2), hc)

    return np.array(mod_img), markers, sentinels, hc


def manifest_detect(test_pixels, markers, min_prime=7):
    """Known-position detection: check each marker's prime at its exact position."""
    chain_markers = [m for m in markers
                     if isinstance(m, dict) and m.get('type') == 'chain_link']
    if not chain_markers:
        return {"n_markers": 0, "survived": 0, "rate": 0.0, "detected": False}

    h, w = test_pixels.shape[:2]
    survived = 0
    for m in chain_markers:
        r, c = m['row'], m['col']
        if r >= h or c + 1 >= w:
            continue
        d = abs(_pixel_luma(test_pixels, r, c) - _pixel_luma(test_pixels, r, c + 1))
        # Exact match or within ±2 (fuzzy for JPEG)
        if abs(d - m['prime']) <= 2:
            survived += 1

    n = len(chain_markers)
    rate = survived / n if n > 0 else 0
    # Binomial test: P(survived | n trials, p=0.14 natural prime rate)
    from scipy.stats import binomtest
    if n > 0 and survived > 0:
        pval = binomtest(survived, n, 0.14, alternative='greater').pvalue
    else:
        pval = 1.0

    return {
        "n_markers": n,
        "survived": survived,
        "rate": round(rate, 4),
        "pvalue": pval,
        "detected": pval < 0.01,
    }


def rotation_test(orig_img_pil, embedded_img_pil, halo_centers, angles):
    """Rotate embedded image, re-detect halos.  Returns survival per angle."""
    results = {}
    for angle in angles:
        if angle == 0:
            rotated = embedded_img_pil
        else:
            rotated = embedded_img_pil.rotate(angle, resample=Image.BILINEAR, expand=False)

        centers = detect_halo_centers(rotated)
        present = [c for c in centers if c.state == HaloState.PRESENT]
        results[angle] = len(present)

    return results


def splice_test(embedded_arr, clean_arr):
    """
    Splice attack: take left half of embedded, right half of clean.
    Verify should detect signal in left half but not right.
    """
    h, w = embedded_arr.shape[:2]
    mid = w // 2

    spliced = clean_arr.copy()
    spliced[:, :mid, :] = embedded_arr[:, :mid, :]

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        Image.fromarray(spliced).save(f.name)
        report = verify_image(f.name)
        os.unlink(f.name)

    return report


def save_jpeg(arr, quality):
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    Image.fromarray(arr).save(tmp.name, 'JPEG', quality=quality)
    out = np.array(Image.open(tmp.name).convert('RGB'))
    os.unlink(tmp.name)
    return out


def run():
    print("=" * 100)
    print("GRANITE STRESS TEST — 5 images × 4 qualities × blind + manifest + rotation + splice")
    print("=" * 100)

    all_results = {}

    for img_name in TEST_IMAGES:
        path = f'backend/test-images/{img_name}.png'
        img = Image.open(path).convert('RGB')
        pixels = np.array(img)
        h, w = pixels.shape[:2]

        print(f"\n{'='*80}")
        print(f"IMAGE: {img_name}.png ({w}x{h})")
        print(f"{'='*80}")

        t0 = time.time()
        embedded, markers, sentinels, halo_centers = embed_all_layers(pixels)
        embed_time = time.time() - t0

        chain_markers = [m for m in markers if isinstance(m, dict) and m.get('type') == 'chain_link']
        chains_info = [m for m in markers if isinstance(m, dict) and '_chains' in m]
        chain_lengths = [c['length'] for c in chains_info[0]['_chains']] if chains_info else []

        p = psnr(pixels, embedded)
        print(f"  Embed: {len(chain_markers)} chain links, {len(halo_centers)} halos, "
              f"chains={chain_lengths}, PSNR={p:.1f} dB ({embed_time:.1f}s)")

        # --- Per-quality tests ---
        print(f"\n  {'Quality':>8s} | {'Blind':>12s} {'Chain':>5s} | "
              f"{'Manifest':>10s} {'Surv':>5s} {'Rate':>6s} {'p-val':>10s} | {'Verdict':>12s}")
        print(f"  {'-'*75}")

        img_results = {}
        for q in QUALITIES:
            label = 'lossless' if q is None else f'Q{q}'

            if q is None:
                test_px = embedded
                tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                Image.fromarray(embedded).save(tmp.name)
            else:
                tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                Image.fromarray(embedded).save(tmp.name, 'JPEG', quality=q)
                test_px = np.array(Image.open(tmp.name).convert('RGB'))

            # Blind detection
            blind = verify_image(tmp.name)
            os.unlink(tmp.name)
            blind_chain = blind['checks']['prime_enrichment'].get('longest_chain', 0)
            blind_det = blind['checks']['prime_enrichment'].get('detected', False)

            # Manifest detection
            man = manifest_detect(test_px, markers)

            print(f"  {label:>8s} | {'DETECTED' if blind_det else 'no':>12s} {blind_chain:>5d} | "
                  f"{'DETECTED' if man['detected'] else 'no':>10s} "
                  f"{man['survived']:>5d} {man['rate']:>6.3f} {man['pvalue']:>10.2e} | "
                  f"{blind['verdict']:>12s}")

            img_results[label] = {
                "blind_chain": blind_chain,
                "blind_detected": blind_det,
                "manifest_survived": man['survived'],
                "manifest_rate": man['rate'],
                "manifest_detected": man['detected'],
                "verdict": blind['verdict'],
            }

        # --- Rotation test ---
        print(f"\n  Rotation (halo survival):")
        rot = rotation_test(img, Image.fromarray(embedded), halo_centers, ROTATION_ANGLES)
        for angle, n_present in rot.items():
            print(f"    {angle:3d}°: {n_present} PRESENT")
        img_results["rotation"] = rot

        # --- Splice test ---
        print(f"\n  Splice (left=embedded, right=clean):")
        splice = splice_test(embedded, pixels)
        splice_chain = splice['checks']['prime_enrichment'].get('longest_chain', 0)
        splice_det = splice['checks']['prime_enrichment'].get('detected', False)
        print(f"    Verdict: {splice['verdict']} chain={splice_chain} detected={splice_det}")
        img_results["splice"] = {
            "verdict": splice['verdict'],
            "chain": splice_chain,
            "detected": splice_det,
        }

        all_results[img_name] = img_results

    # --- CLEAN IMAGE BASELINE ---
    print(f"\n{'='*80}")
    print("CLEAN IMAGE BASELINE (no embedding)")
    print(f"{'='*80}")
    for img_name in TEST_IMAGES:
        path = f'backend/test-images/{img_name}.png'
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        Image.open(path).convert('RGB').save(tmp.name)
        r = verify_image(tmp.name)
        os.unlink(tmp.name)
        pe = r['checks']['prime_enrichment']
        chain = pe.get('longest_chain', 0)
        print(f"  {img_name}: {r['verdict']} chain={chain}")

    # --- SUMMARY TABLE ---
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"\n  {'Image':>6s} | {'lossless':>10s} | {'Q95':>10s} | {'Q85':>10s} | {'Q75':>10s} | "
          f"{'Rotation':>8s} | {'Splice':>8s}")
    print(f"  {'-'*72}")
    for img_name, res in all_results.items():
        def _cell(label):
            r = res.get(label, {})
            if r.get('manifest_detected'):
                return f"B{'Y' if r['blind_detected'] else 'n'}/M✓"
            elif r.get('blind_detected'):
                return "B✓/Mn"
            else:
                return f"--/c{r.get('blind_chain',0)}"

        rot_survive = res.get("rotation", {}).get(45, 0)
        spl = "✓" if res.get("splice", {}).get("detected") else "n"

        print(f"  {img_name:>6s} | {_cell('lossless'):>10s} | {_cell('Q95'):>10s} | "
              f"{_cell('Q85'):>10s} | {_cell('Q75'):>10s} | "
              f"{rot_survive:>5d}@45 | {spl:>8s}")

    print(f"\n  B=blind chain, M=manifest, c=chain length, ✓=detected")
    return all_results


if __name__ == "__main__":
    run()
