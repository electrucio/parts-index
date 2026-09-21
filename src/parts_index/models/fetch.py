"""Download model files from a source, record where each came from, and unpack what arrives as an archive.

    pidx models fetch <source> --url <url>     add a file to a source
    pidx models recover [--source <id>]        fetch again whatever the catalogue says the tree has lost

Every download goes through `core.http`, so robots.txt, the per-host delay and the retry policy apply here
as everywhere else. What arrives is inspected before it is kept: a login page, an empty body or a binary
with no definitions in it is not a model, and saying so at download time is what keeps the ledger honest.

Two records are written for each file. The **manifest**, `sources/<id>/manifest.json`, is private and maps
a URL to the local file it became, with its checksum — it is the only place that mapping exists. The
**ledger**, `data/models/state/<id>.csv`, is public and holds the URL, the checksum and the outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import yaml

from parts_index.core import http
from parts_index.core.config import (
    model_sources,
    model_state,
    require,
    spice_models_root,
    spice_source,
    spice_source_manifest,
)
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger

DEF = re.compile(rb"^\s*\.(model|subckt)\s+(\S+)", re.I | re.M)
ENC = (b"$CDNENCSTART", b"<Encrypted Library>", b"* LTspice Encrypted File", b"**$ENCRYPTED_LIB")
MAX_MEMBER = 8_000_000


def inspect(data: bytes) -> tuple[str, list[str]]:
    """What a downloaded body actually is, and the definitions in it.

    One of: model, zip, text_no_model, zip_no_model, encrypted, html, binary, empty. A vendor that has
    stopped publishing a model usually answers with a page, not a 404, so this is what catches it.
    """
    if len(data) < 20:
        return "empty", []
    head = data[:600].lstrip().lower()
    if head.startswith((b"<!doctype", b"<html", b"<?xml")) or b"<title>" in head:
        return "html", []
    if data[:2] == b"PK":
        names: list[str] = []
        enc = False
        try:
            with zipfile.ZipFile(io_bytes(data)) as z:
                for n in z.namelist():
                    if n.endswith("/") or z.getinfo(n).file_size > MAX_MEMBER:
                        continue
                    b = z.read(n)
                    enc |= any(e in b[:4000] for e in ENC)
                    names += [m.group(2).decode("latin1") for m in DEF.finditer(b)]
        except (zipfile.BadZipFile, OSError):
            return "binary", []
        return ("zip" if names else "encrypted" if enc else "zip_no_model"), names
    if any(e in data[:4000] for e in ENC):
        return "encrypted", []
    names = [m.group(2).decode("latin1") for m in DEF.finditer(data)]
    return ("model" if names else "binary" if b"\x00" in data[:2000] else "text_no_model"), names


def io_bytes(data: bytes):
    import io
    return io.BytesIO(data)


class Manifest:
    """`sources/<id>/manifest.json`: which URL became which local file, and its checksum."""

    def __init__(self, source: str):
        self.source = source
        self.path = spice_source_manifest(source)
        self.data = {"source_id": source, "fetched": date.today().isoformat(), "files": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        self.data.setdefault("files", [])

    @property
    def files(self) -> list[dict]:
        return self.data["files"]

    def by_url(self, url: str) -> dict | None:
        key = url.lower().rstrip("/")
        return next((f for f in self.files if (f.get("url") or "").lower().rstrip("/") == key), None)

    def by_path(self, rel: str) -> dict | None:
        return next((f for f in self.files if (f.get("path") or "") == rel), None)

    def add(self, url: str, rel: str, data: bytes, note: str = "") -> dict:
        entry = {"url": url, "path": rel, "sha256": hashlib.sha256(data).hexdigest(),
                 "bytes": len(data), "note": note, "fetched": date.today().isoformat()}
        old = self.by_url(url) or self.by_path(rel)
        if old:
            old.update(entry)
            return old
        self.files.append(entry)
        return entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def how_to_ask(source: str) -> dict:
    """How this vendor wants to be asked, from its registry entry.

    Not every site wants the same client. onsemi, for one, serves its model files to a plain programmatic
    request and answers 403 to anything claiming to be a browser — it is blocking page scraping, not us.
    Recording that per source is the difference between asking correctly and concluding we are banned.
    """
    reg = model_sources(source)
    if not reg.exists():
        return {}
    entry = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    ask = entry.get("ask") or {}
    out: dict = {}
    if ask.get("user_agent") == "none":
        out["ua"] = None
    if ask.get("transport"):
        out["transport"] = ask["transport"]
    if ask.get("delay"):
        out["delay"] = float(ask["delay"])
    return out


def stamp(source: str, url: str, *, status: str, data: bytes | None = None, note: str = "") -> None:
    """Record the outcome in the public ledger: the URL, what it was, and its checksum."""
    led = Ledger(model_state(source), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)
    # The ledger's convention: the key is the URL, and the column repeats it only when they differ.
    values = {"status": status}
    if data is not None:
        values |= {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if status == "downloaded":
        led.stamp(url, "fetch", **values)
    else:
        led.skip(url, note or status, **values)
    led.save()


def members(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as z:
        return [m for m in z.namelist()
                if not m.endswith("/") and not m.startswith(("/", "..")) and ".." not in Path(m).parts]


def unpack_base(archive: Path, source: str, expected: set[str] | None = None) -> str:
    """Where this archive's members belong, relative to the source directory.

    The convention is `extracted/<stem>/`, but the older sources were unpacked by hand straight into
    `extracted/`, so an archive carrying its own top folder ends up one level higher. Rather than guess,
    ask the catalogue: whichever base reproduces paths it already recorded is the right one.
    """
    stem_base = f"extracted/{archive.stem}"
    if expected:
        for base in (stem_base, "extracted"):
            if any(f"sources/{source}/{base}/{m}" in expected for m in members(archive)):
                return base
    return stem_base


def unpack(archive: Path, into: Path) -> int:
    """Unpack an archive, never writing outside `into`. Returns the number of files written."""
    n = 0
    into.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in members(archive):
            target = into / member
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not os.access(target, os.W_OK):
                target.chmod(target.stat().st_mode | stat.S_IWUSR)   # archives carry read-only mode bits
            target.write_bytes(z.read(member))
            n += 1
    return n


def fetch(source: str, url: str, *, name: str | None = None, rel: str | None = None, note: str = "",
          subdir: str = "raw", transport: str = "requests", keep_anything: bool = False,
          expected: set[str] | None = None) -> dict:
    """Download one URL into a source. Returns {status, path, verdict, definitions}.

    `rel` puts the file back exactly where it was, which matters when recovering: a source may keep its
    downloads in a directory tree of its own, and flattening it to a file name loses that.
    """
    resp = http.get(url, **{"transport": transport, **how_to_ask(source)})
    if not resp.ok:
        stamp(source, url, status="error", note=resp.why or f"http {resp.status}")
        return {"status": "error", "why": resp.why or f"http {resp.status}"}

    verdict, names = inspect(resp.body)
    if verdict in ("html", "empty") and not keep_anything:
        stamp(source, url, status="not_published", data=resp.body, note=verdict)
        return {"status": "not_published", "verdict": verdict}

    if rel is None:
        filename = name or resp.disposition or Path(url.split("?")[0]).name or "download"
        rel = f"{subdir}/{re.sub(r'[^A-Za-z0-9._-]', '_', filename)}"
    target = spice_source(source) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(resp.body)

    manifest = Manifest(source)
    manifest.add(url, rel, resp.body, note or verdict)
    manifest.save()
    stamp(source, url, status="downloaded", data=resp.body, note=verdict)

    written = 0
    if verdict in ("zip", "zip_no_model", "encrypted") and resp.body[:2] == b"PK":
        written = unpack(target, spice_source(source) / unpack_base(target, source, expected))
    return {"status": "downloaded", "path": rel, "verdict": verdict,
            "definitions": len(names), "unpacked": written}


# --- getting back what the tree has lost ------------------------------------------------------------
def recovery_targets(gone: list[dict]) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Map missing files onto the manifest entries that would restore them.

    A file under `extracted/<X>/` came out of an archive, so the thing to fetch again is the archive, not
    the file. The archive is matched by the name it unpacked into, and where a source kept no local copy
    of it — several were too large to keep — by being the only archive that source ever recorded.

    Matching on the recorded path alone is not enough, because an early recovery run wrote the path
    flattened: `raw/MAX4200.FAM` for a file that belongs at `raw/KiCad-Spice-Library/Models/Manufacturer/
    Maxim Integrated/MAX4200.FAM`, spaces turned to underscores. The entry still holds the right URL, so
    the file name recovers it when it names exactly one entry. Each target therefore carries the `rel` to
    write, and for a direct file that is **the catalogue's** path, never the manifest's: the catalogue
    says where the file belongs, and re-fetching to the recorded path would flatten it a second time.
    """
    targets: dict[tuple[str, str], dict] = {}
    unmatched: list[dict] = []
    by_source: dict[str, list[dict]] = {}
    for g in gone:
        by_source.setdefault(g["source"], []).append(g)

    for source, items in by_source.items():
        mf = spice_source_manifest(source)
        files = json.loads(mf.read_text(encoding="utf-8")).get("files", []) if mf.exists() else []
        with_url = [f for f in files if f.get("url")]
        archives = [f for f in with_url if not f.get("path")
                    or Path(f["path"]).suffix.lower() in (".zip", ".7z", ".rar", ".tgz", ".gz")]
        by_name: dict[str, list[dict]] = {}
        for f in with_url:
            by_name.setdefault(unquote(Path(f["url"].split("?")[0]).name).lower(), []).append(f)
        for g in items:
            parts = g["file"].split("/")
            rel = "/".join(parts[2:])
            hit = next((f for f in with_url if f.get("path") == rel), None)
            if hit is None and len(parts) > 3 and parts[2] == "extracted":
                stem = parts[3].lower()
                hit = next((f for f in with_url if f.get("path") and Path(f["path"]).stem.lower() == stem), None)
                if hit is None:
                    hit = next((f for f in archives
                                if Path(f["url"].split("?")[0]).stem.lower() == stem), None)
                if hit is None and len(archives) == 1:
                    hit = archives[0]                      # the one archive this source ever recorded
                rel = hit["path"] if hit and hit.get("path") else None   # fetch the archive, not the member
            elif hit is None:
                same = by_name.get(Path(rel).name.lower(), [])
                hit = same[0] if len(same) == 1 else None  # one candidate only: two would be a guess
            if hit is None:
                unmatched.append(g)
            else:
                targets.setdefault((source, hit["url"]), dict(hit, rel=rel))
    return [(s, f) for (s, _), f in sorted(targets.items())], unmatched


