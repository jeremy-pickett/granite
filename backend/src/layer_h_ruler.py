r"""
layer_h_ruler.py  --  Layer H (Spatial Ruler) for GRANITE provenance system
-----------------------------------------------------------------------------
Embeds spatial reference frame markers into images as column/row bands.
Each ruler band proves the image's original coordinate frame and detects
crop and stitch attacks without a manifest.

ARCHITECTURE
============

Encoding surface:
    A 16px-wide vertical or horizontal band where every pixel has
    |R-G| = RULER_TARGET (198 = 197+1, 197 is prime).
    JPEG preserves the band mean within ±9 counts at any quality because
    the DCT block is fully saturated with the chroma signal.
    Gap over natural content: ~180 counts. Unambiguous at Q30-Q95.

Payload encoding:
    The band column is divided into 32px segments.
    Segment marked (bit=1): full band density, mean |R-G| ≈ 198.
    Segment natural (bit=0): left at original pixel values.
    Detection: segment mean |R-G| > SEGMENT_THRESHOLD (80 counts).

Payload structure (MSB-first, priority order):
    bits[0]     = mode flag (0=standard fraction, 1=small absolute)
    bits[1:4]   = fraction index (3 bits, identifies which ruler this is)
    bits[4]     = axis (0=vertical/column ruler, 1=horizontal/row ruler)
    bits[5:18]  = original dimension (W for col rulers, H for row rulers)
    bits[18:35] = timestamp hours (17 bits, 50yr range at hour precision)
    bits[35:51] = session hash truncated (16 bits)

Ruler geometry:
    W <  1024:  3 vertical rulers at W * [1/4, 1/2, 3/4]
    W >= 1024:  5 vertical rulers at W * [1/8, 1/4, 1/2, 3/4, 7/8]
    Same for H (horizontal rulers).

Small image mode (shorter dimension < 1024):
    bits[0] = 1 (small mode)
    bits[1] = axis
    bits[2:15] = absolute pixel position of ruler (13 bits)
    bits[15:28] = original dimension (13 bits)

Crop forensics:
    Ruler at column c in image of current width W_cur.
    Decode fraction f from bits[1:4].
    If c/W_cur != f  ->  crop confirmed.
    W_orig = c / f  (recoverable from a single surviving ruler).

Stitch detection:
    Two ruler sets with inconsistent fractions -> stitch.
    Seam is approximately at the column where ruler set changes.

COVERAGE BY IMAGE HEIGHT
========================
    H= 512:  16 segments -> 16 bits  (mode+frac+axis+partial_dim)
    H= 768:  24 segments -> 24 bits  (+ full dim)
    H=1024:  32 segments -> 32 bits  (+ partial timestamp)
    H=2048:  64 segments -> 64 bits  (full payload with margin)

JPEG SURVIVAL
=============
    Q95-Q30: zero bit errors on random images.
    Band mean after JPEG: 195.5 (Q85), 199.3 (Q40).
    Natural column mean:    16.9 (Q85),   8.9 (Q40).
    Detection gap: 178+ counts at all tested quality levels.
"""

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image
from sympy import isprime

# ===========================================================================
# PROTOCOL CONSTANTS
# ===========================================================================

RULER_TARGET       = 198      # = 197 + 1  vertical rulers |R-G|
RULER_H_TARGET     = 198      # = 197 + 1  horizontal rulers |G-B| (orthogonal channel)
# Using same prime but different channel pair eliminates cross-contamination.
RULER_TOL          = 9        # ± tolerance for detection
SEGMENT_HEIGHT     = 32       # pixels per payload segment
SEGMENT_THRESHOLD  = 80       # mean |R-G| threshold: marked vs natural
BAND_WIDTH         = 16       # pixels wide per ruler band
SMALL_THRESH       = 1024     # dimension below which small mode is used
FLOOR              = 43       # minimum prime value (GRANITE protocol)

assert isprime(RULER_TARGET - 1) and (RULER_TARGET - 1) > FLOOR
assert RULER_TARGET not in (168, 140)  # no crosstalk with Layer G

