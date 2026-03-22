# THE GRANITE TEST — Setup Instructions
## Jeremy Pickett — Axiomatic Fictions Series

---

## What This Does

Runs the amplification hypothesis test on real photographs.
Embeds twin prime-gap markers, cascades through 5 JPEG compression
generations, measures whether the perturbation signal amplifies
under heavy compression.

Outputs a VERDICT.txt that says one of three things:
- GRANITE CONFIRMED (book the flight)
- GRANITE PARTIAL (publishable with caveats)
- GRANITE NOT CONFIRMED (cancel the flight, keep working)

---

## Repository Structure

```
backend/
├── src/                        # Core library
│   ├── pgps_detector.py        # Core detector
│   ├── compound_markers.py     # Twin/magic markers
│   ├── dqt_prime.py            # Strategy 4 (prime quant tables)
│   ├── smart_embedder.py       # File-type profiles
│   ├── layer2_detect.py        # Known-position detection
│   └── fp_forensics.py         # Distance forensics
│
├── tests/                      # Experimental harnesses
│   ├── div2k_harness_v2.py     # THE GRANITE TEST (v2)
│   ├── div2k_harness.py        # Original granite test
│   ├── cascade_test.py         # Multi-generation cascade
│   ├── scale_test.py           # Scale/resize stability
│   ├── channel_pair_test.py    # RGB pair independence
│   ├── jpeg_to_webp.py         # Cross-codec boundary
│   ├── slice_attack.py         # Slice-and-stitch attack
│   ├── rotation_attack.py      # Geometric attacks
│   └── prime_floor_sweep.py    # Basket floor sweep
│
└── test-images/                # 10 sample images for quick testing
```

---

## Setup on EC2 Micro (or any Linux box)

### Step 1: Spin up the instance

t3.micro is fine. Amazon Linux 2023 or Ubuntu 22.04.
Bump EBS to 15GB (default 8GB is tight).

### Step 2: Install dependencies

```bash
sudo yum install -y python3 python3-pip unzip wget   # Amazon Linux
# OR
sudo apt install -y python3 python3-pip unzip wget    # Ubuntu

pip3 install Pillow numpy scipy matplotlib --break-system-packages
# If --break-system-packages fails (older pip), just:
pip3 install Pillow numpy scipy matplotlib
```

### Step 3: Clone the repo

```bash
git clone https://github.com/jeremypickett/granite-under-sandstone.git
cd granite-under-sandstone/backend
```

### Step 4: Download DIV2K (or use included test images)

```bash
cd ~
mkdir -p div2k && cd div2k

# Validation set (100 images, ~400MB) — START HERE
wget http://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_valid_HR.zip
unzip DIV2K_valid_HR.zip

# OPTIONAL: Full training set (800 images, ~3.5GB) — run this AFTER
# the validation set confirms the result
# wget http://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_train_HR.zip
# unzip DIV2K_train_HR.zip
```

### Step 5: Run it

```bash
cd granite-under-sandstone/backend

# Quick sanity check with included test images (10 images, ~10 seconds)
python3 tests/div2k_harness_v2.py -i test-images -o results -n 10

# Or use DIV2K validation set (100 images)
python3 tests/div2k_harness_v2.py -i ~/div2k/DIV2K_valid_HR -o results -n 5

# Full validation set — use screen/tmux so it survives SSH disconnect
screen -S granite
python3 tests/div2k_harness_v2.py -i ~/div2k/DIV2K_valid_HR -o results

# Detach from screen: Ctrl+A then D
# Reattach later: screen -r granite
```

The synthetic test harnesses (cascade, scale, attacks) generate their own images and can be run directly:

```bash
python3 tests/cascade_test.py
python3 tests/channel_pair_test.py
python3 tests/rotation_attack.py
python3 tests/slice_attack.py
python3 tests/jpeg_to_webp.py
python3 tests/scale_test.py
python3 tests/prime_floor_sweep.py
```

### Step 6: Read the verdict

```bash
cat ~/results_full/VERDICT.txt
```

If matplotlib installed correctly, there's also:
```bash
# Download the plot to your local machine
scp -i your-key.pem ec2-user@your-instance:~/results_full/granite_test.png .
```

---

## Expected Runtime

- t3.micro (1 vCPU): ~3-5 seconds per image
  - 5 images: ~30 seconds
  - 100 images (validation): ~5-8 minutes
  - 800 images (full training): ~40-60 minutes

- Your ASUS Ascent GX10: probably 1-2 seconds per image
  - 100 images: ~2-3 minutes
  - 800 images: ~15-20 minutes

This is CPU-bound, not GPU-bound. No CUDA needed.

---

## What the Output Means

`results.jsonl` — One JSON object per line, per image. Every
measurement at every generation. This is your raw data.

`aggregate.json` — Summary statistics across the corpus.

`VERDICT.txt` — The bottom line.

`granite_test.png` — Two plots:
1. Histogram of Gen4 KS p-values (how many images show the
   amplification effect)
2. Box plot of variance ratios across generations (does the
   granite pattern hold: variance ratio increasing with
   compression?)

---

## What You're Looking For

The key number is: **what percentage of images show KS < 0.05
at Gen4 (Q40)?**

- > 50%: The effect is real. Write the paper.
- 20-50%: The effect is content-dependent. Characterize which
  content classes amplify. Still publishable.
- < 20%: The synthetic result didn't replicate. The DQT and
  twin-prime results still stand. The amplification claim
  doesn't.

The second key number: **variance ratio at Gen4.**

If marker positions consistently show higher twin-pair variance
than control positions (ratio > 1.0) at Gen4, and that ratio is
HIGHER than at Gen1-2, that's the amplification pattern.
That's the granite.

---

## If Something Breaks

Most likely failure: an image that's too small or has unusual
color space. The harness skips images below 256px and logs
errors. Check the console output.

If scipy complains about binomtest, you have an old scipy.
Run: pip3 install --upgrade scipy

If Pillow can't open some images, they might be 16-bit or
CMYK. The harness converts to RGB but exotic formats may fail.
Errors are logged, not fatal.

---

## After the Verdict

If granite confirmed:
1. Save results_full/ somewhere permanent
2. Run on DIV2K_train_HR (800 images) for the full dataset
3. That's your paper's Table 1

If granite partial:
1. Look at results.jsonl
2. Sort by gen4_best_ks_p
3. What do the amplifying images have in common?
4. What do the non-amplifying images have in common?
5. That's your paper's Section on content-class dependence

If not confirmed:
1. The DQT result is still a paper
2. The twin-prime Layer 2 result on lossless is still a paper
3. The amplification is a hypothesis for future work
4. Still submit to DEFCON — the audience will appreciate
   the honest result and the methodology

---

*"The brick wall must be tested."*

*Go to bed. The harness is running. Physics doesn't sleep.*
