# Raw Integration Guide

**Granite Under Sandstone — Direct Source Integration**

This guide shows how to embed provenance signals into images and detect them later, using the source modules directly. No library installation required — just copy the `src/` directory and import.

---

## Prerequisites

```bash
pip install Pillow numpy scipy
```

Your project needs the `backend/src/` directory on `sys.path`:

```python
import sys
sys.path.insert(0, "/path/to/backend/src")
```

---

## Quick Start: Embed and Detect in 10 Lines

```python
import numpy as np
from PIL import Image
from smart_embedder import smart_embed, PROFILES
from layer2_detect import layer2_detect

# Load image
pixels = np.array(Image.open("photo.png").convert("RGB"))

# Embed
modified, metadata = smart_embed(pixels, PROFILES["jpeg_75"], seed=42)
Image.fromarray(modified).save("photo_signed.png")

# Detect (requires the metadata from embedding)
result = layer2_detect(modified, metadata.positions, min_prime=37, channel_pair=(0, 1))
print(f"Detected: {result['detected']}  (p={result['chi2_pvalue']:.2e})")
```

---

## Embedding

### Choosing a Profile

The `smart_embedder` module provides format-aware profiles that control where and how markers are placed. The profile choice determines signal survival characteristics.

| Profile | Use When | Notes |
|---------|----------|-------|
| `PROFILES["jpeg_95"]` | Output will be JPEG Q90+ | Avoids Q95 quantization grids |
| `PROFILES["jpeg_85"]` | Output will be JPEG Q80-90 | Good general-purpose choice |
| `PROFILES["jpeg_75"]` | Output will be JPEG Q70-80 | Aggressive grid avoidance |
| `PROFILES["jpeg_60"]` | Output will face heavy compression | Most conservative |
| `PROFILES["png"]` | Output stays lossless (PNG) | Maximum embedding freedom |
| `PROFILES["generic"]` | Unknown downstream pipeline | Assumes worst case |

**Rule of thumb:** Choose the profile matching the *lowest quality* JPEG the image might encounter. If unsure, use `"generic"`.

### smart_embed()

The primary embedding function. Format-aware, entropy-gated, quantization-grid-avoiding.

```python
from smart_embedder import smart_embed, PROFILES

profile = PROFILES["jpeg_75"]
profile.n_markers = 500  # Number of markers to embed (default: 500)

modified_pixels, metadata = smart_embed(pixels, profile, seed=42)
```

**Parameters:**
- `pixels` — `np.ndarray` shape `(H, W, 3)`, dtype `uint8`. RGB image.
- `profile` — `EmbedProfile` instance. Controls basket filtering, position selection, and embedding parameters.
- `seed` — `int`. Deterministic RNG seed. Same seed + same image = same marker positions.

**Returns:**
- `modified_pixels` — `np.ndarray` shape `(H, W, 3)`, dtype `uint8`. The signed image.
- `metadata` — `EmbedResult` dataclass with:
  - `.n_markers_embedded` — How many markers were actually placed
  - `.positions` — List of dicts: `{"row", "col", "prime", "adjustment", "original_b", "new_b"}`
  - `.basket_primes` — The prime values used for embedding
  - `.mean_channel_adjustment` — Average pixel modification magnitude
  - `.embed_time_ms` — Embedding time

**You must save `metadata.positions`** — detection requires knowing where markers were placed.

### embed_compound()

For compound markers (twin-prime pairs, magic sentinels, rare basket). Higher false-positive resistance at the cost of embedding density.

```python
from compound_markers import embed_compound, MARKER_TYPES

config = MARKER_TYPES["compound"]  # Full compound: twin + magic + rare basket
# Or: "single_basic", "single_rare", "twin", "magic"

modified_pixels, markers = embed_compound(pixels, config, variable_offset=42)
```

**Returns:**
- `modified_pixels` — Signed image.
- `markers` — List of dicts with position and marker details. Required for detection.

### encode_prime_jpeg() — Layer 1 DQT

Encodes a JPEG with prime-shifted quantization tables. The table itself is the signal — no pixel-space markers needed for this layer.

```python
from dqt_prime import encode_prime_jpeg

jpeg_bytes, meta = encode_prime_jpeg(
    pixels,
    quality=75,       # Base JPEG quality
    min_prime=2,      # Minimum prime for table entries
    preserve_dc=True, # Don't modify DC coefficient (preserves visual quality)
    output_path="signed.jpg"  # Optional: write directly to disk
)
```

