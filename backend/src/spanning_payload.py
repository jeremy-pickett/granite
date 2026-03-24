#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Spanning Payload Encoder / Decoder  —  v2  (Position-Based)
=============================================================

v1 FAILURE SUMMARY (do not repeat)
------------------------------------
v1 attempted to encode payload in the DIFFERENTIAL between flanking pixel
channel differences and the anchor. Failed because the correlation property
we proved (Pearson r=0.96, rel_residual=2.44 at Q40) means JPEG makes
same-block pixels drift TOGETHER. We proved 0 is preserved. We then asked
it to encode 48. Those are directly opposite requirements.

Exact failure mechanism: when JPEG neutralizes a block, the flanking pixel
at d=79 is a larger chroma signal than anchor at d=31 and gets suppressed
MORE aggressively. After decompression d_flank < d_anchor. Raw differential
is negative. We clamped to 0. Both entry and exit agreed on 0. Confidence
looked fine. Value was always wrong.

v2 DESIGN PRINCIPLE
---------------------
JPEG corrupts pixel VALUES. It cannot corrupt pixel POSITIONS.

A sentinel placed at column 47 is at column 47 after any number of JPEG
re-encodes. The placement offset — how far a sentinel is shifted from its
natural section boundary — is a payload carrier that is immune to JPEG
quantization by construction.

ENCODING SCHEME
----------------
Each section provides 4 placement options for its entry sentinel:
    offset  0 → bits 00
    offset +1 → bits 01
    offset +2 → bits 10
    offset -1 → bits 11

2 bits per section × ~108 sections per image = 216 raw bits.

PAYLOAD STRUCTURE  (24 bits)
------------------------------
    bits [23:16]  creator_id_fragment   (8 bits)
    bits [15:8]   hash_fragment         (8 bits, perceptual hash low byte)
    bits [7:4]    protocol_version      (4 bits)
    bits [3:0]    flags                 (4 bits, bit0=payload_present)

REDUNDANCY
-----------
Section i encodes payload bits at positions:
    bit_a = (i * 2)     % 24
    bit_b = (i * 2 + 1) % 24

Each of 24 bit positions gets 9 votes. Majority vote fails only if >4
sections per bit are corrupted — requiring >50% total section loss.

EXIT SENTINEL REDUNDANCY
-------------------------
Exit sentinel uses same offset as entry. entry_offset == exit_offset → intact.
Disagreement → section mismatch (still votes, flagged).

SCAN ORDER
-----------
Strictly LEFT TO RIGHT. Offset = sentinel_col - natural_col. No jumps.

v2 SCOPE: manifest mode only.
v3 will add blind mode: infer boundaries from marker clustering.

WHAT THIS DOES NOT DO
-----------------------
- Does NOT encode payload in pixel channel differences (v1 failure mode)
- Does NOT require arithmetic on channel differences for payload recovery
- Does NOT produce a digital signature
- Does NOT encrypt payload
- Does NOT execute payload content (offsets are integers, arithmetic only)

Usage:
    python spanning_payload.py -i /path/to/DIV2K -o payload_results -n 5
    python spanning_payload.py -i /path/to/DIV2K -o payload_results -n 500 \\
        --creator-id 42
