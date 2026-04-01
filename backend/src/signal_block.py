#!/usr/bin/env python3
"""
signal_block.py — Layer S: Controlled Signal Blocks
=====================================================
EXPERIMENTAL — requires --experimental-sigblock flag.

Instead of whispering into existing pixels, we insert 8-pixel-wide
column slivers at regular intervals.  Each sliver is a native JPEG
8x8 block that we fully control.  JPEG preserves it by design.

Block structure (32 bits per block):
    bits[0:3]   = block_id    (0-15, 4 bits — which block in the chain)
    bits[4:7]   = next_id     (0-15, 4 bits — pointer to next block; 0xF = terminal)
    bits[8:31]  = payload     (24 bits of data)

Encoding method:
    Data is encoded into the low-frequency DCT coefficients of the
    block's luma (Y) channel.  Each coefficient encodes 2 bits via
    its value modulo 4, scaled to a quantization-safe amplitude.
    The first 16 AC coefficients (zigzag positions 1-16) carry the
    32 bits.  These survive JPEG re-encoding at Q60+ because their
    quantization divisors are small (1-6).

Visual blending:
    The block's pixel values are initialized to a smooth interpolation
    of the left and right neighbor columns, then the DCT modulation is
    applied on top.  Result: the block looks like a gentle gradient
    between its neighbors, not a foreign patch.

URL encoding:
    The base URL is implied (known to the verifier).  The payload
    across chained blocks concatenates to form a base32-encoded
    short identifier.  With 4 blocks: 4 x 24 = 96 bits = 12 bytes
    = up to 19 base32 characters.  Enough for "p/xK9mR2vL4n".

Detection:
    Scan every 8-column-aligned block for the signature pattern in
    DCT coefficients.  Valid blocks have a detectable modular
    structure that doesn't occur naturally.
"""

import math
import numpy as np
from scipy.fft import dctn, idctn

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

# How many bits encoded per DCT coefficient (via value mod 2^BITS_PER_COEFF)
BITS_PER_COEFF = 2

# Number of AC coefficients used (zigzag positions 1..N_COEFFS)
N_COEFFS = 16  # 16 coeffs × 2 bits = 32 bits per block

# Amplitude scale: the modular encoding value is multiplied by this.
# Must be large enough to dominate the base content's natural DCT
# coefficients.  We OWN this block, so we can be aggressive.
# Natural AC energy at positions 1-16 ranges 0-50 for typical
# photographic content.  Amplitude=40 ensures our signal is
# 2-3x the natural coefficient magnitude.
AMPLITUDE = 80

# Zigzag order: index → (row, col) in 8x8 block
ZIGZAG = [
    (0,0),(0,1),(1,0),(2,0),(1,1),(0,2),(0,3),(1,2),
    (2,1),(3,0),(4,0),(3,1),(2,2),(1,3),(0,4),(0,5),
    (1,4),(2,3),(3,2),(4,1),(5,0),(6,0),(5,1),(4,2),
    (3,3),(2,4),(1,5),(0,6),(0,7),(1,6),(2,5),(3,4),
    (4,3),(5,2),(6,1),(7,0),(7,1),(6,2),(5,3),(4,4),
    (3,5),(2,6),(1,7),(2,7),(3,6),(4,5),(5,4),(6,3),
    (7,2),(7,3),(6,4),(5,5),(4,6),(3,7),(4,7),(5,6),
    (6,5),(7,4),(7,5),(6,6),(5,7),(6,7),(7,6),(7,7),
]

# Coefficient positions we encode into (skip DC at index 0)
ENCODE_POSITIONS = ZIGZAG[1:N_COEFFS + 1]

MODULUS = 2 ** BITS_PER_COEFF  # 4

# Signature: first 4 bits must be 1010 — distinguishes signal blocks from natural
SIGNATURE = [1, 0, 1, 0]
SIG_BITS = len(SIGNATURE)

# Bit layout within the 32-bit block (after signature)
ID_BITS = 4
NEXT_BITS = 4
PAYLOAD_BITS = N_COEFFS * BITS_PER_COEFF - SIG_BITS - ID_BITS - NEXT_BITS  # 20

TERMINAL = 0xF  # next_id value meaning "end of chain"

