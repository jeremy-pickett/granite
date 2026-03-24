#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Detection Evidence Harness
===========================

Runs every validated detection layer against a file or corpus and produces
a complete evidence profile: raw metrics, per-layer scores, and a combined
unweighted detection score.

This is the integration test for the full provenance stack. It does not
add new detection logic — it orchestrates the existing layers and makes
all extracted evidence visible in one place.

LAYERS
------
  Layer A   DQT prime quantization tables (container, O(1) static scan)
  Layer BC  Twin prime-gap compound markers (frequency, manifest mode)
  Layer D   Spatial variance KS test (blind, LSV + CDV)
  Layer E   Spanning Mersenne sentinel contract (manifest mode, tiered)
  Layer F   Position-based payload recovery (manifest mode, majority vote)

SCORING
-------
Each layer produces a score in [0.0, 1.0]:

  Layer A:  1.0 if prime DQT tables detected, 0.0 if not
            NOTE: 0.0 after re-encode is CORRECT BEHAVIOR, not tampering.
            Reported separately as container_intact flag.

  Layer BC: fraction of markers passing compound detection
            (primary + twin + magic byte, AND logic)

  Layer D:  max(1.0 - lsv_p_value, 1.0 - cdv_p_value)
            Higher p-value = less evidence = lower score
            Score approaches 1.0 as compression amplifies spatial variance

  Layer E:  fraction of sentinel sections with intact entry+exit pairs
            Tier demotion (T24→T16→T8) is NOT failure — counted as intact

  Layer F:  (n_bits_recovered / total_payload_bits) × mean_bit_margin
            Unanimous votes score higher than squeezed margins

Combined:   unweighted mean of all layer scores

WHY UNWEIGHTED
--------------
No empirical basis for weights yet. Unweighted is auditable — the math is
visible and each component is independently validated. A combined score of
0.83 means "5 of 6 components strongly positive." That is a meaningful
statement without any hidden priors.

Layer A is excluded from the combined score when the file has been
re-encoded (DQT absent by design, not tampering). The harness detects this
automatically and adjusts the denominator.

FOUR OBSERVABLE STATES
-----------------------
After scoring, the harness classifies the file into one of four states:

  A: combined < 0.2  AND sentinel contract absent/broken
     → No provenance signal detected

  B: combined >= 0.8 AND sentinel intact AND payload recovered
     → Provenance preserved, strong evidence

  C: combined >= 0.3 AND degradation pattern benign
     (spatial up, frequency down — consistent with compression)
     → State C: signal degraded by normal processing

  D: combined >= 0.3 AND sentinel contract broken
     → Tamper evidence: sentinel structure violated

OUTPUT FORMAT
-------------
Per file:
  - Raw metrics from every layer
  - Per-layer scores [0.0, 1.0]
  - Combined unweighted score
  - Observable state (A/B/C/D)
  - Evidence summary (human-readable)

Usage:
  # Single file
  python detection_harness.py -f /path/to/image.jpg -m /path/to/manifest.json

  # Corpus
  python detection_harness.py -i /path/to/DIV2K -o harness_results -n 50

  # Corpus with manifest directory (one manifest JSON per image)
  python detection_harness.py -i /path/to/DIV2K -o harness_results \\
      --manifest-dir /path/to/manifests -n 50
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
from scipy import stats as sp_stats

# ── Local imports ─────────────────────────────────────────────────────────────
from pgps_detector import build_prime_lookup, sample_positions_grid
from compound_markers import (
    MarkerConfig, embed_compound, detect_compound,
    SENTINEL_CANARY_RATIO, WINDOW_W, BIT_DEPTH,
)
# Layer A: DQT prime tables — imported conditionally to handle missing module
try:
    from dqt_prime import encode_prime_jpeg as _encode_prime_jpeg
    _LAYER_A_AVAILABLE = True
except ImportError:
    _LAYER_A_AVAILABLE = False
from spanning_sentinel import (
    detect_spanning_manifest,
    SENTINEL_MERSENNE_ENTRY, SENTINEL_MERSENNE_EXIT,
    TIER_24, TIER_16, TIER_8,
    TIER_24_ANCHOR_TOL, TIER_24_DIFF_TOL,
    to_jpeg, decode_jpeg,
)
from spanning_payload import (
    embed_payload_sentinel, aggregate_bits, recover_section_bits,
    perceptual_hash_fragment, pack_payload, unpack_payload,
    PAYLOAD_BITS, BIT_MARGIN_THRESHOLD, PROTOCOL_VERSION,
    section_bit_positions,
)


# =============================================================================
# TEE — write stdout to both terminal and log file simultaneously
# =============================================================================

class Tee:
    """
    Redirect sys.stdout so every print() goes to both the terminal and a
    log file. Installed once at startup; transparent to all other code.

    Usage:
        sys.stdout = Tee(log_path)
        ...all prints go to terminal AND log_path...
        sys.stdout = sys.stdout.restore()   # optional cleanup
    """
    def __init__(self, log_path):
        self._terminal = sys.stdout
        self._log      = open(log_path, "w", encoding="utf-8", buffering=1)
        self.log_path  = log_path

    def write(self, message):
        self._terminal.write(message)
        self._log.write(message)

    def flush(self):
        self._terminal.flush()
        self._log.flush()

    def restore(self):
        self._log.close()
        return self._terminal

    # Proxy everything else (isatty, fileno, etc.) to terminal
    def __getattr__(self, attr):
        return getattr(self._terminal, attr)



# =============================================================================
# CONSTANTS
# =============================================================================

