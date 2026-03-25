#!/usr/bin/env python3
# =============================================================================
# BSD 2-Clause License
# Copyright (c) 2026, Jeremy Pickett. All rights reserved.
# =============================================================================
"""
Image Profiler
==============
Extracts a rich, structured profile from every image that passes through
the provenance pipeline — combining technical pixel analysis with semantic
scene analysis from Claude Haiku.

TWO CHANNELS
------------
Technical (no API, instant):
  Pixel statistics, color temperature, entropy, aspect ratio, and all
  provenance payload fields extracted during embedding.

Semantic (Haiku vision, ~$0.001/image):
  Scene type, lighting, time of day, weather, subject distance, color mood,
  crowd density, geographic region, and more — all returned as structured JSON.

OUTPUT
------
A flat dict per image, suitable for direct insertion into a database table,
or accumulated as JSONL for batch analysis.

The profile is designed to be the foundation of a two-table attack/enrichment
schema:
  Table 1: image_profiles   — one row per image, all 37 fields
  Table 2: image_events     — join on creator_id + hash, many-to-many
                              with attack_mitigations, threat_intel, etc.

USAGE
-----
  # Single image
  from image_profiler import profile_image
  record = profile_image("path/to/image.jpg")

  # With provenance manifest (adds payload fields)
  record = profile_image("path/to/image.jpg",
                          markers=markers, sentinels=sentinels,
                          payload_int=payload_int)

  # Corpus
  python image_profiler.py -i /path/to/DIV2K -o profiles.jsonl -n 50

NOTES
-----
- Haiku is called with a compact, strict JSON-only prompt. No preamble.
  If the response is not valid JSON, semantic fields default to "unknown".
- The API key is read from ANTHROPIC_API_KEY environment variable.
- If the API key is absent, semantic analysis is skipped gracefully.
- Technical analysis always runs without any API dependency.
"""

# Bootstrap: resolve project src/ directory regardless of invocation location
try:
    from _bootstrap import bootstrap
    bootstrap(__file__)
except ImportError:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import os
import io
import sys
import json
import math
import base64
import time
import urllib.request
import urllib.error
import numpy as np
from PIL import Image
from datetime import datetime, timezone


# =============================================================================
# CONSTANTS
# =============================================================================

HAIKU_MODEL     = "claude-haiku-4-5-20251001"
ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VER   = "2023-06-01"
MAX_TOKENS      = 512
RESIZE_MAX      = 1024     # longest edge for Haiku input
JPEG_QUALITY    = 85       # re-encode quality for API input (smaller payload)

SEMANTIC_FIELDS_DEFAULT = {
    "scene_type":                    "unknown",
    "lighting_quality":              "unknown",
    "time_of_day":                   "unknown",
    "weather":                       "unknown",
    "approximate_subject_distance":  "unknown",
    "depth_of_field":                "unknown",
    "dominant_colors":               ["unknown", "unknown", "unknown"],
    "color_mood":                    "unknown",
    "subject_category":              "unknown",
    "crowd_density":                 "unknown",
    "motion_blur":                   "unknown",
    "image_quality":                 "unknown",
    "contains_text":                 False,
    "contains_faces":                False,
    "contains_recognizable_landmark":False,
    "estimated_geographic_region":   "unknown",
    "extreme_weather_present":       False,
    "notable_elements":              "",
}

SEMANTIC_PROMPT = """\
Analyze this image and return ONLY a JSON object with these exact keys.
No preamble, no explanation, no markdown. Raw JSON only.

{
  "scene_type": one of [outdoor, indoor, studio, abstract],
  "lighting_quality": one of [harsh, soft, diffuse, artificial, mixed, unknown],
  "time_of_day": one of [dawn, morning, midday, afternoon, dusk, night, unknown],
  "weather": one of [clear, cloudy, overcast, rain, snow, fog, haze, unknown],
  "approximate_subject_distance": one of [close, medium, distant, aerial, unknown],
  "depth_of_field": one of [shallow, deep, unknown],
  "dominant_colors": [color1, color2, color3] as plain English words,
  "color_mood": one of [warm, cool, neutral, high-contrast, desaturated],
  "subject_category": one of [person, animal, landscape, architecture, object, text, abstract, mixed],
  "crowd_density": one of [none, sparse, moderate, dense, unknown],
  "motion_blur": one of [none, mild, strong, unknown],
  "image_quality": one of [high, medium, low, compressed],
  "contains_text": true or false,
  "contains_faces": true or false,
  "contains_recognizable_landmark": true or false,
  "estimated_geographic_region": continent name or "unknown",
  "extreme_weather_present": true or false,
  "notable_elements": brief description max 20 words
}"""


