"""Take in a delivery of model files gathered by hand, with where each came from and what was not found.

    pidx models ingest <zip or directory>

A delivery is a folder per source plus, ideally, a log naming for each piece what was searched, what was
found and what was not. Both halves are worth keeping: a row saying a vendor never published a model is
what stops the same search being run again next year, and it is recorded against the page a person can
open to check.

Files are the truth and the log is provenance: the log's file column is written by people and is often
prose, so a file is matched to its row by name, and anything unmatched is credited to the source of the
folder it sits in. Every file lands in `sources/<id>/raw/`, with its checksum in the private manifest and
its URL in the public ledger — the same two records `pidx models fetch` writes, so what arrived by hand
and what arrived over the network are afterwards indistinguishable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import yaml

from parts_index.core.config import model_sources, model_state, spice_source
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger
from parts_index.models.fetch import Manifest, unpack, unpack_base

# What a hand-written log says, and what it means for the ledger. `searched` is final: somebody looked
# and there is nothing there for us, which is worth exactly as much as a file.
STATUS = {
    "encontrado": "downloaded", "found": "downloaded",
    "encontrado_parcial": "downloaded", "partial_found": "downloaded",
    "no_publicado": "not_published", "not_published": "not_published",
    "parcial": "searched", "partial": "searched",
    "licence_wall": "licence_wall", "login": "login", "blocked": "blocked",
}
FINAL = {"not_published", "searched", "blocked", "licence_wall", "login", "listed"}
LOG_COLUMNS = {"source_id", "estado", "notas"}
NOT_A_MODEL_FILE = {".md"}


def real_url(value: str) -> str:
    """The first URL in a field written by hand.

    Such a log uses placeholders like "N/A", and often lists two addresses in one cell when a piece was
    found in more than one place. Only something that can actually be opened counts, and only the first.
    """
    m = re.search(r"https?://[^\s;,]+", value or "")
    return m.group().rstrip(".") if m else ""


def piece_name(piece: str) -> str:
    """The part a row is about, as a name rather than a sentence about it."""
    first = re.sub(r"\s*\(.*", "", piece).strip().split(",")[0].strip()   # drop the commentary
    return first[:40] if re.fullmatch(r"[A-Za-z0-9][\w.+/-]*", first) else piece.strip()[:40]


def find_log(root: Path) -> Path | None:
    """The delivery's own record of what was looked for, if it brought one."""
    for p in sorted(root.rglob("*.csv")):
        try:
            head = next(csv.reader(open(p, encoding="utf-8")))
        except (StopIteration, OSError, UnicodeDecodeError):
            continue
        if LOG_COLUMNS <= set(head):
            return p
    return None


def payload(root: Path, log: Path | None) -> list[Path]:
    """Every file that is part of the delivery rather than a note about it."""
    return sorted(p for p in root.rglob("*") if p.is_file() and p != log
                  and p.suffix.lower() not in NOT_A_MODEL_FILE)


def claim(files: list[Path], rows: list[dict]) -> tuple[dict[Path, dict], set[int]]:
    """Match each file to the log row that mentions it, by name.

    Returns the file -> row map and the rows that named a file which did arrive. Several rows often name
    the same file — one collection answering several parts — and every one of them has been satisfied,
    even though only the first is recorded as that file's provenance.
    """
    by_name: dict[str, list[Path]] = {}
    for p in files:
        by_name.setdefault(p.name, []).append(p)
    out: dict[Path, dict] = {}
    satisfied: set[int] = set()
    for r in rows:
        for token in re.findall(r"[\w./+-]+\.\w{1,6}", r.get("fichero", "") or ""):
            for p in by_name.get(Path(token).name, []):
                out.setdefault(p, r)
                satisfied.add(id(r))
    return out, satisfied


def source_of_folder(files: list[Path], claimed: dict[Path, dict], root: Path) -> dict[str, str]:
    """Which source each top folder belongs to, decided by the rows that named its files."""
    votes: dict[str, Counter] = {}
    for p in files:
        folder = p.relative_to(root).parts[0]
        votes.setdefault(folder, Counter())
        if p in claimed:
            votes[folder][claimed[p]["source_id"]] += 1
    return {folder: (c.most_common(1)[0][0] if c else folder) for folder, c in votes.items()}