**DQT embedding is independent of pixel-space embedding.** You can (and should) use both layers together:

```python
# Layer 2+3: pixel-space markers
modified, metadata = smart_embed(pixels, PROFILES["jpeg_75"])

# Layer 1: prime quantization tables
jpeg_bytes, dqt_meta = encode_prime_jpeg(modified, quality=75)
```

### Saving the Embedding Manifest

Detection requires the marker positions. Serialize them alongside or embedded in the image metadata.

```python
import json
from dataclasses import asdict

manifest = {
    "version": 1,
    "seed": 42,
    "profile": metadata.profile_name,
    "n_markers": metadata.n_markers_embedded,
    "positions": metadata.positions,
    "basket": metadata.basket_primes,
}

with open("photo_signed.manifest.json", "w") as f:
    json.dump(manifest, f)
```

For Layer 3 (Rare Basket attribution), the seed alone is sufficient — positions are deterministically derived via HMAC-SHA512, so the manifest can be just the seed.

---

## Detection

### Layer 1: DQT Detection (Blind, No Manifest)

The only layer that works without knowing the embedding parameters. Reads the JPEG quantization table and checks if entries are prime.

```python
from dqt_prime import detect_prime_dqt

result = detect_prime_dqt("suspect.jpg")

print(f"Prime rate: {result['overall_prime_rate']:.3f}")  # Natural: ~0.21, Embedded: ~0.95
print(f"Detected:   {result['detected']}")                # True if rate > 0.60 and p < 1e-10
```

**Works on:**
- Original prime-encoded JPEGs (near-perfect detection)
- Not useful after re-encoding (the new encoder writes its own tables)

**For ghost detection after re-encoding:**

```python
from dqt_prime import detect_dqt_ghost

ghost = detect_dqt_ghost(original_prime_jpeg_bytes, reencoded_jpeg_bytes)
# ghost["ghost_signal"] shows double-quantization artifacts
```

### Layer 2: Known-Position Detection (Requires Manifest)

Compares prime-gap hit rate at known marker positions vs. control positions in the same image. The image is its own control group.

```python
from layer2_detect import layer2_detect

# Load the suspect image
suspect = np.array(Image.open("suspect.jpg").convert("RGB"))

# Load the manifest
with open("photo_signed.manifest.json") as f:
    manifest = json.load(f)

result = layer2_detect(
    suspect,
    manifest["positions"],
    min_prime=37,
    channel_pair=(0, 1),  # R-G channel pair
)

print(f"Marker hit rate:  {result['marker_hit_rate']:.4f}")
print(f"Control hit rate: {result['control_hit_rate']:.4f}")
print(f"Rate ratio:       {result['rate_ratio']:.2f}x")
print(f"Chi-squared p:    {result['chi2_pvalue']:.2e}")
print(f"Detected:         {result['detected']}")
```

### Layer 2: Compound Detection

For images embedded with compound markers (twin, magic, or full compound):

```python
from compound_markers import detect_compound, MARKER_TYPES

config = MARKER_TYPES["compound"]
result = detect_compound(suspect_pixels, markers, config)

print(f"Compound pass rate: {result['marker_rate']:.4f}")
print(f"Control pass rate:  {result['control_rate']:.4f}")
print(f"Rate ratio:         {result['rate_ratio']:.1f}x")
print(f"Chi-squared p:      {result['chi2_pvalue']:.2e}")
```

### Layer 1: Blind Aggregate Detection (No Manifest)

Statistical detection without knowing marker positions. Less sensitive, but works as a screening pass.

```python
from pgps_detector import (
    load_and_decode, build_prime_lookup,
    sample_positions_grid, extract_distances,
    analyze_distances, DEFAULT_CHANNEL_PAIRS,
)

pixels = load_and_decode("suspect.png")
positions = sample_positions_grid(pixels.shape[0], pixels.shape[1], window_w=8)
distances = extract_distances(pixels, positions, DEFAULT_CHANNEL_PAIRS)

prime_lookup = build_prime_lookup(8, min_prime=37)
stats = analyze_distances(distances["ALL"], prime_lookup)

print(f"rho:        {stats.rho:.4f}")
print(f"Chi-sq p:   {stats.chi2_pvalue:.4f}")
print(f"KS p:       {stats.ks_pvalue:.4f}")
```