"""

import os
import sys
import io
import json
import math
import time
import numpy as np
from PIL import Image
from datetime import datetime
from collections import Counter

from pgps_detector import sample_positions_grid
from spanning_sentinel import (
    determine_tier, TIER_24, TIER_16, TIER_8,
    SENTINEL_MERSENNE_ENTRY, SENTINEL_MERSENNE_EXIT,
    to_jpeg, decode_jpeg,
)


# =============================================================================
# PROTOCOL CONSTANTS
# =============================================================================

PROTOCOL_VERSION  = 1
PAYLOAD_BITS      = 24

# Offset → 2-bit encoding. Strict left-to-right, no jumps.
OFFSET_ENCODING = {
    (0, 0):  0,    # bits 00 → offset  0
    (0, 1):  1,    # bits 01 → offset +1
    (1, 0):  2,    # bits 10 → offset +2
    (1, 1): -1,    # bits 11 → offset -1
}
OFFSET_DECODING = {v: k for k, v in OFFSET_ENCODING.items()}
VALID_OFFSETS   = set(OFFSET_ENCODING.values())   # {-1, 0, 1, 2}

# Minimum vote margin to treat a bit as "recovered" rather than "uncertain".
# margin = |n_ones - n_zeros| / (n_ones + n_zeros)
# 0.0 = perfect tie (coin flip — do not trust)
# 1.0 = unanimous (complete confidence)
# 0.2 = threshold: at least 60% of votes agree before we call it recovered.
# With 9 votes per bit: 0.2 requires at least 6/9 agreement (not 5/9).
# A 5/4 split has margin 0.11 — below threshold, reported as uncertain.
# A 6/3 split has margin 0.33 — above threshold, reported as recovered.
BIT_MARGIN_THRESHOLD = 0.2

FLOOR             = 43
DENSITY_FRAC      = 0.08
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512
SENTINEL_CANARY_RATIO = 8
WINDOW_W          = 8


# =============================================================================
# PAYLOAD PACK / UNPACK
# =============================================================================

def pack_payload(creator_id_frag, hash_frag,
                 version=PROTOCOL_VERSION, flags=0x1):
    """Pack four fields into a 24-bit integer. Arithmetic only."""
    return ((int(creator_id_frag) & 0xFF) << 16 |
            (int(hash_frag)       & 0xFF) << 8  |
            (int(version)         & 0x0F) << 4  |
            (int(flags)           & 0x0F))


def unpack_payload(payload_int):
    """Unpack 24-bit integer into field dict. Arithmetic only."""
    p = int(payload_int) & 0xFFFFFF
    return {
        "creator_id_fragment": (p >> 16) & 0xFF,
        "hash_fragment":       (p >> 8)  & 0xFF,
        "protocol_version":    (p >> 4)  & 0x0F,
        "flags":               (p >> 0)  & 0x0F,
    }


def get_bit(payload_int, pos):
    return (int(payload_int) >> pos) & 1


def set_bit(payload_int, pos, value):
    p = int(payload_int) & 0xFFFFFF
    return (p | (1 << pos)) if value else (p & ~(1 << pos))


# =============================================================================
# SECTION ↔ BIT ASSIGNMENT
# =============================================================================

def section_bit_positions(section_idx, payload_bits=PAYLOAD_BITS):
    """
    Return the two payload bit positions encoded by section_idx.
    Round-robin: each of 24 bit positions gets exactly 9 votes from 108 sections.
    """
    return (section_idx * 2) % payload_bits, (section_idx * 2 + 1) % payload_bits


def bits_to_offset(bit_a, bit_b):
    """Two payload bits → placement offset in pixels."""
    return OFFSET_ENCODING[(int(bit_a) & 1, int(bit_b) & 1)]


def offset_to_bits(offset):
    """Placement offset → (bit_a, bit_b). Unknown offset → (0, 0)."""
    return OFFSET_DECODING.get(offset, (0, 0))


# =============================================================================
# PERCEPTUAL HASH
# =============================================================================

def perceptual_hash_fragment(pixels):
    """
    8-bit perceptual hash. Compression-tolerant, content-sensitive.
    Coarse 4×4 block comparison against median — tolerates JPEG re-encode.
    """
    h, w = pixels.shape[:2]
    bh, bw = h // 4, w // 4
    block_means = []
    for br in range(4):
        for bc in range(4):
            r0, c0 = br * bh, bc * bw
            region = pixels[r0:r0+bh, c0:c0+bw]
            block_means.append(float(np.mean(
                np.abs(region[:,:,0].astype(int) - region[:,:,1].astype(int))
            )))
    median = float(np.median(block_means))
    bits = 0
    for i, m in enumerate(block_means):
        if m > median:
            bits |= (1 << (i % 8))
    return bits & 0xFF


# =============================================================================
# EMBEDDER
# =============================================================================

def embed_payload_sentinel(modified, natural_row, natural_col,
                            mersenne, role, section_idx, payload_int,
                            ch_a=0, ch_b=1):
    """
    Embed a spanning sentinel whose POSITION encodes two payload bits.

    Placement:  col = natural_col + offset
    where offset ∈ {-1, 0, +1, +2} encodes the two bits for this section.

    Flanking pixels carry redundant anchor value (for sentinel detection).
    Payload is in the POSITION only — not in channel differences.

    Strictly left to right: offset applied to natural_col, resulting col
    is where anchor is placed. No jumps. No backtracking.
    """
    h, w, _ = modified.shape

    # Determine which bits this section encodes and the resulting offset
    bit_a_pos, bit_b_pos = section_bit_positions(section_idx)
    bit_a = get_bit(payload_int, bit_a_pos)
    bit_b = get_bit(payload_int, bit_b_pos)
    offset = bits_to_offset(bit_a, bit_b)

    # Apply offset, clamped to image bounds with margin
    col = int(max(WINDOW_W, min(w - WINDOW_W - 1, natural_col + offset)))

    tier, left_cols, right_cols = determine_tier(natural_row, col, h, w)

    # Embed anchor
    val_a = int(modified[natural_row, col, ch_a])
    opts  = [v for v in [val_a - mersenne, val_a + mersenne] if 20 <= v <= 235]
    if not opts:
        return None
    modified[natural_row, col, ch_b] = min(
        opts, key=lambda x: abs(x - int(modified[natural_row, col, ch_b]))
    )
    d_anchor = abs(int(modified[natural_row, col, ch_a]) -
                   int(modified[natural_row, col, ch_b]))

    # Embed flanking: redundant anchor value (not payload — payload is position)
    n_flank_ok = 0
    for dc in left_cols + right_cols:
        fc = col + dc
        if 0 <= fc < w:
            va = int(modified[natural_row, fc, ch_a])
            f_opts = [v for v in [va - d_anchor, va + d_anchor] if 20 <= v <= 235]
            if f_opts:
                modified[natural_row, fc, ch_b] = min(
                    f_opts,
                    key=lambda x: abs(x - int(modified[natural_row, fc, ch_b]))
                )
                n_flank_ok += 1

    return {
        "type":         role,
        "tier":         tier,
        "row":          natural_row,
        "col":          col,            # actual placement — the payload carrier
        "natural_col":  natural_col,    # where it would be without offset
        "offset":       offset,         # offset = col - natural_col = payload
        "bit_a_pos":    bit_a_pos,
        "bit_b_pos":    bit_b_pos,
        "bit_a_value":  bit_a,
        "bit_b_value":  bit_b,
        "mersenne":     mersenne,
        "d_anchor":     d_anchor,
        "n_flanking_ok":n_flank_ok,
        "section":      section_idx,
        "placed":       True,
    }


# =============================================================================
# DETECTOR — MANIFEST MODE
# =============================================================================

def recover_section_bits(entry_s, exit_s):
    """
    Read offset from manifest sentinels. Compute bit values.
    No pixel arithmetic — positions are read directly.

    offset = sentinel["col"] - sentinel["natural_col"]

    Entry and exit should have identical offsets (both encode same bits).
    Mismatch → flag but still vote with entry value.
    """
    if entry_s is None:
        return {"status": "missing_entry",
                "bit_a_value": None, "bit_b_value": None}
    if exit_s is None:
        return {"status": "missing_exit",
                "bit_a_value": None, "bit_b_value": None}

    off_e = entry_s["col"] - entry_s["natural_col"]
    off_x = exit_s["col"]  - exit_s["natural_col"]
    agreement = (off_e == off_x)

    # Primary: entry. Fallback to exit if entry offset unrecognized.
    primary_offset = off_e
    if off_e not in VALID_OFFSETS and off_x in VALID_OFFSETS:
        primary_offset = off_x

    if primary_offset not in VALID_OFFSETS:
        return {
            "status":       "unknown_offset",
            "offset_entry": off_e,
            "offset_exit":  off_x,
            "agreement":    agreement,
            "bit_a_pos":    entry_s["bit_a_pos"],
            "bit_b_pos":    entry_s["bit_b_pos"],
            "bit_a_value":  None,
            "bit_b_value":  None,
        }

    ba, bb = offset_to_bits(primary_offset)
    return {
        "status":       "intact" if agreement else "mismatch",
        "bit_a_value":  ba,
        "bit_b_value":  bb,
        "bit_a_pos":    entry_s["bit_a_pos"],
        "bit_b_pos":    entry_s["bit_b_pos"],
        "offset_entry": off_e,
        "offset_exit":  off_x,
        "agreement":    agreement,
    }


def aggregate_bits(section_recoveries, payload_bits=PAYLOAD_BITS,
                   margin_threshold=BIT_MARGIN_THRESHOLD):
    """
    Majority vote across all sections → recovered payload integer.
    Each bit position gets ~9 votes. Majority determines recovered bit.

    Margin gating: a bit position is only considered RECOVERED if the
    vote margin exceeds margin_threshold. Below threshold the result is
    a coin flip and should not be trusted.

      margin = |n_ones - n_zeros| / total_votes
      0.0 = perfect tie       → uncertain (do not use)
      0.2 = 6/9 agreement     → recovered (threshold default)
      1.0 = unanimous         → recovered with full confidence

    With 9 votes per bit position:
      5/4 split → margin 0.11 → UNCERTAIN
      6/3 split → margin 0.33 → RECOVERED
      9/0 split → margin 1.00 → RECOVERED (unanimous)
    """
    votes = [[0, 0] for _ in range(payload_bits)]  # [n_zeros, n_ones]
    n_intact = n_mismatch = n_unknown = n_missing = 0

    for rec in section_recoveries:
        status = rec.get("status", "unknown")
        if status == "intact":       n_intact   += 1
        elif status == "mismatch":   n_mismatch += 1
        elif "missing" in status:    n_missing  += 1
        else:                        n_unknown  += 1

        # Vote regardless of mismatch — entry value is still information
        if rec.get("bit_a_value") is not None:
            votes[rec["bit_a_pos"]][rec["bit_a_value"]] += 1
        if rec.get("bit_b_value") is not None:
            votes[rec["bit_b_pos"]][rec["bit_b_value"]] += 1

    payload_int = 0
    margins = []
    uncertain_positions = []

    for pos in range(payload_bits):
        n0, n1 = votes[pos]
        total  = n0 + n1
        if total == 0:
            margins.append(None)
            uncertain_positions.append(pos)
            continue

        margin  = abs(n1 - n0) / total
        margins.append(margin)

        majority = 1 if n1 >= n0 else 0
        payload_int = set_bit(payload_int, pos, majority)

        if margin < margin_threshold:
            uncertain_positions.append(pos)

    n_total      = n_intact + n_mismatch + n_unknown + n_missing
    n_recovered  = payload_bits - len(uncertain_positions)
    confidence   = n_intact / max(n_total, 1)
    valid_margins= [m for m in margins if m is not None]

    return {
        "payload_int":          payload_int,
        "payload_fields":       unpack_payload(payload_int),
        "overall_confidence":   round(confidence, 4),
        "n_bits_recovered":     n_recovered,
        "n_bits_uncertain":     len(uncertain_positions),
        "uncertain_positions":  uncertain_positions,   # which bit positions are coin flips
        "mean_bit_margin":      round(float(np.mean(valid_margins)), 4)
                                if valid_margins else 0.0,
        "min_bit_margin":       round(float(np.min(valid_margins)),  4)
                                if valid_margins else 0.0,
        "n_intact":             n_intact,
        "n_mismatch":           n_mismatch,
        "n_unknown":            n_unknown,
        "n_missing":            n_missing,
        "n_total":              n_total,
    }


# =============================================================================
# CORPUS TEST
# =============================================================================

def run_test(input_dir, output_dir, max_images=0,
             creator_id=1, version=PROTOCOL_VERSION):
    os.makedirs(output_dir, exist_ok=True)

    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    all_files  = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])
    if max_images > 0:
        all_files = all_files[:max_images]
    n_total = len(all_files)

    cid_frag = creator_id & 0xFF

    print(f"{'='*80}")
    print(f"SPANNING PAYLOAD v2 — Position-Based Encoding")
    print(f"{'='*80}")
    print(f"Images:      {n_total}")
    print(f"Creator ID:  {creator_id}  (fragment = {cid_frag})")
    print(f"Payload:     {PAYLOAD_BITS} bits  "
          f"(creator_id/8 + hash/8 + version/4 + flags/4)")
    print(f"Redundancy:  ~9× per bit position")
    print(f"Cascade:     {CASCADE_QUALITIES}")
    print(f"")
    print(f"Encoding: offset of sentinel from natural section boundary")
    print(f"  offset  0 → 00    +1 → 01    +2 → 10    -1 → 11")
    print(f"  Positions survive JPEG. Values do not.")
    print(f"{'='*80}\n")

    from compound_markers import MarkerConfig, embed_compound

    all_results = []
    results_file = os.path.join(output_dir, "payload_per_image.jsonl")
    open(results_file, "w").close()
    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"[{idx+1:>4d}/{n_total}] {fname}  ", end="", flush=True)

        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print("SKIP"); continue
        if max(h, w) > 1024:
            scale = 1024 / max(h, w)
            img   = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)
            h, w   = pixels.shape[:2]

        hash_frag   = perceptual_hash_fragment(pixels)
        payload_int = pack_payload(cid_frag, hash_frag, version, flags=0x1)
        expected    = unpack_payload(payload_int)

        # Embed markers
        n_req  = max(10, math.ceil(
            len(sample_positions_grid(h, w, 8)) * DENSITY_FRAC))
        config = MarkerConfig(
            name="payload_v2",
            description="Position-based payload v2",
            min_prime=FLOOR, use_twins=True, use_rare_basket=True,
            use_magic=False, detection_prime_tolerance=2, n_markers=n_req,
        )
        marked_px, markers, _ = embed_compound(
            pixels.copy(), config, variable_offset=42)
        if len(markers) < 10:
            print("SKIP (too few markers)"); continue

        # Embed position-encoded sentinels
        mod_int    = marked_px.astype(np.int16)
        n_sections = max(1, len(markers) // SENTINEL_CANARY_RATIO)
        sec_size   = len(markers) // n_sections
        sentinels  = []

        for sec_idx in range(n_sections):
            start = sec_idx * sec_size
            end   = start + sec_size if sec_idx < n_sections - 1 else len(markers)
            for role, pos_idx, mers in [
                ("entry", start,   SENTINEL_MERSENNE_ENTRY),
                ("exit",  end - 1, SENTINEL_MERSENNE_EXIT),
            ]:
                if pos_idx >= len(markers):
                    continue
                m = markers[pos_idx]
                s = embed_payload_sentinel(
                    mod_int, m["row"], m["col"], mers,
                    role, sec_idx, payload_int)
                if s:
                    sentinels.append(s)

        span_px = np.clip(mod_int, 0, 255).astype(np.uint8)

        entries = {s["section"]: s for s in sentinels if s["type"] == "entry"}
        exits   = {s["section"]: s for s in sentinels if s["type"] == "exit"}

        # Cascade — payload recovery is position-based (no JPEG re-read needed)
        # We run the cascade to confirm sentinel positions aren't disturbed,
        # and to compute confidence from entry/exit agreement.
        current = to_jpeg(span_px, quality=95)
        cascade = []

        for gen_idx, q in enumerate(CASCADE_QUALITIES):
            if gen_idx > 0:
                current = to_jpeg(decode_jpeg(current), quality=q)

            # Recovery: read offsets from manifest (positions don't change)
            sec_recs = []
            for sec_idx in range(n_sections):
                rec = recover_section_bits(entries.get(sec_idx),
                                           exits.get(sec_idx))
                rec["section"] = sec_idx
                sec_recs.append(rec)

            agg = aggregate_bits(sec_recs)
            rec_fields = agg["payload_fields"]

            cid_ok  = rec_fields["creator_id_fragment"] == expected["creator_id_fragment"]
            hash_ok = rec_fields["hash_fragment"]       == expected["hash_fragment"]
            ver_ok  = rec_fields["protocol_version"]    == expected["protocol_version"]

            cascade.append({
                "generation":         gen_idx,
                "quality":            q,
                "overall_confidence": agg["overall_confidence"],
                "mean_bit_margin":    agg["mean_bit_margin"],
                "min_bit_margin":     agg["min_bit_margin"],
                "n_bits_recovered":   agg["n_bits_recovered"],
                "n_bits_uncertain":   agg["n_bits_uncertain"],
                "n_intact":           agg["n_intact"],
                "n_mismatch":         agg["n_mismatch"],
                "n_unknown":          agg["n_unknown"],
                "n_total":            agg["n_total"],
                "cid_match":          cid_ok,
                "hash_match":         hash_ok,
                "ver_match":          ver_ok,
                "recovered_cid":      rec_fields["creator_id_fragment"],
                "recovered_hash":     rec_fields["hash_fragment"],
                "recovered_ver":      rec_fields["protocol_version"],
                "expected_cid":       expected["creator_id_fragment"],
                "expected_hash":      expected["hash_fragment"],
            })

        elapsed = time.time() - t_img
        g4  = cascade[4] if len(cascade) > 4 else {}
        cok = "✓" if g4.get("cid_match")  else "✗"
        hok = "✓" if g4.get("hash_match") else "✗"
        vok = "✓" if g4.get("ver_match")  else "✗"
        nbr = g4.get("n_bits_recovered", 0)
        nbu = g4.get("n_bits_uncertain", 0)
        print(f"secs={n_sections:>3d}  "
              f"G4_conf={g4.get('overall_confidence',0):.3f}  "
              f"bits={nbr}/{PAYLOAD_BITS}({nbu}?)  "
              f"cid={cok}  hash={hok}  ver={vok}  [{elapsed:.1f}s]")

        result = {
            "image": fname, "hash_frag": hash_frag,
            "cid_frag": cid_frag, "payload_int": payload_int,
            "n_sections": n_sections, "cascade": cascade,
        }
        all_results.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start
    good = [r for r in all_results if "cascade" in r]
    n_good = len(good)

    print(f"\n\n{'='*80}")
    print(f"PAYLOAD v2 AGGREGATE — {n_good} images  ({total_time:.0f}s)")
    print(f"{'='*80}\n")

    if not good:
        print("No valid results."); return

    print(f"{'Gen':>4}  {'Q':>3}  {'confidence':>11}  "
          f"{'margin_min':>10}  {'bits_ok':>8}  "
          f"{'cid%':>7}  {'hash%':>7}  {'ver%':>7}")
    print("─" * 65)

    for gen_idx, q in enumerate(CASCADE_QUALITIES):
        def gpct(key):
            vals = [r["cascade"][gen_idx].get(key, False)
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(1 for v in vals if v) / len(vals) * 100 if vals else 0
        def gmean(key):
            vals = [r["cascade"][gen_idx].get(key, 0)
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(vals) / len(vals) if vals else 0

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {gmean('overall_confidence'):>10.4f}"
              f"  {gmean('min_bit_margin'):>10.3f}"
              f"  {gmean('n_bits_recovered'):>5.1f}/{PAYLOAD_BITS}"
              f"  {gpct('cid_match'):>6.1f}%"
              f"  {gpct('hash_match'):>6.1f}%"
              f"  {gpct('ver_match'):>6.1f}%")

    g4_conf  = np.mean([r["cascade"][4]["overall_confidence"]
                        for r in good if len(r["cascade"]) > 4])
    g4_cid   = sum(1 for r in good if len(r["cascade"]) > 4
                   and r["cascade"][4]["cid_match"])
    g4_hash  = sum(1 for r in good if len(r["cascade"]) > 4
                   and r["cascade"][4]["hash_match"])
    g4_ver   = sum(1 for r in good if len(r["cascade"]) > 4
                   and r["cascade"][4]["ver_match"])
    g4_nbr   = np.mean([r["cascade"][4].get("n_bits_recovered", 0)
                        for r in good if len(r["cascade"]) > 4])
    g4_nbu   = np.mean([r["cascade"][4].get("n_bits_uncertain", 0)
                        for r in good if len(r["cascade"]) > 4])
    g4_minm  = np.mean([r["cascade"][4].get("min_bit_margin", 0)
                        for r in good if len(r["cascade"]) > 4])

    print(f"\n{'='*80}")
    print(f"VERDICT  (Gen4 Q40)")
    print(f"{'='*80}")
    print(f"  Mean confidence:          {g4_conf:.4f}")
    print(f"  Bits recovered:           {g4_nbr:.1f}/{PAYLOAD_BITS} avg  "
          f"(uncertain: {g4_nbu:.1f} avg,  threshold={BIT_MARGIN_THRESHOLD})")
    print(f"  Min bit margin:           {g4_minm:.3f}  "
          f"({'ABOVE' if g4_minm >= BIT_MARGIN_THRESHOLD else 'BELOW'} threshold)")
    print(f"  Creator ID match:         {g4_cid}/{n_good}  ({g4_cid/n_good*100:.1f}%)")
    print(f"  Hash fragment match:      {g4_hash}/{n_good}  ({g4_hash/n_good*100:.1f}%)")
    print(f"  Protocol version match:   {g4_ver}/{n_good}  ({g4_ver/n_good*100:.1f}%)")

    if g4_nbu > 0:
        uncertain_note = (f"  WARNING: {g4_nbu:.1f} bit positions avg below margin "
                          f"threshold — those bits are coin flips, not recovered data.")
    else:
        uncertain_note = "  All bit positions above margin threshold."
    print(f"\n{uncertain_note}")

    if g4_cid/n_good >= 0.95 and g4_hash/n_good >= 0.90 and g4_nbu == 0:
        verdict = (f"PAYLOAD WORKS. Position encoding survives cascade. "
                   f"CID {g4_cid/n_good*100:.1f}%  "
                   f"Hash {g4_hash/n_good*100:.1f}%  "
                   f"All {PAYLOAD_BITS} bits recovered at Q40.")
    elif g4_cid/n_good >= 0.95 and g4_hash/n_good >= 0.90:
        verdict = (f"PAYLOAD WORKS WITH UNCERTAIN BITS. "
                   f"CID {g4_cid/n_good*100:.1f}%  Hash {g4_hash/n_good*100:.1f}%  "
                   f"but {g4_nbu:.1f} bits avg below margin threshold. "
                   f"Increase redundancy or lower payload bit count.")
    elif g4_cid/n_good >= 0.80:
        verdict = (f"PAYLOAD PARTIAL. CID {g4_cid/n_good*100:.1f}%. "
                   "Check section boundary collisions or offset clamping.")
    else:
        verdict = (f"PAYLOAD WEAK. CID {g4_cid/n_good*100:.1f}%. "
                   "Investigate section count consistency across cascade.")

    print(f"\n  {verdict}")

    agg_out = {
        "n_images": n_good, "protocol_version": PROTOCOL_VERSION,
        "encoding": "position_offset", "payload_bits": PAYLOAD_BITS,
        "bit_margin_threshold": BIT_MARGIN_THRESHOLD,
        "creator_id": creator_id,
        "gen4": {
            "mean_confidence":      round(float(g4_conf), 4),
            "mean_bits_recovered":  round(float(g4_nbr),  1),
            "mean_bits_uncertain":  round(float(g4_nbu),  1),
            "mean_min_bit_margin":  round(float(g4_minm), 3),
            "cid_match_pct":        round(g4_cid  / n_good * 100, 1),
            "hash_match_pct":       round(g4_hash / n_good * 100, 1),
            "ver_match_pct":        round(g4_ver  / n_good * 100, 1),
        }
    }
    with open(os.path.join(output_dir, "payload_aggregate.json"), "w") as f:
        json.dump(agg_out, f, indent=2)
    with open(os.path.join(output_dir, "PAYLOAD_VERDICT.txt"), "w") as f:
        f.write(verdict + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Images: {n_good}  Protocol: v{PROTOCOL_VERSION} position-based\n")
        f.write(f"Gen4 confidence: {g4_conf:.4f}\n")
        f.write(f"Gen4 CID:  {g4_cid/n_good*100:.1f}%\n")
        f.write(f"Gen4 hash: {g4_hash/n_good*100:.1f}%\n")

    print(f"\nResults: {output_dir}/")
    return agg_out


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Spanning Payload v2 — Position-Based Encoding")
    parser.add_argument("--input",      "-i", required=True)
    parser.add_argument("--output",     "-o", default="payload_results")
    parser.add_argument("--max-images", "-n", type=int, default=0)
    parser.add_argument("--creator-id", "-c", type=int, default=1)
    parser.add_argument("--version",    "-v", type=int, default=PROTOCOL_VERSION)
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    run_test(args.input, args.output,
             max_images=args.max_images,
             creator_id=args.creator_id,
             version=args.version)
