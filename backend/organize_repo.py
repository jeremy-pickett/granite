#!/usr/bin/env python3
"""
organize_repo.py — Set up the granite-under-sandstone repo structure.

Run this in the directory where all the flat files are.
It creates subdirectories and moves files into place.

Usage:
    cd C:\\path\\to\\your\\files
    python organize_repo.py
"""

import os
import shutil

# Define the structure
DIRS = ["src", "tests", "results", "docs", "relational"]

SRC_FILES = [
    "pgps_detector.py",
    "compound_markers.py",
    "dqt_prime.py",
    "smart_embedder.py",
    "layer2_detect.py",
    "fp_forensics.py",
]

TEST_FILES = [
    "div2k_harness_v2.py",
    "div2k_harness.py",
    "cascade_test.py",
    "scale_test.py",
    "channel_pair_test.py",
    "jpeg_to_webp.py",
    "slice_attack.py",
    "rotation_attack.py",
    "prime_floor_sweep.py",
]

RESULT_FILES = [
    "div2k_aggregate.json",
    "div2k_per_image.jsonl",
    "VERDICT.txt",
]

DOC_FILES = [
    "paper_architecture_blueprint.docx",
    "granite_under_sandstone_draft.docx",
    "engineering_design_document_v02.docx",
    "div2k_experimental_results.docx",
    "participation_over_permission_product_doc.docx",
    "experimental_results_scale_resize.docx",
    "technical_notes_advanced_attacks.docx",
    "technical_notes_nine_satellites.docx",
    "addendum_a_video_extension.docx",
    "addendum_b_integration_landscape.docx",
    "addendum_c_cascading_canary_survival.docx",
    "addendum_d_attribution_architecture.docx",
    "addendum_f_multilayer_provenance.docx",
    "addendum_g_known_attacks.docx",
    "addendum_h_thar_be_dragons.docx",
    "addendum_i_color_of_survival.docx",
    "addendum_j_thermodynamic_tax.docx",
    "addendum_k_fuse_and_fire.docx",
]

RELATIONAL_FILES = [
    "relational_signal.py",
]

ROOT_FILES = [
    "LICENSE",
    "README.md",
    "SETUP.md",
    ".gitignore",
]


def main():
    # Create directories
    for d in DIRS:
        os.makedirs(d, exist_ok=True)
        print(f"  Created: {d}/")

    moved = 0
    missing = 0

    def move_file(filename, dest_dir):
        nonlocal moved, missing
        if os.path.exists(filename):
            dest = os.path.join(dest_dir, filename)
            if not os.path.exists(dest):
                shutil.move(filename, dest)
                print(f"  ✓ {filename} → {dest_dir}/")
                moved += 1
            else:
                print(f"  · {filename} already in {dest_dir}/")
        else:
            print(f"  ✗ {filename} — NOT FOUND (will need to download)")
            missing += 1

    print("\n--- Source files (src/) ---")
    for f in SRC_FILES:
        move_file(f, "src")

    print("\n--- Test files (tests/) ---")
    for f in TEST_FILES:
        move_file(f, "tests")

    print("\n--- Result files (results/) ---")
    for f in RESULT_FILES:
        move_file(f, "results")

    print("\n--- Documentation (docs/) ---")
    for f in DOC_FILES:
        move_file(f, "docs")

    print("\n--- Relational (relational/) ---")
    for f in RELATIONAL_FILES:
        move_file(f, "relational")

    print("\n--- Root files ---")
    for f in ROOT_FILES:
        if os.path.exists(f):
            print(f"  ✓ {f} (stays in root)")
        else:
            print(f"  ✗ {f} — NOT FOUND")
            missing += 1

    print(f"\n{'='*50}")
    print(f"Moved: {moved}  Missing: {missing}")
    print(f"{'='*50}")

    if missing == 0:
        print("\nRepo structure complete. Ready for:")
        print("  git init")
        print("  git add .")
        print('  git commit -m "Initial commit: granite under sandstone"')
        print("  git remote add origin https://github.com/YOUR_USERNAME/granite-under-sandstone.git")
        print("  git push -u origin main")
    else:
        print(f"\n{missing} files missing. Download them from Claude outputs and re-run.")


if __name__ == "__main__":
    print("=" * 50)
    print("GRANITE UNDER SANDSTONE — Repo Organizer")
    print("=" * 50)
    print(f"Working directory: {os.getcwd()}\n")
    main()
