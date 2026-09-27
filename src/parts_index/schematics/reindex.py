"""Read the corpus again with the current extractor, without downloading or rendering anything.

    pidx schematics reindex [--source esp] [--limit N] [--workers 12] [--dry]

The index database holds what each document is, where its pages are and what they say; none of that
depends on the extractor. What does depend on it is which part numbers each page mentions — the
`page_parts` rows — and that is recomputed here, from the OCR already on disk. No network, no GPU, no
re-reading of a single PDF.

It is how an extractor change reaches the site at all. A fix that makes 6V6 readable changes nothing
until the pages that say "6V6" are asked again, and `export` only ever reads this database.

Incremental on the extractor version, like every other stage: a document whose `extractor_version`
already matches is skipped, so an interrupted run resumes and a finished one costs nothing. Bump
`EXTRACTOR` to have the corpus read again.

Ingesting *new* documents is the other half and is not here: these are the documents the database
already knows. What audiocircuit and tagboard have downloaded needs `ocr` first and then an ingest
that creates document rows, which is still to be ported.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from parts_index.core import adfilter, pagesio
from parts_index.core.config import index_db, index_db_uri, ocr_map, ocr_root, require
from parts_index.core.parts import extractor as parts

EXTRACTOR = f"parts-judged-7 ({len(parts.CENSUS)} census, {len(parts.NOT_HERE)} judged out, {len(parts.KNOWN)} dictionary)"
CONF_RANK = {"high": 3, "medium": 2, "low": 1}
NEAR_MAX = 3


def summarise(hits_with_label):
    """[(Hit, is_label)] -> {part: row}. One row per part per page, carrying how it was read."""
    out: dict[str, dict] = {}
    for h, label in hits_with_label:
        d = out.setdefault(h.part, {"base": h.base, "family": h.family, "kind": h.kind, "n": 0,
                                    "n_label": 0, "conf": h.conf, "read_by": "ocr", "raw": h.raw})
        d["n"] += 1
        d["n_label"] += int(label)
        if CONF_RANK[h.conf] > CONF_RANK[d["conf"]]:
            d["conf"] = h.conf
        if h.fixed:
            d["read_by"] = "ocr_fix"
    return out


def locate(blocks, idx, w, h):
    """Where a label sits, without the image: its box in thousandths of the page, and the designators
    printed beside it. This is what lets a result say where on a big sheet the part is."""
    x0, y0, x1, y1 = blocks[idx]["box"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    near = sorted((((b["box"][0] + b["box"][2]) / 2 - cx) ** 2 + ((b["box"][1] + b["box"][3]) / 2 - cy) ** 2,
                   b["text"].strip())
                  for i, b in enumerate(blocks)
                  if i != idx and len(b["text"].strip()) <= 6 and parts.DESIG.fullmatch(b["text"].strip()))
    box = [int(1000 * x0 / w), int(1000 * y0 / h), int(1000 * x1 / w), int(1000 * y1 / h)]
    return box, [t for d, t in near[:NEAR_MAX] if d < (0.12 * max(w, h)) ** 2]


def page_record(page):
    """One OCR page -> (page features, {part: row}). The advert score is recomputed too: it depends on
    which tokens were read as parts, so a different extractor gives a different page."""
    blocks = [b for b in page.get("blocks") or [] if (b.get("text") or "").strip()]
    hits = [h for h in parts.extract_page(page) if h.block is not None and h.block < len(blocks)]
    summ = summarise((h, len(blocks[h.block]["text"].strip()) <= 14) for h in hits)
    if page.get("how") == "cad" or any("box" not in b for b in blocks):
        # A design read from its own file has no geometry: cad.py writes each field as a block with no
        # box, because a box says where a word was on a picture and there is no picture. So there is
        # nothing to locate, no advert to score, and nothing to decide about whether it is a schematic —
        # it is one by definition, which is what `has_schematic` gates the export on.
        distinct = {d["base"] for d in summ.values()}
        feats = {"n_blocks": len(blocks), "n_desig": parts.count_designators(blocks),
                 "n_values": parts.count_values(blocks), "n_parts": len(distinct), "priced_rows": 0,
                 "seq_run": 0.0, "ad_score": 0, "is_ad": 0, "has_schematic": 1}
        return feats, summ
    w, h = page.get("w") or 1, page.get("h") or 1
    for hit in hits:
        d = summ[hit.part]
        if len(d.setdefault("boxes", [])) < 4:
            box, near = locate(blocks, hit.block, w, h)
            d["boxes"].append(box)
            d.setdefault("near", near)
    distinct = {d["base"] for d in summ.values()}
    scored = dict(page, n_parts=len(distinct),
                  priced_rows=adfilter.priced_rows(page, [h.block for h in hits]),
                  seq_run=adfilter.seq_run(distinct))
    pts, _ = adfilter.score(scored)
    n_desig, n_values = parts.count_designators(blocks), parts.count_values(blocks)
    feats = {"n_blocks": len(blocks), "n_desig": n_desig, "n_values": n_values, "n_parts": len(distinct),
             "priced_rows": scored["priced_rows"], "seq_run": round(scored["seq_run"], 3),
             "ad_score": pts, "is_ad": int(pts >= 3),
             "has_schematic": int(n_desig + n_values >= 8 and pts < 3)}
    return feats, summ


def read_one(job):
    """(doc_id, ocr file) -> (doc_id, [(page_no, feats, parts)]). Runs in a worker; opens no database."""
    doc_id, path = job
    out = []
    try:
        for page in pagesio.iter_pages(path):
            feats, summ = page_record(page)
            out.append((int(page["page"]), feats, summ))
    except (OSError, ValueError) as e:
        return doc_id, None, str(e)[:120]
    return doc_id, out, None


def _ocr_files() -> dict[tuple[str, str], str]:
    """(source, doc_key) -> the OCR file that holds it, from the map that travels with the tree."""
    import csv

    out = {}
    with open(ocr_map(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["source"], r["doc_key"])] = r["ocr_file"]
    return out


def _part_ids(db) -> dict[str, int]:
    return {p: i for i, p in db.execute("SELECT part_id, part FROM parts")}


def run(sources=None, limit=0, workers=12, dry=False) -> dict:
    require(index_db(), "reading the corpus again")
    db = sqlite3.connect(index_db_uri(readonly=False), uri=True, timeout=120)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    where = "WHERE (extractor_version IS NULL OR extractor_version <> ?)"
    args: list = [EXTRACTOR]
    if sources:
        where += f" AND source IN ({','.join('?' * len(sources))})"
        args += list(sources)
    todo = db.execute(f"SELECT doc_id, source, doc_key FROM documents {where} ORDER BY doc_id", args).fetchall()
    files = _ocr_files()
    jobs = [(doc_id, str(ocr_root() / files[(source, key)]))
            for doc_id, source, key in todo if files.get((source, key))]
    # A document the reader opened and found no page in (a .tif, a PDF with nothing inside) is in the
    # map with no file. There is nothing to read; it is stamped so it is not offered again — 88 of them
    # came back as "Is a directory" on every pass, the OCR root joined with an empty name.
    empty = [doc_id for doc_id, source, key in todo if (source, key) in files and not files[(source, key)]]
    counts = {"documents to read": len(todo), "with an OCR file": len(jobs), "with no page": len(empty)}
    if limit:
        jobs = jobs[:limit]
    if dry or not jobs:
        return counts
    for doc_id in empty:
        db.execute("UPDATE documents SET extractor_version = ?, ingested_at = date('now') WHERE doc_id = ?",
                   (EXTRACTOR, doc_id))
    db.commit()

    part_ids = _part_ids(db)
    done = pages_written = rows_written = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for doc_id, pages, error in pool.map(read_one, jobs, chunksize=8):
            if error:
                counts["unreadable"] = counts.get("unreadable", 0) + 1
                print(f"  !! doc {doc_id}: {error}", file=sys.stderr)
                continue
            page_ids = dict(db.execute("SELECT page_no, page_id FROM pages WHERE doc_id = ?", (doc_id,)))
            for page_no, feats, summ in pages:
                page_id = page_ids.get(page_no)
                if page_id is None:
                    counts["page not in the index"] = counts.get("page not in the index", 0) + 1
                    continue
                db.execute("""UPDATE pages SET n_blocks=?, n_desig=?, n_values=?, n_parts=?, priced_rows=?,
                              seq_run=?, ad_score=?, is_ad=?, has_schematic=? WHERE page_id=?""",
                           (feats["n_blocks"], feats["n_desig"], feats["n_values"], feats["n_parts"],
                            feats["priced_rows"], feats["seq_run"], feats["ad_score"], feats["is_ad"],
                            feats["has_schematic"], page_id))
                db.execute("DELETE FROM page_parts WHERE page_id = ?", (page_id,))
                for part, d in summ.items():
                    pid = part_ids.get(part)
                    if pid is None:
                        cur = db.execute(
                            "INSERT INTO parts (part, base_part, family, kind, in_dictionary) VALUES (?,?,?,?,?)",
                            (part, d["base"], d["family"], d["kind"], int(parts.norm(part) in parts.KNOWN)))
                        pid = part_ids[part] = cur.lastrowid
                    db.execute("""INSERT INTO page_parts (page_id, part_id, n, n_label, conf, read_by, raw, boxes, near)
                                  VALUES (?,?,?,?,?,?,?,?,?)""",
                               (page_id, pid, d["n"], d["n_label"], d["conf"], d["read_by"], d["raw"],
                                json.dumps(d.get("boxes") or []), " ".join(d.get("near") or [])))
                    rows_written += 1
                pages_written += 1
            db.execute("UPDATE documents SET extractor_version = ?, ingested_at = date('now') WHERE doc_id = ?",
                       (EXTRACTOR, doc_id))
            done += 1
            if done % 500 == 0:
                db.commit()
                rate = done / max(time.time() - t0, 1)
                left = (len(jobs) - done) / max(rate, 0.001) / 60
                print(f"  {done:,}/{len(jobs):,} documents, {pages_written:,} pages, "
                      f"{rate:.0f}/s, about {left:.0f} min left", flush=True)
    db.commit()
    db.execute("ANALYZE")
    db.commit()
    db.close()
    counts |= {"documents read": done, "pages rewritten": pages_written, "part rows written": rows_written,
               "minutes": round((time.time() - t0) / 60, 1)}
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics reindex", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many documents")
    ap.add_argument("--workers", type=int, default=12, help="how many processes read at once")
    ap.add_argument("--dry", action="store_true", help="say how much there is to read and write nothing")
    a = ap.parse_args(argv)
    print(f"extractor: {EXTRACTOR}")
    counts = run(a.source, a.limit, a.workers, a.dry)
    for k, v in counts.items():
        print(f"  {v:>12,}  {k}" if isinstance(v, int) else f"  {v:>12}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
