"""OCR page records on disk: one gzip JSON-lines file per document, one line per page.

    {"page": 1, "w": 3300, "h": 2550, "how": "ocr" | "text", "blocks": [{"box": [x0, y0, x1, y1], "text": "...", "conf": 0.98}]}

`<name>.jsonl.gz` holds the pages; an empty `<name>.done` next to it marks a document that was written completely, so an
interrupted run is detected and redone. Uncompressed `.jsonl` files from early runs are still read.
"""
from __future__ import annotations

import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Iterator


def out_path(folder, name: str) -> Path:
    return Path(folder) / f"{name}.jsonl.gz"


def done_path(folder, name: str) -> Path:
    return Path(folder) / f"{name}.done"


def existing(folder, name: str) -> Path | None:
    """The OCR file of a document (gzip preferred), or None."""
    for suffix in (".jsonl.gz", ".jsonl"):
        p = Path(folder) / f"{name}{suffix}"
        if p.exists():
            return p
    return None


def is_done(folder, name: str) -> bool:
    return done_path(folder, name).exists() and existing(folder, name) is not None


def iter_pages(path) -> Iterator[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_pages(path) -> list[dict]:
    return list(iter_pages(path))


def write_pages(folder, name: str, pages: Iterable[dict]) -> Path:
    """Write atomically, then drop the .done marker."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = out_path(folder, name)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=target.name, suffix=".tmp")
    os.close(fd)
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps(page, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, target)
    done_path(folder, name).touch()
    return target
