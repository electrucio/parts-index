"""Put the documents that have been read into the index database, so `reindex` and `export` can see them.

    pidx schematics ingest [--source openhw_parts] [--limit N] [--dry]

The stages before this one leave a document in three places: a ledger row that says it was downloaded
and read, a page file under the OCR tree, and a line in the OCR map saying which file that is. None of
those is the index. `reindex` recomputes which parts each page mentions, `export` writes the site's
tables, and both work only over the `documents` and `pages` rows of the database — which is why 20,000
schematics read this week produced 28,000 uses on this machine and nothing on the site.

This is the missing half that `reindex` names in its own docstring: it creates the rows. For every
document the map knows and the database does not, it reads the page file once and writes the document,
its pages, and each page's text (for the full-text search), and leaves `extractor_version` empty — that
is the signal `reindex` already answers to, so the parts are computed there, by the code that owns them,
and not a second time here.

Ported from `build_index.py` in staging, with two departures that are on purpose:

  * A document's public link is the page a person is meant to open, when the listing recorded one, and
    the file itself otherwise. For a schematic on GitHub that is the blob page, which renders it, rather
    than the raw file, which is text. The raw URL stays the key.
  * The old crawler wrote down which page a figure was found on and this one does not, so a figure has
    no parent here and keeps the role the old mapping gave a figure without one. When the crawler learns
    to record its parent, this is the one line to change.

Incremental on (source, doc_key): a document already in the database is skipped, so a run resumes and a
finished one costs nothing. The ledger is stamped `index` for each document written, as every stage does.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time

import yaml

from parts_index.core import pagesio
from parts_index.core.config import (
    downloads,
    index_db,
    index_db_uri,
    ocr_map,
    ocr_root,
    schematics_registry,
    schematics_state,
    source_list,
)
from parts_index.core.ledger import Ledger
from parts_index.schematics import titles
from parts_index.schematics.download import safe_name

VERSION = "ingest-1"
PDF_PAGES_MAX = 200

# The database, for a clone that has none yet. Copied from the one this project has been building since
# September; `reindex` and `export` are written against exactly these tables.
SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (source TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT, home_url TEXT);
CREATE TABLE IF NOT EXISTS documents (
  doc_id INTEGER PRIMARY KEY, source TEXT NOT NULL REFERENCES sources(source), doc_key TEXT NOT NULL,
  role TEXT NOT NULL, parent_doc_id INTEGER REFERENCES documents(doc_id),
  title TEXT, public_url TEXT NOT NULL, page_url_tpl TEXT, page_offset INTEGER DEFAULT 0,
  link_verified INTEGER DEFAULT 0, link_ok INTEGER, checked_at TEXT,
  sha256 TEXT, year INTEGER, month TEXT, n_pages INTEGER, text_method TEXT,
  ocr_path TEXT, local_path TEXT, extractor_version TEXT, ingested_at TEXT,
  UNIQUE (source, doc_key));
CREATE INDEX IF NOT EXISTS ix_documents_sha ON documents(sha256);
CREATE INDEX IF NOT EXISTS ix_documents_parent ON documents(parent_doc_id);
CREATE TABLE IF NOT EXISTS pages (
  page_id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL REFERENCES documents(doc_id), page_no INTEGER NOT NULL,
  n_blocks INTEGER, n_desig INTEGER, n_values INTEGER, n_parts INTEGER, priced_rows INTEGER, seq_run REAL,
  ad_score INTEGER, is_ad INTEGER DEFAULT 0, has_schematic INTEGER DEFAULT 0, classifier_version TEXT,
  w_pt REAL, h_pt REAL, UNIQUE (doc_id, page_no));
CREATE TABLE IF NOT EXISTS parts (part_id INTEGER PRIMARY KEY, part TEXT UNIQUE NOT NULL, base_part TEXT NOT NULL,
  family TEXT, kind TEXT, in_dictionary INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_parts_base ON parts(base_part);
CREATE TABLE IF NOT EXISTS page_parts (
  page_id INTEGER NOT NULL, part_id INTEGER NOT NULL, n INTEGER, n_label INTEGER,
  conf TEXT, read_by TEXT, raw TEXT, boxes TEXT, near TEXT,
  PRIMARY KEY (page_id, part_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_page_parts_part ON page_parts(part_id, page_id);
CREATE TABLE IF NOT EXISTS page_text (page_id INTEGER PRIMARY KEY, text TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, content='page_text', content_rowid='page_id',
  tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS ingest_runs (source TEXT, started TEXT, finished TEXT, extractor_version TEXT,
  documents INTEGER, pages INTEGER);
"""