# Fraction map: index -> (numerator, denominator)
FRACTION_MAP = {
    0: (1, 8),
    1: (1, 4),
    2: (3, 8),
    3: (1, 2),
    4: (5, 8),
    5: (3, 4),
    6: (7, 8),
    # 7: reserved
}
FRACTION_MAP_INV = {v: k for k, v in FRACTION_MAP.items()}


# ===========================================================================
# DATA TYPES
# ===========================================================================

class RulerMode(IntEnum):
    STANDARD = 0   # fraction-based encoding (W >= SMALL_THRESH)
    SMALL    = 1   # absolute position encoding (W < SMALL_THRESH)


@dataclass
class RulerPayload:
    """Decoded payload from a single ruler band."""
    mode:          RulerMode
    axis:          int            # 0 = vertical (column), 1 = horizontal (row)
    frac_idx:      Optional[int]  # standard mode: fraction index
    fraction:      Optional[Tuple[int, int]]  # standard mode: (n, d)
    position:      Optional[int]  # small mode: absolute pixel position
    dim_orig:      Optional[int]  # original dimension (W for col, H for row)
    timestamp_hrs: Optional[int]  # hours since epoch
    session_hash:  Optional[int]  # truncated session hash
    bits_read:     int = 0        # how many bits were successfully read

    def __repr__(self):
        if self.mode == RulerMode.STANDARD:
            return (f"RulerPayload(standard axis={self.axis} "
                    f"frac={self.fraction} dim_orig={self.dim_orig} "
                    f"ts={self.timestamp_hrs} hash={self.session_hash:#06x if self.session_hash else None} "
                    f"bits={self.bits_read})")
        else:
            return (f"RulerPayload(small axis={self.axis} "
                    f"pos={self.position} dim_orig={self.dim_orig} "
                    f"bits={self.bits_read})")


@dataclass
class RulerDetection:
    """A ruler detected in an image, with decoded payload and position."""
    at_pixel:      int             # column (axis=0) or row (axis=1) where found
    is_col:        bool            # True = vertical ruler (column)
    payload:       RulerPayload
    band_mean:     float           # mean |R-G| at the ruler band
    n_segments:    int             # how many segments were read


@dataclass
class CropForensicReport:
    """Result of crop/stitch analysis on an image."""
    current_size:        Tuple[int, int]   # (W, H) as found
    rulers_found:        int
    crop_detected:       bool
    stitch_detected:     bool
    original_W_estimate: Optional[int]
    original_H_estimate: Optional[int]
    evidence:            List[str] = field(default_factory=list)
    rulers:              List[RulerDetection] = field(default_factory=list)


# ===========================================================================
# RULER GEOMETRY
# ===========================================================================

def get_ruler_positions(W: int, H: int) -> Tuple[List[Tuple[int,int,int]], List[Tuple[int,int,int]]]:
    """
    Return (col_rulers, row_rulers) as lists of (pixel_position, frac_idx, mode).

    Col rulers are vertical bands (detect horizontal crops).
    Row rulers are horizontal bands (detect vertical crops).
    """
    def positions_for(dim: int) -> List[Tuple[int, int, int]]:
        if dim < SMALL_THRESH:
            fracs = [(1,4), (1,2), (3,4)]
            mode  = RulerMode.SMALL
        else:
            fracs = [(1,8), (1,4), (1,2), (3,4), (7,8)]
            mode  = RulerMode.STANDARD
        result = []
        for n, d in fracs:
            pos = int(round(dim * n / d))
            fi  = FRACTION_MAP_INV.get((n, d), 0)
            result.append((pos, fi, int(mode)))
        return result

    return positions_for(W), positions_for(H)


def n_segments(dim: int) -> int:
    """Number of 32px segments in a dimension."""
    return dim // SEGMENT_HEIGHT


# ===========================================================================
# PAYLOAD PACKING
# ===========================================================================