# =============================================================================
# TECHNICAL ANALYSIS
# =============================================================================

def _color_temp_estimate(mean_r, mean_b):
    """
    Rough color temperature estimate from R/B ratio.
    Formula: higher R/B = warmer (lower K), lower R/B = cooler (higher K).
    Range: ~2000K (candlelight) to ~10000K (overcast sky).
    """
    if mean_b < 1:
        return 6500
    ratio = mean_r / mean_b
    # Empirical fit: ratio ~1.8 ≈ 3200K (tungsten), ~1.0 ≈ 6500K (daylight), ~0.7 ≈ 9000K (shade)
    try:
        k = int(6500 / (ratio ** 1.5))
        return max(1500, min(12000, k))
    except Exception:
        return 6500


def _entropy(channel):
    """Shannon entropy of a single channel in bits."""
    hist, _ = np.histogram(channel.flatten(), bins=256, range=(0, 256))
    hist     = hist[hist > 0].astype(float)
    probs    = hist / hist.sum()
    return float(-np.sum(probs * np.log2(probs)))


def technical_profile(pixels, filename="",
                       markers=None, sentinels=None, payload_int=None):
    """
    Extract technical statistics from pixel array.
    All computation is local — no API calls.
    """
    h, w = pixels.shape[:2]
    r, g, b = pixels[:,:,0], pixels[:,:,1], pixels[:,:,2]

    mean_r = float(np.mean(r))
    mean_g = float(np.mean(g))
    mean_b = float(np.mean(b))

    # Luminance (ITU-R BT.601)
    luma   = (0.299 * r.astype(float) +
              0.587 * g.astype(float) +
              0.114 * b.astype(float))
    mean_luma = float(np.mean(luma))
    std_luma  = float(np.std(luma))

    # Channel dominance
    ranked = sorted(
        [("R", mean_r), ("G", mean_g), ("B", mean_b)],
        key=lambda x: -x[1]
    )
    channel_dominance = ">".join(c for c, _ in ranked)

    # Entropy per channel
    entropy_r = _entropy(r)
    entropy_g = _entropy(g)
    entropy_b = _entropy(b)

    # Color temperature
    color_temp_k = _color_temp_estimate(mean_r, mean_b)

    # Aspect ratio as simplified fraction
    from math import gcd
    g_ = gcd(w, h)
    aspect = f"{w//g_}:{h//g_}"

    # Provenance fields
    n_markers   = len(markers)   if markers   else 0
    n_sentinels = len(sentinels) if sentinels else 0
    n_sections  = n_sentinels // 2 if sentinels else 0

    payload_fields = {}
    if payload_int is not None:
        p = int(payload_int) & 0xFFFFFF
        payload_fields = {
            "creator_id_fragment": (p >> 16) & 0xFF,
            "hash_fragment":       (p >> 8)  & 0xFF,
            "protocol_version":    (p >> 4)  & 0x0F,
            "flags":               (p >> 0)  & 0x0F,
        }

    return {
        "filename":          filename,
        "width":             w,
        "height":            h,
        "aspect_ratio":      aspect,
        "mean_r":            round(mean_r, 2),
        "mean_g":            round(mean_g, 2),
        "mean_b":            round(mean_b, 2),
        "mean_luminance":    round(mean_luma, 2),
        "luminance_std":     round(std_luma, 2),
        "color_temp_est_K":  color_temp_k,
        "channel_dominance": channel_dominance,
        "entropy_r":         round(entropy_r, 4),
        "entropy_g":         round(entropy_g, 4),
        "entropy_b":         round(entropy_b, 4),
        "n_markers":         n_markers,
        "n_sections":        n_sections,
        "n_sentinels":       n_sentinels,
        "payload_int":       payload_int,
        **payload_fields,
    }


# =============================================================================
# SEMANTIC ANALYSIS — HAIKU VISION
# =============================================================================

