#!/usr/bin/env python3
"""
Blind Sanity Check: Inject → Save → Verify (zero shared state)
================================================================
1. Inject each DIV2K test image using the web injector pipeline
2. Save to disk (JPEG with DQT + PNG)
3. Hand the saved file to the blind verifier — no manifest, no positions
4. Report what the verifier finds

This is exactly what a user does: upload → inject → download → verify.
"""

import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from injection_report import generate_injection_report
from verify_image import verify_image

TEST_IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'test-images')


def run_blind_test():
    images = sorted([f for f in os.listdir(TEST_IMAGES_DIR) if f.endswith('.png')])
    if not images:
        print("ERROR: No test images found in", TEST_IMAGES_DIR)
        sys.exit(1)

    print()
    print("=" * 120)
    print("BLIND SANITY CHECK — Inject → Save to disk → Blind Verify (no manifest)")
    print("=" * 120)
    print()

    hdr = (f"  {'Image':<12s}  {'Format':<6s}  {'Verdict':<14s}  "
           f"{'DQT':>5s}  {'Prime':>9s}  {'Twins':>9s}  "
           f"{'Magic':>9s}  {'Mersn':>5s}  {'Halos':>5s}  "
           f"{'Signals':>7s}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    all_results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for img_name in images:
            path = os.path.join(TEST_IMAGES_DIR, img_name)

            # ── STEP 1: INJECT (produces JPEG + PNG in tmpdir) ──
            report = generate_injection_report(
                path, tmpdir, profile_name="compound", variable_offset=42
            )

            slug = f"{report.image_name}_{report.image_hash}"
            jpeg_path = os.path.join(tmpdir, f"{slug}_embedded.jpg")
            png_path = os.path.join(tmpdir, f"{slug}_embedded.png")

            # ── STEP 2: BLIND VERIFY (verifier gets only the file path) ──
            for fmt, fpath in [("JPEG", jpeg_path), ("PNG", png_path)]:
                if not os.path.exists(fpath):
                    print(f"  {img_name:<12s}  {fmt:<6s}  FILE MISSING")
                    continue

                vr = verify_image(fpath)
                ck = vr["checks"]

                def _yn(d, key="detected"):
                    return "YES" if d.get(key, False) else "no"

                def _rate(d, key):
                    v = d.get(key)
                    return f"{v:.4f}" if v is not None else "—"

                dqt_str = _yn(ck["dqt_primes"]) if ck["dqt_primes"].get("applicable", True) else "n/a"
                prime_str = f"{_yn(ck['prime_enrichment'])} {_rate(ck['prime_enrichment'], 'prime_hit_rate')}"
                twin_str = f"{_yn(ck['twin_pairs'])} {_rate(ck['twin_pairs'], 'twin_rate')}"
                magic_str = f"{_yn(ck['magic_sentinels'])} {_rate(ck['magic_sentinels'], 'magic_rate')}"

                tag = img_name if fmt == "JPEG" else "  └─ PNG"
                print(f"  {tag:<12s}  {fmt:<6s}  {vr['verdict']:<14s}  "
                      f"{dqt_str:>5s}  {prime_str:>9s}  {twin_str:>9s}  "
                      f"{magic_str:>9s}  {_yn(ck['mersenne_sentinels']):>5s}  "
                      f"{_yn(ck['radial_halos']):>5s}  "
                      f"{vr['signal_count']:>7d}")

                all_results.append({
                    "image": img_name,
                    "format": fmt,
                    "verdict": vr["verdict"],
                    "signal_count": vr["signal_count"],
                    "dqt": ck["dqt_primes"].get("detected", False),
                    "prime": ck["prime_enrichment"].get("detected", False),
                    "twin": ck["twin_pairs"].get("detected", False),
                    "magic": ck["magic_sentinels"].get("detected", False),
                    "mersenne": ck["mersenne_sentinels"].get("detected", False),
                    "halos": ck["radial_halos"].get("detected", False),
                    "prime_rate": ck["prime_enrichment"].get("prime_hit_rate", 0),
                    "twin_rate": ck["twin_pairs"].get("twin_rate", 0),
                    "magic_rate": ck["magic_sentinels"].get("magic_rate", 0),
                })

    # ── SUMMARY ──
    print()
    print("=" * 120)
    print("SUMMARY")
    print("=" * 120)

    for fmt in ["JPEG", "PNG"]:
        subset = [r for r in all_results if r["format"] == fmt]
        n = len(subset)
        if n == 0:
            continue

        verdicts = {}
        for r in subset:
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1

        checks = ["dqt", "prime", "twin", "magic", "mersenne", "halos"]
        det_counts = {c: sum(1 for r in subset if r[c]) for c in checks}

        print(f"\n  {fmt} ({n} images):")
        print(f"    Verdicts: {verdicts}")
        for c in checks:
            print(f"    {c:>12s}: {det_counts[c]:>2d}/{n} detected")

    print()


if __name__ == "__main__":
    run_blind_test()
