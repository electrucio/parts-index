"""Import the state of the pre-monorepo SPICE model campaign into the public registry and ledgers.

    make migrate        # writes data/models/sources/<id>.yaml (if missing) and data/models/state/<id>.csv

Reads, under the private data root:  spice/sources/<id>/{SOURCE.md,manifest.json} (what was downloaded, with URL and
sha256), spice/index.jsonl (which definitions each file yielded) and staging/.../model_links.csv (per part and vendor:
downloaded, not published, behind a licence wall or login, blocked, or not tried yet).

Writes facts only: URLs, hashes, sizes, dates, counts and statuses. Model text and local paths stay private.
A ledger row is either a downloaded file (key = its URL) or the attempt to find one part at one vendor
(key = "part:<PART>", url = the page a person would open).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from parts_index.core.config import PUBLIC_DATA, spice_index, spice_root, staging
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger

OUT = PUBLIC_DATA / "models"
INDEX_VERSION = "index_models-1"
ADAPTERS = {"ti", "onsemi", "onsemi-ic", "nexperia", "vishay", "infineon", "diodes-inc"}
# Statuses that must not be retried automatically. "not_tried" stays pending.
FINAL = {"not_published", "licence_wall", "login", "blocked", "encrypted_only"}
# Licences read in the upstream repositories during the survey; to be re-checked before any file is hosted.
HOMES = {"ti": "https://www.ti.com/", "onsemi": "https://www.onsemi.com/", "onsemi-ic": "https://www.onsemi.com/",
         "nexperia": "https://www.nexperia.com/", "vishay": "https://www.vishay.com/", "infineon": "https://www.infineon.com/",
         "diodes-inc": "https://www.diodes.com/"}
TITLES = {"electrucio": "Electrucio's own LTspice parts"}        # titles reworded for the public registry
LICENCE_HINTS = {"germaniumbjts": "MIT", "spiceypedals": "MIT", "pnp-fuzz-simulation": "GPL-2.0-only"}


def model_ledger(source: str) -> Ledger:
    return Ledger(OUT / "state" / f"{source}.csv", stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)


def source_doc(folder: Path) -> tuple[str, str]:
    """(title, first URL) out of SOURCE.md; the prose itself is not published."""
    f = folder / "SOURCE.md"
    if not f.exists():
        return folder.name, ""
    text = f.read_text(encoding="utf-8", errors="replace")
    head = text.splitlines()[0].lstrip("# ").strip() if text else folder.name
    title = re.split(r"\s[—–-]\s", head, maxsplit=1)[-1].strip() or folder.name
    urls = [u.rstrip(".,;") for u in re.findall(r"https?://[^\s)>`\"']+", text)]
    return title, next((u for u in urls if "<" not in u and "{" not in u), "")


def defs_per_file(index: Path) -> Counter:
    """Definitions per manifest path: a file under extracted/<stem>/ is credited to the archive raw/**/<stem>.*"""
    n: Counter = Counter()
    with open(index, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            parts = (r.get("file") or "").split("/")
            if len(parts) < 4 or parts[0] != "sources":
                continue
            sid, where = parts[1], parts[2]
            n[(sid, "stem:" + parts[3].lower()) if where == "extracted" else (sid, "/".join(parts[2:]))] += 1
    return n


def seed_source(folder: Path, defs: Counter, index_day: str, links: list[dict]) -> tuple[dict, Ledger]:
    sid = folder.name
    led = model_ledger(sid)
    led.rows.clear()
    files, total_bytes, fetched = [], 0, ""
    mf = folder / "manifest.json"
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        fetched, files = m.get("fetched", ""), m.get("files", [])
    by_path, credited = {}, set()
    for x in files:
        path, url = x.get("path") or "", x.get("url") or ""
        key = url or f"manual:{path}"
        if key in led:
            key = f"{key}#{path}"
        row = led.row(key)
        if not path and not x.get("sha256"):                  # listed in the manifest, never downloaded
            row.update(status="listed", skip_reason=(x.get("note") or "listed only")[:80])
            continue
        stem = Path(path or url.rsplit("/", 1)[-1]).stem.lower()   # an archive that was unpacked and not kept has no path
        n = defs.get((sid, path), 0)
        if stem not in credited:                              # two archives with the same stem: credit the first only
            n += defs.get((sid, "stem:" + stem), 0)
            credited.add(stem)
        row.update(status="downloaded", bytes=str(x.get("bytes") or ""), sha256=x.get("sha256") or "",
                   fetch_at=x.get("fetched") or fetched, n_defs=str(n or ""))
        if n:
            row["index_at"], row["index_v"] = index_day, INDEX_VERSION
        total_bytes += int(x.get("bytes") or 0)
        by_path[f"sources/{sid}/{path}"] = row
    for r in links:
        hits = [by_path[f] for f in r["model_file"].split() if f in by_path]
        if r["model_status"] == "downloaded" and hits:
            for row in hits:
                row["part"] = (row["part"] + " " + r["part"]).strip()
            continue
        row = led.row(f"part:{r['part']}")
        row.update(url=r["resource_url"], part=r["part"], status=r["model_status"])
        if r["model_status"] != "not_tried":
            row["fetch_at"] = r["checked"]
        if r["model_status"] in FINAL:
            row["skip_reason"] = r["model_status"]
    title, home = source_doc(folder) if folder.exists() else (sid, "")
    on_disk = folder.exists() and any(p.is_dir() for p in folder.iterdir())
    status = "active" if files or on_disk else ("link_only" if links else "pending_manual")
    entry = dict(title=TITLES.get(sid, title), home_url=HOMES.get(sid, home), status=status,
                 fetch="adapter" if sid in ADAPTERS else "manual", fetched=fetched, files=len(files), bytes=total_bytes,
                 licence=LICENCE_HINTS.get(sid, "unreviewed"), licence_checked_at=None, redistributable=False)
    if on_disk and not files:
        entry["note"] = "downloaded in bulk; its manifest (URL + sha256 per file) has not been written yet"
    led.dirty = True
    return entry, led


def main() -> int:
    sources, index = spice_root() / "sources", spice_index()
    links_csv = staging("spice-library/research/model-search/model_links.csv")
    if not sources.exists():
        print("no spice/sources under the data root: nothing to seed", file=sys.stderr)
        return 1
    defs = defs_per_file(index) if index.exists() else Counter()
    index_day = datetime.fromtimestamp(index.stat().st_mtime, tz=timezone.utc).date().isoformat() if index.exists() else ""
    links: dict[str, list[dict]] = {}
    if links_csv.exists():
        with open(links_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r["source"].startswith("("):                 # "(index)" rows: the part was already covered
                    links.setdefault(r["source"], []).append(r)
    ids = sorted({p.name for p in sources.iterdir() if p.is_dir()} | set(links))
    (OUT / "sources").mkdir(parents=True, exist_ok=True)
    for sid in ids:
        entry, led = seed_source(sources / sid, defs, index_day, links.get(sid, []))
        reg = OUT / "sources" / f"{sid}.yaml"
        if not reg.exists():
            reg.write_text(yaml.safe_dump(entry, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
        if len(led):
            led.save()
        print(f"{sid:28s} {entry['status']:10s} {led.summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