def _pixels_to_base64_jpeg(pixels, max_edge=RESIZE_MAX, quality=JPEG_QUALITY):
    """Resize if needed, encode to JPEG, return base64 string."""
    h, w = pixels.shape[:2]
    if max(h, w) > max_edge:
        scale = max_edge / max(h, w)
        img   = Image.fromarray(pixels).resize(
            (int(w * scale), int(h * scale)), Image.LANCZOS
        )
    else:
        img = Image.fromarray(pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def semantic_profile(pixels, api_key=None):
    """
    Call Claude Haiku with vision to extract semantic scene metadata.
    Returns dict of semantic fields. Falls back to defaults on any error.
    """
    if api_key is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {**SEMANTIC_FIELDS_DEFAULT, "_semantic_source": "skipped_no_api_key"}

    try:
        b64 = _pixels_to_base64_jpeg(pixels)

        payload = json.dumps({
            "model":      HAIKU_MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type":   "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       b64,
                        },
                    },
                    {"type": "text", "text": SEMANTIC_PROMPT},
                ],
            }],
        }).encode("utf-8")

        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         api_key,
                "anthropic-version": ANTHROPIC_VER,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            text   = data["content"][0]["text"].strip()
            # Strip any accidental markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)

        # Merge with defaults to fill any missing keys
        merged = {**SEMANTIC_FIELDS_DEFAULT, **result}
        merged["_semantic_source"] = "haiku"
        return merged

    except urllib.error.HTTPError as e:
        return {**SEMANTIC_FIELDS_DEFAULT,
                "_semantic_source": f"error_http_{e.code}"}
    except json.JSONDecodeError as e:
        return {**SEMANTIC_FIELDS_DEFAULT,
                "_semantic_source": f"error_json_{str(e)[:40]}"}
    except Exception as e:
        return {**SEMANTIC_FIELDS_DEFAULT,
                "_semantic_source": f"error_{type(e).__name__}"}


# =============================================================================
# COMBINED PROFILE
# =============================================================================

def profile_image(path_or_pixels, markers=None, sentinels=None,
                  payload_int=None, api_key=None, skip_semantic=False):
    """
    Full profile: technical + semantic.

    Args:
        path_or_pixels: file path (str) or numpy RGB array
        markers:        list of marker dicts from embed manifest (optional)
        sentinels:      list of sentinel dicts from embed manifest (optional)
        payload_int:    24-bit payload integer (optional)
        api_key:        Anthropic API key (reads ANTHROPIC_API_KEY if None)
        skip_semantic:  if True, skip Haiku call (technical only)

    Returns:
        Flat dict with ~37 fields + metadata
    """
    t0 = time.time()

    # Load pixels
    if isinstance(path_or_pixels, str):
        filename = os.path.basename(path_or_pixels)
        img      = Image.open(path_or_pixels).convert("RGB")
        pixels   = np.array(img, dtype=np.uint8)
    else:
        filename = ""
        pixels   = path_or_pixels

    tech  = technical_profile(pixels, filename, markers, sentinels, payload_int)
    sem   = {} if skip_semantic else semantic_profile(pixels, api_key)

    record = {
        **tech,
        **sem,
        "profiled_at": datetime.now(timezone.utc).isoformat(),
        "profile_ms":  round((time.time() - t0) * 1000, 1),
    }
    return record


# =============================================================================
# CORPUS RUN
# =============================================================================

def run_profiler(input_dir, output_path, max_images=0,
                 skip_semantic=False, api_key=None):
    extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}
    all_files  = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in extensions
    ])
    if max_images > 0:
        all_files = all_files[:max_images]

    print(f"{'='*60}")
    print(f"IMAGE PROFILER")
    print(f"{'='*60}")
    print(f"Images:          {len(all_files)}")
    print(f"Semantic:        {'ENABLED (Haiku)' if not skip_semantic else 'SKIPPED'}")
    print(f"Output:          {output_path}")
    print(f"{'='*60}\n")

    open(output_path, "w").close()
    t_start = time.time()

    for idx, fname in enumerate(all_files):
        fpath = os.path.join(input_dir, fname)
        print(f"[{idx+1:>4d}/{len(all_files)}] {fname}  ", end="", flush=True)

        try:
            record = profile_image(
                fpath, api_key=api_key, skip_semantic=skip_semantic
            )
            src = record.get("_semantic_source", "ok")
            print(f"luma={record['mean_luminance']:.0f}  "
                  f"K={record['color_temp_est_K']}  "
                  f"scene={record.get('scene_type','?')}  "
                  f"weather={record.get('weather','?')}  "
                  f"[{record['profile_ms']:.0f}ms] {src}")
            with open(output_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            print(f"ERROR: {e}")

    elapsed = time.time() - t_start
    n = len(all_files)
    print(f"\nDone: {n} images in {elapsed:.0f}s "
          f"({elapsed/max(n,1):.1f}s/image)")
    print(f"Output: {output_path}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Image Profiler — technical + semantic")
    parser.add_argument("--input",          "-i", required=True)
    parser.add_argument("--output",         "-o", default="image_profiles.jsonl")
    parser.add_argument("--max-images",     "-n", type=int, default=0)
    parser.add_argument("--skip-semantic",        action="store_true",
                        help="Technical stats only, no Haiku API call")
    parser.add_argument("--api-key",        "-k", default=None,
                        help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: {args.input} not a directory"); sys.exit(1)

    run_profiler(
        args.input, args.output,
        max_images=args.max_images,
        skip_semantic=args.skip_semantic,
        api_key=args.api_key,
    )