def register(source: str, title: str, home: str, note: str) -> Path:
    """Give a new source its entry. An existing one is left as it is."""
    reg = model_sources(source)
    if reg.exists():
        return reg
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(yaml.safe_dump({
        "title": title, "home_url": home, "status": "active", "fetch": "manual",
        "note": note, "licence": "unreviewed", "licence_checked_at": None, "redistributable": False,
    }, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return reg


def ledger(source: str) -> Ledger:
    return Ledger(model_state(source), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)


def ingest(root: Path, dry: bool = False) -> dict:
    log = find_log(root)
    rows = list(csv.DictReader(open(log, encoding="utf-8"))) if log else []
    files = payload(root, log)
    claimed, satisfied = claim(files, rows)
    folders = source_of_folder(files, claimed, root)
    counts = Counter()
    ledgers: dict[str, Ledger] = {}
    manifests: dict[str, Manifest] = {}

    for p in files:
        row = claimed.get(p)
        rel_from_root = p.relative_to(root)
        source = row["source_id"] if row else folders.get(rel_from_root.parts[0], rel_from_root.parts[0])
        rel = "raw/" + "/".join(rel_from_root.parts[1:])
        url = real_url((row or {}).get("url_descarga", "")) or real_url((row or {}).get("url_pagina", ""))
        key = url or f"manual:{rel}"
        counts["files"] += 1
        if dry:
            counts[f"into:{source}"] += 1
            continue

        data = p.read_bytes()
        target = spice_source(source) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)

        # An archive is not readable where it lies: the indexer walks files, not zip members, so a
        # delivery of zips would land with every model inside it invisible. `fetch` unpacks what it
        # downloads for exactly this reason; a hand-gathered delivery has to be treated the same.
        if data[:2] == b"PK":
            try:
                counts["unpacked"] += unpack(target, spice_source(source) / unpack_base(target, source))
            except (zipfile.BadZipFile, OSError):
                counts["unpack_failed"] += 1

        m = manifests.setdefault(source, Manifest(source))
        m.add(url, rel, data, (row or {}).get("notas", "")[:200])   # the manifest is private: prose is fine here
        led = ledgers.setdefault(source, ledger(source))
        led.stamp(key, "fetch", url="" if url == key else url, status="downloaded", bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest())
        counts[f"into:{source}"] += 1

    # What was looked for and not found is worth keeping: it is what stops the search being repeated.
    for r in rows:
        if id(r) in satisfied:
            # Its file arrived and the file's own row carries the provenance. But a part looked up at a
            # vendor has a row of its own, and leaving that at not_tried makes the ledger say both "we
            # hold this model" and "nobody has looked for it" -- and the second is what decides whether
            # the part is searched again.
            answered = piece_name((r.get("pieza") or "").strip())
            if answered and not dry:
                led = ledgers.setdefault(r["source_id"], ledger(r["source_id"]))
                led.stamp(f"part:{answered}", "fetch", part=answered, status="downloaded",
                          url=real_url(r.get("url_descarga", "")) or real_url(r.get("url_pagina", "")))
            counts["outcome:answered"] += 1
            continue
        status = STATUS.get((r.get("estado") or "").strip(), "not_tried")
        part = (r.get("pieza") or "").strip()
        url = real_url(r.get("url_descarga", "")) or real_url(r.get("url_pagina", ""))
        if status == "downloaded":
            # The log says found, but no file arrived with the delivery. Either it is only a link, which
            # is still worth publishing, or there is nothing at all.
            status = "listed" if url else "not_published"
        # Nothing published anywhere leaves no URL to key on, so the piece itself is the key — the same
        # convention the ledger already uses for a part looked up at a vendor.
        key = url or (f"part:{part}" if part else "")
        if not key:
            counts["outcomes_without_a_key"] += 1
            continue
        counts[f"outcome:{status}"] += 1
        if dry:
            continue
        source = r["source_id"]
        led = ledgers.setdefault(source, ledger(source))
        # The delivery's own notes stay with the delivery: they are prose written for a person, often in
        # another language and naming them. The ledger is public and carries the machine-readable reason.
        if status in FINAL:
            led.skip(key, status, url="" if url == key else url, part=piece_name(part), status=status)
        else:
            led.stamp(key, "fetch", url="" if url == key else url, part=piece_name(part), status=status)

    if not dry:
        for source in set(list(manifests) + list(ledgers)):        # keep the delivery's own account of itself
            if log:
                keep = spice_source(source) / "delivery"
                keep.mkdir(parents=True, exist_ok=True)
                shutil.copy2(log, keep / log.name)
                for doc in root.glob("*.md"):
                    shutil.copy2(doc, keep / doc.name)
        for source, m in manifests.items():
            m.save()
        for source, led in ledgers.items():
            led.save()
            register(source, f"{source} (hand-gathered)", "", f"delivered in {root.name}")
    counts["sources"] = len(set(list(manifests) + list(ledgers)))
    return dict(counts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", help="a zip or a directory")
    ap.add_argument("--dry", action="store_true", help="say what would happen and change nothing")
    a = ap.parse_args(argv)

    src = Path(a.path)
    if not src.exists():
        print(f"{src} is not here", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="pidx_ingest_") as tmp:
        if src.is_file() and zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                z.extractall(tmp)
            root = Path(tmp)
            inner = [p for p in root.iterdir() if p.is_dir()]
            if len(inner) == 1 and not any(p.is_file() for p in root.iterdir()):
                root = inner[0]                      # a delivery usually carries one top folder
        else:
            root = src
        counts = ingest(root, dry=a.dry)

    print(f"{counts.get('files', 0)} files into {counts.get('sources', 0)} sources"
          + (" (dry run)" if a.dry else ""))
    for k in sorted(counts):
        if k.startswith(("into:", "outcome:")):
            print(f"  {k:34s} {counts[k]}")
    if counts.get("outcomes_without_a_key"):
        print(f"  {counts['outcomes_without_a_key']} outcomes named neither a piece nor a URL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