---

## Interpreting Results

### Detection Verdicts

| Metric | Meaning | Threshold |
|--------|---------|-----------|
| `detected` | Boolean verdict | `chi2_pvalue < 0.01` AND `marker_rate > control_rate` |
| `chi2_pvalue` | Chi-squared p-value | < 0.01 = significant signal |
| `binomial_pvalue` | Binomial test p-value | < 0.01 = significant signal |
| `rate_ratio` | marker_hit_rate / control_hit_rate | > 1.0 = signal present |
| `overall_prime_rate` | DQT: fraction of table entries that are prime | > 0.60 = embedded (natural ~0.21) |

### Understanding Rate Ratio

The rate ratio is the primary signal strength indicator. It answers: "Are marker positions more likely to have prime-gap distances than random positions in the same image?"

| Rate Ratio | Interpretation |
|------------|----------------|
| ~1.0 | No signal (or signal destroyed) |
| 1.2 - 1.5 | Weak signal, marginal detection |
| 1.5 - 3.0 | Clear signal, reliable detection |
| 3.0+ | Strong signal |
| 10.0+ | Lossless or near-lossless path |

### Understanding p-values

Both `chi2_pvalue` and `binomial_pvalue` test the null hypothesis: "marker positions show the same prime-gap rate as control positions."

| p-value | Meaning |
|---------|---------|
| > 0.05 | No significant difference (signal not detected) |
| 0.01 - 0.05 | Marginal (possible signal, low confidence) |
| 0.001 - 0.01 | Significant (signal likely present) |
| < 0.001 | Highly significant (signal confirmed) |
| < 1e-10 | Overwhelming evidence |

**Always check both the p-value AND the rate ratio.** A low p-value with rate_ratio < 1.0 means the control positions are *more* prime than markers — this indicates the signal was destroyed, not confirmed.

### JPEG Cascade Survival

Signals degrade through JPEG compression cascades. Expected behavior:

| JPEG Quality | Expected Rate Ratio | Notes |
|-------------|-------------------|-------|
| Lossless (PNG) | 5.0 - 15.0+ | Near-perfect survival |
| Q95 | 3.0 - 8.0 | Minimal degradation |
| Q85 | 2.0 - 5.0 | Moderate degradation |
| Q75 | 1.5 - 3.0 | Significant but detectable |
| Q60 | 1.0 - 2.0 | Marginal, content-dependent |
| Q40 | ~1.0 | Signal likely destroyed |

### Variance Ratio and Amplification

In the Granite Test (div2k_harness_v2), two additional metrics appear:

- **Variance ratio** = variance of distances at marker positions / variance at control positions. A ratio > 1.0 means markers introduce more spread into the distance distribution.
- **Amplification** = whether the variance ratio *increases* across JPEG compression generations. This is the key insight: compression doesn't just preserve the signal, it can amplify the statistical divergence.

| Variance Ratio | Interpretation |
|----------------|----------------|
| ~1.0 | No structural difference |
| 1.1 - 1.5 | Mild signal |
| 1.5+ | Strong structural perturbation |

### Channel Pair Performance

Different channel pairs show different detection rates due to how JPEG handles color:

| Channel Pair | Detection Rate (800-image DIV2K) | Notes |
|-------------|--------------------------------|-------|
| G-B (1,2) | 96.4% | Best performer — JPEG chroma subsampling is gentler here |
| R-G (0,1) | 90.1% | Good but slightly lower |

**Recommendation:** Embed in both channel pairs and detect on G-B first, falling back to R-G.

### The Granite Test Verdicts

The div2k_harness_v2 produces three possible verdicts:

| Verdict | Meaning |
|---------|---------|
| **GRANITE CONFIRMED** | Signal detected in >95% of images across both channel pairs with amplification |
| **GRANITE PARTIAL** | Signal detected in >80% of images in at least one channel pair |
| **GRANITE NOT CONFIRMED** | Signal not reliably detected |

---

## Full Integration Example

A complete embed-save-load-detect cycle:

