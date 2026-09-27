"""The data sheets a manufacturer publishes, read one by one to learn which parts each really covers.

    pidx datasheets harvest [--source onsemi_docs] [--list-only] [--limit N]

Some manufacturers list every document they publish in a sitemap: onsemi 6,449 data sheets, NXP 4,707.
The file name only names the first part of a sheet — onsemi's bc546-d.pdf documents BC546, BC547 and
BC548, and 1n914-d.pdf the 1N4148 as well — so a sheet is read before it is linked to anything: its
first page, where a manufacturer states which types the sheet covers, and the rest of its text for the
ordering tables.

Only sheets whose name points at a part this project knows are fetched, at the pace the site asks. Each
is kept just long enough to be read: its text goes to the private tree (so a better reader costs no
second visit) and the PDF is deleted. What is published is the fact and the link — the sheet's title,
revision, page count and checksum, and for each part it covers, how that was seen.

A part that is only mentioned — "complementary to the 2N3906", "replaces the MC1458" — is not covered by
the sheet, and is not linked to it.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

from parts_index.core import http
from parts_index.core.config import (
    datasheet_covers,
    datasheet_documents,
    datasheets_registry,
    datasheets_state,
    datasheets_text,
    known_parts,
    parts_census,
    schematics_parts,
)
from parts_index.core.ledger import Ledger, today
from parts_index.core.parts.extractor import KNOWN, base_part, canonical, family_of, norm

STAGES = ("fetch", "read")
VERSIONED = ("read",)
FIELDS = ("key", "url", "http", "bytes", "sha256", "fetch_at", "read_at", "read_v", "skip_reason")
READ_VERSION = "2"  # 2: no one-word titles; a stem is not a part when the full name is there
DOC_FIELDS = ("url", "maker", "title", "revision", "pages", "bytes", "sha256", "covers", "checked")
COVER_FIELDS = ("part", "url", "seen", "times")

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9\-]{2,20})(?![A-Za-z0-9])")
REVISION = re.compile(r"\bRev(?:ision)?\.?\s*:?\s*([A-Z]?\d{0,3}[A-Z]?)\b")
# "Complementary PNP type: BC556", "replaces MC1458", "see also": what follows names another part.
NOT_COVERED = re.compile(r"(complement\w*|replac\w*|see also|similar to|instead of|pin.compatible with|"
                         r"second source|equivalent)\W{0,12}(?:\w+\W{0,3}){0,4}$", re.I)
FIRST_PAGE = 2500       # characters of page one where a manufacturer names what the sheet covers
# Who is asking, in plain words. onsemi and NXP answer this and refuse the browser string the client
# otherwise sends (403 and 404 on 2026-09-27): a site that asks who is reading gets the true answer.
PROJECT_UA = "parts-index (+https://electrucio.github.io/parts-index/)"


def registry() -> dict:
    p = datasheets_registry()
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def known() -> set[str]:
    """Every part number the project knows: printed somewhere, in the dictionary or in a census."""
    out = set()
    for path, col in ((schematics_parts(), "part"), (known_parts(), "name")):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                out |= {r[col] for r in csv.DictReader(f)}
    for p in parts_census().parent.glob("*.csv"):
        with open(p, encoding="utf-8") as f:
            out |= {r["part"] for r in csv.DictReader(f)}
    return out


def head(url: str, strip: str = "") -> str:
    """The part a sheet's file name starts with: bc546-d.pdf -> BC546."""
    name = url.rsplit("/", 1)[-1].split("?")[0]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    if strip:
        name = re.sub(strip, "", name, flags=re.I)
    return name.upper()


def listing(source: str, entry: dict) -> list[str]:
    """Every data sheet the source's sitemaps name, fetched politely and never twice in one run."""
    urls: list[str] = []
    for sm in entry["sitemaps"]:
        r = http.get(sm, ua=PROJECT_UA, delay=float(entry.get("delay", http.DELAY)), max_bytes=64 << 20)
        if not r.ok:
            print(f"  {sm}: {r.why or r.status}", file=sys.stderr)
            continue
        body = r.body
        if sm.endswith(".gz") or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        keep = re.compile(entry["keep"])
        urls += [u for u in LOC.findall(body.decode("utf-8", "replace")) if keep.search(u)]
    return sorted(set(urls))