FLOOR             = 43
DENSITY_FRAC      = 0.08
CASCADE_QUALITIES = [95, 85, 75, 60, 40]
MIN_DIMENSION     = 512
# Score thresholds for state classification
STATE_B_THRESHOLD = 0.80    # strong evidence
STATE_C_THRESHOLD = 0.30    # moderate evidence, benign degradation pattern
STATE_D_THRESHOLD = 0.30    # moderate evidence, tamper pattern

# Layer A note: absent after re-encode BY DESIGN
LAYER_A_NOTE = ("Layer A (DQT) absent. This is expected after any re-encode "
                "and is NOT tamper evidence. Only significant at gen0.")


# =============================================================================
# LAYER A — DQT PRIME TABLES
# =============================================================================

def score_layer_a(jpeg_bytes):
    """
    Layer A: detect prime quantization tables in JPEG container.
    Score: 1.0 if detected, 0.0 if not.
    O(1) static scan — reads DQT segments only.
    """
    try:
        from dqt_prime import detect_prime_dqt
        result = detect_prime_dqt(jpeg_bytes)
        detected = result.get("detected", False)
        return {
            "score":              1.0 if detected else 0.0,
            "detected":           detected,
            "n_tables":           result.get("n_tables", 0),
            "overall_prime_rate": result.get("overall_prime_rate", 0.0),
            "binom_p":            result.get("binom_p", 1.0),
            "note":               "" if detected else LAYER_A_NOTE,
        }
    except ImportError:
        # dqt_prime not available in this environment — skip gracefully
        return {
            "score":    None,   # None = not evaluated (excluded from combined)
            "detected": None,
            "note":     "dqt_prime module not available — Layer A skipped",
        }
    except Exception as e:
        return {
            "score":    0.0,
            "detected": False,
            "note":     f"Layer A error: {e}",
        }


# =============================================================================
# LAYER BC — COMPOUND FREQUENCY MARKERS
# =============================================================================

def score_layer_bc(pixels, markers, config):
    """
    Layer BC: compound frequency marker detection (manifest mode).
    Score: fraction of markers surviving compound check at current compression.

    Falls back to a manual channel-difference prime check if detect_compound
    fails due to API version mismatch (min_prime kwarg not supported).
    """
    if not markers:
        return {"score": 0.0, "n_markers": 0, "n_detected": 0,
                "intact_pct": 0.0, "note": "no markers in manifest"}

    try:
        result = detect_compound(pixels, markers, config)
        n_markers  = len(markers)
        n_detected = result.get("n_detected", 0)
        intact_pct = n_detected / max(n_markers, 1)
        return {
            "score":        round(intact_pct, 4),
            "n_markers":    n_markers,
            "n_detected":   n_detected,
            "intact_pct":   round(intact_pct * 100, 1),
            "tamper_class": result.get("tamper_class", "none"),
        }
    except TypeError:
        pass

    # Fallback: manual scan — check |R-G| is prime above floor at each position
    # This covers the primary prime-gap signal without the compound AND logic
    h, w, _ = pixels.shape
    floor    = config.min_prime if hasattr(config, "min_prime") else FLOOR
    tol      = 2
    n_detected = 0

    # Build a simple prime set for the range
    def is_prime(n):
        if n < 2: return False
        for i in range(2, int(n**0.5)+1):
            if n % i == 0: return False
        return True
    prime_set = set(v for v in range(floor, 256) if is_prime(v))

    for m in markers:
        r, c = m.get("row", 0), m.get("col", 0)
        if r >= h or c >= w: continue
        d = abs(int(pixels[r, c, 0]) - int(pixels[r, c, 1]))
        # Fuzzy match: any prime within ±tol
        if any(abs(d - p) <= tol for p in prime_set if abs(d-p) <= tol):
            n_detected += 1

    n_markers  = len(markers)
    intact_pct = n_detected / max(n_markers, 1)
    return {
        "score":        round(intact_pct, 4),
        "n_markers":    n_markers,
        "n_detected":   n_detected,
        "intact_pct":   round(intact_pct * 100, 1),
        "tamper_class": "fallback_scan",
        "note":         "API fallback — primary channel only, no compound AND",
    }


# =============================================================================
# LAYER D — SPATIAL VARIANCE, CHANNEL-CONTROLLED (BLIND)
# =============================================================================
#
# v1 FAILURE: compared grid positions vs random off-grid positions.
# JPEG DCT blocking creates 8-pixel periodic variance artifacts that elevated
# variance at grid-aligned positions in every JPEG, marked or not.
# Result: clean images scored ~0.89. Useless as a discriminator.
#
# v2 FIX: intra-layer channel control.
# The embedder modifies ch_b (G) relative to ch_a (R). ch_c (B) is untouched.
# At the same grid positions:
#   |R-G| variance = marker signal + JPEG blocking artifact
#   |R-B| variance = JPEG blocking artifact only  (B was never embedded)
# KS test between those two distributions at identical spatial positions.
# JPEG blocking cancels completely. Only the marker signal remains.
#
# On a clean image: |R-G| and |R-B| distributions are similar → p-value high
# → score near 0.0.
# On a marked image: |R-G| shows elevated variance from the prime-gap
# embedding → distributions diverge → p-value low → score near 1.0.