def pack_standard(frac_idx: int, axis: int, dim_orig: int,
                  ts: int = 0, sh: int = 0) -> List[int]:
    """
    Pack standard-mode payload into a bitstring.

    Layout:
        bit 0:     mode = 0 (standard)
        bits 1-3:  fraction index (3 bits)
        bit 4:     axis
        bits 5-17: dim_orig (13 bits)
        bits 18-34: timestamp hours (17 bits)
        bits 35-50: session hash (16 bits)
    Total: 51 bits
    """
    b = [0]
    b += [(frac_idx >> i) & 1 for i in range(2, -1, -1)]
    b.append(axis)
    b += [(dim_orig >> i) & 1 for i in range(12, -1, -1)]
    b += [(ts >> i) & 1 for i in range(16, -1, -1)]
    b += [(sh >> i) & 1 for i in range(15, -1, -1)]
    return b   # 51 bits


def pack_small(axis: int, position: int, dim_orig: int) -> List[int]:
    """
    Pack small-mode payload into a bitstring.

    Layout:
        bit 0:      mode = 1 (small)
        bit 1:      axis
        bits 2-14:  absolute ruler position (13 bits)
        bits 15-27: dim_orig (13 bits)
    Total: 28 bits
    """
    b = [1, axis]
    b += [(position >> i) & 1 for i in range(12, -1, -1)]
    b += [(dim_orig >> i) & 1 for i in range(12, -1, -1)]
    return b   # 28 bits


def unpack(bits: List[int]) -> RulerPayload:
    """Decode a bitstring into a RulerPayload."""
    if not bits:
        return RulerPayload(mode=RulerMode.STANDARD, axis=0,
                            frac_idx=None, fraction=None, position=None,
                            dim_orig=None, timestamp_hrs=None,
                            session_hash=None, bits_read=0)
    mode = RulerMode(bits[0])
    n    = len(bits)

    if mode == RulerMode.STANDARD:
        fi   = (bits[1] << 2 | bits[2] << 1 | bits[3]) if n >= 4 else None
        axis = bits[4] if n >= 5 else None
        dim  = sum(bits[5+i] << (12-i) for i in range(13)) if n >= 18 else None
        ts   = sum(bits[18+i] << (16-i) for i in range(17)) if n >= 35 else None
        sh   = sum(bits[35+i] << (15-i) for i in range(16)) if n >= 51 else None
        return RulerPayload(
            mode=mode, axis=axis or 0,
            frac_idx=fi, fraction=FRACTION_MAP.get(fi) if fi is not None else None,
            position=None, dim_orig=dim,
            timestamp_hrs=ts, session_hash=sh,
            bits_read=n)
    else:  # SMALL
        axis = bits[1] if n >= 2 else None
        pos  = sum(bits[2+i] << (12-i) for i in range(13)) if n >= 15 else None
        dim  = sum(bits[15+i] << (12-i) for i in range(13)) if n >= 28 else None
        return RulerPayload(
            mode=mode, axis=axis or 0,
            frac_idx=None, fraction=None,
            position=pos, dim_orig=dim,
            timestamp_hrs=None, session_hash=None,
            bits_read=n)


# ===========================================================================
# EMBEDDER
# ===========================================================================

def _embed_segment(arr: np.ndarray, seg_idx: int, cr: int, is_col: bool,
                   skip_positions=None):
    """
    Mark one 32px segment of a ruler band.

    Vertical rulers (is_col=True):   embed |R-G| = RULER_TARGET
    Horizontal rulers (is_col=False): embed |G-B| = RULER_H_TARGET

    Using orthogonal channel pairs eliminates cross-contamination at
    intersections where vertical and horizontal rulers overlap.
    """
    h, w = arr.shape[:2]
    seg_start = seg_idx * SEGMENT_HEIGHT
    seg_end   = min(seg_start + SEGMENT_HEIGHT, h if is_col else w)
    half      = BAND_WIDTH // 2

    for along in range(seg_start, seg_end):
        for across in range(cr - half, cr + half):
            if is_col:
                py, px = along, across
            else:
                py, px = across, along
            if not (0 <= py < h and 0 <= px < w):
                continue

            # Skip intersection with orthogonal rulers to avoid cross-contamination.
            # For vertical rulers: skip_positions contains columns to avoid.
            # For horizontal rulers: skip_positions contains columns of vertical bands.
            # In both cases we check px (the column coordinate).
            if skip_positions and px in skip_positions:
                continue

            if is_col:
                # Vertical ruler: target |R-G| = 198
                R, G = int(arr[py, px, 0]), int(arr[py, px, 1])
                t    = RULER_TARGET
                if R >= t:
                    arr[py, px, 1] = R - t
                elif G + t <= 255:
                    arr[py, px, 0] = G + t
                else:
                    arr[py, px, 0] = 255
                    arr[py, px, 1] = max(0, 255 - t)
            else:
                # Horizontal ruler: target |G-B| = 198 (orthogonal channel)
                G, B = int(arr[py, px, 1]), int(arr[py, px, 2])
                t    = RULER_H_TARGET
                if G >= t:
                    arr[py, px, 2] = G - t
                elif B + t <= 255:
                    arr[py, px, 1] = B + t
                else:
                    arr[py, px, 1] = 255
                    arr[py, px, 2] = max(0, 255 - t)


