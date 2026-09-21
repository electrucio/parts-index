#!/usr/bin/env python3
"""Refuse files that must never enter the public repository.

Used by the pre-commit hook (``--staged``) and by CI (``--all``). Standard library only.

Blocks:
  * anything under the private trees
  * documents and archives (PDF, zip, sqlite ...): the project publishes links, not files
  * files over 1 MB
  * SPICE model text outside the places where redistribution is known to be allowed
  * saved web pages and images outside web/ and docs/
  * local absolute paths, personal e-mail addresses and API-key shaped strings
  * any regex listed in private_material/guard_extra_patterns.txt (local only)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 1_000_000
MAX_BYTES_DATA = 5_000_000          # ledgers and exports under data/ are plain CSV and may be larger

PRIVATE_DIRS = ("private_web_spice_models/", "private_material/")
BLOCKED_SUFFIXES = {
    ".pdf", ".djvu", ".zip", ".tgz", ".gz", ".7z", ".rar", ".sqlite", ".sqlite3", ".db",
    ".xlsx", ".xls", ".msi", ".exe", ".dmg",
}
# Saved web pages and pictures are usually somebody else's: link to them instead.
SAVED_PAGE_SUFFIXES = {".htm", ".html", ".mht", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"}
SAVED_PAGE_ALLOWED_PREFIXES = ("web/", "docs/", "tests/fixtures/")
MODEL_SUFFIXES = {".lib", ".mod", ".cir", ".sub", ".inc", ".spi", ".ckt", ".mdl"}
# A suffix list only catches the file names we thought of. A patch against a model file carries the
# vendor's surrounding lines and has none of these suffixes, so the text itself is looked for too.
MODEL_TEXT = re.compile(r"^[-+ ]?\s*\.(?:model|subckt)\s+\S", re.I | re.M)
# SPICE text is allowed only where it is original work or carries an allow-listed licence. Everything
# under tests/ is written for the test suite — a plausible-looking .MODEL line there is invented, not a
# vendor's — so the whole directory is allowed rather than only its fixtures.
MODEL_ALLOWED_PREFIXES = ("components/", "circuits/", "data/models/files/", "tests/")
# gz fixtures are tiny OCR page records used by the tests
SUFFIX_EXCEPTIONS = ("tests/fixtures/",)

# Patterns are assembled from pieces so that this file does not match itself.
# Machine-specific names (user, host, data mount) go in the local pattern file, not here.
CONTENT_PATTERNS = [
    ("local absolute path", re.compile(r"/(?:home|Users)" + r"/[A-Za-z0-9_.-]+/")),
    ("personal e-mail address", re.compile(r"[A-Za-z0-9._%+-]+@" + r"(?:gmail|hotmail|outlook|yahoo)\.")),
    ("API-key shaped string", re.compile(r"\bsk-" + r"[A-Za-z0-9_-]{24,}")),
]


# Public URLs are third-party facts, not our paths or names: they are blanked before the content checks.
PUBLIC_URL = re.compile(r"https?://[^\s,\"'<>]+")


def local_patterns() -> list[tuple[str, re.Pattern]]:
    """Extra private patterns (real names, hostnames ...), one regex per line, kept out of git."""
    f = ROOT / "private_material" / "guard_extra_patterns.txt"
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
    # Tracked files, and anything new that is not ignored. Leaving the second half out made `--all`
    # blind to exactly the files about to be published for the first time: a generated tree passed
    # `make check` and was refused by the pre-commit hook a moment later.
    return git("ls-files", "-z") + git("ls-files", "-z", "--others", "--exclude-standard")


def check(path: str) -> list[str]:
    problems: list[str] = []
    p = ROOT / path
    suffix = p.suffix.lower()
    if path.startswith(PRIVATE_DIRS):
        return [f"{path}: is under a private tree (never committed)"]
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
    limit = MAX_BYTES_DATA if path.startswith("data/") else MAX_BYTES
    if size > limit:
        problems.append(f"{path}: {size / 1e6:.1f} MB is over the {limit // 1_000_000} MB limit")
        return problems
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return problems
    if not path.startswith(MODEL_ALLOWED_PREFIXES):
        m = MODEL_TEXT.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{path}:{line}: SPICE model text outside "
                            f"{', '.join(MODEL_ALLOWED_PREFIXES)}")
    text = PUBLIC_URL.sub(lambda m: " " * len(m.group()), text)
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