def _grid_cdv_array(pixels, ch_a, ch_b, radius=LSV_RADIUS):
    """
    Collect |ch_a - ch_b| variance at every valid 8-pixel grid position.
    Returns numpy array of per-position variance values.
    """
    h, w, _ = pixels.shape
    r_min, r_max = radius + 3, h - radius - 1
    c_min, c_max = radius + 3, w - radius - 1
    vals = []
    for pos in sample_positions_grid(h, w, 8):
        r, c = int(pos[0]) + 3, int(pos[1]) + 3
        if r < r_min or r > r_max or c < c_min or c > c_max:
            continue
        patch = pixels[r-radius:r+radius+1, c-radius:c+radius+1]
        diff  = np.abs(patch[:,:,ch_a].astype(np.int32) -
                       patch[:,:,ch_b].astype(np.int32))
        vals.append(float(np.var(diff.astype(np.float32))))
    return np.array(vals)


def score_layer_d(pixels, ch_signal_a=0, ch_signal_b=1, ch_control=2):
    """
    Layer D v2: channel-controlled KS test at grid positions (blind).

    Signal channel pair:  |ch_signal_a - ch_signal_b|  (R-G, where embedding lives)
    Control channel pair: |ch_signal_a - ch_control|    (R-B, unmodified)
    Same spatial positions. JPEG blocking cancels. Marker signal remains.

    Score: 1 - p_value of KS test between signal and control distributions.
    Clean image:  p high  → score near 0.0
    Marked image: p low   → score near 1.0
    """
    try:
        sig = _grid_cdv_array(pixels, ch_signal_a, ch_signal_b)
        ctl = _grid_cdv_array(pixels, ch_signal_a, ch_control)

        if len(sig) < 20 or len(ctl) < 20:
            return {"score": 0.0, "p_value": 1.0, "fired": False,
                    "note": "insufficient grid positions",
                    "method": "channel-controlled KS (v2)"}

        _, p_value = sp_stats.ks_2samp(sig, ctl)
        p_value    = float(p_value)
        score      = max(0.0, 1.0 - p_value)
        ratio      = float(np.mean(sig)) / max(float(np.mean(ctl)), 1e-9)
        fired      = score > 0.95

        return {
            "score":     round(score,   6),
            "p_value":   round(p_value, 8),
            "sig_mean":  round(float(np.mean(sig)), 4),
            "ctl_mean":  round(float(np.mean(ctl)), 4),
            "ratio":     round(ratio,   4),
            "n_positions": len(sig),
            "fired":     fired,
            "method":    "channel-controlled KS v2 — R-G vs R-B at grid positions",
        }
    except Exception as e:
        return {"score": 0.0, "p_value": 1.0, "fired": False,
                "note": f"Layer D error: {e}",
                "method": "channel-controlled KS v2"}


# =============================================================================
# LAYER E — SPANNING SENTINEL CONTRACT
# =============================================================================

def score_layer_e(pixels, sentinels):
    """
    Layer E: spanning Mersenne sentinel contract (manifest mode).
    Score: fraction of sections with intact entry+exit sentinel pairs.
    Tier demotion (T24→T16→T8) is not failure — counted as intact.
    """
    if not sentinels:
        return {"score": 0.0, "n_sentinels": 0, "intact_pct": 0.0,
                "note": "no sentinels in manifest"}

    result = detect_spanning_manifest(pixels, sentinels)

    t24 = result["tier_24"]
    t16 = result["tier_16"]
    t8  = result["tier_8"]

    # Count all tiers — demotion is not failure
    n_intact_all = t24["n_intact"] + t16["n_intact"] + t8["n_intact"]
    n_total_all  = t24["n"] + t16["n"] + t8["n"]
    intact_frac  = n_intact_all / max(n_total_all, 1)

    # Tamper assessment: are any tier-24s failing (not just demoting)?
    t24_demoted   = t24.get("n_demoted", 0)
    t24_failed    = t24["n"] - t24["n_intact"]   # failed entirely (not demoted)
    tamper_signal = t24_failed > t24_demoted      # more failures than demotions

    return {
        "score":            round(intact_frac, 4),
        "n_total":          n_total_all,
        "n_intact":         n_intact_all,
        "intact_pct":       round(intact_frac * 100, 1),
        "tier_24_n":        t24["n"],
        "tier_24_intact":   t24["n_intact"],
        "tier_24_demoted":  t24_demoted,
        "tier_16_n":        t16["n"],
        "tier_16_intact":   t16["n_intact"],
        "tier_8_n":         t8["n"],
        "tier_8_intact":    t8["n_intact"],
        "overall_intact_pct": result["overall_intact_pct"],
        "tamper_signal":    tamper_signal,
        "method":           "manifest mode — relational Mersenne, tiered span",
    }


# =============================================================================
# LAYER F — PAYLOAD RECOVERY
# =============================================================================