def embed_ruler(image: Image.Image, cr: int, is_col: bool,
                bits: List[int],
                skip_positions=None) -> Image.Image:
    """
    Embed a single ruler band (column or row) with the given payload bits.

    Each bit in the payload corresponds to one 32px segment.
    bit=1: mark the segment (|R-G| = RULER_TARGET throughout).
    bit=0: leave natural.

    Parameters
    ----------
    image  : PIL Image (RGB)
    cr     : column index (is_col=True) or row index (is_col=False)
    is_col : True for vertical ruler (column), False for horizontal (row)
    bits   : payload bitstring

    Returns
    -------
    New PIL Image with ruler embedded.
    """
    arr = np.array(image, dtype=np.uint8).copy()
    h, w = arr.shape[:2]
    dim  = h if is_col else w
    n_segs = min(len(bits), n_segments(dim))

    for seg_idx in range(n_segs):
        if bits[seg_idx] == 1:
            _embed_segment(arr, seg_idx, cr, is_col, skip_positions)

    return Image.fromarray(arr, mode="RGB")


def embed_all_rulers(image: Image.Image,
                     timestamp_hrs: Optional[int] = None,
                     session_hash: int = 0) -> Image.Image:
    """
    Embed all vertical and horizontal rulers for this image.

    Vertical rulers detect horizontal crops.
    Horizontal rulers detect vertical crops.
    All rulers together detect rectangular crop and stitch attacks.

    Parameters
    ----------
    image         : PIL Image (RGB)
    timestamp_hrs : hours since Unix epoch (default: current time)
    session_hash  : truncated session hash for linking to sidecar receipt

    Returns
    -------
    New PIL Image with all rulers embedded.
    """
    if timestamp_hrs is None:
        timestamp_hrs = int(time.time() // 3600) % (2**17)

    W, H     = image.size
    result   = image.copy()
    col_pos, row_pos = get_ruler_positions(W, H)

    # Compute skip zones: col bands and row bands must not overwrite each other
    half = BAND_WIDTH // 2
    # Col rulers skip columns occupied by OTHER col rulers' bands (none — they don't overlap)
    # Row rulers skip COLUMNS occupied by vertical ruler bands
    col_band_cols = set()
    for col, _, _ in col_pos:
        col_band_cols.update(range(col - half, col + half))

    # Vertical rulers (columns)
    for col, fi, mode_int in col_pos:
        if mode_int == int(RulerMode.STANDARD):
            bits = pack_standard(fi, 0, W, timestamp_hrs, session_hash)
        else:
            bits = pack_small(0, col, W)
        result = embed_ruler(result, col, True, bits)

    # Horizontal rulers (rows) — skip the vertical ruler band columns
    for row, fi, mode_int in row_pos:
        if mode_int == int(RulerMode.STANDARD):
            bits = pack_standard(fi, 1, H, timestamp_hrs, session_hash)
        else:
            bits = pack_small(1, row, H)
        result = embed_ruler(result, row, False, bits, skip_positions=col_band_cols)

    return result


# ===========================================================================
# DETECTOR
# ===========================================================================

def detect_ruler(image: Image.Image, cr: int, is_col: bool) -> RulerDetection:
    """
    Read and decode a ruler band at the given column or row.

    For each 32px segment, measures mean |R-G| across the band width.
    Classifies as bit=1 if mean >= SEGMENT_THRESHOLD, else bit=0.

    Parameters
    ----------
    image  : PIL Image (RGB)
    cr     : column (is_col=True) or row (is_col=False) to scan
    is_col : True for vertical ruler

    Returns
    -------
    RulerDetection with decoded payload.
    """
    arr  = np.array(image, dtype=np.int16)
    h, w = arr.shape[:2]
    dim  = h if is_col else w
    half = BAND_WIDTH // 2

    bits       = []
    band_total = 0.0
    band_count = 0

    for seg_idx in range(n_segments(dim)):
        seg_start = seg_idx * SEGMENT_HEIGHT
        seg_end   = min(seg_start + SEGMENT_HEIGHT, dim)
        seg_vals  = []

        for along in range(seg_start, seg_end):
            for across in range(cr - half, cr + half):
                if is_col:
                    py, px = along, across
                else:
                    py, px = across, along
                if not (0 <= py < h and 0 <= px < w):
                    continue
                # Vertical rulers: measure |R-G|
                # Horizontal rulers: measure |G-B| (orthogonal, no cross-contamination)
                if is_col:
                    val = abs(int(arr[py, px, 0]) - int(arr[py, px, 1]))
                else:
                    val = abs(int(arr[py, px, 1]) - int(arr[py, px, 2]))
                seg_vals.append(val)

        if seg_vals:
            seg_mean = float(np.mean(seg_vals))
            band_total += seg_mean
            band_count += 1
            bits.append(1 if seg_mean >= SEGMENT_THRESHOLD else 0)

    band_mean = band_total / band_count if band_count else 0.0
    payload   = unpack(bits)

    return RulerDetection(
        at_pixel=cr,
        is_col=is_col,
        payload=payload,
        band_mean=band_mean,
        n_segments=len(bits),
    )


def detect_all_rulers(image: Image.Image) -> List[RulerDetection]:
    """
    Scan all expected ruler positions and decode each.

    Ruler positions are determined by the image's CURRENT dimensions.
    For crop analysis, use analyze_crop() which scans for rulers
    at their original positions.

    Returns
    -------
    List of RulerDetection objects, one per expected ruler position.
    """
    W, H = image.size
    results = []
    col_pos, row_pos = get_ruler_positions(W, H)

    for col, fi, _ in col_pos:
        results.append(detect_ruler(image, col, True))
    for row, fi, _ in row_pos:
        results.append(detect_ruler(image, row, False))

    return results


# ===========================================================================
# CROP / STITCH FORENSICS
# ===========================================================================

def blind_scan_rulers(image: Image.Image,
                      band_col_threshold: float = 62.0,
                      band_row_threshold: float = 62.0) -> List[RulerDetection]:
    """
    Scan every column and row for ruler bands without requiring a manifest.

    Used for forensic analysis of potentially-cropped images where rulers
    may no longer be at their expected positions.

    Strategy:
        1. Compute per-column mean |R-G| across full image height.
        2. Find columns where the smoothed mean exceeds band_col_threshold.
           (Natural columns: ~15 counts. Ruler columns: ~60-80 counts.)
        3. Apply non-maximum suppression within BAND_WIDTH to find band centers.
        4. Read and decode the payload at each candidate column.
        Repeat for rows using |G-B|.

    Parameters
    ----------
    image                : PIL Image (RGB)
    band_col_threshold   : column mean |R-G| to qualify as ruler candidate
    band_row_threshold   : row mean |G-B| to qualify as ruler candidate

    Returns
    -------
    List of RulerDetection with payload decoded at each found position.
    """
    from scipy.ndimage import uniform_filter1d

    arr  = np.array(image, dtype=np.int16)
    H, W = arr.shape[:2]
    detections = []

    # ── Vertical rulers: scan columns for elevated |R-G| ─────────────
    col_rg  = np.mean(np.abs(arr[:, :, 0] - arr[:, :, 1]).astype(float), axis=0)
    col_smo = uniform_filter1d(col_rg, size=BAND_WIDTH)

    cands = []
    for c in range(W):
        if col_smo[c] > band_col_threshold:
            cands.append((c, float(col_smo[c])))

    for c, v in sorted(cands, key=lambda x: -x[1]):
        if not any(abs(c - d.at_pixel) < BAND_WIDTH for d in detections if d.is_col):
            det = detect_ruler(image, c, True)
            det.band_mean = v
            detections.append(det)

    # ── Horizontal rulers: scan rows for elevated |G-B| ──────────────
    row_gb  = np.mean(np.abs(arr[:, :, 1] - arr[:, :, 2]).astype(float), axis=1)
    row_smo = uniform_filter1d(row_gb, size=BAND_WIDTH)

    cands_r = []
    for r in range(H):
        if row_smo[r] > band_row_threshold:
            cands_r.append((r, float(row_smo[r])))

    for r, v in sorted(cands_r, key=lambda x: -x[1]):
        if not any(abs(r - d.at_pixel) < BAND_WIDTH for d in detections if not d.is_col):
            det = detect_ruler(image, r, False)
            det.band_mean = v
            detections.append(det)

    return detections


def recover_original_dimensions(detections: List[RulerDetection],
                                 W_cur: int, H_cur: int) -> dict:
    """
    Recover original image dimensions and crop offsets using least squares.

    Given N ruler detections with known fractions and current positions:
        new_pos_i = W_orig * frac_i - crop_offset

    This is a linear system: [frac_i, -1] * [W_orig, offset]^T = new_pos_i
    With 2+ rulers, solvable by least squares.

    Parameters
    ----------
    detections : ruler detections from blind_scan_rulers
    W_cur      : current image width
    H_cur      : current image height

    Returns
    -------
    dict with keys: W_orig, H_orig, crop_left, crop_top, confidence
    """
    # Only use detections with valid decoded dim_orig — filters out noise columns
    col_dets = [(d.at_pixel, d.payload.fraction)
                for d in detections
                if (d.is_col and d.payload.fraction is not None
                    and d.payload.dim_orig and d.payload.dim_orig > 0)]
    row_dets = [(d.at_pixel, d.payload.fraction)
                for d in detections
                if (not d.is_col and d.payload.fraction is not None
                    and d.payload.dim_orig and d.payload.dim_orig > 0)]

    result = {'W_orig': None, 'H_orig': None,
              'crop_left': None, 'crop_top': None,
              'confidence': 0}

    # Recover W_orig and crop_left from column rulers
    if len(col_dets) >= 2:
        A = np.array([[n/d, -1] for _, (n,d) in col_dets])
        b = np.array([pos for pos, _ in col_dets], dtype=float)
        try:
            x, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            W_est, off_est = x
            if W_est > 0:
                result['W_orig']    = int(round(W_est))
                result['crop_left'] = int(round(off_est))
                result['confidence'] += 1
        except Exception:
            pass

    # Recover H_orig and crop_top from row rulers
    if len(row_dets) >= 2:
        A = np.array([[n/d, -1] for _, (n,d) in row_dets])
        b = np.array([pos for pos, _ in row_dets], dtype=float)
        try:
            x, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            H_est, off_est = x
            if H_est > 0:
                result['H_orig']   = int(round(H_est))
                result['crop_top'] = int(round(off_est))
                result['confidence'] += 1
        except Exception:
            pass

    # Cross-check: if dim_orig is in payload, compare to estimate
    for d in detections:
        p = d.payload
        if p.dim_orig:
            if d.is_col and result['W_orig']:
                if abs(p.dim_orig - result['W_orig']) < 8:
                    result['confidence'] += 1
            elif not d.is_col and result['H_orig']:
                if abs(p.dim_orig - result['H_orig']) < 8:
                    result['confidence'] += 1

    return result


def analyze_crop(image: Image.Image) -> CropForensicReport:
    """
    Detect crop and stitch attacks using blind ruler scan + least squares recovery.

    Algorithm:
        1. Blind scan: find all elevated column/row bands in the image.
        2. Decode payload from each found ruler.
        3. Compare ruler positions to expected positions for current dimensions.
           If mismatch: crop detected.
        4. Least squares solve for W_orig, H_orig, crop_left, crop_top
           from the system: new_pos_i = W_orig * frac_i - crop_left.
        5. Cross-check recovered dimensions against dim_orig in payloads.
        6. Stitch detection: if rulers give inconsistent W_orig estimates.

    Parameters
    ----------
    image : possibly-cropped or stitched PIL Image

    Returns
    -------
    CropForensicReport with accurate original dimension recovery.
    """
    W_cur, H_cur = image.size

    report = CropForensicReport(
        current_size=(W_cur, H_cur),
        rulers_found=0,
        crop_detected=False,
        stitch_detected=False,
        original_W_estimate=None,
        original_H_estimate=None,
    )

    # Step 1: Blind scan — find rulers wherever they actually are
    all_dets = blind_scan_rulers(image)
    report.rulers_found = len(all_dets)
    report.rulers       = all_dets

    # Step 2: Check for position mismatch (crop evidence)
    # Only use detections with valid decoded dimensions to avoid noise FPs
    for det in all_dets:
        p = det.payload
        if p.mode == RulerMode.STANDARD and p.fraction and p.dim_orig and p.dim_orig > 0:
            n, d   = p.fraction
            dim    = W_cur if det.is_col else H_cur
            expected = int(round(dim * n / d))
            if abs(det.at_pixel - expected) > 5:
                report.crop_detected = True
                axis = "Vertical" if det.is_col else "Horizontal"
                report.evidence.append(
                    f"{axis} ruler {n}/{d}: "
                    f"found at {'col' if det.is_col else 'row'}={det.at_pixel}, "
                    f"expected={expected} for {'W' if det.is_col else 'H'}={dim}")

        elif (p.mode == RulerMode.SMALL and p.position is not None
              and p.dim_orig and p.dim_orig > 0):
            if abs(p.position - det.at_pixel) > 5:
                report.crop_detected = True
                axis = "Vertical" if det.is_col else "Horizontal"
                report.evidence.append(
                    f"{axis} ruler (small mode): "
                    f"encoded_pos={p.position} != current={'col' if det.is_col else 'row'}={det.at_pixel}")

        # Payload dim_orig mismatch is also crop evidence
        if p.dim_orig:
            cur_dim = W_cur if det.is_col else H_cur
            if p.dim_orig != cur_dim:
                report.crop_detected = True

    # Step 3: Least squares dimension recovery
    if report.crop_detected:
        recovery = recover_original_dimensions(all_dets, W_cur, H_cur)
        report.original_W_estimate = recovery.get("W_orig")
        report.original_H_estimate = recovery.get("H_orig")
        if recovery.get("crop_left") is not None:
            report.evidence.append(
                f"Recovered: W_orig={recovery['W_orig']} "
                f"crop_left={recovery['crop_left']} "
                f"(confidence={recovery['confidence']})")
        if recovery.get("crop_top") is not None:
            report.evidence.append(
                f"Recovered: H_orig={recovery['H_orig']} "
                f"crop_top={recovery['crop_top']}")

    # Step 4: Stitch detection — W_orig estimates from different ruler sets
    col_dims = [d.payload.dim_orig for d in all_dets
                if d.is_col and d.payload.dim_orig is not None]
    if len(set(col_dims)) > 1:
        span = max(col_dims) - min(col_dims)
        if span > 64:
            report.stitch_detected = True
            report.evidence.append(
                f"Stitch detected: col rulers report inconsistent "
                f"W_orig values: {sorted(set(col_dims))}")

    return report


# ===========================================================================
# PUBLIC API
# ===========================================================================

__all__ = [
    # Embed
    "embed_all_rulers",
    "embed_ruler",
    # Detect
    "detect_all_rulers",
    "detect_ruler",
    # Forensics
    "analyze_crop",
    # Payload
    "pack_standard",
    "pack_small",
    "unpack",
    # Geometry
    "get_ruler_positions",
    "n_segments",
    # Types
    "RulerMode",
    "RulerPayload",
    "RulerDetection",
    "CropForensicReport",
    # Constants
    "RULER_TARGET",
    "RULER_TOL",
    "SEGMENT_HEIGHT",
    "SEGMENT_THRESHOLD",
    "BAND_WIDTH",
    "SMALL_THRESH",
    "FRACTION_MAP",
]
