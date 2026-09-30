#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emoji_scan.py — Detect (and optionally remove) emoji in a project.

Detection rules (Unicode-safe, stdlib only):
  - U+1F000–U+1FAFF  : main emoji blocks (symbols, pictographs, flags, extended)
  - U+FE0F           : variation selector — reported together with its leading
                       character (makes text-presentation glyphs render as emoji)
  - U+200D           : ZWJ sequence — the whole joined emoji cluster is reported
  - U+2600–U+27BF    : misc symbols — reported, EXCEPT a small whitelist of
                       common text glyphs (box U+2610, star U+2605, check
                       U+2713, etc.) that are not emoji — those stay untouched

Default behavior: report only (`文件:行:列:片段`). Pass --fix to remove all
detected emoji clusters (replace with empty string) and rescan.

Exit codes:
  0  no emoji found (after --fix: none remaining)
  1  emoji found
  2  error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "out",
    ".workbuddy", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "target", "vendor", ".next",
    ".nuxt", ".parcel-cache", ".cache", ".idea", ".vscode", ".eggs",
    "coverage", "htmlcov", ".selfcheck", ".DS_Store",
}

# Common text-presentation glyphs inside U+2600–U+27BF that are NOT emoji.
TEXT_SYMBOLS = {
    "\u2605", "\u2606",  # ★ ☆
    "\u2610", "\u2611", "\u2612",  # ☐ ☑ ☒
    "\u266a", "\u266b",  # ♪ ♫
    "\u2713", "\u2717", "\u2718",  # ✓ ✗ ✘
}

MAX_LINE_LEN = 400  # skip absurdly long lines (minified files)
MAX_FILE_BYTES = 5 * 1024 * 1024  # skip oversized files (memory guard)


def is_emoji_cp(cp: int) -> bool:
    """True when a single code point is emoji-presentation (or in emoji blocks)."""
    if 0x1F000 <= cp <= 0x1FAFF:
        return True
    if 0x2600 <= cp <= 0x27BF and chr(cp) not in TEXT_SYMBOLS:
        return True
    return False


def find_emoji_clusters(text: str) -> list[tuple[int, int]]:
    """Return [(start, end)] spans of emoji clusters in `text` (code point offsets)."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        cp = ord(text[i])

        if is_emoji_cp(cp):
            start = i
            j = i + 1
            suppressed = False
            # Consume variation selectors, ZWJ chains, skin tones, keycaps,
            # regional indicators (flag pairs), ©®™ℹ
            while j < n:
                cj = ord(text[j])
                if cj == 0xFE0E and 0x2600 <= cp <= 0x27BF:
                    # explicit text presentation (e.g. ⚠︎) — not emoji
                    suppressed = True
                    break
                if cj in (0xFE0F, 0xFE0E):            # variation selectors
                    j += 1
                    continue
                if cj == 0x200D:                      # ZWJ — include next emoji
                    j += 1
                    if j < n and is_emoji_cp(ord(text[j])):
                        j += 1                        # consume the joined emoji
                        continue
                    break
                if 0x1F3FB <= cj <= 0x1F3FF:          # skin tone modifiers
                    j += 1
                    continue
                if 0x1F1E6 <= cj <= 0x1F1FF:          # regional indicators
                    j += 1
                    continue
                if cj == 0x20E3:                      # keycap combining
                    j += 1
                    continue
                if cj in (0x00A9, 0x00AE, 0x2122, 0x2139):  # © ® ™ ℹ
                    # emoji only when followed by FE0F
                    if j + 1 < n and ord(text[j + 1]) == 0xFE0F:
                        j += 2
                        continue
                    break
                break
            if not suppressed:
                spans.append((start, j))
            i = j if not suppressed else start + 1
            continue

        # Variation selector alone (emoji indicator) — report with leading char
        if cp == 0xFE0F:
            s = start = i - 1 if i > 0 else i
            e = i + 1
            if i + 1 < n and ord(text[i + 1]) == 0x20E3:  # keycap base
                e = i + 2
            spans.append((s, e))
            i = e
            continue

        i += 1
    return spans


def iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                print(f"emoji-skip: oversized file (> {MAX_FILE_BYTES} bytes): "
                      f"{p}", file=sys.stderr)
                continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if b"\x00" in data[:8192]:
                continue  # binary
            try:
                yield p, data.decode("utf-8")
            except UnicodeDecodeError:
                continue  # non-utf8 / binary


def scan_file(path: Path, text: str, fix: bool) -> tuple[list[dict], str, bool]:
    """Return (matches, new_text, changed). With fix=True, emoji are removed."""
    lines = text.splitlines(keepends=True)
    matches: list[dict] = []
    out_lines: list[str] = []
    changed = False
    for lineno, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE_LEN:
            out_lines.append(line)
            continue
        spans = find_emoji_clusters(line)
        for (s, e) in spans:
            matches.append({
                "file": str(path),
                "line": lineno,
                "column": s + 1,
                "fragment": line[s:e],
            })
        if spans and fix:
            new_line = line
            for (s, e) in reversed(spans):
                new_line = new_line[:s] + new_line[e:]
            out_lines.append(new_line)
            changed = True
        else:
            out_lines.append(line)
    return matches, "".join(out_lines), changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emoji scanner (read-only by default).")
    parser.add_argument("path", nargs="?", default=".",
                        help="Project root (default: current directory)")
    parser.add_argument("--fix", action="store_true",
                        help="REMOVE all detected emoji "
                             "(rewrites files; explicit opt-in)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    all_matches: list[dict] = []
    rewritten: list[str] = []
    for p, text in iter_text_files(root):
        matches, new_text, changed = scan_file(p, text, args.fix)
        all_matches.extend(matches)
        if changed:
            try:
                p.write_text(new_text, encoding="utf-8")
                rewritten.append(str(p))
            except OSError as e:
                print(f"error: cannot write {p}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps({
            "root": str(root),
            "count": len(all_matches),
            "fix": args.fix,
            "rewritten": rewritten,
            "matches": all_matches[:500],  # cap payload
            "truncated": len(all_matches) > 500,
        }, ensure_ascii=True, indent=2))
    else:
        if all_matches:
            print(f"emoji: {len(all_matches)} found"
                  + (" (removed)" if args.fix else ""))
            for m in all_matches[:100]:
                frag = m["fragment"].replace("\n", "\\n")
                print(f"  {m['file']}:{m['line']}:{m['column']}: {frag!r}")
            if len(all_matches) > 100:
                print(f"  ... and {len(all_matches) - 100} more")
        else:
            print("emoji: none found"
                  + (" (project is emoji-clean)" if args.fix else ""))
        if rewritten:
            print(f"rewritten: {len(rewritten)} file(s)")
    return 1 if all_matches else 0


if __name__ == "__main__":
    sys.exit(main())