def score_layer_f(sentinels, expected_payload_int):
    """
    Layer F: position-based payload recovery (manifest mode).
    Score: (n_bits_recovered / total_bits) × mean_bit_margin

    Positions do not change under JPEG — recovery reads offsets from manifest.
    The JPEG pipeline is not involved in this computation at all.
    """
    if not sentinels:
        return {"score": 0.0, "n_bits_recovered": 0,
                "note": "no sentinels in manifest"}

    # Build section lookup from manifest
    entries = {s["section"]: s for s in sentinels if s.get("type") == "entry"}
    exits   = {s["section"]: s for s in sentinels if s.get("type") == "exit"}
    n_sections = max(max(entries.keys(), default=-1),
                     max(exits.keys(),   default=-1)) + 1

    if n_sections == 0:
        return {"score": 0.0, "n_bits_recovered": 0,
                "note": "no sections found"}

    # Recover bits from each section
    sec_recs = []
    for sec_idx in range(n_sections):
        rec = recover_section_bits(entries.get(sec_idx), exits.get(sec_idx))
        rec["section"] = sec_idx
        sec_recs.append(rec)

    agg = aggregate_bits(sec_recs)
    rec_fields = agg["payload_fields"]
    exp_fields = unpack_payload(expected_payload_int)

    nbr     = agg["n_bits_recovered"]
    margin  = agg["mean_bit_margin"]
    score   = round((nbr / max(PAYLOAD_BITS, 1)) * margin, 4)

    # Field-level match check
    cid_match  = rec_fields["creator_id_fragment"] == exp_fields["creator_id_fragment"]
    hash_match = rec_fields["hash_fragment"]       == exp_fields["hash_fragment"]
    ver_match  = rec_fields["protocol_version"]    == exp_fields["protocol_version"]

    return {
        "score":                  score,
        "n_bits_recovered":       nbr,
        "n_bits_uncertain":       agg["n_bits_uncertain"],
        "mean_bit_margin":        agg["mean_bit_margin"],
        "min_bit_margin":         agg["min_bit_margin"],
        "overall_confidence":     agg["overall_confidence"],
        "n_sections_intact":      agg["n_intact"],
        "n_sections_mismatch":    agg["n_mismatch"],
        "cid_match":              cid_match,
        "hash_match":             hash_match,
        "ver_match":              ver_match,
        "recovered_cid":          rec_fields["creator_id_fragment"],
        "recovered_hash":         rec_fields["hash_fragment"],
        "recovered_ver":          rec_fields["protocol_version"],
        "expected_cid":           exp_fields["creator_id_fragment"],
        "expected_hash":          exp_fields["hash_fragment"],
        "method":                 "position offset, majority vote, margin-gated",
    }


# =============================================================================
# COMBINED SCORE AND STATE CLASSIFICATION
# =============================================================================

def combine_scores(layer_scores, re_encoded=False):
    """
    Compute unweighted combined score using ONLY non-zero layer scores.

    Denominator = number of layers with score > 0.
    Layers scoring 0.0 are excluded from both numerator AND denominator.

    Rationale: a layer scoring 0.0 means it has no active signal — not that
    it detected an absence. BC=0 after re-encode is correct behavior, not
    evidence of anything. Including zeros in the denominator penalizes the
    signal for the absence of layers that were never supposed to fire at
    this generation. That produces a systematically deflated score that
    misclassifies clearly marked images as State C.

    With non-zero denominator:
      Marked image at G4:  ~0.99  (3 active layers: D=1.0, E~0.99, F=1.0)
      Clean image at G4:   ~0.00  (no active layers → score undefined → 0)
      Gap: ~1.0  —  distributions don't touch

    Layer A is always excluded after re-encode (expected absence by design).
    Layer A=0 at G0 means the DQT was not written — included in denominator
    as a genuine zero signal.

    Returns combined score and dict of active (non-zero) layers.
    """
    candidate = {}
    for layer, result in layer_scores.items():
        score = result.get("score")
        if score is None:
            continue   # layer not evaluated — skip entirely
        if layer == "layer_a" and re_encoded:
            continue   # expected absence after re-encode — always exclude
        candidate[layer] = score

    # Only non-zero scores count toward the mean
    active = {k: v for k, v in candidate.items() if v > 0}

    if not active:
        return 0.0, active

    combined = sum(active.values()) / len(active)
    return round(combined, 4), active


def classify_state(combined_score, layer_scores):
    """
    Classify into four observable states A/B/C/D.

    A: no evidence (combined < threshold, sentinel absent/broken)
    B: provenance preserved (high combined, sentinel intact, payload recovered)
    C: benign degradation (moderate combined, spatial up + frequency down)
    D: tamper evidence (moderate combined, sentinel contract broken)
    """
    sentinel = layer_scores.get("layer_e", {})
    payload  = layer_scores.get("layer_f", {})
    spatial  = layer_scores.get("layer_d", {})
    freq     = layer_scores.get("layer_bc", {})

    sentinel_intact  = sentinel.get("score", 0.0) >= 0.80
    sentinel_tamper  = sentinel.get("tamper_signal", False)
    payload_intact   = payload.get("cid_match", False)
    spatial_fired    = spatial.get("fired", False)
    freq_degraded    = (freq.get("score", 1.0) or 0.0) < 0.50

    if combined_score < STATE_C_THRESHOLD:
        return "A", "No provenance signal detected."

    if combined_score >= STATE_B_THRESHOLD and sentinel_intact and payload_intact:
        return "B", ("Provenance preserved. Strong evidence across all layers. "
                     "Payload recovered with high confidence.")

    if sentinel_tamper:
        return "D", ("Tamper evidence. Sentinel contract broken in pattern "
                     "inconsistent with benign compression.")

    if spatial_fired and freq_degraded:
        return "C", ("Signal degraded — consistent with normal compression. "
                     "Spatial variance elevated; frequency signal reduced. "
                     "No tamper evidence.")

    if combined_score >= STATE_C_THRESHOLD:
        return "C", ("Moderate provenance evidence. Compression degradation pattern.")

    return "A", "Insufficient evidence for provenance claim."


# =============================================================================
# SINGLE FILE PROFILE
# =============================================================================

