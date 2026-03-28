# GRANITE — Project Layout

## Directory Structure

```
C:\GRANITE\                    ← project root
    .granite_root              ← marker file (empty, just needs to exist)
    src\
        _bootstrap.py          ← path resolver (run this once, forget it)
        pgps_detector.py
        compound_markers.py
        smart_embedder.py
        smart_blind_detector.py
        spanning_sentinel.py
        spanning_payload.py
        detection_harness.py
        image_profiler.py
        dqt_prime.py
    attacks\                   ← attack scripts (coming)
        crop_attack.py
        save_for_web.py
        ...
    harness_results\           ← output (git-ignored)
    .gitignore
```

## One-Time Setup

```powershell
# 1. Create the marker file (tells bootstrap where root is)
New-Item C:\GRANITE\.granite_root -ItemType File

# 2. Create src/ directory
New-Item C:\GRANITE\src -ItemType Directory

# 3. Move all .py files into src\
Move-Item C:\GRANITE\*.py C:\GRANITE\src\
```

## Running Scripts

After setup, run from anywhere — bootstrap finds src/ automatically:

```powershell
# From project root
python src\detection_harness.py -i C:\DIV2K_train_HR\ -o harness_results -n 50 --creator-id 42 --no-cascade -C C:\DIV2K_train_HR\

# From src\ directory  
cd C:\GRANITE\src
python detection_harness.py -i C:\DIV2K_train_HR\ -o ..\harness_results -n 50 --creator-id 42 --no-cascade -C C:\DIV2K_train_HR\

# From anywhere else
python C:\GRANITE\src\detection_harness.py -i C:\DIV2K_train_HR\ ...
```

All three work. Bootstrap resolves the rest.

## How Bootstrap Works

Each script starts with:
```python
try:
    from _bootstrap import bootstrap
    bootstrap(__file__)
except ImportError:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

`bootstrap(__file__)` walks upward from the script's own location looking
for `.granite_root` or a `src/` directory containing `_bootstrap.py`.
When found, it inserts `src/` at the front of `sys.path`.

The `except ImportError` fallback handles the case where `_bootstrap.py`
itself hasn't been found yet — it just adds the script's own directory,
which is correct for the flat-file layout in C:\GRANITE\ during transition.

## Transition Plan

If you're currently running scripts from C:\GRANITE\ with all files flat:
- They still work (the fallback catches the ImportError)
- When you move files to src\, they work better (bootstrap finds root)
- No script changes required after the move

## .gitignore

```
harness_results/
*.jsonl
*.log
__pycache__/
*.pyc
.env
```
