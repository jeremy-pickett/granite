#!/usr/bin/env python3
"""
Strategy 4 — The Prime Quantization Table (Douglas Rule: DQT)
==============================================================
Jeremy Pickett — Axiomatic Fictions Series

The quantization table is mandatory. The encoder controls it completely.
The decoder must read it. Every tool that doesn't re-encode preserves it.
And even after re-encode, the ghost persists as double-quantization
artifacts in DCT coefficient space.

Strategy: shift each quantization table entry to its nearest large prime.
The table itself becomes the provenance signal. No pixel-space embedding
required for this layer.

Detection: read the DQT segment. Check whether the entries are prime.
Natural JPEG encoders (libjpeg, mozjpeg, Pillow, ImageMagick) produce
quantization tables that are overwhelmingly composite. A table full of
primes is not natural. The signal is the table itself.

Ghost detection after re-encode: the double-quantization artifact
carries the fingerprint of the original prime grid. The ghost of the
table haunts the pixels.
"""

import os
import sys
import io
import struct
import json
import numpy as np
from PIL import Image
from scipy import stats as sp_stats

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import sieve_of_eratosthenes, build_prime_lookup, _gen_synthetic_photo


# =============================================================================
# STANDARD QUANTIZATION TABLES (ITU-T T.81 Annex K)
# =============================================================================

STANDARD_LUMA_QT = np.array([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68,109,103, 77,
    24, 35, 55, 64, 81,104,113, 92,
    49, 64, 78, 87,103,121,120,101,
    72, 92, 95, 98,112,100,103, 99,
], dtype=np.uint8).reshape(8, 8)

STANDARD_CHROMA_QT = np.array([
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
], dtype=np.uint8).reshape(8, 8)


def scale_qt(table: np.ndarray, quality: int) -> np.ndarray:
    """Scale quantization table by JPEG quality factor (libjpeg formula)."""
    if quality < 50:
        scale = 5000 // quality
    else:
        scale = 200 - 2 * quality
    scaled = (table.astype(int) * scale + 50) // 100
    return np.clip(scaled, 1, 255).astype(np.uint8)


# =============================================================================
# PRIME TABLE CONSTRUCTION
# =============================================================================

def nearest_prime(value: int, direction: str = "closest",
                   min_prime: int = 2) -> int:
    """
    Find the nearest prime to value.
    direction: 'closest', 'up', 'down'
    """
    primes = set(sieve_of_eratosthenes(max(255, value + 50)).tolist())

    if value in primes and value >= min_prime:
        return value

    for d in range(1, 256):
        up = value + d
        down = value - d
        if direction == "up":
            if up in primes and up >= min_prime and up <= 255:
                return up
        elif direction == "down":
            if down in primes and down >= min_prime and down >= 1:
                return down
        else:  # closest
            up_ok = up in primes and up >= min_prime and up <= 255
            down_ok = down in primes and down >= min_prime and down >= 1
            if up_ok and down_ok:
                return up if d == d else up  # tie goes up
            if up_ok:
                return up
            if down_ok:
                return down

    return value  # Fallback (shouldn't happen in 8-bit range)


def primify_qt(table: np.ndarray, min_prime: int = 2,
                preserve_dc: bool = False) -> np.ndarray:
    """
    Shift every quantization table entry to its nearest prime.

    Args:
        table: 8x8 quantization table
        min_prime: minimum prime floor
        preserve_dc: if True, don't modify [0,0] (DC coefficient step)
            — the DC step has the most visual impact
    """
    result = table.copy().astype(int)
    for r in range(8):
        for c in range(8):
            if preserve_dc and r == 0 and c == 0:
                continue
            result[r, c] = nearest_prime(int(table[r, c]), min_prime=min_prime)
    return np.clip(result, 1, 255).astype(np.uint8)