def registry() -> dict:
    with open(schematics_registry(), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def role_of(ledger_role: str, kind: str, source_kind: str) -> str:
    """The old mapping, as it was: a figure with no parent is not called a figure, an HTML page is a
    project page, a factory's document is a service manual, and everything else is a schematic."""
    if kind == "html":
        return "project_page"
    return "service_manual" if source_kind == "factory" else "schematic"


def listed(source: str) -> dict[str, dict]:
    """What the listing wrote about each URL — a title, and the page a person should open."""
    path = source_list(source)
    out: dict[str, dict] = {}
    if path.exists():
        import json
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[r["url"]] = r
    return out


def pt_sizes(path) -> list[tuple[float, float]]:
    """Page sizes in points, for the zoom link. Only a PDF has them, and only while the file is here."""
    try:
        import fitz
        fitz.TOOLS.mupdf_display_errors(False)
        with fitz.open(path) as doc:
            return [(round(p.rect.width, 1), round(p.rect.height, 1)) for p in doc][:PDF_PAGES_MAX]
    except Exception:                                      # noqa: BLE001  a released file, or not a PDF
        return []


def page_text(page: dict) -> str:
    return "\n".join((b.get("text") or "").strip() for b in page.get("blocks") or [] if (b.get("text") or "").strip())


def document_row(source: str, entry: dict, row: dict, meta: dict, note: dict) -> dict:
    """One ledger row + its map line + what the listing said -> the `documents` row."""
    kind = row.get("type") or "pdf"
    url = row["key"]
    title = note.get("title") or titles.clean(None, url)
    return dict(
        source=source, doc_key=url,
        role=role_of(row.get("role") or "", kind, entry.get("kind", "site")),
        parent_doc_id=None, title=title,
        public_url=note.get("page") or url,
        page_url_tpl="{url}#page={n}" if kind == "pdf" else None,
        sha256=row.get("sha256") or None, year=None, month=None,
        n_pages=int(meta.get("pages") or 0) or None,
        text_method=meta.get("text_method") or None,
        ocr_path=meta.get("ocr_file") or None, local_path=None,
        extractor_version=None, ingested_at=time.strftime("%Y-%m-%d %H:%M:%S"))


def _map_rows() -> dict[tuple[str, str], dict]:
    out = {}
    path = ocr_map()
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # The map is appended by OCR shards while this reads it; a line still being written is short.
            if r.get("source") and r.get("doc_key") and r.get("ocr_file"):
                out[(r["source"], r["doc_key"])] = r
    return out


def stamp_index(source: str, keys: list[str]) -> None:
    """Stamp `index` on these rows without losing what anyone else wrote to the ledger meanwhile.

    A ledger is one CSV, and every stage holds its own copy in memory and saves the whole of it. Two
    stages on one source at the same time — the downloader still fetching audiocircuit while this
    indexes the 20,416 documents already read — would each overwrite the other's stamps, last writer
    wins. So this stage never saves the copy it worked from: it reads the file again now, adds only its
    own stamps to what is there, and writes that. The window left is the milliseconds between the two.
    """
    fresh = Ledger(schematics_state(source))
    for key in keys:
        fresh.stamp(key, "index", version=VERSION)
    fresh.save()


def open_db():
    index_db().parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(index_db_uri(readonly=False), uri=True, timeout=900)
    db.executescript(SCHEMA)
    db.execute("PRAGMA journal_mode = WAL")
    return db


def put(db, doc: dict, pages: list[dict], sizes: list[tuple[float, float]]) -> int:
    """Write one document, its pages and their text. Returns the number of pages."""
    doc_id = db.execute(
        f"INSERT INTO documents({', '.join(doc)}) VALUES ({', '.join(':' + k for k in doc)})", doc).lastrowid
    n = 0
    for page in pages:
        page_no = int(page.get("page") or n + 1)
        w_pt, h_pt = sizes[page_no - 1] if page_no - 1 < len(sizes) else (None, None)
        pid = db.execute(
            "INSERT INTO pages (doc_id, page_no, n_blocks, w_pt, h_pt) VALUES (?,?,?,?,?)",
            (doc_id, page_no, len(page.get("blocks") or []), w_pt, h_pt)).lastrowid
        text = page_text(page)
        if text:
            db.execute("INSERT INTO page_text VALUES (?,?)", (pid, text))
            db.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (pid, text))
        n += 1
    return n


