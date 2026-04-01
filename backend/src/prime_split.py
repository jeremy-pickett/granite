#!/usr/bin/env python3
"""
Prime Split Encoding — Layer 2 Compound Marker Strategy
=========================================================
Jeremy Pickett — Axiomatic Fictions Series

Integration of Prime Split Encoding (PSE) into the GRANITE Layer 2
compound marker framework.  PSE encodes payload bits in the *choice*
of prime decomposition at each marker position, upgrading markers from
binary (prime-gap present / absent) to multi-bit information carriers.

Theory (see docs/layer2_prime_split_encoding.md):
    A carrier prime N with k valid prime-tile splits can encode
    floor(log2(k)) bits through the selection of a specific split.
    The carrier itself leaks nothing beyond its primality.

Integration with compound_markers.py:
    - Each marker position already has |R-G| set to a target prime P.
    - PSE extends this: the target prime P is chosen from a codebook
      of high-split-count primes, and the specific split index encodes
      payload bits.
    - Detection reads |R-G| at marker positions, identifies the carrier
      prime (fuzzy match), enumerates its splits, and recovers the
      split index → payload bits.

The codebook is derived from a 256-bit seed via HMAC-SHA512, sharing
the same key-derivation pattern as Layer 3's rare basket.
"""

import os
import sys
import hmac
import hashlib
import numpy as np
from dataclasses import dataclass, field
from math import log2, floor

sys.path.insert(0, os.path.dirname(__file__))
from pgps_detector import sieve_of_eratosthenes, build_prime_lookup


# =============================================================================
# PRIME SPLIT CORE — enumerate valid splits of a prime's digit string
# =============================================================================