def analyze_qt_primality(table: np.ndarray, min_prime: int = 2) -> dict:
    """Analyze how prime a quantization table is."""
    primes = set(sieve_of_eratosthenes(255).tolist())
    primes = {p for p in primes if p >= min_prime}

    flat = table.flatten()
    n = len(flat)
    is_prime = [int(v) in primes for v in flat]
    n_prime = sum(is_prime)

    # Expected under random (uniform 1-255)
    expected_rate = len(primes) / 255

    # Binomial test: is this table more prime than random?
    binom_p = float(sp_stats.binomtest(
        n_prime, n, expected_rate, alternative='greater').pvalue)

    # Adjacent pair prime-gap analysis
    prime_gaps = 0
    total_pairs = 0
    for i in range(n - 1):
        diff = abs(int(flat[i]) - int(flat[i+1]))
        if diff in primes:
            prime_gaps += 1
        total_pairs += 1

    return {
        "n_entries": n,
        "n_prime": n_prime,
        "prime_rate": n_prime / n,
        "expected_rate": expected_rate,
        "enrichment": (n_prime / n) / expected_rate if expected_rate > 0 else 0,
        "binomial_pvalue": binom_p,
        "n_prime_gaps": prime_gaps,
        "total_adjacent_pairs": total_pairs,
        "prime_gap_rate": prime_gaps / total_pairs if total_pairs > 0 else 0,
        "entries": flat.tolist(),
        "prime_mask": is_prime,
    }


# =============================================================================
# JPEG FILE SURGERY — Read and Replace DQT
# =============================================================================

def read_jpeg_markers(data: bytes) -> list:
    """Parse JPEG marker segments. Returns list of (marker, offset, length, payload)."""
    markers = []
    pos = 0
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker == 0xD8:  # SOI
            markers.append((0xD8, pos, 2, b''))
            pos += 2
        elif marker == 0xD9:  # EOI
            markers.append((0xD9, pos, 2, b''))
            pos += 2
        elif marker == 0x00:  # Byte stuffing
            pos += 2
        elif 0xD0 <= marker <= 0xD7:  # RST markers
            markers.append((marker, pos, 2, b''))
            pos += 2
        elif marker == 0xDA:  # SOS — scan data follows
            length = struct.unpack('>H', data[pos+2:pos+4])[0]
            # Scan data runs until next marker
            markers.append((0xDA, pos, length + 2, data[pos+4:pos+2+length]))
            pos += 2 + length
            # Skip entropy-coded data
            while pos < len(data) - 1:
                if data[pos] == 0xFF and data[pos+1] != 0x00:
                    break
                pos += 1
        else:
            if pos + 3 < len(data):
                length = struct.unpack('>H', data[pos+2:pos+4])[0]
                payload = data[pos+4:pos+2+length] if pos+2+length <= len(data) else b''
                markers.append((marker, pos, length + 2, payload))
                pos += 2 + length
            else:
                pos += 2
    return markers


def extract_dqt_tables(data: bytes) -> list:
    """Extract quantization tables from JPEG file data."""
    markers = read_jpeg_markers(data)
    tables = []
    for marker, offset, length, payload in markers:
        if marker == 0xDB:  # DQT
            pos = 0
            while pos < len(payload):
                precision_id = payload[pos]
                precision = (precision_id >> 4) & 0x0F  # 0=8bit, 1=16bit
                table_id = precision_id & 0x0F
                pos += 1
                if precision == 0:
                    entries = np.array(list(payload[pos:pos+64]), dtype=np.uint8)
                    pos += 64
                else:
                    entries = np.array(struct.unpack('>' + 'H'*64,
                                       payload[pos:pos+128]), dtype=np.uint16)
                    pos += 128
                tables.append({
                    "table_id": table_id,
                    "precision": precision,
                    "entries": entries.reshape(8, 8),
                    "offset": offset,
                })
    return tables


