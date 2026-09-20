"""What has been processed and what comes next, per source. Generates STATUS.md from the registry and ledgers.

Reads only committed files (data/schematics/sources.yaml, data/schematics/state/*.csv), so anyone can run it.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from parts_index.core.config import PUBLIC_DATA, REPO_ROOT
from parts_index.core.ledger import Ledger, today

SCHEMATICS = PUBLIC_DATA / "schematics"
MODELS = PUBLIC_DATA / "models"
STAGE_VERB = {"download": "download", "ocr": "OCR", "index": "index", "linkcheck": "link-check"}


def last_activity(led: Ledger) -> str:
    return max((r[f"{s}_at"] for r in led.rows.values() for s in led.stages if r[f"{s}_at"]), default="")


def next_action(entry: dict, led: Ledger | None) -> str:
    if entry["status"] in ("excluded", "blocked"):
        return f"{entry['status']}: {entry.get('blocked_reason', '')}".rstrip(": ")
    if entry["status"] in ("proposed", "paused"):
        return entry["status"]
    if led is None or not len(led):
        return "crawl"
    for stage in led.stages:
        n = len(led.pending(stage))
        if n:
            return f"{STAGE_VERB[stage]} {n}"
    return "up to date"


def schematics_rows() -> list[dict]:
    registry = yaml.safe_load((SCHEMATICS / "sources.yaml").read_text(encoding="utf-8")) or {}
    rows = []
    for source, entry in registry.items():
        f = SCHEMATICS / "state" / f"{source}.csv"
        led = Ledger(f) if f.exists() else None
        s = led.summary() if led else {}
        rows.append(dict(source=source, kind=entry["kind"], status=entry["status"], last=last_activity(led) if led else "",
                         next=next_action(entry, led), **{k: s.get(k, 0) for k in ("items", "download", "ocr", "index", "linkcheck", "skipped")}))
    return rows


def model_rows() -> list[dict]:
    from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED
    rows = []
    for reg in sorted((MODELS / "sources").glob("*.yaml")):
        entry = yaml.safe_load(reg.read_text(encoding="utf-8"))
        f = MODELS / "state" / f"{reg.stem}.csv"
        led = Ledger(f, stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED) if f.exists() else None
        rs = list(led.rows.values()) if led else []
        files = [r for r in rs if not r["key"].startswith("part:") and r["status"] == "downloaded"]
        lookups = [r for r in rs if r["key"].startswith("part:")]
        not_tried = sum(1 for r in lookups if r["status"] == "not_tried")
        to_index = sum(1 for r in files if not r["index_at"])
        if entry["status"] in ("link_only", "pending_manual"):
            nxt = "manual: link only" if entry["status"] == "link_only" else "manual download"
        elif entry.get("note"):
            nxt = "write manifest"
        elif not_tried:
            nxt = f"fetch {not_tried} parts"
        else:
            nxt = "up to date"
        rows.append(dict(source=reg.stem, status=entry["status"], fetch=entry.get("fetch", ""), files=len(files),
                         indexed=len(files) - to_index, defs=sum(int(r["n_defs"] or 0) for r in files),
                         unavailable=sum(1 for r in lookups if r["skip_reason"]), not_tried=not_tried,
                         licence=entry.get("licence", ""), last=last_activity(led) if led else "", next=nxt))
    return rows


def render_models() -> list[str]:
    rows = model_rows()
    if not rows:
        return []
    tot = {k: sum(r[k] for r in rows) for k in ("files", "indexed", "defs", "unavailable", "not_tried")}
    out = [
        "## SPICE model sources",
        "",
        f"{len(rows)} sources · {tot['files']:,} files downloaded · {tot['indexed']:,} with indexed definitions "
        f"({tot['defs']:,} definitions) · part look-ups: {tot['unavailable']:,} not available, {tot['not_tried']:,} not tried yet",
        "",
        "Registry: `data/models/sources/<id>.yaml`. Ledgers: `data/models/state/<id>.csv`, one row per downloaded file",
        "(URL + sha256) and one per part looked up at that vendor. A file without indexed definitions is usually a",
        "symbol, a document or a binary format. Model files themselves are not in this repository unless the source",
        "is marked `redistributable: true`.",
        "",
        "| Source | Status | Fetch | Files | Indexed | Definitions | Parts not available | Parts not tried | Licence | Last activity | Next |",
        "|---|---|---|--:|--:|--:|--:|--:|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (-r["files"], r["source"])):
        out.append(f"| {r['source']} | {r['status']} | {r['fetch']} | {r['files']:,} | {r['indexed']:,} | {r['defs']:,} | "
                   f"{r['unavailable']:,} | {r['not_tried']:,} | {r['licence']} | {r['last']} | {r['next']} |")
    return out + [""]


def render() -> str:
    rows = schematics_rows()
    total = {k: sum(r[k] for r in rows) for k in ("items", "download", "ocr", "index", "linkcheck", "skipped")}
    out = [
        "# Processing status",
        "",
        f"Generated by `pidx status --write` on {today()} from the registries and ledgers under `data/`. Do not edit by hand.",
        "",
        "Each item (a page, figure, PDF, magazine issue or book) moves through download → OCR → index → link-check.",
        "A stage is never repeated for an item unless its input or the stage version changes; see",
        "`src/parts_index/core/ledger.py`. **To add a site:** add it to `sources.yaml` with `status: proposed`.",
        "",
        "## Schematic and reference sources",
        "",
        f"{len(rows)} sources · {total['items']:,} items · {total['download']:,} downloaded · {total['ocr']:,} OCR'd · "
        f"{total['index']:,} indexed · {total['linkcheck']:,} link-checked · {total['skipped']:,} skipped",
        "",
        "| Source | Kind | Status | Items | Downloaded | OCR'd | Indexed | Link-checked | Skipped | Last activity | Next |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|---|---|",
    ]
    order = {"active": 0, "proposed": 1, "paused": 2, "blocked": 3, "excluded": 4}
    for r in sorted(rows, key=lambda r: (order.get(r["status"], 9), r["kind"], r["source"])):
        out.append(f"| {r['source']} | {r['kind']} | {r['status']} | {r['items']:,} | {r['download']:,} | {r['ocr']:,} | "
                   f"{r['index']:,} | {r['linkcheck']:,} | {r['skipped']:,} | {r['last']} | {r['next']} |")
    out += ["", "OCR'd counts only items that need OCR (scans and images); HTML pages and born-digital PDFs skip that stage.", ""]
    out += render_models()
    return "\n".join(out)


def write(path: Path = REPO_ROOT / "STATUS.md") -> Path:
    path.write_text(render(), encoding="utf-8")
    return path
