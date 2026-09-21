"""Write the OCR records the old pipeline never wrote to disk, and the two indexes over them.

    make migrate

Most documents were OCR'd into a file. Some were not: an HTML page and a born-digital PDF have a text
layer, so the old ingester read their text straight from the source and kept it only inside the database.
Those documents get their page records written here, in the same format and the same tree as every other
document — there is nothing special about them beyond `how: "text"` inside the record, which is where
that distinction belongs. The database then holds the last copy of nothing.

Two indexes come with them:

  `ocr_map.csv`     which OCR file holds each document. That link was only a convention, derived from a
                    column that never leaves the database; written down, the OCR files stop being orphans.
  `linkchecks.csv`  the links checked by hand. Re-indexing regenerates the advert and schematic judgements,
                    because the classifier is deterministic; it cannot regenerate these.

What a written-out record can and cannot carry: an HTML page was always one chunk of text with no geometry,
so it loses nothing — measured, 99.4 % of them re-extract identically. A born-digital article had line
blocks with boxes built from the PDF's text layer, and those were never saved, so its page becomes one
block holding the whole text; 95.5 % re-extract identically, the rest losing a hit that depended on the
line structure. Their already-extracted positions survive in the export.

Reads the database through an explicit column allow-list, and writes no local path.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from parts_index.core.config import corpus, corpus_db, corpus_db_uri, data_root, require

MAP_FIELDS = ("source", "doc_key", "text_method", "pages", "ocr_file", "present")
LINK_FIELDS = ("source", "doc_key", "link_verified", "link_ok", "checked_at")


def ocr_root() -> Path:
    """The one OCR tree: every document's page records, whatever produced them."""
    return data_root() / "ocr"


def ocr_file(source: str, text_method: str | None, ocr_path: str | None, local_path: str | None) -> str | None:
    """The OCR file holding this document, relative to the corpus, or None when only the database has it.

    Three conventions, all set by the original ingester: magazines record a path relative to `magazines/`,
    Elektor issues and books record one relative to the corpus, and everything OCR'd with boxes is found
    from the name of the file it was read from.
    """
    if ocr_path:
        return f"magazines/{ocr_path}" if text_method == "ocr" else ocr_path
    if text_method and text_method.startswith("ocr_boxes") and local_path:
        return f"ocr_boxes/{source}/{Path(local_path).name}.jsonl.gz"
    return None


def written_name(source: str, doc_key: str) -> str:
    """Where a document with no OCR file gets one. Its key is a URL, so the name is a stable digest of it
    and `ocr_map.csv` resolves it back, exactly as it resolves every other file."""
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
    path.with_suffix("").with_suffix(".done").touch()


def run(db: sqlite3.Connection, out: Path, corpus_root: Path | None = None) -> dict:
    """Write the records and the two indexes. Returns counts, for the caller to report and a test to assert."""
    out.mkdir(parents=True, exist_ok=True)
    counts = {"documents": 0, "with_ocr": 0, "ocr_missing": 0, "written": 0, "written_pages": 0, "linkchecks": 0}

    q = ("select d.doc_id, d.source, d.doc_key, d.text_method, d.ocr_path, d.local_path, d.n_pages "
         "from documents d order by d.source, d.doc_key")
    with open(out / "ocr_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAP_FIELDS, lineterminator="\n")
        w.writeheader()
        for doc_id, source, doc_key, method, ocr_path, local_path, n_pages in db.execute(q):
            counts["documents"] += 1
            rel = ocr_file(source, method, ocr_path, local_path)
            present = bool(rel) and (corpus_root is None or (corpus_root / rel).exists())
            if rel and present:
                counts["with_ocr"] += 1
            elif rel:
                counts["ocr_missing"] += 1

            if not present:
                records = page_records(db, doc_id)
                if records:
                    rel = written_name(source, doc_key)
                    write_records(out / rel, records)
                    counts["written"] += 1
                    counts["written_pages"] += len(records)
                    present = True
            w.writerow({"source": source, "doc_key": doc_key, "text_method": method or "",
                        "pages": n_pages or 0, "ocr_file": rel or "", "present": int(present)})

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
    require(corpus_db(), "writing the OCR records the old pipeline never wrote")
    db = sqlite3.connect(corpus_db_uri(), uri=True)
    out = ocr_root()
    counts = run(db, out, corpus())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"{counts['documents']:,} documents: {counts['with_ocr']:,} already had an OCR file, "
          f"{counts['written']:,} written here ({counts['written_pages']:,} pages)")
    if counts["ocr_missing"]:
        print(f"{counts['ocr_missing']:,} pointed at an OCR file that is not on disk; written out instead")
    print(f"{counts['linkchecks']:,} hand-checked links kept")
    print(f"{size / 1048576:.0f} MB in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