def replace_dqt_in_jpeg(original_data: bytes,
                         new_tables: dict) -> bytes:
    """
    Replace quantization tables in JPEG file data.
    new_tables: dict mapping table_id -> 8x8 numpy array

    Strategy: rebuild the DQT segment(s) with new values.
    """
    result = bytearray(original_data)
    markers = read_jpeg_markers(original_data)

    # Process DQT markers in reverse order (so offsets don't shift)
    dqt_markers = [(m, off, ln, pl) for m, off, ln, pl in markers if m == 0xDB]

    for marker, offset, length, payload in reversed(dqt_markers):
        # Rebuild payload with new tables
        new_payload = bytearray()
        pos = 0
        while pos < len(payload):
            precision_id = payload[pos]
            precision = (precision_id >> 4) & 0x0F
            table_id = precision_id & 0x0F
            new_payload.append(precision_id)
            pos += 1

            if table_id in new_tables:
                new_entries = new_tables[table_id].flatten().astype(np.uint8)
                new_payload.extend(new_entries.tobytes())
            else:
                # Keep original
                if precision == 0:
                    new_payload.extend(payload[pos:pos+64])
                else:
                    new_payload.extend(payload[pos:pos+128])

            pos += 64 if precision == 0 else 128

        # Build new DQT segment: FF DB + length + payload
        new_length = len(new_payload) + 2  # +2 for the length field itself
        new_segment = bytes([0xFF, 0xDB]) + struct.pack('>H', new_length) + bytes(new_payload)

        # Replace in file
        result[offset:offset+length+2] = new_segment  # +2 for FF DB marker bytes... 
        # Actually: the 'length' from parsing already includes some accounting.
        # Let's be more careful:
        old_segment_size = 2 + length  # FF DB + length bytes + payload
        # Wait, length from the struct already includes the 2-byte length field
        # So total segment = 2 (marker) + length
        result[offset:offset + 2 + length] = new_segment

    return bytes(result)


# =============================================================================
# PRIME JPEG ENCODER
# =============================================================================

def encode_prime_jpeg(pixels: np.ndarray, quality: int = 75,
                       min_prime: int = 2, preserve_dc: bool = True,
                       output_path: str = None) -> tuple[bytes, dict]:
    """
    Encode a JPEG with prime-shifted quantization tables.

    Strategy:
    1. Encode normally with Pillow at requested quality
    2. Extract the DQT tables Pillow generated
    3. Shift each entry to nearest prime
    4. Re-encode using the prime tables

    The re-encode step is necessary because just patching the DQT bytes
    without re-quantizing the DCT coefficients would produce garbage.
    We need Pillow to use our specific tables during encoding.

    Pillow allows custom qtables via the 'qtables' parameter.
    """
    img = Image.fromarray(pixels)

    # First, get the tables Pillow would use at this quality
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    buf.seek(0)
    standard_tables = extract_dqt_tables(buf.read())

    # Primify each table
    prime_tables = {}
    table_analysis = {}
    for tinfo in standard_tables:
        tid = tinfo["table_id"]
        original = tinfo["entries"]
        primed = primify_qt(original, min_prime=min_prime, preserve_dc=preserve_dc)
        prime_tables[tid] = primed

        table_analysis[f"table_{tid}_original"] = analyze_qt_primality(original, min_prime)
        table_analysis[f"table_{tid}_primed"] = analyze_qt_primality(primed, min_prime)

    # Encode with custom tables
    # Pillow qtables format: list of 64-int lists, one per table
    # Table ordering: [luma_table, chroma_table]
    qt_list = []
    for tid in sorted(prime_tables.keys()):
        qt_list.append(prime_tables[tid].flatten().tolist())

    buf2 = io.BytesIO()
    img.save(buf2, format='JPEG', qtables=qt_list)
    jpeg_data = buf2.getvalue()

    # Verify the tables were actually written
    verify_tables = extract_dqt_tables(jpeg_data)
    verification = {}
    for vt in verify_tables:
        tid = vt["table_id"]
        if tid in prime_tables:
            match = np.array_equal(vt["entries"], prime_tables[tid])
            verification[f"table_{tid}"] = {
                "match": match,
                "written": vt["entries"].flatten().tolist(),
                "intended": prime_tables[tid].flatten().tolist(),
            }

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(jpeg_data)

    metadata = {
        "quality": quality,
        "min_prime": min_prime,
        "preserve_dc": preserve_dc,
        "n_tables": len(prime_tables),
        "table_analysis": table_analysis,
        "verification": verification,
        "file_size": len(jpeg_data),
    }

    return jpeg_data, metadata


# =============================================================================
# DQT DETECTION
# =============================================================================

