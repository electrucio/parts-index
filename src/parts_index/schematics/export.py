"""Take the index out of the maintainer's database and into `data/`, where the site is built from.

    pidx schematics export

The database is a build-time intermediate that the website never sees: it lives on one machine, it is
3.9 GB, and it is rebuildable from the OCR. What the site reads is what this writes — four kinds of
plain CSV that a person can open, diff and correct in a pull request.

  `documents/<source>.csv`  one row per document: its public id, title, link and parent
  `pages/<source>.csv`      one row per page that has anything on it, with the link to that page
  `uses/<source>.csv`       one row per (part, page): the answer to "where is this part used"
  `parts.csv`               every part with how much there is of it, which is what search loads first
  `export.json`             what this run produced, per source, so any change is measurable

**Only a link we can stand behind is published.** Of 3,037,475 references, 237,829 come through. The
advert filter takes most of it — 1.75 million references sit on mail-order price lists, where a part
number means somebody sold it, not that it was used in anything. After that a document has to justify
its link: we downloaded it and hold its checksum, or a person checked the link by hand, or the link is a
search rather than a location, which cannot rot the same way. Rule 4 is the whole of it — a wrong link
is worse than no link.

**A public id, once given, is never given to anything else.** People link to these pages. The id is a
base-36 counter per source, and a re-export reads the ids it wrote last time and keeps them, so a
document that disappears takes its id out of use rather than handing it to its neighbour.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from parts_index.core import links
from parts_index.core.config import (
    index_db,
    index_db_uri,
    require,
    schematics_documents,
    schematics_export_manifest,
    schematics_pages,
    schematics_parts,
    schematics_registry,
    schematics_uses,
    schematics_withdrawn,
)
from parts_index.schematics import titles

VERSION = "export_schematics-1"
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
# A designator is R3, IC1, Q12 — it turns "page 47" into "R3 and IC1 on page 47". Anything else on the
# line is noise, and four is as many as a result can usefully show.
DESIGNATOR = re.compile(r"^[A-Z]{1,4}[0-9]{1,4}[A-Za-z]?$")
NEAR_MAX = 4
# A document has to be able to justify the link we publish for it.
GATE = """pp.conf = 'high' AND p.is_ad = 0
          AND (d.sha256 IS NOT NULL OR d.link_verified = 1 OR d.page_url_tpl LIKE '%?q=%')"""

DOC_FIELDS = ("id", "key", "title", "url", "parent", "role", "year", "month", "pages", "sha")
# Enough of the checksum to group the copies of one sheet without carrying 64 characters 22,383 times.
# 2,827 sheets are published by more than one archive; the Bassman 5F6-A is in three.
SHA_LEN = 16
PAGE_FIELDS = ("doc", "page", "url", "schematic", "parts")
USE_FIELDS = ("part", "doc", "page", "times", "near")
PART_FIELDS = ("part", "documents", "pages", "uses", "sources")


def base36(n: int) -> str:
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = DIGITS[r] + out
        if not n:
            return out


class Ids:
    """Public ids for one source, remembered across runs by reading what was written last time.

    The file is the memory: no extra state to keep in step with it, and a hand edit to the published
    documents is visible to the next run. A key that has gone keeps its id out of circulation, because
    somewhere there is a link to it.
    """

    def __init__(self, source: str):
        self.by_key: dict[str, str] = {}
        self.next = 0
        path = schematics_documents(source)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self.by_key[row["key"]] = row["id"]
                    self.next = max(self.next, int(row["id"], 36) + 1)

    def of(self, key: str) -> str:
        if key not in self.by_key:
            self.by_key[key] = base36(self.next)
            self.next += 1
        return self.by_key[key]


def withdrawn() -> set[str]:
    """Documents never to publish, whatever the index says: a takedown, or a link found to be wrong."""
    path = schematics_withdrawn()
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {r["key"] for r in csv.DictReader(f) if r.get("key")}


def near_of(value: str | None) -> str:
    """The designators beside the part, as a phrase a result can show."""
    if not value:
        return ""
    return " ".join([t for t in value.split() if DESIGNATOR.fullmatch(t)][:NEAR_MAX])


def rows(db: sqlite3.Connection):
    return db.execute(f"""
        SELECT pa.part, d.source, d.doc_id, d.doc_key, d.title, d.public_url, d.page_url_tpl,
               d.page_offset, d.role, d.year, d.month, d.n_pages, d.parent_doc_id, d.sha256,
               par.doc_key par_key, par.title par_title, par.public_url par_url,
               p.page_no, p.w_pt, p.h_pt, p.has_schematic, p.n_parts,
               pp.n, pp.boxes, pp.near
        FROM page_parts pp
             JOIN pages p ON p.page_id = pp.page_id
             JOIN documents d ON d.doc_id = p.doc_id
             JOIN parts pa ON pa.part_id = pp.part_id
             LEFT JOIN documents par ON par.doc_id = d.parent_doc_id
        WHERE {GATE}
        ORDER BY d.source, d.doc_id, p.page_no, pa.part""")


def write(path: Path, fields, rows_) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(fields)
        n = 0
        for r in rows_:
            w.writerow(r)
            n += 1
    return n


def export(only: list[str] | None = None, dry: bool = False) -> dict:
    require(index_db(), "exporting the index")
    db = sqlite3.connect(index_db_uri(), uri=True, timeout=900)
    db.row_factory = sqlite3.Row
    skip = withdrawn()
    registry = yaml.safe_load(schematics_registry().read_text(encoding="utf-8")) or {}

    docs: dict[str, dict] = {}          # source -> {key: row}
    pages: dict[str, dict] = {}         # source -> {(key, page): row}
    uses: dict[str, list] = {}
    part_docs: dict[str, set] = {}
    part_pages: dict[str, Counter] = {}
    part_sources: dict[str, set] = {}
    counts = Counter()

    for r in rows(db):
        source = r["source"]
        if only and source not in only:
            continue
        if r["doc_key"] in skip or (r["par_key"] and r["par_key"] in skip):
            counts["withdrawn"] += 1
            continue
        counts["references"] += 1
        d = docs.setdefault(source, {})
        key = r["doc_key"]
        if key not in d:
            d[key] = {
                "key": key,
                "title": titles.clean(r["title"] or r["par_title"], r["public_url"] or ""),
                "url": r["public_url"] or "",
                "parent": r["par_key"] or "",
                "role": r["role"] or "",
                "year": r["year"] or "",
                "month": r["month"] or "",
                "pages": r["n_pages"] or 0,
                "sha": (r["sha256"] or "")[:SHA_LEN],
            }
        pg = pages.setdefault(source, {})
        pkey = (key, r["page_no"])
        if pkey not in pg:
            pg[pkey] = {
                "page": r["page_no"],
                "url": links.part_url(dict(r), r["page_no"], r["boxes"], r["part"]),
                "schematic": int(bool(r["has_schematic"])),
                "parts": r["n_parts"] or 0,
            }
        uses.setdefault(source, []).append(
            {"part": r["part"], "key": key, "page": r["page_no"],
             "times": r["n"] or 1, "near": near_of(r["near"])})
        part_docs.setdefault(r["part"], set()).add((source, key))
        part_pages.setdefault(r["part"], Counter())[(source, key, r["page_no"])] += 1
        part_sources.setdefault(r["part"], set()).add(source)

    manifest = {"version": VERSION, "built": date.today().isoformat(),
                "gate": "high confidence, not an advert page, and a link we can justify",
                "withdrawn": len(skip), "sources": {}}
    for source in sorted(docs):
        ids = Ids(source)
        for key in docs[source]:
            ids.of(key)
        if dry:
            manifest["sources"][source] = {"documents": len(docs[source]),
                                           "pages": len(pages[source]), "uses": len(uses[source])}
            continue
        n_doc = write(schematics_documents(source), DOC_FIELDS,
                      ([ids.of(d["key"]), d["key"], d["title"], d["url"],
                        ids.by_key.get(d["parent"], "") if d["parent"] else "",
                        d["role"], d["year"], d["month"], d["pages"], d["sha"]]
                       for d in sorted(docs[source].values(), key=lambda x: ids.of(x["key"]))))
        n_page = write(schematics_pages(source), PAGE_FIELDS,
                       ([ids.of(k), p["page"], p["url"], p["schematic"], p["parts"]]
                        for (k, _), p in sorted(pages[source].items(),
                                                key=lambda kv: (ids.of(kv[0][0]), kv[0][1]))))
        n_use = write(schematics_uses(source), USE_FIELDS,
                      ([u["part"], ids.of(u["key"]), u["page"], u["times"], u["near"]]
                       for u in sorted(uses[source], key=lambda u: (u["part"], ids.of(u["key"]), u["page"]))))
        manifest["sources"][source] = {"documents": n_doc, "pages": n_page, "uses": n_use,
                                       "title": (registry.get(source) or {}).get("title", source),
                                       "kind": (registry.get(source) or {}).get("kind", "")}
        counts["documents"] += n_doc
        counts["pages"] += n_page
        counts["uses"] += n_use

    if not dry:
        counts["parts"] = write(
            schematics_parts(), PART_FIELDS,
            ([p, len(part_docs[p]), len(part_pages[p]), sum(part_pages[p].values()),
              " ".join(sorted(part_sources[p]))] for p in sorted(part_docs)))
        manifest["totals"] = {k: counts[k] for k in ("documents", "pages", "uses", "parts", "references")}
        schematics_export_manifest().parent.mkdir(parents=True, exist_ok=True)
        schematics_export_manifest().write_text(
            json.dumps(manifest, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    counts["sources"] = len(docs)
    return dict(counts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--dry", action="store_true", help="count what would be written and write nothing")
    a = ap.parse_args(argv)

    c = export(a.source, dry=a.dry)
    print(f"{c.get('references', 0):,} references from {c.get('sources', 0)} sources"
          + (" (dry run)" if a.dry else ""))
    if not a.dry:
        print(f"{c.get('documents', 0):,} documents, {c.get('pages', 0):,} pages, "
              f"{c.get('uses', 0):,} uses, {c.get('parts', 0):,} parts")
        print(f"-> {schematics_parts().parent}")
    if c.get("withdrawn"):
        print(f"{c['withdrawn']:,} references dropped: their document is withdrawn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