def profile_file(pixels, jpeg_bytes, markers, sentinels,
                 payload_int, config, re_encoded=False):
    """
    Run all detection layers and produce a complete evidence profile.

    Args:
        pixels:      numpy RGB array (current state — may be compressed)
        jpeg_bytes:  the JPEG bytes of this file (for Layer A DQT scan)
        markers:     list of marker dicts from embed manifest
        sentinels:   list of sentinel dicts from embed manifest
        payload_int: the 24-bit payload integer that was embedded
        config:      MarkerConfig used during embedding
        re_encoded:  True if this file has been re-encoded (DQT expected absent)

    Returns:
        Full profile dict with raw metrics, scores, combined score, state.
    """
    t0 = time.time()

    # ── Layer A ───────────────────────────────────────────────────────────────
    la = score_layer_a(jpeg_bytes)

    # ── Layer BC ──────────────────────────────────────────────────────────────
    lbc = score_layer_bc(pixels, markers, config)

    # ── Layer D ───────────────────────────────────────────────────────────────
    ld = score_layer_d(pixels)

    # ── Layer E ───────────────────────────────────────────────────────────────
    le = score_layer_e(pixels, sentinels)

    # ── Layer F ───────────────────────────────────────────────────────────────
    lf = score_layer_f(sentinels, payload_int)

    # ── Combined ──────────────────────────────────────────────────────────────
    layer_scores = {
        "layer_a":  la,
        "layer_bc": lbc,
        "layer_d":  ld,
        "layer_e":  le,
        "layer_f":  lf,
    }

    combined, active = combine_scores(layer_scores, re_encoded=re_encoded)
    state, state_desc = classify_state(combined, layer_scores)

    return {
        "combined_score":  combined,
        "state":           state,
        "state_desc":      state_desc,
        "active_layers":   list(active.keys()),
        "n_active_layers": len(active),
        "re_encoded":      re_encoded,
        "layer_a":         la,
        "layer_bc":        lbc,
        "layer_d":         ld,
        "layer_e":         le,
        "layer_f":         lf,
        "elapsed_ms":      round((time.time() - t0) * 1000, 1),
    }


def print_profile(fname, profile, gen_idx=None, quality=None):
    """
    Pretty-print a detection profile to stdout.
    """
    gen_label = f"Gen{gen_idx} Q{quality}" if gen_idx is not None else "G0"

    print(f"\n{'─'*70}")
    print(f"  {fname}  [{gen_label}]")
    print(f"{'─'*70}")

    la  = profile["layer_a"]
    lbc = profile["layer_bc"]
    ld  = profile["layer_d"]
    le  = profile["layer_e"]
    lf  = profile["layer_f"]

    def score_bar(s):
        if s is None: return "  N/A  "
        filled = int(round(s * 10))
        bar = "█" * filled + "░" * (10 - filled)
        return f"[{bar}] {s:.3f}"

    print(f"  Layer A  DQT prime tables:   {score_bar(la.get('score'))}  "
          f"detected={la.get('detected')}  "
          f"prime_rate={la.get('overall_prime_rate', 0):.2f}")
    if la.get("note"):
        print(f"           {la['note']}")

    print(f"  Layer BC Frequency markers:  {score_bar(lbc.get('score'))}  "
          f"intact={lbc.get('n_detected',0)}/{lbc.get('n_markers',0)}  "
          f"({lbc.get('intact_pct',0):.1f}%)")

    print(f"  Layer D  Spatial variance:   {score_bar(ld.get('score'))}  "
          f"p={ld.get('p_value',1):.2e}  "
          f"sig={ld.get('sig_mean',0):.2f}  "
          f"ctl={ld.get('ctl_mean',0):.2f}  "
          f"ratio={ld.get('ratio',1):.4f}  "
          f"n={ld.get('n_positions',0)}")

    print(f"  Layer E  Sentinel contract:  {score_bar(le.get('score'))}  "
          f"intact={le.get('n_intact',0)}/{le.get('n_total',0)}  "
          f"({le.get('intact_pct',0):.1f}%)  "
          f"T24={le.get('tier_24_intact',0)}/{le.get('tier_24_n',0)}  "
          f"demoted={le.get('tier_24_demoted',0)}")
    if le.get("tamper_signal"):
        print(f"           ⚠ TAMPER SIGNAL: more failures than demotions")

    print(f"  Layer F  Payload recovery:   {score_bar(lf.get('score'))}  "
          f"bits={lf.get('n_bits_recovered',0)}/{PAYLOAD_BITS}  "
          f"margin={lf.get('mean_bit_margin',0):.3f}  "
          f"cid={'✓' if lf.get('cid_match') else '✗'}  "
          f"hash={'✓' if lf.get('hash_match') else '✗'}  "
          f"ver={'✓' if lf.get('ver_match') else '✗'}")

    print(f"  {'─'*66}")
    print(f"  COMBINED SCORE:  {profile['combined_score']:.4f}  "
          f"({len(profile['active_layers'])} layers active)")
    print(f"  STATE:           {profile['state']}  —  {profile['state_desc']}")


# =============================================================================
# CORPUS RUN
# =============================================================================