def detect_prime_dqt(jpeg_path_or_data, min_prime: int = 2) -> dict:
    """
    Detect whether a JPEG file has prime-shifted quantization tables.

    This is a static detection — no decoder needed. Read the DQT bytes,
    check primality. O(1) per file.
    """
    if isinstance(jpeg_path_or_data, (str, os.PathLike)):
        with open(jpeg_path_or_data, 'rb') as f:
            data = f.read()
    else:
        data = jpeg_path_or_data

    tables = extract_dqt_tables(data)
    if not tables:
        return {"error": "No DQT found", "detected": False}

    results = {}
    overall_prime_count = 0
    overall_total = 0

    for tinfo in tables:
        tid = tinfo["table_id"]
        analysis = analyze_qt_primality(tinfo["entries"], min_prime)
        results[f"table_{tid}"] = analysis
        overall_prime_count += analysis["n_prime"]
        overall_total += analysis["n_entries"]

    overall_rate = overall_prime_count / overall_total if overall_total > 0 else 0
    expected = len([p for p in sieve_of_eratosthenes(255) if p >= min_prime]) / 255

    # Binomial test on combined tables
    binom_p = float(sp_stats.binomtest(
        overall_prime_count, overall_total, expected,
        alternative='greater').pvalue)

    # Detection threshold: a natural table might have ~21% primes by chance
    # A fully primed table has 95%+ primes
    # Threshold at 60% — way above natural, conservative
    detected = overall_rate > 0.60 and binom_p < 1e-10

    return {
        "n_tables": len(tables),
        "overall_prime_count": overall_prime_count,
        "overall_total": overall_total,
        "overall_prime_rate": overall_rate,
        "expected_rate": expected,
        "enrichment": overall_rate / expected if expected > 0 else 0,
        "binomial_pvalue": binom_p,
        "detected": detected,
        "per_table": results,
    }


# =============================================================================
# GHOST DETECTION (double quantization artifacts)
# =============================================================================

def detect_dqt_ghost(original_prime_jpeg: bytes, reencoded_jpeg: bytes,
                      min_prime: int = 2) -> dict:
    """
    Detect the ghost of prime quantization after re-encoding.

    The original prime table creates a specific quantization grid in
    DCT coefficient space. After re-encoding with a different table,
    the DCT coefficients cluster at intersections of the old and new grids.
    This double-quantization artifact carries the fingerprint of the
    original prime grid.
    """
    # Decode both to pixel space
    orig_pixels = np.array(Image.open(io.BytesIO(original_prime_jpeg)).convert("RGB"))
    reenc_pixels = np.array(Image.open(io.BytesIO(reencoded_jpeg)).convert("RGB"))

    # Extract the tables from both
    orig_tables = extract_dqt_tables(original_prime_jpeg)
    reenc_tables = extract_dqt_tables(reencoded_jpeg)

    # The ghost manifests as: pixel value differences between the two
    # decodings cluster at multiples of the ORIGINAL quantization steps
    diff = reenc_pixels.astype(np.int16) - orig_pixels.astype(np.int16)
    flat_diff = diff.flatten()

    # Check if differences cluster at multiples of prime table entries
    prime_table_values = set()
    for tinfo in orig_tables:
        for v in tinfo["entries"].flatten():
            if v > 1:
                prime_table_values.add(int(v))

    # For each original table entry, count how many pixel differences
    # are multiples of that value
    ghost_signal = {}
    for pv in sorted(prime_table_values):
        # Count diffs that are multiples of pv (within tolerance)
        multiples = np.abs(flat_diff) % pv
        near_multiple = np.sum((multiples <= 1) | (multiples >= pv - 1))
        expected = len(flat_diff) * (3 / pv)  # ±1 tolerance = 3 values out of pv
        ghost_signal[pv] = {
            "near_multiples": int(near_multiple),
            "expected": float(expected),
            "enrichment": near_multiple / expected if expected > 0 else 0,
        }

    return {
        "n_pixels": len(flat_diff),
        "mean_diff": float(np.mean(np.abs(flat_diff))),
        "ghost_signal": ghost_signal,
        "orig_table_primes": analyze_qt_primality(orig_tables[0]["entries"], min_prime)
            if orig_tables else {},
        "reenc_table_primes": analyze_qt_primality(reenc_tables[0]["entries"], min_prime)
            if reenc_tables else {},
    }