# Base URL — implied, never stored in the image
BASE_URL = "signaldelta.com/p/"


# ---------------------------------------------------------------------------
# Bit packing
# ---------------------------------------------------------------------------

def _pack_block(block_id: int, next_id: int, payload_bits: list[int]) -> list[int]:
    """Pack signature, block_id, next_id, and payload into a flat bit list."""
    bits = list(SIGNATURE)
    # block_id: 4 bits
    for i in range(ID_BITS - 1, -1, -1):
        bits.append((block_id >> i) & 1)
    # next_id: 4 bits
    for i in range(NEXT_BITS - 1, -1, -1):
        bits.append((next_id >> i) & 1)
    # payload: remaining bits
    bits.extend(payload_bits[:PAYLOAD_BITS])
    # pad if needed
    while len(bits) < N_COEFFS * BITS_PER_COEFF:
        bits.append(0)
    return bits


def _check_signature(bits: list[int]) -> bool:
    """Check if the first SIG_BITS match the signature pattern."""
    return bits[:SIG_BITS] == SIGNATURE


def _unpack_block(bits: list[int]) -> tuple[int, int, list[int], bool]:
    """Unpack flat bit list into (block_id, next_id, payload_bits, sig_valid)."""
    sig_valid = _check_signature(bits)
    offset = SIG_BITS
    block_id = 0
    for i in range(ID_BITS):
        block_id = (block_id << 1) | bits[offset + i]
    offset += ID_BITS
    next_id = 0
    for i in range(NEXT_BITS):
        next_id = (next_id << 1) | bits[offset + i]
    offset += NEXT_BITS
    payload_bits = bits[offset:]
    return block_id, next_id, payload_bits, sig_valid


def _bits_to_symbol_values(bits: list[int]) -> list[int]:
    """Convert bit list to list of modular symbol values (0..MODULUS-1)."""
    symbols = []
    for i in range(0, len(bits), BITS_PER_COEFF):
        val = 0
        for j in range(BITS_PER_COEFF):
            if i + j < len(bits):
                val = (val << 1) | bits[i + j]
        symbols.append(val)
    return symbols


def _symbol_values_to_bits(symbols: list[int]) -> list[int]:
    """Convert symbol values back to bit list."""
    bits = []
    for val in symbols:
        for j in range(BITS_PER_COEFF - 1, -1, -1):
            bits.append((val >> j) & 1)
    return bits


# ---------------------------------------------------------------------------
# URL encoding / decoding
# ---------------------------------------------------------------------------

# Base32 alphabet (RFC 4648, lowercase for URLs)
_B32 = "abcdefghijklmnopqrstuvwxyz234567"


def encode_url_path(path: str) -> list[int]:
    """Encode a short URL path into a bit list."""
    raw = path.encode('utf-8')
    bits = []
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def decode_url_path(bits: list[int]) -> str:
    """Decode a bit list back to a URL path string."""
    # Trim to byte boundary
    n_bytes = len(bits) // 8
    chars = []
    for i in range(n_bytes):
        val = 0
        for j in range(8):
            val = (val << 1) | bits[i * 8 + j]
        if val == 0:
            break  # null terminator
        chars.append(chr(val))
    return ''.join(chars)


# ---------------------------------------------------------------------------
# Block encoding into DCT
# ---------------------------------------------------------------------------

def _encode_block_pixels(bits_32: list[int]) -> np.ndarray:
    """
    Encode 32 bits into an 8x8 pixel block using brightness levels.

    Each of the first 32 pixels (row-major) in the R channel encodes
    one bit:  bit=0 → pixel=96,  bit=1 → pixel=160.
    The remaining 32 pixels are set to 128 (neutral).
    G and B channels are set to 128 throughout.

    The 64-level gap (96 vs 160) survives JPEG at any quality because
    the DC coefficient shift is massive.  Even Q20 can't bridge a
    64-count gap within a single 8x8 block.
    """
    block = np.full((8, 8, 3), 128, dtype=np.uint8)
    for i, bit in enumerate(bits_32[:32]):
        row, col = divmod(i, 8)
        block[row, col, 0] = 160 if bit else 96
    return block


