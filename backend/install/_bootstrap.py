"""
_bootstrap.py — GRANITE path resolver
======================================
Call bootstrap() at the top of any GRANITE script to ensure all local
modules are importable regardless of the working directory.

Usage (first two executable lines of every script):
    from _bootstrap import bootstrap; bootstrap(__file__)
    # ... all other imports follow

What it does:
1. Resolves the absolute path of the calling script's directory.
2. Walks UP from that directory looking for the project root
   (identified by the presence of a src/ subdirectory or a
   .granite_root marker file).
3. Adds src/ to sys.path if not already present.
4. Optionally adds the project root itself (for top-level scripts).

Project layout assumed:
    GRANITE/
        .granite_root          ← marker file (touch this once)
        src/
            _bootstrap.py      ← this file
            pgps_detector.py
            compound_markers.py
            spanning_sentinel.py
            spanning_payload.py
            detection_harness.py
            image_profiler.py
            ...
        harness_results/
        attacks/
        ...

If the marker file is absent, the root is inferred as the parent of src/.
"""

import os
import sys


def _find_project_root(start_dir, max_levels=6):
    """
    Walk upward from start_dir looking for:
      1. A .granite_root marker file
      2. A directory named 'src' (use its parent as root)
    Returns the project root path, or None if not found.
    """
    current = os.path.abspath(start_dir)
    for _ in range(max_levels):
        # Explicit marker wins
        if os.path.isfile(os.path.join(current, ".granite_root")):
            return current
        # Infer: if this dir has a src/ child that contains _bootstrap.py
        candidate_src = os.path.join(current, "src")
        if (os.path.isdir(candidate_src) and
                os.path.isfile(os.path.join(candidate_src, "_bootstrap.py"))):
            return current
        parent = os.path.dirname(current)
        if parent == current:   # filesystem root
            break
        current = parent
    return None


def bootstrap(calling_file, verbose=False):
    """
    Resolve and inject the src/ directory into sys.path.

    Args:
        calling_file:  pass __file__ from the script calling bootstrap()
        verbose:       if True, print resolved paths to stderr

    Side effects:
        Inserts project src/ at the front of sys.path if not already present.
        No-op if already bootstrapped (idempotent).

    Returns:
        Absolute path of the project root (str), or None if not resolved.
    """
    script_dir = os.path.dirname(os.path.abspath(calling_file))

    # Case 1: this script IS in src/ — walk up one level to find root
    # Case 2: this script is at root level — look for src/ sibling
    root = _find_project_root(script_dir)

    if root is None:
        # Graceful fallback: add script's own directory, emit warning
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        if verbose:
            print(f"[bootstrap] WARNING: could not find project root from {script_dir}",
                  file=sys.stderr)
            print(f"[bootstrap] Falling back to script directory: {script_dir}",
                  file=sys.stderr)
        return None

    src_dir = os.path.join(root, "src")

    # Always inject src/ — that's where our modules live
    for path in [src_dir, root]:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    if verbose:
        print(f"[bootstrap] root: {root}", file=sys.stderr)
        print(f"[bootstrap] src:  {src_dir}", file=sys.stderr)
        print(f"[bootstrap] sys.path[0:2]: {sys.path[:2]}", file=sys.stderr)

    return root


def src_path(*parts):
    """
    Return an absolute path relative to the project src/ directory.
    Useful for loading data files that live next to the source.

    Example:
        config = src_path("config", "embed_profiles.json")
    """
    # Find src/ by walking from this file's location
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, *parts)


def project_path(*parts):
    """
    Return an absolute path relative to the project root.

    Example:
        results = project_path("harness_results", "harness_aggregate.json")
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = _find_project_root(here) or os.path.dirname(here)
    return os.path.join(root, *parts)
