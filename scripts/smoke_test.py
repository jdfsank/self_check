#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test.py — Detect and run the project's smoke tests.

Runs ALL matching test entry points (not just the first found), so mixed
projects (e.g. Python + Node) are fully covered. When no test framework
exists, falls back to read-only syntax checks (AST parse / node --check).

Read-only guarantees:
  - never installs dependencies
  - never writes source files
  - pytest runs with `-p no:cacheprovider` (no .pytest_cache)
  - syntax fallback uses ast.parse (no __pycache__)

Exit codes:
  0  all checks passed
  1  at least one check failed
  2  nothing to run (smoke skipped)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT = 300  # seconds per check

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "out",
    ".workbuddy", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "target", "vendor", ".next",
    ".nuxt", ".parcel-cache", ".cache", ".idea", ".vscode", ".eggs",
    "coverage", "htmlcov", ".selfcheck",
}

PYTEST_MARKERS = ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"]
# Match unittest discover's default pattern (`test*.py`). Deliberately NOT
# matching `*_test.py` — that would misclassify tool scripts such as
# `smoke_test.py` itself as test files and trigger a failing unittest run.
TEST_FILE_RE = re.compile(r"^test.*\.py$", re.IGNORECASE)


def walk_files(root: Path, exts: set[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                files.append(p)
    return sorted(files)


def run(cmd: list[str], cwd: Path, timeout: int, env_extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["CI"] = "1"
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        exit_code, timed_out = proc.returncode, False
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code, timed_out = -1, True
        output = (exc.stdout or b"").decode(errors="replace") if isinstance(
            exc.stdout, bytes) else str(exc.stdout or "")
        output += f"\n[timed out after {timeout}s]"
    except FileNotFoundError:
        exit_code, timed_out = 127, False
        output = f"command not found: {cmd[0]}"
    return {
        "exit": exit_code,
        "timed_out": timed_out,
        "output_tail": output[-4000:],
    }


def check_has_pytest(root: Path) -> bool:
    for marker in PYTEST_MARKERS:
        p = root / marker
        if p.exists():
            text = p.read_text(errors="ignore")
            if marker == "pyproject.toml" and "[tool.pytest" not in text:
                continue
            if marker == "setup.cfg" and (
                    "[tool:pytest]" not in text and "[pytest]" not in text):
                continue
            return True
    return False


def has_unittest_tests(root: Path, py_files: list[Path] | None = None) -> bool:
    if py_files is None:
        py_files = walk_files(root, {".py"})
    return any(TEST_FILE_RE.match(f.name) for f in py_files)


def ast_syntax_check(root: Path, timeout: int) -> dict:
    """Read-only syntax check of every .py file via ast.parse."""
    py_files = walk_files(root, {".py"})
    if not py_files:
        return {"skipped": True, "reason": "no .py files"}
    script = (
        "import ast, sys\n"
        "bad = 0\n"
        "for f in sys.argv[1:]:\n"
        "    try:\n"
        "        ast.parse(open(f, encoding='utf-8').read(), f)\n"
        "    except Exception as e:\n"
        "        print(f'{f}: {e}', flush=True)\n"
        "        bad += 1\n"
        "sys.exit(1 if bad else 0)\n"
    )
    if len(py_files) > 400:
        # chunk to avoid argv length limits
        chunks = [py_files[i:i + 400] for i in range(0, len(py_files), 400)]
        overall = {"exit": 0, "timed_out": False, "output_tail": ""}
        for chunk in chunks:
            r = run([sys.executable, "-c", script, *[str(f) for f in chunk]],
                    root, timeout)
            overall["exit"] = overall["exit"] or r["exit"]
            overall["output_tail"] += r["output_tail"]
        overall["output_tail"] = overall["output_tail"][-4000:]
        overall["skipped"] = False
        return overall
    return run([sys.executable, "-c", script, *[str(f) for f in py_files]],
               root, timeout)


def node_syntax_check(root: Path, timeout: int) -> dict:
    js_files = walk_files(root, {".js", ".mjs", ".cjs"})
    if not js_files:
        return {"skipped": True, "reason": "no .js/.mjs/.cjs files"}
    node = shutil.which("node")
    if not node:
        return {"skipped": True, "reason": "node not installed"}
    overall = {"exit": 0, "timed_out": False, "output_tail": ""}
    for f in js_files:
        r = run([node, "--check", str(f)], root, timeout)
        if r["exit"] != 0:
            overall["exit"] = 1
            overall["output_tail"] += f"{f}: {r['output_tail'][-500:]}\n"
    overall["output_tail"] = overall["output_tail"][-4000:]
    overall["skipped"] = False
    return overall


def gofmt_check(root: Path, timeout: int) -> dict:
    go_files = walk_files(root, {".go"})
    if not go_files:
        return {"skipped": True, "reason": "no .go files"}
    go = shutil.which("gofmt")
    if not go:
        return {"skipped": True, "reason": "gofmt not installed"}
    r = run([go, "-l", str(root)], root, timeout)
    if r["exit"] == 0 and not r["output_tail"].strip():
        r["skipped"] = False
        r["output_tail"] = "gofmt: all files formatted"
        return r
    r["skipped"] = False
    r["exit"] = 1 if r["output_tail"].strip() else r["exit"]
    return r


def makefile_has_test_target(root: Path) -> bool:
    mf = root / "Makefile"
    if not mf.exists():
        return False
    for line in mf.read_text(errors="ignore").splitlines():
        if re.match(r"^test\s*:", line.strip()):
            return True
    return False


def collect_checks(root: Path, timeout: int, allow_fallback: bool) -> list[dict]:
    checks: list[dict] = []
    has_any_file = False
    # Walk each file type once, reuse across branches (perf: avoid N walks).
    py_files = walk_files(root, {".py"})
    js_files = walk_files(root, {".js", ".mjs", ".cjs"})
    go_files = walk_files(root, {".go"})

    # ---- Python ----
    if py_files or any((root / m).exists() for m in PYTEST_MARKERS):
        has_any_file = True
        pytest_bin = shutil.which("pytest")
        if check_has_pytest(root) and pytest_bin:
            checks.append({
                "kind": "pytest",
                "command": f"pytest -q --maxfail=3 -p no:cacheprovider (CI=1)",
                **run([pytest_bin, "-q", "--maxfail=3", "-p", "no:cacheprovider"],
                      root, timeout),
            })
        elif has_unittest_tests(root, py_files):
            checks.append({
                "kind": "unittest",
                "command": f"{sys.executable} -m unittest discover -q (CI=1)",
                **run([sys.executable, "-m", "unittest", "discover", "-q"],
                      root, timeout),
            })
        elif allow_fallback and py_files:
            checks.append({
                "kind": "python-syntax",
                "command": "ast.parse on all .py files (read-only)",
                **ast_syntax_check(root, timeout),
            })

    # ---- Node ----
    pkg_json = root / "package.json"
    if pkg_json.exists() or js_files:
        has_any_file = True
        if pkg_json.exists():
            try:
                scripts = json.loads(
                    pkg_json.read_text(errors="ignore")).get("scripts", {})
            except Exception:
                scripts = {}
        else:
            scripts = {}
        if scripts.get("test") and shutil.which("npm"):
            checks.append({
                "kind": "npm-test",
                "command": "npm test (CI=1, timeout-limited)",
                **run(["npm", "test", "--no-update-notifier"], root, timeout),
            })
        elif allow_fallback and js_files:
            checks.append({
                "kind": "node-syntax",
                "command": "node --check on all .js/.mjs/.cjs files (read-only)",
                **node_syntax_check(root, timeout),
            })

    # ---- Go ----
    if (root / "go.mod").exists():
        has_any_file = True
        if shutil.which("go"):
            checks.append({
                "kind": "go-test",
                "command": "go test ./... (CI=1, timeout-limited)",
                **run(["go", "test", "./..."], root, timeout),
            })
    elif allow_fallback and go_files:
        has_any_file = True
        checks.append({
            "kind": "gofmt",
            "command": "gofmt -l (read-only)",
            **gofmt_check(root, timeout),
        })

    # ---- Rust ----
    if (root / "Cargo.toml").exists():
        has_any_file = True
        if shutil.which("cargo"):
            checks.append({
                "kind": "cargo-test",
                "command": "cargo test (CI=1, timeout-limited)",
                **run(["cargo", "test", "--quiet"], root, timeout),
            })

    # ---- Make ----
    if makefile_has_test_target(root):
        has_any_file = True
        if shutil.which("make"):
            checks.append({
                "kind": "make-test",
                "command": "make test (CI=1, timeout-limited)",
                **run(["make", "test"], root, timeout),
            })

    return checks, has_any_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test runner (read-only).")
    parser.add_argument("path", nargs="?", default=".",
                        help="Project root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"per-check timeout seconds (default {DEFAULT_TIMEOUT})")
    parser.add_argument("--no-fallback", action="store_true",
                        help="skip syntax-check fallbacks "
                             "(only run real test frameworks)")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2

    checks, has_any_file = collect_checks(root, args.timeout, not args.no_fallback)

    if not checks:
        result = {
            "root": str(root),
            "checks": [],
            "overall": "skip",
            "reason": "no test entry points found"
                       + ("" if has_any_file else " and no source files"),
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print(f"smoke: skipped ({result['reason']})")
        return 2

    failed = [c for c in checks if c.get("exit", 0) != 0]
    overall = "fail" if failed else "pass"
    result = {
        "root": str(root),
        "checks": [
            {"kind": c["kind"], "command": c["command"],
             "passed": c.get("exit", 0) == 0,
             "timed_out": c.get("timed_out", False),
             "output_tail": c.get("output_tail", "")}
            for c in checks
        ],
        "overall": overall,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        for c in result["checks"]:
            mark = "PASS" if c["passed"] else "FAIL"
            note = " (timed out)" if c.get("timed_out") else ""
            print(f"[{mark}]{note} {c['kind']}: {c['command']}")
            if not c["passed"] and c.get("output_tail"):
                print(c["output_tail"][-1200:])
        print(f"smoke: overall {overall}")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