def wanted(urls: list[str], entry: dict, parts: set[str]) -> list[str]:
    """The sheets whose file name starts with a part this project knows, or with the type of one."""
    out = []
    for u in urls:
        h = head(u, entry.get("strip", ""))
        h2 = re.sub(r"[^A-Z0-9]", "", h)
        if h in parts or h2 in parts or base_part(h2) in parts:
            out.append(u)
    return out


def same_series(name: str, sheet_head: str) -> bool:
    """BF245B on the BF245A-B-C sheet, BC548C on bc546-d: the letters of the head and the first digits."""
    h = re.match(r"([A-Z]+\d{2})", sheet_head)
    return bool(h) and name.startswith(h.group(1))


def is_a_part(name: str) -> bool:
    """A name the extractor's families recognise, or the dictionary judged real. S12, LED1 and BIT0 are in
    some census list and on every other data sheet as a parameter or a pin: not parts."""
    return bool(family_of(name)) or norm(name) in KNOWN


def covered(pages: list[str], parts: set[str], sheet_head: str = "") -> dict[str, tuple[str, int]]:
    """The known parts a sheet documents, and how that was seen: on its first page, or only in its text
    (an ordering table). A name that follows "complementary to" or "replaces" is another part's.

    Two ways in. A part of the sheet's own series (BF245C on the BF245A-B-C sheet) needs its first page
    or two mentions. Any other part needs its first page, more than one mention, and to be recognisably a
    part: a sheet's first page names its related products once, and its register tables name S12 and
    LED1 dozens of times."""
    found: dict[str, tuple[str, int]] = {}
    counts: Counter = Counter()
    first: set[str] = set()
    for i, text in enumerate(pages):
        for m in TOKEN.finditer(text):
            tok = canonical(m.group(1)) or ""
            if not tok or not re.search(r"[A-Z]", tok) or not re.search(r"\d", tok):
                continue                     # 103 is a capacitor code and a page number before it is a part
            names = {n for n in (tok, base_part(tok)) if n in parts}
            if not names:
                continue
            before = text[max(0, m.start() - 60):m.start()]
            if NOT_COVERED.search(before):
                continue
            for n in names:
                counts[n] += 1
                if i == 0 and m.start() < FIRST_PAGE:
                    first.add(n)
    for n, c in counts.items():
        own = n == sheet_head or same_series(n, sheet_head)
        if (own and (n in first or c >= 2)) or (n in first and c >= 2 and is_a_part(n)):
            found[n] = ("first page" if n in first else "text", c)
    return {n: v for n, v in found.items() if not stem(n, found)}


def stem(name: str, found: dict) -> bool:
    """Whether a name is the start of another the sheet covers rather than a part: 1N400 and the
    placeholder 1N400X beside 1N4001. A letter after it is a grade, so BC846 beside BC846A stays."""
    root = name[:-1] if name.endswith("X") else name
    return any(o != name and o.startswith(root) and o[len(root):].isdigit() for o in found)


def read_pdf(data: bytes) -> tuple[list[str], dict]:
    import pymupdf  # the `ocr` extra: `uv sync --extra ocr`
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = [p.get_text() for p in doc]
    meta = doc.metadata or {}
    return pages, meta


def title_of(pages: list[str], meta: dict, sheet_head: str = "") -> str:
    """The sheet's own title, from the PDF's title field when that is one, and otherwise none: the first
    lines of a page are a web address, a legal notice or the maker's own sentence as often as a title, and
    the page shows the file name instead."""
    t = " ".join((meta.get("title") or "").split())
    # A title names the part and says what it is in a few words. "The TDA8920B is a high efficiency
    # class-D audio power amplifier with…" is the maker's sentence, not a title, and is not taken.
    sentence = re.search(r"\b(is|are|was|provides|offers|features)\b", t, re.I) or len(t) > 110
    # One word is a file name or a label ("BC447.rev3", "Document:"), not a title.
    if (len(t) >= 6 and len(t.split()) >= 2 and not sentence and "www." not in t.lower()
            and not re.fullmatch(r"[\w\-. ]+\.(?:pdf|docx?|indd|fm)", t, re.I)):
        return t
    return ""


def load(path: Path, key: tuple[str, ...]) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {tuple(r[k] for k in key): r for r in csv.DictReader(f)}


