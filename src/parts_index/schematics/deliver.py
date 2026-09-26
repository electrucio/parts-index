"""A delivery: material that arrived by hand instead of down a wire.

Somebody drops an archive into a source's download directory — recovered from the Wayback Machine,
saved out of a forum thread over the years, carried on a disk — and it has to enter the project the way
a download does or it is not in the project at all: one ledger row per file, with its checksum, what
kind of file it turned out to be, and the public URL a reader can be sent to when there is one.

Each member is keyed `delivery:<path inside the archive>`, and the file on disk is named after that key
exactly as a downloaded file is named after its URL, so no local path is ever recorded. Members of a
nested archive carry both: `delivery:a/b.zip!inner/c.pdf`.

Where a public URL comes from is declared in the registry, because it is a property of the delivery and
not of the code:

    passlabs_diyaudio:
      kind: delivery
      status: active
      delivery:
        role: schematic
        link:
          - match: '^diyAudio/([^/]+)/'
            url: 'https://www.diyaudio.com/community/threads/{1}/'

Everything that comes in is written to disk, whatever it is. A downloaded document is temporary here
because it can always be fetched again; a delivery cannot, and the archive is deleted once it is taken
in. So a board file, a Word document, an archive inside the archive — none of which anything here reads
— are stored all the same, with a `skip_reason` that keeps the reading stages away from them rather
than throwing the bytes away. The exception is a file some source already holds, which is recorded as
the duplicate it is and not stored twice.

Two things it refuses to read. A file whose checksum some source already holds is recorded as the
duplicate it is, naming the row that has it — the same drawing gathered twice is one document, and the
copy that arrived with a public URL is the one worth publishing. And a file that is not what its name
says it is, which in a hand-gathered pile is usually a saved error page, is recorded with that reason
instead of being stored as a document.

    python -m parts_index.schematics.deliver --source passlabs_diyaudio \
        --archive NelsonPass_PassLabs_Esquematicos.zip [--remove-archive]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path

from parts_index.core.config import downloads, schematics_dir, schematics_state
from parts_index.core.http import Response
from parts_index.core.ledger import Ledger
from parts_index.schematics.download import (
    DOCUMENT_KINDS,
    FILE_EXT,
    MARKUP,
    registry_entry,
    safe_name,
    say,
    summary,
)

ARCHIVE_SUFFIXES = (".zip",)
MAX_MEMBER = 200 << 20          # a member larger than this is not a document anybody reads


def kind_of(body: bytes) -> str:
    """What this actually is, by its first bytes — the same judgement the download stage makes."""
    return Response(200, "", body=body).kind or ("html" if MARKUP.search(body[:20000]) else "")


def link_for(cfg: dict, path: str) -> str:
    """The public URL for a member: the one the registry names for it, or the first pattern that matches.

    A pile gathered thread by thread shares a pattern; a pile recovered file by file does not, and each
    URL there was found and checked one at a time. Both belong in the registry, which is what gets
    published, rather than in a note somewhere.
    """
    named = (cfg.get("links") or {}).get(path)
    if named:
        return named
    for rule in cfg.get("link") or []:
        m = re.search(rule["match"], path)
        if m:
            url = rule["url"]
            for i, group in enumerate(m.groups(), 1):
                url = url.replace("{%d}" % i, group or "")
            return url
    return ""


def known_checksums() -> dict[str, tuple[str, str]]:
    """Every checksum any source already holds, so the same file is never taken in twice."""
    out: dict[str, tuple[str, str]] = {}
    for path in sorted((schematics_dir() / "state").glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("sha256"):
                    out.setdefault(row["sha256"], (path.stem, row["key"]))
    return out


def members(data: bytes, prefix: str = "") -> list[tuple[str, bytes]]:
    """(path, body) for every file in an archive, descending into the archives it contains."""
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir() or info.file_size > MAX_MEMBER:
                continue
            path = f"{prefix}{info.filename}"
            body = z.read(info.filename)
            if info.filename.lower().endswith(ARCHIVE_SUFFIXES) and body[:2] == b"PK":
                out.append((path, body))
                out += members(body, prefix=f"{path}!")
            else:
                out.append((path, body))
    return out


def deliver(source: str, archive: Path, *, remove: bool = False, log=say) -> dict:
    entry = registry_entry(source)
    if entry.get("status") != "active":
        raise SystemExit(f"{source} is '{entry.get('status')}' in the registry; set it to active to take a delivery")
    cfg = entry.get("delivery")
    if cfg is None:
        raise SystemExit(f"{source} has no `delivery:` block: that is how a source opts into this stage")
    if not archive.exists():
        raise SystemExit(f"no archive at {archive}")

    data = archive.read_bytes()
    led = Ledger(schematics_state(source))
    seen = known_checksums()
    counts: Counter = Counter()

    # What arrived, as one row: the checksum of the pile itself, so the delivery can be identified again.
    led.stamp(f"delivery:{archive.name}", "download", role="archive", type="zip", bytes=len(data),
              sha256=hashlib.sha256(data).hexdigest())
    led.row(f"delivery:{archive.name}")["skip_reason"] = "unpacked, and its members are the documents"

    inside = members(data)
    # Strip the single top folder an archive usually carries, so keys read as the delivery not the packer.
    tops = {p.split("/", 1)[0] for p, _ in inside}
    strip = len(tops) == 1 and any("/" in p for p, _ in inside)
    log(f"{source}: {len(inside)} files in {archive.name}")

    for path, body in inside:
        rel = path.split("/", 1)[1] if strip and "/" in path else path
        key = f"delivery:{rel}"
        digest = hashlib.sha256(body).hexdigest()
        kind = kind_of(body)
        url = link_for(cfg, rel)
        role = cfg.get("role", "document")

        if digest in seen and seen[digest][1] != key:
            held_by, held_key = seen[digest]
            led.stamp(key, "download", role=role, type=kind, bytes=len(body), sha256=digest, url=url)
            led.row(key)["skip_reason"] = f"same file as {held_by}: {held_key}"
            counts[f"already held by {held_by}"] += 1
            continue

        target = downloads(source) / (kind or "other") / safe_name(key, kind or "other")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        led.stamp(key, "download", role=role, type=kind, bytes=len(body), sha256=digest, url=url)
        seen[digest] = (source, key)

        # Kept either way; the reason only tells the reading stages to leave it alone. A delivery taken in
        # again after a reader was added is classified afresh, so the old reason goes first.
        led.row(key)["skip_reason"] = ""
        if not kind:
            led.row(key)["skip_reason"] = "not a document"
            counts["kept, nothing reads it"] += 1
        elif kind not in DOCUMENT_KINDS and kind != "html":
            led.row(key)["skip_reason"] = f"{kind}, which nothing here reads"
            counts["kept, nothing reads it"] += 1
        elif FILE_EXT.search(rel) and kind not in DOCUMENT_KINDS:
            led.row(key)["skip_reason"] = "not the declared file type"      # a saved error page, usually
            counts["not the declared file type"] += 1
        else:
            counts[kind] += 1
            counts["with a public link"] += 1 if url else 0

    led.save()
    log(f"{source}: {summary(counts)}")
    if remove:
        archive.unlink()
        log(f"{source}: {archive.name} removed; what it held is in the ledger with its checksum")
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics deliver", description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True, help="a source with a `delivery:` block")
    ap.add_argument("--archive", required=True, help="the archive, relative to that source's download directory")
    ap.add_argument("--remove-archive", action="store_true", help="delete it once its members are recorded")
    args = ap.parse_args(argv)
    path = Path(args.archive)
    if not path.is_absolute():
        path = downloads(args.source) / path
    deliver(args.source, path, remove=args.remove_archive)
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
