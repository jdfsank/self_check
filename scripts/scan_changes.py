#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_changes.py — Locate recently modified code for the single-round quick check.

Strategy (fallback chain):
  1. git diff (staged + unstaged + untracked) when inside a git repository
  2. Last-modified timestamp window (default 24h, configurable via --hours)

Dependency/build directories are always excluded.

Exit codes:
  0  changes found (JSON printed to stdout)
  1  no changes found
  2  error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Directories never reported as changes.
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "out",
    ".workbuddy", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "target", "vendor", ".next",
    ".nuxt", ".parcel-cache", ".cache", ".idea", ".vscode", ".DS_Store",
    "coverage", "htmlcov", ".eggs", ".selfcheck",
}

EXCLUDE_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".o", ".a", ".class",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".war", ".jar", ".lock", ".min.js", ".min.css",
}


def is_excluded(path: Path) -> bool:
    """True when the path should never be reported as a change."""
    for part in path.parts:
        if part in EXCLUDE_DIRS or part.endswith(".egg-info"):
            return True
    return path.suffix.lower() in EXCLUDE_EXTENSIONS


def run_git(cwd: Path) -> tuple[int, str]:
    """Return (exit_code, combined_output) of a git command."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), "status", "--porcelain"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return proc.returncode, proc.stderr
    return proc.returncode, proc.stdout


def changes_from_git(cwd: Path) -> list[str]:
    """Collect changed files via `git status --porcelain`."""
    code, out = run_git(cwd)
    if code != 0:
        return []
    changed: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        # porcelain format: XY path  (XY may contain renames: X -> Y)
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ")[-1].strip()
        entry = entry.strip('"')
        if not entry or entry == ".":
            continue
        changed.append(entry)
    return changed


def is_git_repo(cwd: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def changes_from_mtime(cwd: Path, hours: float) -> list[str]:
    """Collect files modified within the last `hours` hours."""
    cutoff = time.time() - hours * 3600
    found: list[str] = []
    for root, dirs, files in os.walk(cwd):
        # prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in files:
            p = Path(root) / name
            if is_excluded(p):
                continue
            try:
                if p.stat().st_mtime >= cutoff:
                    found.append(str(p.relative_to(cwd)))
            except OSError:
                continue
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Locate changed files for single-round quick check.")
    parser.add_argument("path", nargs="?", default=".",
                        help="Project root (default: current directory)")
    parser.add_argument("--hours", type=float, default=24.0,
                        help="mtime window in hours when no git repo (default 24)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    cwd = Path(args.path).resolve()
    if not cwd.is_dir():
        print(f"error: not a directory: {cwd}", file=sys.stderr)
        return 2

    source = "git"
    changes = changes_from_git(cwd)
    if not changes:
        # No git repo or no git changes — fall back to mtime window.
        if not is_git_repo(cwd):
            source = "mtime"
        elif changes == [] and run_git(cwd)[0] == 0:
            # git repo clean — still useful to report nothing from git;
            # fall back to mtime to catch files the user touched outside git.
            source = "mtime"
        changes = changes_from_mtime(cwd, args.hours) if source == "mtime" else changes

    # Filter to paths that exist and are not excluded.
    final = []
    for rel in changes:
        p = cwd / rel
        if not p.exists():
            continue
        if is_excluded(p):
            continue
        final.append(rel)
    final = sorted(set(final))

    if args.json:
        print(json.dumps({"source": source, "files": final},
                         ensure_ascii=True, indent=2))
    else:
        print(f"# source: {source} ({len(final)} files)")
        for rel in final:
            print(rel)
    return 0 if final else 1


if __name__ == "__main__":
    sys.exit(main())