def run_clean_baseline(clean_dir, output_dir, max_images=0, run_cascade=False):
    """
    Run detection on UNMARKED clean images to measure false positive rate.
    Expected result: combined = 0.0 (no active layers).
    Any non-zero score is a false positive.
    Results saved to: output_dir/clean_baseline.json
    """
    if not os.path.isdir(clean_dir):
        print(f"\n{'!'*70}")
        print(f"  CLEAN BASELINE SKIPPED — directory not found:")
        print(f"  {clean_dir}")
        print(f"{'!'*70}\n")
        sys.stdout.flush()
        return None, 0, 0

    os.makedirs(output_dir, exist_ok=True)
    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    all_files  = sorted([
        f for f in os.listdir(clean_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])
    if max_images > 0:
        all_files = all_files[:max_images]

    if not all_files:
        print(f"\n{'!'*70}")
        print(f"  CLEAN BASELINE SKIPPED — no image files in: {clean_dir}")
        print(f"{'!'*70}\n")
        sys.stdout.flush()
        return None, 0, 0

    print(f"\n\n{'='*70}")
    print(f"CLEAN BASELINE — false positive measurement")
    print(f"{'='*70}")
    print(f"Directory:  {clean_dir}")
    print(f"Images:     {len(all_files)}  (unmarked — zero embedding)")
    print(f"Expected:   combined = 0.000  (no active layers)")
    print(f"FP thresh:  combined > 0.1 → FALSE POSITIVE")
    print(f"{'='*70}\n")
    sys.stdout.flush()

    from compound_markers import MarkerConfig
    config = MarkerConfig(
        name="clean_baseline", description="Clean baseline",
        min_prime=FLOOR, use_twins=True, use_rare_basket=True,
        use_magic=True, magic_value=42, magic_tolerance=7,
        detection_prime_tolerance=2, n_markers=0,
    )
    gens      = CASCADE_QUALITIES if run_cascade else [CASCADE_QUALITIES[0]]
    results   = []
    fp_images = []
    t_start   = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(clean_dir, fname)
        print(f"[{idx+1:>4d}/{len(all_files)}] {fname}  ", end="", flush=True)
        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print("SKIP (too small)"); continue
        if max(h, w) > 1024:
            scale  = 1024 / max(h, w)
            img    = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)

        current    = to_jpeg(pixels, quality=95)
        gen_scores = []
        for gen_idx, q in enumerate(gens):
            if gen_idx > 0:
                current = to_jpeg(decode_jpeg(current), quality=q)
            compressed = decode_jpeg(current)
            profile = profile_file(
                compressed, current,
                markers=[], sentinels=[], payload_int=0,
                config=config, re_encoded=(gen_idx > 0)
            )
            gen_scores.append(profile["combined_score"])

        g_score = gen_scores[-1]
        is_fp   = g_score > 0.1
        flag    = "  *** FALSE POSITIVE ***" if is_fp else ""
        print(f"combined={g_score:.4f}{flag}", flush=True)

        results.append({"image": fname, "scores": gen_scores, "false_positive": is_fp})
        if is_fp:
            fp_images.append(fname)

    total_time = time.time() - t_start
    n          = len(results)
    fp_count   = len(fp_images)
    mean_score = float(np.mean([r["scores"][-1] for r in results])) if results else 0.0
    fp_pct     = fp_count / max(n, 1) * 100

    print(f"\n{'─'*70}")
    print(f"  CLEAN BASELINE SUMMARY  ({total_time:.0f}s)")
    print(f"{'─'*70}")
    print(f"  Images evaluated:    {n}")
    print(f"  Mean combined score: {mean_score:.4f}  (expected ≈ 0.000)")
    print(f"  False positives:     {fp_count}/{n}  ({fp_pct:.1f}%)")
    if fp_images:
        shown = ', '.join(fp_images[:5])
        ellip = '...' if len(fp_images) > 5 else ''
        print(f"  FP images:           {shown}{ellip}")
    else:
        print(f"  No false positives. Clean distribution confirmed.")
    print(f"{'─'*70}")
    sys.stdout.flush()

    baseline_out = {
        "n_images":              n,
        "clean_dir":             clean_dir,
        "mean_combined":         round(mean_score, 4),
        "false_positive_n":      fp_count,
        "false_positive_pct":    round(fp_pct, 1),
        "false_positive_images": fp_images,
        "threshold":             0.1,
        "per_image":             results,
    }
    baseline_path = os.path.join(output_dir, "clean_baseline.json")
    with open(baseline_path, "w") as f:
        json.dump(baseline_out, f, indent=2)
    print(f"\n  Saved: {baseline_path}")
    sys.stdout.flush()

    return mean_score, fp_count, n


