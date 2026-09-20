#!/usr/bin/env python3
"""Refuse files that must never enter the public repository.

Used by the pre-commit hook (``--staged``) and by CI (``--all``). Standard library only.

Blocks:
  * anything under private_uncommitted/
  * documents and archives (PDF, zip, sqlite ...): the project publishes links, not files
  * files over 1 MB
  * SPICE model text outside the places where redistribution is known to be allowed
  * saved web pages and images outside web/ and docs/
  * local absolute paths, personal e-mail addresses and API-key shaped strings
  * any regex listed in private_uncommitted/guard_extra_patterns.txt (local only)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 1_000_000

PRIVATE_DIR = "private_uncommitted/"
BLOCKED_SUFFIXES = {
    ".pdf", ".djvu", ".zip", ".tgz", ".gz", ".7z", ".rar", ".sqlite", ".sqlite3", ".db",
    ".xlsx", ".xls", ".msi", ".exe", ".dmg",
}
# Saved web pages and pictures are usually somebody else's: link to them instead.
SAVED_PAGE_SUFFIXES = {".htm", ".html", ".mht", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"}
SAVED_PAGE_ALLOWED_PREFIXES = ("web/", "docs/", "tests/fixtures/")
MODEL_SUFFIXES = {".lib", ".mod", ".cir", ".sub", ".inc", ".spi", ".ckt", ".mdl"}
# SPICE text is allowed only where it is original work or carries an allow-listed licence.
MODEL_ALLOWED_PREFIXES = ("components/", "circuits/", "data/models/files/", "tests/fixtures/")
# gz fixtures are tiny OCR page records used by the tests
SUFFIX_EXCEPTIONS = ("tests/fixtures/",)

# Patterns are assembled from pieces so that this file does not match itself.
# Machine-specific names (user, host, data mount) go in the local pattern file, not here.
CONTENT_PATTERNS = [
    ("local absolute path", re.compile(r"/(?:home|Users)" + r"/[A-Za-z0-9_.-]+/")),
    ("personal e-mail address", re.compile(r"[A-Za-z0-9._%+-]+@" + r"(?:gmail|hotmail|outlook|yahoo)\.")),
    ("API-key shaped string", re.compile(r"\bsk-" + r"[A-Za-z0-9_-]{24,}")),
]


def local_patterns() -> list[tuple[str, re.Pattern]]:
    """Extra private patterns (real names, hostnames ...), one regex per line, kept out of git."""
    f = ROOT / PRIVATE_DIR / "guard_extra_patterns.txt"
    if not f.is_file():
        return []
    lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()]
    return [("private pattern", re.compile(ln, re.I)) for ln in lines if ln and not ln.startswith("#")]


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return [p for p in out.split("\0") if p]


def candidates(mode: str) -> list[str]:
    if mode == "--staged":
        return git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return git("ls-files", "-z")


def check(path: str) -> list[str]:
    problems: list[str] = []
    p = ROOT / path
    suffix = p.suffix.lower()
    if path.startswith(PRIVATE_DIR):
        return [f"{path}: is under {PRIVATE_DIR} (never committed)"]
    if suffix in BLOCKED_SUFFIXES and not path.startswith(SUFFIX_EXCEPTIONS):
        problems.append(f"{path}: {suffix} files are not published; store a URL + sha256 instead")
    if suffix in SAVED_PAGE_SUFFIXES and not path.startswith(SAVED_PAGE_ALLOWED_PREFIXES):
        problems.append(f"{path}: saved pages and images belong in {', '.join(SAVED_PAGE_ALLOWED_PREFIXES)} "
                        "only, and only if they are our own work; otherwise link to the original")
    if suffix in MODEL_SUFFIXES and not path.startswith(MODEL_ALLOWED_PREFIXES):
        problems.append(f"{path}: SPICE model text outside {', '.join(MODEL_ALLOWED_PREFIXES)}")
    if not p.is_file():
        return problems
    size = p.stat().st_size
    if size > MAX_BYTES:
        problems.append(f"{path}: {size / 1e6:.1f} MB is over the {MAX_BYTES // 1_000_000} MB limit")
        return problems
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return problems
    for label, pattern in CONTENT_PATTERNS + local_patterns():
        m = pattern.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{path}:{line}: {label}")
    return problems


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--staged"
    if mode not in ("--staged", "--all"):
        print(__doc__)
        return 2
    problems = [msg for path in candidates(mode) for msg in check(path)]
    for msg in problems:
        print(f"licence-guard: {msg}", file=sys.stderr)
    if problems:
        print(f"licence-guard: {len(problems)} problem(s). See CLAUDE.md > Hard rules.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