```python
import sys
import json
import numpy as np
from PIL import Image

sys.path.insert(0, "/path/to/backend/src")

from smart_embedder import smart_embed, PROFILES
from dqt_prime import encode_prime_jpeg, detect_prime_dqt
from layer2_detect import layer2_detect

# ── EMBEDDING (at content creation time) ──

original = np.array(Image.open("original.png").convert("RGB"))

# Layer 2+3: pixel-space markers
profile = PROFILES["jpeg_75"]
profile.n_markers = 500
signed_pixels, embed_meta = smart_embed(original, profile, seed=42)

# Layer 1: prime quantization tables (if outputting JPEG)
jpeg_bytes, dqt_meta = encode_prime_jpeg(signed_pixels, quality=85)
with open("signed.jpg", "wb") as f:
    f.write(jpeg_bytes)

# Save manifest (store securely — this is needed for Layer 2 detection)
manifest = {
    "positions": embed_meta.positions,
    "seed": 42,
    "profile": embed_meta.profile_name,
    "basket": embed_meta.basket_primes,
    "channel_pair": [0, 1],
}
with open("signed.manifest.json", "w") as f:
    json.dump(manifest, f)

print(f"Embedded {embed_meta.n_markers_embedded} markers")
print(f"Mean pixel adjustment: {embed_meta.mean_channel_adjustment:.1f}")


# ── DETECTION (later, possibly after re-sharing/compression) ──

suspect = np.array(Image.open("signed.jpg").convert("RGB"))

# Layer 1: DQT check (blind, no manifest needed)
dqt_result = detect_prime_dqt("signed.jpg")
print(f"\nLayer 1 (DQT): prime_rate={dqt_result['overall_prime_rate']:.3f}"
      f"  detected={dqt_result['detected']}")

# Layer 2: known-position check (requires manifest)
with open("signed.manifest.json") as f:
    manifest = json.load(f)

l2_result = layer2_detect(
    suspect,
    manifest["positions"],
    min_prime=37,
    channel_pair=tuple(manifest["channel_pair"]),
)

print(f"\nLayer 2 (Known Position):")
print(f"  Marker hit rate:  {l2_result['marker_hit_rate']:.4f}")
print(f"  Control hit rate: {l2_result['control_hit_rate']:.4f}")
print(f"  Rate ratio:       {l2_result['rate_ratio']:.2f}x")
print(f"  p-value:          {l2_result['chi2_pvalue']:.2e}")
print(f"  Verdict:          {'SIGNAL DETECTED' if l2_result['detected'] else 'NOT DETECTED'}")
```

---

## Module Reference

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `pgps_detector.py` | Foundation: primes, sampling, distances, statistics | `sieve_of_eratosthenes()`, `build_prime_lookup()`, `sample_positions_grid()`, `extract_distances()`, `analyze_distances()`, `embed_prime_gap_markers()` |
| `smart_embedder.py` | Format-aware embedding with profiles | `smart_embed()`, `PROFILES`, `build_smart_basket()` |
| `compound_markers.py` | Compound marker strategies | `embed_compound()`, `detect_compound()`, `MARKER_TYPES` |
| `dqt_prime.py` | Prime quantization table embedding/detection | `encode_prime_jpeg()`, `detect_prime_dqt()`, `detect_dqt_ghost()` |
| `layer2_detect.py` | Known-position detection | `layer2_detect()` |
| `fp_forensics.py` | False positive forensics and diagnostics | `full_distance_forensics()` |

---

## Common Pitfalls

1. **Forgetting to save the manifest.** Layer 2 detection *requires* knowing where markers were placed. Without the manifest, you're limited to Layer 1 (DQT) detection.

2. **Wrong channel pair at detection.** If you embedded with `channel_pair=(0, 1)` (R-G), you must detect with the same pair. The default in `smart_embed` is R-G.

3. **Profile mismatch.** Using `PROFILES["png"]` to embed an image that will be JPEG-compressed defeats the purpose of grid avoidance. Match the profile to the expected pipeline.

4. **Expecting survival below Q60.** Aggressive JPEG compression (Q40 and below) destroys most pixel-space signals. The DQT layer is your backstop here, but only until the image is re-encoded.

5. **Testing on tiny images.** Images below 512px on either dimension don't have enough sample positions for statistical significance. The test harness skips these.

6. **Interpreting a single image.** The detection is statistical. A single image can be a false negative due to content characteristics (smooth gradients, saturated regions). Corpus-level analysis is always more reliable than single-image results.
