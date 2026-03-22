# ADDENDUM A

**Extension to Video: I-Frames Are JPEGs in a Trench Coat**

*Addendum to: Participation Over Permission — March 2026*


---


## A.1 The Short Answer


Every modern video codec (H.264/AVC, H.265/HEVC, VP9, AV1) uses block-based transform coding on its independently decodable frames. These frames — I-frames (Intra-coded frames) — are compressed using spatial frequency decomposition and quantization within blocks. H.264 uses a 4×4 or 8×8 integer DCT. H.265 uses variable-size transform blocks up to 32×32. AV1 uses transform blocks from 4×4 to 64×64.


The quantization is different from JPEG’s. The block sizes vary. The entropy coding differs. But the principle that creates the amplification effect — block-based spatial frequency decomposition that exploits local spatial correlation and penalizes local complexity — is identical across all of them.


I-frames are JPEGs in a trench coat. The same granite hypothesis applies.


---


## A.2 Why Video Is Easier, Not Harder


The still-image experiments operated under severe constraints: 512×512 pixels, approximately 200 twin markers, statistical power marginal at Generation 2+. Video eliminates every one of these constraints.


### A.2.1 Massive Marker Capacity


A single 1080p I-frame contains 1920 × 1080 ≈ 2.07 million pixels. At the marker density used in the still-image experiments (approximately 1 twin marker per 1,400 pixels), a single I-frame supports roughly 1,500 twin markers. That is 7.5× the 200 markers that achieved detection at Generation 0 on the 512×512 test image.


A 4K frame (3840 × 2160 ≈ 8.3 million pixels) supports approximately 5,900 markers per I-frame. Detection statistical power scales with the square root of marker count. The detection floor moves substantially deeper into the compression cascade.


| Resolution | Pixels | Markers/I-frame | vs. 512×512 |
| --- | --- | --- | --- |
| 512×512 (test) | 262,144 | ~200 | 1× (baseline) |
| 720p | 921,600 | ~660 | 3.3× |
| 1080p | 2,073,600 | ~1,500 | 7.5× |
| 4K | 8,294,400 | ~5,900 | 29.5× |


**Table A1. ***Marker capacity per I-frame by resolution. The statistical power problem that constrained the 512×512 experiments does not exist at video resolutions.*


### A.2.2 Temporal Redundancy as Cross-Validation


Video contains multiple I-frames across its duration. A typical encoding configuration produces an I-frame every 1–2 seconds. A 10-minute video at 2-second I-frame intervals contains 300 I-frames. Each I-frame is an independent embedding target and an independent detection opportunity.


This provides two benefits that still images cannot offer:


**Independent replication within a single file.** If twin markers at position (r, c) show amplified variance anomaly in I-frame 47 AND I-frame 49 AND I-frame 51, that is three independent measurements of the same perturbation surviving three independent compression events. The probability of three false positives at the same spatial position across three independent frames is the cube of the single-frame false positive rate.


**Corpus-within-a-file forensics.** The 300 I-frames of a single video file constitute a mini-corpus. Every corpus-level analysis described in the paper — repetitive basket patterns, predictable absence patterns, cross-frame correlation, temporal clustering — applies within a single video file. A single video provides the statistical population that still images require a dataset to achieve.


| Duration | I-frames | Markers (1080p) | Markers (4K) | Statistical Power |
| --- | --- | --- | --- | --- |
| 30 seconds | 15 | ~22,500 | ~88,500 | Substantial |
| 5 minutes | 150 | ~225,000 | ~885,000 | Overwhelming |
| 10 minutes | 300 | ~450,000 | ~1,770,000 | Effectively unlimited |
| 2 hours (film) | 3,600 | ~5,400,000 | ~21,240,000 | Absurd |


**Table A2. ***Total marker count across I-frames by video duration at 2-second I-frame interval. A feature film at 4K provides over 21 million independent twin markers.*


### A.2.3 Richer Container Layer


Video formats provide more embedding surface for container-layer signals than JPEG:


**SEI NAL units (H.264/H.265):** Supplemental Enhancement Information units are the video equivalent of JPEG APP segments. They are preserved by compliant muxers, ignored by decoders, and provide arbitrary-length payload space. The spec defines registered and unregistered SEI types; unregistered SEI (user_data_unregistered) accepts arbitrary payloads identified by a UUID. This is purpose-built carry-your-own-luggage space.


**PPS quantization parameters:** The Picture Parameter Set carries quantization parameters that control per-frame compression. This is the video analog of JPEG’s DQT segment. Strategy 4 (prime-shifted quantization) applies directly: the PPS quantization matrix entries can be shifted to primes with the same negligible visual impact and the same O(1) static detection.


**Container metadata:** MP4 (ISO BMFF), MKV (Matroska), and WebM containers provide extensive metadata structures — user-defined atoms, tags, and attachments — that survive remuxing (container format change without re-encoding). These are additional Douglas Rule embedding surfaces that survive any operation short of re-encoding the video stream itself.


---


## A.3 What You Embed In, What You Don’t


### A.3.1 I-Frames Only


The scheme embeds exclusively in I-frames (intra-coded frames). I-frames are compressed independently, like still images. Each I-frame contains full pixel data for every position, decoded through block-based transform coding. The twin marker embedding and the amplification hypothesis apply directly.


**P-frames and B-frames are excluded.** P-frames (Predicted) store motion-compensated residuals from a reference frame. B-frames (Bi-predicted) store residuals from two reference frames. The pixel values in P and B frames are differences, not absolute values. They change unpredictably under re-encoding as the motion estimation algorithm makes different choices. Embedding in P/B frames would produce markers that are entangled with motion estimation in ways that are not characterizable from first principles.