def run(sources: list[str] | None = None, limit: int = 0, dry: bool = False, say=print) -> dict:
    reg = registry()
    known = _map_rows()
    db = open_db()
    have = {(s, k) for s, k in db.execute("SELECT source, doc_key FROM documents")}
    counts = {"documents": 0, "pages": 0, "skipped": 0, "no file": 0}
    for source in sources or sorted({s for s, _ in known}):
        entry = reg.get(source)
        if not entry:
            say(f"{source}: not in the registry, not indexed")
            continue
        if entry.get("status") == "excluded":
            continue
        led = Ledger(schematics_state(source))
        notes = listed(source)
        todo = [k for (s, k) in known if s == source and (s, k) not in have and k in led.rows
                and led.rows[k].get("download_at") and not led.rows[k].get("skip_reason")]
        if limit:
            todo = todo[:limit]
        if not todo:
            continue
        say(f"{source}: {len(todo)} documents to index")
        if dry:
            counts["documents"] += len(todo)
            continue
        db.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?)",
                   (source, entry.get("kind", "site"), entry.get("title", source), entry.get("home_url", "")))
        t0, nd, npg = time.strftime("%Y-%m-%d %H:%M:%S"), 0, 0
        stamped: list[str] = []
        for key in sorted(todo):
            row, meta = led.rows[key], known[(source, key)]
            path = ocr_root() / meta["ocr_file"]
            if not path.exists():
                counts["no file"] += 1
                continue
            try:
                pages = pagesio.read_pages(path)
            except (OSError, ValueError) as e:
                say(f"  !! {meta['ocr_file']}: {str(e)[:100]}")
                counts["skipped"] += 1
                continue
            kind = row.get("type") or "pdf"
            local = downloads(source) / kind / safe_name(key, kind)
            sizes = pt_sizes(local) if kind == "pdf" and local.exists() else []
            doc = document_row(source, entry, row, meta, notes.get(key) or {})
            doc["n_pages"] = len(pages) or doc["n_pages"]
            npg += put(db, doc, pages, sizes)
            stamped.append(key)
            nd += 1
            if nd % 500 == 0:
                db.commit()
                stamp_index(source, stamped)
                stamped = []
                say(f"  {source}: {nd}/{len(todo)} documents, {npg} pages")
        db.execute("INSERT INTO ingest_runs VALUES (?,?,?,?,?,?)",
                   (source, t0, time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, nd, npg))
        db.commit()
        stamp_index(source, stamped)
        counts["documents"] += nd
        counts["pages"] += npg
        say(f"{source}: {nd} documents, {npg} pages")
    db.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics ingest", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many documents per source")
    ap.add_argument("--dry", action="store_true", help="say how much there is to index and write nothing")
    a = ap.parse_args(argv)
    counts = run(a.source, limit=a.limit, dry=a.dry)
    print(" · ".join(f"{v} {k}" for k, v in counts.items()), file=sys.stderr)
    if counts["documents"]:
        print("now: pidx schematics reindex" + "".join(f" --source {s}" for s in a.source or []), file=sys.stderr)
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
