"""Assemble the one OCR tree, and the two indexes over it, from the old pipeline's four.

    make migrate

The old pipeline kept its OCR in four places, one per origin: `magazines/ocr/<magazine>/`, `ocr_boxes/
<source>/`, `elektor/ocr/` and `books/ocr/`. Which file held which document was never written down — it was
derived from a database column. This gathers all of it under `ocr/<source>/`, one scheme, and writes:

  `ocr_map.csv`     document -> its file. The tree is self-describing: copy it and the map comes with it.
  `linkchecks.csv`  the links checked by hand. Re-indexing regenerates the advert and schematic judgements,
                    because the classifier is deterministic; it cannot regenerate these.

Some documents never had an OCR file at all: an HTML page and a born-digital PDF have a text layer, so the
old ingester read them straight from the source and kept the text only in the database. Those get ordinary
page records written here too — nothing distinguishes them but `how: "text"` inside the record, which is
where that belongs. Afterwards the database holds the last copy of nothing.

What a written-out record can and cannot carry: an HTML page was always one chunk of text with no geometry,
so it loses nothing — measured, 99.4 % of them re-extract identically. A born-digital article had line
blocks with boxes built from the PDF's text layer, and those were never saved, so its page becomes one
block holding the whole text; 95.5 % re-extract identically, the rest losing a hit that depended on the
line structure. Their already-extracted positions survive in the export.

The old `.done` markers are not carried over: `ocr_map.csv` records what is present, which is the same
question answered once instead of fifty thousand times. Reads the database through an explicit column
allow-list, and writes no local path.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from parts_index.core.config import index_db, index_db_uri, ocr_root, require

MAP_FIELDS = ("source", "doc_key", "text_method", "pages", "ocr_file", "origin")
LINK_FIELDS = ("source", "doc_key", "link_verified", "link_ok", "checked_at")


def legacy_file(source: str, text_method: str | None, ocr_path: str | None, local_path: str | None) -> str | None:
    """Where the old pipeline put this document's OCR, relative to the corpus, or None if it made none.

    Three conventions, all its own: magazines recorded a path relative to `magazines/`, Elektor issues and
    books one relative to the corpus, and anything OCR'd with boxes was found from the name of the file it
    was read from.
    """
    if ocr_path:
        return f"magazines/{ocr_path}" if text_method == "ocr" else ocr_path
    if text_method and text_method.startswith("ocr_boxes") and local_path:
        return f"ocr_boxes/{source}/{Path(local_path).name}.jsonl.gz"
    return None


def canonical(source: str, legacy: str | None, doc_key: str) -> str:
    """Where it lives in the new tree: `<source>/<name>`, keeping the name it already had.

    A document that never had a file is named after a digest of its key, which is a URL; the map resolves
    it back exactly as it resolves every other file.
    """
    if legacy:
        return f"{source}/{Path(legacy).name}"
    return f"{source}/{hashlib.sha1(doc_key.encode()).hexdigest()[:16]}.jsonl.gz"


def page_records(db: sqlite3.Connection, doc_id: int) -> list[dict]:
    """The pages of one document as OCR records: one block per page, holding its whole text."""
    rows = db.execute(
        "select p.page_no, p.w_pt, p.h_pt, t.text from pages p join page_text t on t.page_id = p.page_id "
        "where p.doc_id = ? order by p.page_no", (doc_id,)).fetchall()
    out = []
    for page_no, w_pt, h_pt, text in rows:
        if not (text or "").strip():
            continue
        rec: dict = {"page": page_no, "how": "text",
                     "blocks": [{"box": [0, 0, 0, 0], "text": text, "conf": 1.0}]}
        if w_pt and h_pt:                      # in PDF points, which is what a zoom link needs
            rec["w_pt"], rec["h_pt"] = w_pt, h_pt
        out.append(rec)
    return out


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


def run(db: sqlite3.Connection, out: Path, corpus_root: Path | None = None) -> dict:
    """Build the tree and its indexes. Returns counts, for the caller to report and a test to assert."""
    out.mkdir(parents=True, exist_ok=True)
    counts = {"documents": 0, "copied": 0, "written": 0, "written_pages": 0,
              "no_pages": 0, "collisions": 0, "linkchecks": 0}
    taken: dict[str, str] = {}

    q = ("select d.doc_id, d.source, d.doc_key, d.text_method, d.ocr_path, d.local_path, d.n_pages "
         "from documents d order by d.source, d.doc_key")
    with open(out / "ocr_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAP_FIELDS, lineterminator="\n")
        w.writeheader()
        for doc_id, source, doc_key, method, ocr_path, local_path, n_pages in db.execute(q):
            counts["documents"] += 1
            legacy = legacy_file(source, method, ocr_path, local_path)
            rel = canonical(source, legacy, doc_key)

            if rel in taken and taken[rel] != doc_key:     # two documents claiming one file: keep both
                counts["collisions"] += 1
                rel = canonical(source, None, doc_key)
            target, origin = out / rel, ""

            if target.exists():
                origin = "copied" if legacy else "written"
            elif legacy and corpus_root and (corpus_root / legacy).exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(corpus_root / legacy, target)
                counts["copied"] += 1
                origin = "copied"
            else:
                records = page_records(db, doc_id)
                if records:
                    write_records(target, records)
                    counts["written"] += 1
                    counts["written_pages"] += len(records)
                    origin = "written"
                else:
                    counts["no_pages"] += 1
                    rel = ""
            if rel:
                taken[rel] = doc_key
            w.writerow({"source": source, "doc_key": doc_key, "text_method": method or "",
                        "pages": n_pages or 0, "ocr_file": rel, "origin": origin})

    with open(out / "linkchecks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LINK_FIELDS, lineterminator="\n")
        w.writeheader()
        for row in db.execute(
                "select source, doc_key, link_verified, link_ok, checked_at from documents "
                "where link_verified = 1 or link_ok is not null or checked_at is not null "
                "order by source, doc_key"):
            w.writerow(dict(zip(LINK_FIELDS, ["" if v is None else v for v in row])))
            counts["linkchecks"] += 1

    return counts


def main() -> int:
    require(index_db(), "assembling the OCR tree")
    db = sqlite3.connect(index_db_uri(), uri=True)
    out = ocr_root()
    # The old corpus is retired, so there is nothing left to gather: everything either is already in the
    # tree or comes out of the database. Re-running leaves what is there alone.
    counts = run(db, out, corpus_root=None)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"{counts['documents']:,} documents: {counts['copied']:,} OCR files gathered, "
          f"{counts['written']:,} written from the database ({counts['written_pages']:,} pages)")
    if counts["no_pages"]:
        print(f"{counts['no_pages']:,} have no pages at all and no file to point at")
    if counts["collisions"]:
        print(f"{counts['collisions']:,} name collisions, resolved by digest")
    print(f"{counts['linkchecks']:,} hand-checked links kept")
    print(f"{size / 1073741824:.2f} GB in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
