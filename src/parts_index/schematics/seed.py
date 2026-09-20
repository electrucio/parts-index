"""Import the state of the pre-monorepo pipeline into the public registry and ledgers.

    python -m parts_index.schematics.seed            # writes data/schematics/sources.yaml (if missing) and state/*.csv

Reads, under the private data root:  corpus/db/schematics.sqlite (what was indexed), corpus/raw/<source>/files.csv
(what was downloaded, including failures), corpus/magazines/ocr/sources.csv, and the OCR outputs (for their dates).
Writes only public facts: URLs, hashes, sizes, dates and stage versions. Local paths never leave the data root.

Run once at the migration and again after the freeze re-sync; after that the pipeline stages keep the ledgers.
"""
from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from parts_index.core.config import PUBLIC_DATA, data_root
from parts_index.core.ledger import Ledger

STATE = PUBLIC_DATA / "schematics" / "state"
REGISTRY = PUBLIC_DATA / "schematics" / "sources.yaml"

# Sources that are known but deliberately not processed. Recorded so nobody tries again by accident.
NOT_PROCESSED = {
    "schematics_unlimited": dict(kind="factory", title="Schematics Unlimited", home_url="https://www.schematicsunlimited.com/",
                                 status="excluded", blocked_reason="every file is behind a CAPTCHA; never bypass it"),
    "groupdiy_threads": dict(kind="forum", title="GroupDIY", home_url="https://groupdiy.com/",
                             status="excluded", blocked_reason="user forums are out of scope"),
    "ampgarage_threads": dict(kind="forum", title="Amp Garage", home_url="https://ampgarage.com/",
                              status="excluded", blocked_reason="user forums are out of scope"),
}
TITLES = {"books": "Books, linked to their public pages"}      # titles reworded for the public registry
CRAWL_KEYS = ("start", "allow", "deny", "max", "cdn", "figures")


def day(stamp: str | None) -> str:
    return (stamp or "")[:10]


def mtime_day(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date().isoformat()


def ocr_day(corpus: Path, source: str, ocr_path: str, local_name: str) -> str:
    candidates = []
    if ocr_path:
        candidates += [corpus / ocr_path, corpus / "magazines" / ocr_path]
    if local_name:
        candidates.append(corpus / "ocr_boxes" / source / f"{local_name}.jsonl.gz")
    for c in candidates:
        if c.exists():
            return mtime_day(c)
    return ""


def legacy_sites(staging: Path) -> dict:
    f = staging / "schematics_scrap/07_component_index/sites.py"
    if not f.exists():
        return {}
    spec = importlib.util.spec_from_file_location("legacy_sites", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SITES


def downloaded_anything(corpus: Path, source: str) -> bool:
    manifest = corpus / "raw" / source / "files.csv"
    if not manifest.exists():
        return False
    with open(manifest, newline="", encoding="utf-8") as f:
        return any(r["http"] == "200" for r in csv.DictReader(f))


def build_registry(db: sqlite3.Connection, sites: dict, corpus: Path) -> dict:
    reg = {}
    for source, kind, title, home in db.execute("select source, kind, title, home_url from sources order by source"):
        entry = dict(kind=kind, title=TITLES.get(source, title), home_url=home, status="active")
        crawl = {k: sites[source][k] for k in CRAWL_KEYS if k in sites.get(source, {})}
        if crawl:
            entry["crawl"] = crawl
        reg[source] = entry
    for source, s in sites.items():                       # configured but never reached the index
        if source not in reg:
            entry = dict(kind=s.get("kind", "site"), title=s["title"], home_url=s["start"][0], status="active")
            if not downloaded_anything(corpus, source):
                entry.update(status="blocked", blocked_reason="unreachable from the crawler on 2026-09-20; retry later")
            entry["crawl"] = {k: s[k] for k in CRAWL_KEYS if k in s}
            reg[source] = entry
    reg.update(NOT_PROCESSED)
    return dict(sorted(reg.items()))


def seed_source(db: sqlite3.Connection, corpus: Path, source: str) -> Ledger:
    led = Ledger(STATE / f"{source}.csv")
    led.rows.clear()
    local_names: dict[str, str] = {}

    manifest = corpus / "raw" / source / "files.csv"
    if manifest.exists():
        with open(manifest, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                url = r["url"]
                local_names[url] = Path(r["path"]).name if r["path"] else ""
                row = led.row(url)
                row.update(role=r["role"], type=r["type"], http=r["http"], bytes=r["bytes"], sha256=r["sha256"])
                if r["http"] == "200" and r["sha256"]:
                    row["download_at"] = day(r["retrieved_at"])
                elif r["http"] and r["http"] != "200":
                    row["skip_reason"] = f"http {r['http']}"
                elif r["why"]:
                    row["skip_reason"] = r["why"][:80]

    wrh_dates = {}
    ledger_csv = corpus / "magazines/ocr/sources.csv"
    if ledger_csv.exists():
        with open(ledger_csv, newline="", encoding="utf-8") as f:
            wrh_dates = {r["url"]: (day(r["retrieved_at"]), r["pdf_bytes"]) for r in csv.DictReader(f) if r["magazine"] == source}

    q = """select doc_key, public_url, role, sha256, n_pages, text_method, ocr_path, extractor_version, ingested_at,
                  link_verified, link_ok, checked_at from documents where source = ? order by doc_key"""
    for key, url, role, sha, n_pages, method, ocr_path, ext_v, ingested, verified, link_ok, checked in db.execute(q, (source,)):
        row = led.row(key)
        row["url"] = "" if url == key else url
        row["role"] = role or row["role"]
        row["sha256"] = row["sha256"] or (sha or "")
        row["n_pages"] = str(n_pages or "")
        row["text_method"] = method or ""
        if key in wrh_dates:
            row["download_at"], row["bytes"] = wrh_dates[key]
            row["type"], row["http"] = "pdf", "200"
        if method and method != "text":
            row["ocr_at"] = ocr_day(corpus, source, ocr_path or "", local_names.get(key, ""))
            row["ocr_v"] = f"{method}-1" if row["ocr_at"] else ""
        if not row["download_at"] and (row["ocr_at"] or method == "text"):
            row["type"] = row["type"] or "local"           # worked from a local copy; the public URL is what is linked
            row["download_at"] = row["ocr_at"] or day(ingested)
        row["index_at"], row["index_v"] = day(ingested), ext_v or ""
        if verified or checked:
            row["linkcheck_at"] = day(checked) or day(ingested)
            row["link_ok"] = "" if link_ok is None else str(link_ok)
    led.dirty = True
    return led


def main() -> int:
    root = data_root()
    corpus = root / "corpus"
    dbfile = corpus / "db/schematics.sqlite"
    if not dbfile.exists():
        print(f"no index at {dbfile.relative_to(root)} under the data root: nothing to seed", file=sys.stderr)
        return 1
    db = sqlite3.connect(f"file:{dbfile}?mode=ro", uri=True)
    registry = build_registry(db, legacy_sites(root / "staging"), corpus)
    if REGISTRY.exists():
        print(f"{REGISTRY.relative_to(PUBLIC_DATA.parent)} exists: left alone")
    else:
        REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        header = ("# Registry of schematic/reference sources. status: proposed | active | paused | blocked | excluded\n"
                  "# Add a site here (status: proposed) to have it crawled; its progress is in state/<id>.csv and STATUS.md.\n")
        REGISTRY.write_text(header + yaml.safe_dump(registry, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    for source, entry in registry.items():
        if entry["status"] == "excluded":
            continue
        led = seed_source(db, corpus, source)
        if len(led):
            led.save()
            print(f"{source:26s} {led.summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