# =============================================================================
# NATURAL BASELINE — Survey common encoder tables
# =============================================================================

def survey_natural_tables(pixels: np.ndarray, output_dir: str):
    """
    Generate JPEGs with various encoders/quality levels and measure
    the natural primality rate of their quantization tables.
    This establishes the null hypothesis for DQT detection.
    """
    os.makedirs(output_dir, exist_ok=True)
    img = Image.fromarray(pixels)

    print("=" * 80)
    print("NATURAL QUANTIZATION TABLE PRIMALITY SURVEY")
    print("=" * 80)
    print(f"\n{'Quality':>8s}  {'Table':>6s}  {'Primes':>7s}  {'Rate':>7s}  "
          f"{'Expected':>9s}  {'Enrich':>7s}  {'Binom p':>10s}  {'Entries (first 16)'}")
    print("-" * 110)

    all_results = []

    for q in [10, 20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 98]:
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=q)
        data = buf.getvalue()
        tables = extract_dqt_tables(data)

        for tinfo in tables:
            analysis = analyze_qt_primality(tinfo["entries"])
            entries_str = ", ".join(str(v) for v in tinfo["entries"].flatten()[:16])
            print(f"  Q{q:>3d}    T{tinfo['table_id']:>1d}    "
                  f"{analysis['n_prime']:>3d}/64  {analysis['prime_rate']:>7.3f}  "
                  f"{analysis['expected_rate']:>9.3f}  {analysis['enrichment']:>7.2f}  "
                  f"{analysis['binomial_pvalue']:>10.4f}  [{entries_str}...]")

            all_results.append({
                "quality": q,
                "table_id": tinfo["table_id"],
                **analysis,
            })

    # Summary
    rates = [r["prime_rate"] for r in all_results]
    print(f"\n  Natural prime rate across all tables/qualities:")
    print(f"    Mean:   {np.mean(rates):.4f}")
    print(f"    Std:    {np.std(rates):.4f}")
    print(f"    Max:    {np.max(rates):.4f}")
    print(f"    Min:    {np.min(rates):.4f}")

    return all_results


# =============================================================================
# FULL TEST
# =============================================================================