def save(path: Path, rows: dict, fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: rows[k].get(c, "") for c in fields})
    tmp.replace(path)


def run(source: str, entry: dict, limit: int = 0, list_only: bool = False, reread: bool = False) -> dict:
    parts = known()
    urls = listing(source, entry)
    todo = wanted(urls, entry, parts)
    print(f"{source}: {len(urls)} data sheets listed, {len(todo)} named after a known part")
    if list_only:
        return {"listed": len(urls), "wanted": len(todo)}
    led = Ledger(datasheets_state(source), stages=STAGES, fields=FIELDS, versioned=VERSIONED)
    docs = load(datasheet_documents(source), ("url",))
    covers = load(datasheet_covers(source), ("part", "url"))
    text_dir = datasheets_text(source)
    text_dir.mkdir(parents=True, exist_ok=True)
    n = {"fetched": 0, "read": 0, "failed": 0}
    delay = float(entry.get("delay", http.DELAY))
    for url in todo:
        if limit and n["fetched"] >= limit:
            break
        r = led.get(url)
        if r and r["skip_reason"]:
            continue
        if led.done(url, "read", version=READ_VERSION) and not reread:
            continue
        kept = text_dir / f"{head(url)}.json.gz"
        if led.done(url, "fetch") and kept.exists():
            held = json.loads(gzip.decompress(kept.read_bytes()))
            pages, meta, row = held["pages"], held.get("meta") or {}, led.get(url) or {}
            sha, size = row.get("sha256", ""), row.get("bytes", "")
        else:
            resp = http.get(url, ua=PROJECT_UA, delay=delay, max_bytes=40 << 20)
            n["fetched"] += 1
            if resp.status == 404:
                led.skip(url, "gone (404)", url=url, http=404)
                continue
            if not resp.ok or resp.kind != "pdf":
                n["failed"] += 1
                print(f"  {url}: {resp.why or resp.status} {resp.kind} — left for the next run", file=sys.stderr)
                continue
            try:
                pages, meta = read_pdf(resp.body)
            except Exception as e:                                       # a broken PDF is not a crash
                led.skip(url, f"unreadable PDF: {type(e).__name__}"[:60], url=url, http=resp.status)
                continue
            sha, size = resp.sha256, len(resp.body)
            kept.write_bytes(gzip.compress(json.dumps({"meta": meta, "pages": pages}).encode("utf-8")))
            led.stamp(url, "fetch", url=url, http=resp.status, bytes=size, sha256=sha)
        sheet_head = re.sub(r"[^A-Z0-9]", "", head(url, entry.get("strip", "")).split("_")[0])
        found = covered(pages, parts, sheet_head)
        text = "\n".join(pages[:1])
        rev = REVISION.search(text)
        docs[(url,)] = {"url": url, "maker": entry.get("maker", ""), "title": title_of(pages, meta, sheet_head),
                        "revision": rev.group(1) if rev else "", "pages": len(pages), "bytes": size,
                        "sha256": sha, "covers": len(found), "checked": today()}
        for k in [k for k in covers if k[1] == url]:
            del covers[k]
        for part, (seen, times) in found.items():
            covers[(part, url)] = {"part": part, "url": url, "seen": seen, "times": times}
        led.stamp(url, "read", version=READ_VERSION)
        n["read"] += 1
        if n["read"] % 25 == 0:
            led.save()
            save(datasheet_documents(source), docs, DOC_FIELDS)
            save(datasheet_covers(source), covers, COVER_FIELDS)
    led.save()
    save(datasheet_documents(source), docs, DOC_FIELDS)
    save(datasheet_covers(source), covers, COVER_FIELDS)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets harvest")
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many sheets fetched, per source")
    ap.add_argument("--list-only", action="store_true", help="read the sitemaps and say how many would be fetched")
    ap.add_argument("--reread", action="store_true", help="read the kept text again with today's reader")
    a = ap.parse_args(argv)
    reg = registry()
    names = a.source or [s for s, e in reg.items() if (e or {}).get("kind") == "document sitemap"
                         and e.get("status") == "active"]
    for s in names:
        e = reg.get(s) or {}
        if e.get("kind") != "document sitemap":
            print(f"{s}: not a document-sitemap source", file=sys.stderr)
            return 2
        print(f"{s}: {run(s, e, a.limit, a.list_only, a.reread)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