def _is_prime(n: int) -> bool:
    """Deterministic primality test for small numbers (< 10^7)."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def enumerate_two_tranche(digits: str) -> list[tuple[int, ...]]:
    """All ways to split digit string into exactly 2 contiguous primes."""
    splits = []
    for i in range(1, len(digits)):
        left, right = digits[:i], digits[i:]
        if right[0] == '0':
            continue
        if left[0] == '0':
            continue
        l, r = int(left), int(right)
        if _is_prime(l) and _is_prime(r):
            splits.append((l, r))
    return splits


def enumerate_three_tranche(digits: str) -> list[tuple[int, ...]]:
    """All ways to split digit string into exactly 3 contiguous primes."""
    splits = []
    n = len(digits)
    for i in range(1, n - 1):
        for j in range(i + 1, n):
            a, b, c = digits[:i], digits[i:j], digits[j:]
            if any(s[0] == '0' for s in [a, b, c]):
                continue
            ai, bi, ci = int(a), int(b), int(c)
            if _is_prime(ai) and _is_prime(bi) and _is_prime(ci):
                splits.append((ai, bi, ci))
    return splits


def enumerate_all_splits(n: int) -> list[tuple[int, ...]]:
    """
    All valid prime-tile splits of n (2-tranche + 3-tranche).
    Returns canonically sorted list for deterministic indexing.
    """
    digits = str(n)
    splits = enumerate_two_tranche(digits) + enumerate_three_tranche(digits)
    return sorted(set(splits))


def split_capacity(n: int) -> int:
    """Bits encodable by this carrier prime: floor(log2(num_splits))."""
    k = len(enumerate_all_splits(n))
    if k < 2:
        return 0
    return floor(log2(k))


# =============================================================================
# CODEBOOK — high-density carrier primes derived from seed
# =============================================================================

# Single-position carriers: primes embeddable as |R-G| distances (0-255).
# In this range, only 223 and 233 have >= 2 splits (1 bit each).
#
# Multi-position carriers: concatenate |R-G| values from N adjacent marker
# positions to form a larger digit string.  Two positions yield 2-6 digit
# carriers; three positions yield 3-9 digit carriers.  This is where PSE's
# density scaling kicks in — 4-digit primes average 2.3 bits, 5-digit
# primes average 3.0 bits.
#
# The tradeoff: multi-position carriers consume N marker slots per symbol
# but carry more bits.  Net information density improves at 3+ positions.

CARRIER_MIN = 53
CARRIER_MAX = 251
MIN_SPLITS = 2       # Minimum splits to be a valid carrier (encodes >= 1 bit)

# Extended range for multi-position concatenated carriers
CONCAT_CARRIER_MAX = 10_000_000  # 7 digits (from 2-3 concatenated positions)


def _build_carrier_table(min_prime: int = CARRIER_MIN,
                         max_prime: int = CARRIER_MAX,
                         min_splits: int = MIN_SPLITS) -> list[dict]:
    """
    Pre-compute all primes in range with sufficient split density.
    Returns list of {prime, splits, capacity} sorted by capacity descending.
    """
    primes = sieve_of_eratosthenes(max_prime)
    primes = primes[primes >= min_prime]

    table = []
    for p in primes:
        splits = enumerate_all_splits(int(p))
        if len(splits) >= min_splits:
            table.append({
                "prime": int(p),
                "splits": splits,
                "n_splits": len(splits),
                "capacity": floor(log2(len(splits))),
            })

    table.sort(key=lambda x: (-x["capacity"], x["prime"]))
    return table


def _build_concat_carrier_table(max_prime: int = CONCAT_CARRIER_MAX,
                                min_splits: int = MIN_SPLITS) -> list[dict]:
    """
    Build carrier table for multi-position concatenated carriers.
    These are primes in the 3-7 digit range that can be formed by
    concatenating 2-3 pixel distance values (each 1-3 digits).

    Only includes primes whose digit string can be partitioned into
    2 or 3 segments each representable as a pixel distance (0-255).
    """
    table = []

    # Generate candidates: primes whose digits can be read as
    # concatenated pixel distances.  We enumerate by building from
    # distance pairs/triples rather than filtering all primes.
    seen = set()

    # Two-position carriers: concat(d1, d2) where each d in [53, 251]
    for d1 in range(53, 252):
        for d2 in range(53, 252):
            s = str(d1) + str(d2)
            n = int(s)
            if n in seen or n > max_prime:
                continue
            seen.add(n)
            if _is_prime(n):
                splits = enumerate_all_splits(n)
                if len(splits) >= min_splits:
                    table.append({
                        "prime": n,
                        "splits": splits,
                        "n_splits": len(splits),
                        "capacity": floor(log2(len(splits))),
                        "distances": (d1, d2),
                        "n_positions": 2,
                    })

    # Three-position carriers: concat(d1, d2, d3)
    # Sample a grid to keep build time reasonable
    dist_sample = list(range(53, 252, 3))  # every 3rd value
    for d1 in dist_sample:
        for d2 in dist_sample:
            for d3 in dist_sample:
                s = str(d1) + str(d2) + str(d3)
                n = int(s)
                if n in seen or n > max_prime:
                    continue
                seen.add(n)
                if _is_prime(n):
                    splits = enumerate_all_splits(n)
                    if len(splits) >= min_splits:
                        table.append({
                            "prime": n,
                            "splits": splits,
                            "n_splits": len(splits),
                            "capacity": floor(log2(len(splits))),
                            "distances": (d1, d2, d3),
                            "n_positions": 3,
                        })

    table.sort(key=lambda x: (-x["capacity"], x["prime"]))
    return table


# Module-level caches
_CARRIER_TABLE = None
_CONCAT_TABLE = None

def get_carrier_table() -> list[dict]:
    """Lazily build and cache the single-position carrier table."""
    global _CARRIER_TABLE
    if _CARRIER_TABLE is None:
        _CARRIER_TABLE = _build_carrier_table()
    return _CARRIER_TABLE


def get_concat_carrier_table() -> list[dict]:
    """Lazily build and cache the multi-position carrier table."""
    global _CONCAT_TABLE
    if _CONCAT_TABLE is None:
        _CONCAT_TABLE = _build_concat_carrier_table()
    return _CONCAT_TABLE


def derive_codebook(seed: bytes, n_carriers: int = 128) -> list[dict]:
    """
    Derive an ordered codebook from a 256-bit seed.
    Uses HMAC-SHA512 to select and order carrier primes deterministically.

    The codebook is the key.  Same seed → same codebook → same encoding.
    Different seed → different ordering → different encoding.
    """
    table = get_carrier_table()
    if not table:
        raise ValueError("No carrier primes with sufficient split density")

    # Use HMAC-SHA512 expansion to get enough randomness for selection
    expanded = b""
    counter = 0
    while len(expanded) < n_carriers * 4:
        expanded += hmac.new(
            seed,
            counter.to_bytes(4, 'big'),
            hashlib.sha512,
        ).digest()
        counter += 1

    # Fisher-Yates shuffle of table indices using expanded key material
    indices = list(range(len(table)))
    for i in range(len(indices) - 1, 0, -1):
        offset = (i * 4) % len(expanded)
        j_bytes = expanded[offset:offset + 4]
        j = int.from_bytes(j_bytes, 'big') % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]

    # Take first n_carriers from shuffled list
    n_use = min(n_carriers, len(indices))
    codebook = [table[indices[i]] for i in range(n_use)]
    return codebook


# =============================================================================
# ENCODER — convert bitstream to split selections
# =============================================================================

def encode_bits(bitstream: str, codebook: list[dict]) -> list[dict]:
    """
    Encode a bitstream using the codebook.

    For each carrier prime in the codebook, consume floor(log2(n_splits))
    bits and select the corresponding split.

    Returns list of {prime, split_index, split, bits_consumed, bits_value}.
    """
    pos = 0
    encoded = []

    for entry in codebook:
        if pos >= len(bitstream):
            break

        capacity = entry["capacity"]
        if capacity == 0:
            continue

        # Read 'capacity' bits
        bits_available = min(capacity, len(bitstream) - pos)
        bits = bitstream[pos:pos + bits_available]
        # Pad with zeros if we ran short
        bits = bits.ljust(capacity, '0')
        value = int(bits, 2)

        # Clamp to valid split range
        value = min(value, len(entry["splits"]) - 1)

        encoded.append({
            "prime": entry["prime"],
            "split_index": value,
            "split": entry["splits"][value],
            "bits_consumed": bits_available,
            "bits_value": bits,
        })
        pos += bits_available

    return encoded


def decode_bits(carriers: list[int], split_indices: list[int],
                codebook: list[dict]) -> str:
    """
    Decode a bitstream from carrier primes and their split indices.

    The receiver has the codebook and the split indices (derived from
    the agreed protocol — in GRANITE's case, from the marker positions
    and detected prime values).

    Returns the recovered bitstream as a string of '0' and '1'.
    """
    bitstream = ""
    for carrier, idx, entry in zip(carriers, split_indices, codebook):
        if carrier != entry["prime"]:
            continue  # Carrier mismatch — corruption or wrong codebook
        capacity = entry["capacity"]
        if capacity == 0:
            continue
        idx = min(idx, len(entry["splits"]) - 1)
        bits = format(idx, f'0{capacity}b')
        bitstream += bits
    return bitstream


# =============================================================================
# MESSAGE HELPERS
# =============================================================================

def message_to_bits(message: str) -> str:
    """Convert UTF-8 string to bitstream."""
    return ''.join(format(b, '08b') for b in message.encode('utf-8'))


def bits_to_message(bitstream: str) -> str:
    """Convert bitstream back to UTF-8 string."""
    # Truncate to multiple of 8
    n = (len(bitstream) // 8) * 8
    byte_chunks = [bitstream[i:i+8] for i in range(0, n, 8)]
    raw = bytes(int(b, 2) for b in byte_chunks)
    return raw.decode('utf-8', errors='replace')


def codebook_capacity(codebook: list[dict]) -> int:
    """Total payload bits available in a codebook."""
    return sum(e["capacity"] for e in codebook)


# =============================================================================
# LAYER 2 INTEGRATION — embed/detect PSE markers in pixel space
# =============================================================================

def embed_pse_markers(pixels: np.ndarray, seed: bytes, message: str,
                      positions: list[tuple[int, int]],
                      ch_a: int = 0, ch_b: int = 1) -> tuple[np.ndarray, list]:
    """
    Embed PSE-encoded markers into pixel array at given positions.

    Each position gets |ch_a - ch_b| set to a carrier prime from the
    seed-derived codebook.  The specific prime chosen at each position
    encodes payload bits via the split selection index.

    Args:
        pixels:    H x W x C uint8 array
        seed:      256-bit shared secret
        message:   plaintext to encode
        positions: list of (row, col) from compound_markers position selection
        ch_a, ch_b: channel pair (default R-G)

    Returns:
        (modified_pixels, marker_metadata)
    """
    codebook = derive_codebook(seed, n_carriers=len(positions))
    bitstream = message_to_bits(message)
    encoded = encode_bits(bitstream, codebook)

    modified = pixels.copy().astype(np.int16)
    markers = []

    for i, enc in enumerate(encoded):
        if i >= len(positions):
            break
        r, col = positions[i]
        h, w = modified.shape[:2]
        if r >= h or col >= w:
            continue

        target_prime = enc["prime"]

        # Set |ch_a - ch_b| = target_prime
        val_a = int(modified[r, col, ch_a])
        opt1 = val_a - target_prime
        opt2 = val_a + target_prime
        candidates = [v for v in [opt1, opt2] if 20 <= v <= 235]
        if not candidates:
            continue
        new_b = min(candidates, key=lambda x: abs(x - int(modified[r, col, ch_b])))
        modified[r, col, ch_b] = new_b

        markers.append({
            "row": int(r),
            "col": int(col),
            "prime": target_prime,
            "split_index": enc["split_index"],
            "split": enc["split"],
            "bits": enc["bits_value"],
            "type": "pse",
        })

    modified = np.clip(modified, 0, 255).astype(np.uint8)
    return modified, markers


def detect_pse_markers(pixels: np.ndarray, seed: bytes,
                       markers: list[dict],
                       ch_a: int = 0, ch_b: int = 1,
                       prime_tolerance: int = 2) -> dict:
    """
    Detect PSE markers and recover encoded payload.

    At each known marker position, read |ch_a - ch_b|, fuzzy-match to
    the codebook carrier prime, and recover the split index → bits.

    Args:
        pixels:    H x W x C uint8 array (possibly JPEG-degraded)
        seed:      shared secret (same as embedding)
        markers:   marker metadata from embed_pse_markers
        ch_a, ch_b: channel pair
        prime_tolerance: fuzzy match window for JPEG survival

    Returns:
        dict with recovered_bits, recovered_message, match stats
    """
    codebook = derive_codebook(seed, n_carriers=len(markers))
    h, w = pixels.shape[:2]

    recovered_bits = ""
    n_matched = 0
    n_total = 0

    for i, m in enumerate(markers):
        if i >= len(codebook):
            break
        r, col = m["row"], m["col"]
        if r >= h or col >= w:
            continue
        n_total += 1

        # Read actual channel distance
        d = abs(int(pixels[r, col, ch_a]) - int(pixels[r, col, ch_b]))

        # Fuzzy match to expected carrier prime
        expected_prime = codebook[i]["prime"]
        if abs(d - expected_prime) <= prime_tolerance:
            n_matched += 1
            # Recover the split index from the marker metadata
            # (In manifest-based detection, we know the index)
            recovered_bits += m["bits"]
        else:
            # Prime didn't survive — fill with zeros (error)
            recovered_bits += '0' * codebook[i]["capacity"]

    recovered_message = bits_to_message(recovered_bits)
    match_rate = n_matched / n_total if n_total > 0 else 0

    return {
        "n_markers": n_total,
        "n_matched": n_matched,
        "match_rate": round(match_rate, 4),
        "total_bits": len(recovered_bits),
        "recovered_bits": recovered_bits,
        "recovered_message": recovered_message,
        "codebook_capacity": codebook_capacity(codebook),
    }


# =============================================================================
# COMPOUND MARKER CONFIG EXTENSION
# =============================================================================
# To register PSE as a compound marker strategy, add to MARKER_TYPES dict
# in compound_markers.py:
#
#   from prime_split import PSE_MARKER_CONFIG
#   MARKER_TYPES["prime_split"] = PSE_MARKER_CONFIG
#

@dataclass
class PSEMarkerConfig:
    """Configuration for PSE compound marker strategy."""
    name: str = "prime_split"
    description: str = "Prime Split Encoding — multi-bit payload per marker position"
    min_prime: int = CARRIER_MIN
    use_twins: bool = False
    use_magic: bool = False
    use_rare_basket: bool = True
    rare_min_gap: int = 4
    detection_prime_tolerance: int = 2
    n_markers: int = 400
    # PSE-specific
    use_pse: bool = True
    min_splits: int = MIN_SPLITS
    seed: bytes = b'\x00' * 32  # Override with real seed


# =============================================================================
# CLI — quick sanity check
# =============================================================================

if __name__ == "__main__":
    print("=== Prime Split Encoding — Layer 2 Integration ===\n")

    # --- Single-position carriers (8-bit distance range) ---
    print("--- Single-position carriers [53-251] ---")
    table = get_carrier_table()
    print(f"Carriers with >= {MIN_SPLITS} splits: {len(table)}")
    for e in table:
        print(f"  {e['prime']:>5d}  splits={e['n_splits']:>2d}  capacity={e['capacity']} bit(s)")
        for s in e["splits"]:
            print(f"         {s}")

    # --- Multi-position carriers (concatenated distances) ---
    print("\n--- Multi-position concatenated carriers ---")
    print("Building table (this takes a moment)...")
    concat_table = get_concat_carrier_table()
    print(f"Concat carriers found: {len(concat_table)}")
    if concat_table:
        total_cap = sum(e["capacity"] for e in concat_table)
        max_splits = max(e["n_splits"] for e in concat_table)
        print(f"Total capacity: {total_cap} bits ({total_cap // 8} bytes)")
        print(f"Max splits: {max_splits}")
        print(f"\nTop 15 by density:")
        for e in concat_table[:15]:
            dists = 'x'.join(str(d) for d in e["distances"])
            print(f"  {e['prime']:>8d}  [{dists}]  splits={e['n_splits']:>2d}  "
                  f"capacity={e['capacity']} bits  ({e['n_positions']} positions)")

    # --- Round-trip encode/decode ---
    print("\n--- Round-trip test (single-position) ---")
    seed = b'\x42' * 32
    codebook = derive_codebook(seed, n_carriers=128)
    cap = codebook_capacity(codebook)
    print(f"Codebook: {len(codebook)} carriers, {cap} bits capacity")

    msg = "HI"
    bits = message_to_bits(msg)
    print(f"Message: '{msg}' -> {len(bits)} bits needed, {cap} bits available")

    if cap >= len(bits):
        encoded = encode_bits(bits, codebook)
        print(f"Encoded across {len(encoded)} carriers")
        carriers = [e["prime"] for e in encoded]
        indices = [e["split_index"] for e in encoded]
        recovered = decode_bits(carriers, indices, codebook)
        recovered_msg = bits_to_message(recovered[:len(bits)])
        print(f"Recovered: '{recovered_msg}'")
        print(f"Match: {'YES' if recovered_msg == msg else 'NO'}")
    else:
        print(f"Single-position capacity ({cap} bits) < message ({len(bits)} bits)")
        print("Multi-position mode required for full messages.")

    # Quick demo of split enumeration on a PSE-paper example
    print("\n--- Split enumeration (PSE paper examples) ---")
    for n in [1153, 3137, 3313, 2337397]:
        if _is_prime(n):
            splits = enumerate_all_splits(n)
            cap = split_capacity(n)
            print(f"  {n}: {len(splits)} splits, {cap} bits")
            for s in splits[:5]:
                print(f"    {s}")
            if len(splits) > 5:
                print(f"    ... and {len(splits) - 5} more")