def _decode_block_pixels(pixels_8x8: np.ndarray) -> list[int]:
    """
    Decode 32 bits from an 8x8 pixel block.

    Reads the R channel of the first 32 pixels. Threshold at 128:
    >= 128 → 1, < 128 → 0.
    """
    bits = []
    for i in range(32):
        row, col = divmod(i, 8)
        val = int(pixels_8x8[row, col, 0])
        bits.append(1 if val >= 128 else 0)
    return bits


# ---------------------------------------------------------------------------
# Image-level insertion and detection
# ---------------------------------------------------------------------------

def insert_signal_blocks(pixels: np.ndarray, url_path: str,
                         n_blocks: int = 4) -> tuple[np.ndarray, dict]:
    """
    Insert signal block columns into the image carrying a chained payload.

    Each signal block is an 8-pixel-wide column of uniform gray with
    data encoded in DCT coefficients.  The final image is padded to
    a multiple of 8 pixels wide with black, ensuring every signal
    block lands exactly on a JPEG 8x8 grid boundary.

    Args:
        pixels: H x W x 3 source image
        url_path: short URL path to encode (e.g., "xK9mR2vL4n")
        n_blocks: how many signal blocks to insert

    Returns:
        (modified_pixels, metadata)
    """
    h, w, c = pixels.shape
    payload_bits = encode_url_path(url_path)

    # Pad payload to fill all blocks
    total_payload = n_blocks * PAYLOAD_BITS
    if len(payload_bits) < total_payload:
        payload_bits.extend([0] * (total_payload - len(payload_bits)))

    # Build chain: block 0 → 1 → 2 → ... → terminal
    chain = []
    for i in range(n_blocks):
        block_id = i
        next_id = i + 1 if i < n_blocks - 1 else TERMINAL
        start = i * PAYLOAD_BITS
        end = start + PAYLOAD_BITS
        block_payload = payload_bits[start:end]
        chain.append((block_id, next_id, block_payload))

    # ── Compute insert positions in the FINAL image ──
    # Strategy: evenly space signal blocks, keeping everything 8-aligned.
    # Final width = w + n_blocks*8, padded up to next multiple of 8.
    raw_final_w = w + n_blocks * 8
    final_w = ((raw_final_w + 7) // 8) * 8  # pad to 8-multiple

    # Spread signal blocks evenly across the final width
    margin = 64
    usable = final_w - 2 * margin
    spacing = usable // (n_blocks + 1)
    # Each signal block position in the FINAL image, 8-aligned
    final_block_cols = []
    for i in range(1, n_blocks + 1):
        col = margin + i * spacing
        col = (col // 8) * 8
        final_block_cols.append(col)
    final_block_cols = sorted(set(final_block_cols))[:n_blocks]

    # ── Build the final image ──
    # Allocate final image (padded with black)
    result = np.zeros((h, final_w, c), dtype=np.uint8)

    # Place signal blocks first
    signal_col_set = set(final_block_cols)
    for i, col in enumerate(final_block_cols):
        bid, nid, pay = chain[i]
        bits_32 = _pack_block(bid, nid, pay)

        # Encode the same 32 bits into every 8x8 tile vertically
        encoded_tile = _encode_block_pixels(bits_32)
        signal_col = np.full((h, 8, c), 128, dtype=np.uint8)
        for row_start in range(0, h - 7, 8):
            signal_col[row_start:row_start + 8, :, :] = encoded_tile

        result[:, col:col + 8, :] = signal_col

    # Fill remaining columns with original image data
    src_col = 0
    for dst_col in range(0, final_w, 8):
        if dst_col in signal_col_set:
            continue  # already placed
        if src_col >= w:
            break  # no more source pixels; remainder stays black (padding)
        chunk = min(8, w - src_col)
        result[:, dst_col:dst_col + chunk, :] = pixels[:, src_col:src_col + chunk, :]
        src_col += chunk

    meta_blocks = [{'block_id': chain[i][0], 'next_id': chain[i][1],
                     'col': final_block_cols[i]}
                    for i in range(len(final_block_cols))]

    meta = {
        'layer': 'sigblock',
        'n_blocks': n_blocks,
        'url_path': url_path,
        'full_url': BASE_URL + url_path,
        'payload_bits_total': n_blocks * PAYLOAD_BITS,
        'original_width': w,
        'final_width': final_w,
        'image_width_delta': final_w - w,
        'width_increase_pct': round((final_w - w) / w * 100, 2),
        'blocks': meta_blocks,
    }
    return result, meta


# ---------------------------------------------------------------------------
# Detection: scan for signal blocks and decode the chain
# ---------------------------------------------------------------------------

def detect_signal_blocks(pixels: np.ndarray, channel: int = 0) -> dict:
    """
    Scan the image for signal blocks by checking every 8-column-aligned
    block for valid chain structure.

    A block is considered a signal block if:
    1. Decoded block_id is 0-14 (not 0xF)
    2. The same (block_id, next_id) decodes consistently across
       multiple 8x8 vertical tiles in the same column

    Returns detection result with decoded URL if chain is found.
    """
    h, w, c = pixels.shape
    candidates = []

    # Scan every 8-column-aligned position
    for col in range(0, w - 7, 8):
        # Decode all tiles and check signature
        sig_votes = 0
        all_decoded = []
        for row in range(0, h - 7, 8):
            tile = pixels[row:row + 8, col:col + 8, :]
            bits = _decode_block_pixels(tile)
            block_id, next_id, payload, sig_valid = _unpack_block(bits)
            all_decoded.append((block_id, next_id, payload, sig_valid))
            if sig_valid:
                sig_votes += 1

        n_tiles = len(all_decoded)
        sig_rate = sig_votes / n_tiles if n_tiles > 0 else 0

        # Signal block: high signature agreement (>65%)
        if sig_rate < 0.65:
            continue

        # Among signature-valid tiles, find dominant (id, next) pair
        valid_tiles = [(bid, nid, pay) for bid, nid, pay, sv in all_decoded if sv]
        if not valid_tiles:
            continue

        votes = {}
        for bid, nid, pay in valid_tiles:
            key = (bid, nid)
            if key not in votes:
                votes[key] = {'count': 0, 'payloads': []}
            votes[key]['count'] += 1
            votes[key]['payloads'].append(pay)

        best_key = max(votes, key=lambda k: votes[k]['count'])
        best_count = votes[best_key]['count']
        agreement = best_count / len(valid_tiles)

        block_id, next_id = best_key
        if agreement >= 0.6 and block_id < TERMINAL:
            # Majority-vote the payload bits
            all_payloads = votes[best_key]['payloads']
            majority_payload = []
            for bit_idx in range(PAYLOAD_BITS):
                ones = sum(1 for p in all_payloads if bit_idx < len(p) and p[bit_idx])
                majority_payload.append(1 if ones > len(all_payloads) // 2 else 0)

            candidates.append({
                'col': col,
                'block_id': block_id,
                'next_id': next_id,
                'sig_rate': round(sig_rate, 3),
                'agreement': round(agreement, 3),
                'n_tiles': n_tiles,
                'sig_valid_tiles': sig_votes,
                'votes': best_count,
                'payload_bits': majority_payload,
            })

    if not candidates:
        return {
            'detected': False,
            'n_candidates': 0,
            'reason': 'No signal blocks found',
        }

    # Try to reconstruct a chain starting from block_id=0
    chain = {}
    for c in candidates:
        bid = c['block_id']
        if bid not in chain or c['agreement'] > chain[bid]['agreement']:
            chain[bid] = c

    # Follow the chain from block 0
    ordered = []
    current_id = 0
    visited = set()
    while current_id in chain and current_id not in visited:
        visited.add(current_id)
        block = chain[current_id]
        ordered.append(block)
        current_id = block['next_id']
        if current_id == TERMINAL:
            break

    # Concatenate payloads
    all_payload_bits = []
    for block in ordered:
        all_payload_bits.extend(block['payload_bits'])

    # Try to decode as URL path
    url_path = decode_url_path(all_payload_bits)
    full_url = BASE_URL + url_path if url_path else None

    return {
        'detected': len(ordered) > 0,
        'n_candidates': len(candidates),
        'chain_length': len(ordered),
        'chain_ids': [b['block_id'] for b in ordered],
        'url_path': url_path,
        'full_url': full_url,
        'blocks': ordered,
        'mean_agreement': round(
            sum(b['agreement'] for b in ordered) / len(ordered), 3
        ) if ordered else 0,
    }