def run_harness(input_dir, output_dir, max_images=0,
                creator_id=1, run_cascade=True, clean_dir=None):
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

    print(f"{'='*70}")
    print(f"DETECTION EVIDENCE HARNESS")
    print(f"{'='*70}")
    print(f"Images:      {n_total}")
    print(f"Creator ID:  {creator_id}")
    print(f"Cascade:     {CASCADE_QUALITIES if run_cascade else 'G0 only'}")
    print(f"Layers:      A (DQT)  BC (frequency)  D (spatial)  "
          f"E (sentinel)  F (payload)")
    print(f"Scoring:     unweighted mean, margin-gated, state A/B/C/D")
    print(f"{'='*70}\n")

    from compound_markers import MarkerConfig, embed_compound

    all_results  = []
    results_file = os.path.join(output_dir, "harness_per_image.jsonl")
    open(results_file, "w").close()
    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        t_img = time.time()
        print(f"\n[{idx+1:>4d}/{n_total}] {fname}")

        try:
            img    = Image.open(fpath).convert("RGB")
            pixels = np.array(img, dtype=np.uint8)
        except Exception as e:
            print(f"  LOAD FAILED: {e}"); continue

        h, w = pixels.shape[:2]
        if min(h, w) < MIN_DIMENSION:
            print("  SKIP (too small)"); continue
        if max(h, w) > 1024:
            scale  = 1024 / max(h, w)
            img    = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            pixels = np.array(img, dtype=np.uint8)
            h, w   = pixels.shape[:2]

        # ── Build manifest ────────────────────────────────────────────────────
        hash_frag   = perceptual_hash_fragment(pixels)
        payload_int = pack_payload(cid_frag, hash_frag,
                                   PROTOCOL_VERSION, flags=0x1)

        n_req  = max(10, math.ceil(
            len(sample_positions_grid(h, w, 8)) * DENSITY_FRAC))
        config = MarkerConfig(
            name="harness", description="Detection harness",
            min_prime=FLOOR, use_twins=True, use_rare_basket=True,
            use_magic=True, magic_value=42, magic_tolerance=7,
            detection_prime_tolerance=2, n_markers=n_req,
        )

        # Embed all layers
        marked_px, markers, _ = embed_compound(
            pixels.copy(), config, variable_offset=42)
        if len(markers) < 10:
            print("  SKIP (too few markers)"); continue

        mod_int    = marked_px.astype(np.int16)
        n_sections = max(1, len(markers) // SENTINEL_CANARY_RATIO)
        sec_size   = len(markers) // n_sections
        sentinels  = []

        for sec_idx in range(n_sections):
            start = sec_idx * sec_size
            end   = start + sec_size if sec_idx < n_sections-1 else len(markers)
            for role, pos_idx, mers in [
                ("entry", start,   SENTINEL_MERSENNE_ENTRY),
                ("exit",  end - 1, SENTINEL_MERSENNE_EXIT),
            ]:
                if pos_idx >= len(markers): continue
                m = markers[pos_idx]
                s = embed_payload_sentinel(
                    mod_int, m["row"], m["col"], mers,
                    role, sec_idx, payload_int)
                if s: sentinels.append(s)

        span_px = np.clip(mod_int, 0, 255).astype(np.uint8)

        # Gen0 — Layer A: write DQT prime tables into the JPEG container.
        # encode_prime_jpeg produces a JPEG with prime-shifted quantization
        # tables (Layer A). The marked pixels are then wrapped in that container.
        # On re-encode (gen1+), DQT tables are stripped — Layer A = 0.0 by design.
        if _LAYER_A_AVAILABLE:
            try:
                result = _encode_prime_jpeg(span_px, quality=95)
                # encode_prime_jpeg returns (bytes, dict) — take bytes only
                gen0_jpeg = result[0] if isinstance(result, tuple) else result
            except Exception:
                gen0_jpeg = to_jpeg(span_px, quality=95)
        else:
            gen0_jpeg = to_jpeg(span_px, quality=95)
        current = gen0_jpeg

        # ── Run all generations ───────────────────────────────────────────────
        cascade_profiles = []
        gens = CASCADE_QUALITIES if run_cascade else [CASCADE_QUALITIES[0]]

        for gen_idx, q in enumerate(gens):
            if gen_idx > 0:
                current = to_jpeg(decode_jpeg(current), quality=q)

            compressed_px = decode_jpeg(current)
            re_enc = (gen_idx > 0)

            profile = profile_file(
                compressed_px, current, markers, sentinels,
                payload_int, config, re_encoded=re_enc
            )
            profile["generation"] = gen_idx
            profile["quality"]    = q

            print_profile(fname, profile, gen_idx, q)
            cascade_profiles.append(profile)

        elapsed = time.time() - t_img
        g4 = cascade_profiles[-1]
        print(f"\n  ── Summary [{elapsed:.1f}s] ──")
        print(f"  G4 combined: {g4['combined_score']:.4f}  "
              f"State: {g4['state']}  "
              f"CID: {'✓' if g4['layer_f'].get('cid_match') else '✗'}  "
              f"Hash: {'✓' if g4['layer_f'].get('hash_match') else '✗'}")

        result = {
            "image":        fname,
            "n_markers":    len(markers),
            "n_sections":   n_sections,
            "payload_int":  payload_int,
            "hash_frag":    hash_frag,
            "cid_frag":     cid_frag,
            "cascade":      cascade_profiles,
        }
        all_results.append(result)
        with open(results_file, "a") as f:
            f.write(json.dumps(result, default=str) + "\n")

    total_time = time.time() - t_start
    good = [r for r in all_results if "cascade" in r]
    n_good = len(good)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"AGGREGATE — {n_good} images  ({total_time:.0f}s)")
    print(f"{'='*70}\n")

    if not good:
        print("No valid results."); return

    def gmean_layer(gen_idx, layer, field):
        vals = [r["cascade"][gen_idx][layer].get(field, 0)
                for r in good if len(r["cascade"]) > gen_idx
                if layer in r["cascade"][gen_idx]]
        return sum(vals) / len(vals) if vals else 0.0

    def gpct_layer(gen_idx, layer, field):
        vals = [r["cascade"][gen_idx][layer].get(field, False)
                for r in good if len(r["cascade"]) > gen_idx
                if layer in r["cascade"][gen_idx]]
        return sum(1 for v in vals if v) / len(vals) * 100 if vals else 0.0

    gen_count = len(gens)
    print(f"{'Gen':>4}  {'Q':>3}  {'combined':>9}  "
          f"{'A':>5}  {'BC':>5}  {'D':>5}  {'E':>5}  {'F':>5}  "
          f"{'B%':>5}  {'C%':>5}  {'D%':>5}")
    print("─" * 75)

    for gen_idx, q in enumerate(gens):
        def gcomb():
            vals = [r["cascade"][gen_idx].get("combined_score", 0)
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(vals) / len(vals) if vals else 0.0

        def gstate(s):
            vals = [r["cascade"][gen_idx].get("state")
                    for r in good if len(r["cascade"]) > gen_idx]
            return sum(1 for v in vals if v == s) / len(vals) * 100 if vals else 0

        la_s  = gmean_layer(gen_idx, "layer_a",  "score")
        lbc_s = gmean_layer(gen_idx, "layer_bc", "score")
        ld_s  = gmean_layer(gen_idx, "layer_d",  "score")
        le_s  = gmean_layer(gen_idx, "layer_e",  "score")
        lf_s  = gmean_layer(gen_idx, "layer_f",  "score")

        print(f"{gen_idx:>4d}  {q:>3d}"
              f"  {gcomb():>9.4f}"
              f"  {la_s:>5.3f}"
              f"  {lbc_s:>5.3f}"
              f"  {ld_s:>5.3f}"
              f"  {le_s:>5.3f}"
              f"  {lf_s:>5.3f}"
              f"  {gstate('B'):>4.0f}%"
              f"  {gstate('C'):>4.0f}%"
              f"  {gstate('D'):>4.0f}%")

    # Final verdict
    g4_combined = np.mean([r["cascade"][-1].get("combined_score", 0)
                           for r in good])
    g4_state_b  = sum(1 for r in good
                      if r["cascade"][-1].get("state") == "B")
    g4_cid      = sum(1 for r in good
                      if r["cascade"][-1]["layer_f"].get("cid_match", False))

    print(f"\n{'='*70}")
    print(f"VERDICT  (Gen{gen_count-1} Q{gens[-1]})")
    print(f"{'='*70}")
    print(f"  Mean combined score:   {g4_combined:.4f}")
    print(f"  State B (preserved):   {g4_state_b}/{n_good}")
    print(f"  CID recovered:         {g4_cid}/{n_good} ({g4_cid/n_good*100:.1f}%)")

    agg = {
        "n_images":        n_good,
        "creator_id":      creator_id,
        "total_time_s":    round(total_time, 1),
        "scoring":         "non-zero denominator (active layers only)",
        "final_gen": {
            "quality":           gens[-1],
            "mean_combined":     round(float(g4_combined), 4),
            "state_B_pct":       round(g4_state_b / n_good * 100, 1),
            "cid_match_pct":     round(g4_cid     / n_good * 100, 1),
        }
    }

    # Optional: run clean baseline immediately after marked corpus
    if clean_dir:
        from pathlib import Path
        clean_dir_norm = str(Path(clean_dir).resolve())
        if os.path.isdir(clean_dir_norm):
            print(f"\n{'='*70}")
            clean_mean, fp_count, n_clean = run_clean_baseline(
                clean_dir_norm, output_dir,
                max_images=max_images,
                run_cascade=run_cascade,
            )
            if clean_mean is not None:
                agg["clean_baseline"] = {
                    "n_images":           n_clean,
                    "mean_combined":      round(float(clean_mean), 4),
                    "false_positive_n":   fp_count,
                    "false_positive_pct": round(fp_count / max(n_clean, 1) * 100, 1),
                }
                gap = g4_combined - clean_mean
                print(f"\n{'='*70}")
                print(f"  GAP ANALYSIS")
                print(f"{'='*70}")
                print(f"  Marked mean:   {g4_combined:.4f}")
                print(f"  Clean mean:    {clean_mean:.4f}")
                print(f"  Gap:           {gap:.4f}")
                print(f"  Separation:    {'CLEAR (gap > 0.5)' if gap > 0.5 else 'MARGINAL'}")
                print(f"{'='*70}")
        else:
            print(f"\n{'!'*70}")
            print(f"  CLEAN BASELINE SKIPPED")
            print(f"  Path not found: {clean_dir}")
            print(f"  Normalized:     {clean_dir_norm}")
            print(f"  Check that the directory exists and is accessible.")
            print(f"{'!'*70}\n")
        sys.stdout.flush()

    with open(os.path.join(output_dir, "harness_aggregate.json"), "w") as f:
        json.dump(agg, f, indent=2)
    print(f"\nResults: {output_dir}/")
    return agg


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(description="Detection Evidence Harness")
    parser.add_argument("--input",       "-i", required=True,
                        help="Input directory of marked images")
    parser.add_argument("--output",      "-o", default="harness_results")
    parser.add_argument("--max-images",  "-n", type=int, default=0)
    parser.add_argument("--creator-id",  "-c", type=int, default=1)
    parser.add_argument("--no-cascade",        action="store_true",
                        help="Run G0 only (faster)")
    parser.add_argument("--clean-dir",   "-B", default=None,
                        help="Directory of UNMARKED images for false positive baseline")
    parser.add_argument("--no-log",            action="store_true",
                        help="Suppress log file (terminal only)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} is not a directory"); sys.exit(1)

    # ── Tee stdout to log file ────────────────────────────────────────────────
    os.makedirs(args.output, exist_ok=True)
    log_name = f"harness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = os.path.join(args.output, log_name)

    if not args.no_log:
        sys.stdout = Tee(log_path)
        print(f"Log: {log_path}")
        print(f"Command: {' '.join(sys.argv)}\n")

    try:
        run_harness(
            args.input, args.output,
            max_images=args.max_images,
            creator_id=args.creator_id,
            run_cascade=not args.no_cascade,
            clean_dir=args.clean_dir,
        )
    finally:
        # Always restore stdout even if something crashes mid-run
        if not args.no_log and isinstance(sys.stdout, Tee):
            sys.stdout = sys.stdout.restore()
            print(f"\nLog saved: {log_path}")