def recover(gone: list[dict], only: str | None = None, limit: int = 0, dry: bool = False) -> dict:
    targets, unmatched = recovery_targets(gone)
    if only:
        targets = [(s, f) for s, f in targets if s == only]
    if limit:
        targets = targets[:limit]
    counts = {"targets": len(targets), "fetched": 0, "verified": 0, "changed": 0,
              "failed": 0, "unpacked": 0, "unmatched": len(unmatched)}
    if dry:
        return counts
    expected = {g["file"] for g in gone}       # where the catalogue says each file belongs
    for source, entry in targets:
        got = fetch(source, entry["url"], rel=entry.get("rel"), note=entry.get("note", ""),
                    keep_anything=True, expected=expected)
        if got["status"] != "downloaded":
            counts["failed"] += 1
            # Keep what we knew: the checksum and the date we had it stay, and the row says it is gone.
            led = Ledger(model_state(source), stages=MODEL_STAGES, fields=MODEL_FIELDS,
                         versioned=MODEL_VERSIONED)
            if entry["url"] in led:
                led.skip(entry["url"], f"lost: {got.get('why') or got['status']}", status="lost")
                led.save()
            print(f"  ! {source:22s} {got.get('why') or got['status']:20s} {entry['url'][:70]}")
            continue
        counts["fetched"] += 1
        counts["unpacked"] += got.get("unpacked", 0)
        if entry.get("sha256"):
            now = Manifest(source).by_url(entry["url"])
            if now and now["sha256"] == entry["sha256"]:
                counts["verified"] += 1
            else:
                counts["changed"] += 1
                print(f"  ~ {source:22s} checksum differs from what we had: {entry['url'][:60]}")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download one URL into a source")
    f.add_argument("source")
    f.add_argument("--url", required=True)
    f.add_argument("--name", help="file name to store it under")
    f.add_argument("--note", default="")
    f.add_argument("--curl", action="store_true", help="some vendors answer curl and nothing else")
    r = sub.add_parser("recover", help="fetch again what the catalogue says the tree has lost")
    r.add_argument("--source")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    require(spice_models_root() / "sources", "fetching SPICE models")

    if a.cmd == "fetch":
        got = fetch(a.source, a.url, name=a.name, note=a.note,
                    transport="curl" if a.curl else "requests")
        print(json.dumps(got, ensure_ascii=False))
        return 0 if got["status"] == "downloaded" else 1

    from parts_index.core.config import spice_definitions
    from parts_index.models.index import missing
    if not spice_definitions().exists():
        print("no catalogue to compare against: run `make models-index` first", file=sys.stderr)
        return 1
    gone = missing(spice_definitions(), spice_models_root() / "sources")
    counts = recover(gone, only=a.source, limit=a.limit, dry=a.dry)
    print(f"{counts['targets']:,} downloads would restore {len(gone) - counts['unmatched']:,} files"
          if a.dry else
          f"{counts['fetched']:,} of {counts['targets']:,} fetched, {counts['verified']:,} matched their "
          f"old checksum, {counts['changed']:,} differ, {counts['failed']:,} failed, "
          f"{counts['unpacked']:,} files unpacked")
    if counts["unmatched"]:
        print(f"{counts['unmatched']:,} missing files have no URL recorded and cannot be fetched again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
