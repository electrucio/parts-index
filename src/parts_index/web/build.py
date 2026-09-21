"""Build the website's data from `data/`, and from nothing else.

    pidx web build

This is the architectural contract of the project: everything the site shows is committed, so anyone who
clones the repository can rebuild it — no corpus, no GPU, no credentials. `tests/web/test_build.py` proves
it by making the private data root raise and running this anyway.

What it emits grows as the exports land. Today: the source registries with their processing coverage,
which is the "what has been indexed" page. The part index, model recipes and datasheets follow.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from parts_index import status
from parts_index.core.config import PUBLIC_DATA, web_data

SCHEMA = 1


def write_json(out: Path, name: str, payload) -> int:
    """Write one file atomically, compact. Returns its size in bytes."""
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    fd, tmp = tempfile.mkstemp(dir=out, prefix=name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, target)
    return target.stat().st_size


def sources_payload() -> dict:
    """Both registries with their coverage, straight from the committed ledgers."""
    return {
        "schematics": [
            {k: r[k] for k in ("source", "kind", "status", "items", "download", "ocr", "index",
                               "linkcheck", "skipped", "last", "next")}
            for r in status.schematics_rows()
        ],
        "models": [
            {k: r[k] for k in ("source", "status", "fetch", "files", "indexed", "defs",
                               "unavailable", "not_tried", "licence", "last", "next")}
            for r in status.model_rows()
        ],
    }


def totals(payload: dict) -> dict:
    s, m = payload["schematics"], payload["models"]
    return {
        "sources": len(s),
        "items": sum(r["items"] for r in s),
        "indexed": sum(r["index"] for r in s),
        "ocr": sum(r["ocr"] for r in s),
        "modelSources": len(m),
        "modelFiles": sum(r["files"] for r in m),
        "definitions": sum(r["defs"] for r in m),
    }


def build(out: Path | None = None) -> dict:
    """Write every data file the site needs. Returns the manifest."""
    out = Path(out) if out else web_data()
    payload = sources_payload()
    sizes = {"sources.json": write_json(out, "sources.json", payload)}

    # Each of these lands with its exporter; the site renders what is present and says what is not.
    parts_csv = PUBLIC_DATA / "schematics" / "parts.csv"
    manifest = {
        "schema": SCHEMA,
        "built": date.today().isoformat(),
        "totals": totals(payload),
        "have": {
            "sources": True,
            "index": parts_csv.exists(),
            "models": (PUBLIC_DATA / "models" / "parts").is_dir(),
            "datasheets": (PUBLIC_DATA / "datasheets" / "datasheets.csv").exists(),
        },
        "sizes": sizes,
    }
    write_json(out, "manifest.json", manifest)
    return manifest