This is not a limitation. It is a scope boundary. I-frames carry enough embedding surface to provide overwhelming statistical power at any common video resolution and duration. The exclusion of P/B frames is a design choice that trades unnecessary complexity for predictable behavior.


### A.3.2 I-Frame Interval Considerations


The I-frame interval (keyframe interval, GOP length) varies by encoder settings and platform requirements. Typical values:


| Context | Typical I-frame Interval | I-frames per Minute |
| --- | --- | --- |
| YouTube upload processing | 2–4 seconds | 15–30 |
| Netflix / streaming delivery | 2–6 seconds | 10–30 |
| Broadcast television | 0.5–2 seconds | 30–120 |
| Video conferencing | 1–5 seconds (adaptive) | 12–60 |
| Archival / mezzanine | All-intra (every frame) | ~1,800 at 30fps |


**Table A3. ***Typical I-frame intervals. Even the sparsest configurations (6-second intervals) provide ample embedding surface for statistical detection.*


A platform that re-encodes uploaded video may change the I-frame interval. This affects which specific frames carry markers, but does not affect the scheme: the re-encoder must produce its own I-frames, and those I-frames will contain the perturbation artifacts from the original embedding, amplified by the re-encoding process. The markers follow the content, not the frame boundaries.


---


## A.4 The Re-Encoding Pipeline


Video uploaded to a platform is almost always re-encoded. YouTube, for example, re-encodes every upload to multiple resolution and bitrate tiers. This is the adversary’s compression pipeline applied automatically at scale.


The scheme’s response to this pipeline is identical to the still-image case, with amplified statistical power:


**Layer A (PPS/quantization parameter primality):** Destroyed on first re-encode, same as JPEG DQT. The re-encoder writes its own quantization parameters. Presence confirms first-generation video from a participating encoder. Absence is the expected state for re-encoded video.


**Layer B (twin markers in I-frames):** Survives through re-encoding according to the same survival curve as JPEG, but with 7–30× more markers per frame providing substantially greater statistical power. Detection at Generation 2+ becomes feasible where it was marginal on 512×512 still images.


**Layer B+ (amplification):** If the amplification hypothesis holds on video I-frames — and it should, because the transform coding mechanism is the same — then platform re-encoding at lower bitrates amplifies the perturbation signal. A video scraped from YouTube at 720p after being uploaded at 1080p carries a louder variance anomaly than the original upload. The platform’s own compression pipeline is, once again, the detection amplifier.


**Temporal cross-validation:** The adversary who targets specific I-frames for suppression must identify and suppress markers in every I-frame, because the detector can use any surviving I-frame as evidence. Missing one I-frame out of 300 is sufficient for detection. The adversary’s burden of perfection scales with video duration.


---


## A.5 The Adversary’s Problem, Scaled


Consider the adversary’s task on a 10-minute 1080p video with 2-second I-frame intervals:


300 I-frames. ~1,500 twin markers per I-frame. ~450,000 total markers. Each marker must be identified. Each must be suppressed with targeted local smoothing. Each smoothing operation must avoid creating detectable artifacts. The suppression must be validated per-position, per-frame.


On a 2-hour 4K film: 3,600 I-frames. ~5,900 markers per frame. ~21 million markers. The suppression campaign requires identifying and neutralizing 21 million positions across 3,600 independent frames without leaving forensic residue in any of them.


At corpus scale — a platform ingesting thousands of hours of video per day — this is not a pipeline. It is an army. Armies have budgets, employees, managers, Slack channels, and compute bills. All discoverable.


The alternative: don’t suppress. Accept State B. Let the signal ride. Most platforms will choose this option because suppression costs more than compliance. That is the economic argument. It applies to video with approximately 1,000× more force than it applies to still images, because video provides 1,000× more evidence surface.


---


## A.6 What Remains to Be Tested for Video


**H.264 integer DCT vs. JPEG DCT:** The 4×4 integer transform in H.264 has different rounding and normalization properties than JPEG’s 8×8 floating-point DCT. The amplification hypothesis predicts the same behavior (quantization penalizes local complexity) but the specific survival curves and amplification rates must be measured empirically.


**Bitrate-controlled quantization:** Video encoders typically use rate-control (targeting a specific bitrate) rather than fixed quality. Rate-control produces variable quantization per-frame and per-macroblock. The interaction between variable quantization and twin marker perturbation is an empirical question.


**Scene-cut I-frame placement:** Modern encoders insert I-frames at scene cuts. Markers embedded in a scene that appears briefly may land in few or no I-frames after re-encoding if the encoder places keyframes differently. The scheme should embed across the entire video to ensure markers land in I-frames regardless of keyframe placement strategy.


**B-frame reference propagation:** While markers are not embedded in P/B frames, perturbation at marker positions in I-frames propagates into P/B frames via the reference chain. This propagated perturbation may create additional detectable artifacts in reconstructed P/B frames. This is speculative and requires investigation.


**Audio track:** The audio track of a video file is an independent embedding surface. PCM audio samples are the amplitude-domain analog of pixel channel values. Twin prime-gap markers in the amplitude domain, subject to psychoacoustic model survival under MP3/AAC/Opus encoding, are a parallel detection layer independent of the video track. This is future work.


---


*Video is not a harder case. It is the case where every constraint that limited the still-image experiments disappears. The marker capacity is overwhelming. The temporal redundancy provides built-in cross-validation. The adversary’s suppression cost scales linearly with duration. A 10-minute video is not 10 times harder to protect than a photograph. It is 450,000 times harder to attack.*


*Theoretical extension. No experimental validation on video has been performed.*


***The I-frame must be tested.***


Jeremy Pickett — March 2026