def run_dqt_test(output_dir: str):
    """Full Strategy 4 test: prime tables, detection, ghost survival."""
    os.makedirs(output_dir, exist_ok=True)

    rng = np.random.RandomState(42)
    pixels = _gen_synthetic_photo(512, 512, rng)

    # Phase 1: Natural baseline
    print("\n" + "#" * 80)
    print("# PHASE 1: NATURAL BASELINE")
    print("#" * 80)
    natural = survey_natural_tables(pixels, output_dir)

    # Phase 2: Prime encoding
    print("\n\n" + "#" * 80)
    print("# PHASE 2: PRIME QUANTIZATION TABLE ENCODING")
    print("#" * 80)

    for quality in [75, 85, 95]:
        print(f"\n{'='*70}")
        print(f"PRIME JPEG — Quality {quality}")
        print(f"{'='*70}")

        prime_path = os.path.join(output_dir, f"prime_q{quality}.jpg")
        normal_path = os.path.join(output_dir, f"normal_q{quality}.jpg")

        # Normal encode for comparison
        Image.fromarray(pixels).save(normal_path, "JPEG", quality=quality)

        # Prime encode
        prime_data, meta = encode_prime_jpeg(
            pixels, quality=quality, min_prime=2, preserve_dc=True,
            output_path=prime_path
        )

        # Show table comparison
        for tname, tdata in meta["table_analysis"].items():
            suffix = "ORIGINAL" if "original" in tname else "PRIMED"
            print(f"\n  {tname} ({suffix}):")
            print(f"    Primes: {tdata['n_prime']}/64  rate={tdata['prime_rate']:.3f}"
                  f"  enrichment={tdata['enrichment']:.2f}x"
                  f"  binom_p={tdata['binomial_pvalue']:.2e}")
            entries = tdata['entries'][:16]
            primes_mask = tdata['prime_mask'][:16]
            entry_str = " ".join(
                f"\033[92m{v:>3d}\033[0m" if is_p else f"{v:>3d}"
                for v, is_p in zip(entries, primes_mask)
            )
            print(f"    First 16: [{entry_str}]")

        # Verification
        for tid, vdata in meta["verification"].items():
            status = "MATCH" if vdata["match"] else "MISMATCH"
            print(f"\n  Verification {tid}: {status}")

        # File size comparison
        normal_size = os.path.getsize(normal_path)
        prime_size = len(prime_data)
        print(f"\n  File size: normal={normal_size:,}  prime={prime_size:,}"
              f"  delta={prime_size - normal_size:+,}"
              f"  ({(prime_size/normal_size - 1)*100:+.1f}%)")

        # Visual quality comparison (PSNR)
        normal_decoded = np.array(Image.open(normal_path).convert("RGB")).astype(float)
        prime_decoded = np.array(Image.open(io.BytesIO(prime_data)).convert("RGB")).astype(float)
        orig_float = pixels.astype(float)

        mse_normal = np.mean((orig_float - normal_decoded) ** 2)
        mse_prime = np.mean((orig_float - prime_decoded) ** 2)
        psnr_normal = 10 * np.log10(255**2 / mse_normal) if mse_normal > 0 else float('inf')
        psnr_prime = 10 * np.log10(255**2 / mse_prime) if mse_prime > 0 else float('inf')
        print(f"  PSNR: normal={psnr_normal:.2f}dB  prime={psnr_prime:.2f}dB"
              f"  delta={psnr_prime - psnr_normal:+.2f}dB")

    # Phase 3: Detection
    print("\n\n" + "#" * 80)
    print("# PHASE 3: DQT DETECTION (static, no decoder)")
    print("#" * 80)

    print(f"\n{'File':>30s}  {'Primes':>8s}  {'Rate':>7s}  {'Enrich':>7s}  "
          f"{'Binom p':>12s}  {'Detected':>10s}")
    print("-" * 90)

    for fname in sorted(os.listdir(output_dir)):
        if not fname.endswith('.jpg'):
            continue
        fpath = os.path.join(output_dir, fname)
        det = detect_prime_dqt(fpath)
        status = "DETECTED" if det["detected"] else "natural"
        print(f"  {fname:>28s}  {det['overall_prime_count']:>4d}/{det['overall_total']:<3d}"
              f"  {det['overall_prime_rate']:>7.3f}  {det['enrichment']:>7.2f}x"
              f"  {det['binomial_pvalue']:>12.2e}  {status:>10s}")

    # Phase 4: Ghost survival after re-encode
    print("\n\n" + "#" * 80)
    print("# PHASE 4: GHOST DETECTION (after re-encode)")
    print("#" * 80)

    for orig_q in [75, 85, 95]:
        prime_path = os.path.join(output_dir, f"prime_q{orig_q}.jpg")
        with open(prime_path, 'rb') as f:
            prime_data = f.read()

        prime_pixels = np.array(Image.open(prime_path).convert("RGB"))

        print(f"\n  Original: prime_q{orig_q}.jpg")
        for reenc_q in [95, 85, 75, 60, 40]:
            # Re-encode the prime JPEG at a different quality
            reenc_path = os.path.join(output_dir, f"reenc_q{orig_q}_to_q{reenc_q}.jpg")
            Image.fromarray(prime_pixels).save(reenc_path, "JPEG", quality=reenc_q)

            with open(reenc_path, 'rb') as f:
                reenc_data = f.read()

            # Check if the re-encoded file still has prime tables
            det = detect_prime_dqt(reenc_data)
            status = "TABLES SURVIVED" if det["detected"] else "tables replaced"

            # Ghost analysis
            ghost = detect_dqt_ghost(prime_data, reenc_data)

            print(f"    → Q{reenc_q}: DQT prime_rate={det['overall_prime_rate']:.3f}"
                  f"  [{status}]"
                  f"  pixel_diff={ghost['mean_diff']:.1f}")

    # Save summary
    summary = {
        "natural_max_prime_rate": float(max(r["prime_rate"] for r in natural)),
        "natural_mean_prime_rate": float(np.mean([r["prime_rate"] for r in natural])),
    }
    with open(os.path.join(output_dir, "dqt_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    output_dir = "pgps_results/dqt_strategy4"
    run_dqt_test(output_dir)
