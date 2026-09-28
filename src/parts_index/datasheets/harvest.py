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
from urllib.parse import urljoin

import yaml

from parts_index.core import http
from parts_index.core.config import (
    datasheet_covers,
    datasheet_documents,
    datasheets_cache,
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
READ_VERSION = "12"  # 12: a family-named sheet covers its members (l78.pdf: L7805)
DOC_FIELDS = ("url", "maker", "title", "revision", "pages", "bytes", "sha256", "covers", "checked", "copy")
COVER_FIELDS = ("part", "url", "seen", "times")

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9\-]{2,20})(?![A-Za-z0-9])")
REVISION = re.compile(r"\bRev(?:ision)?\.?\s*:?\s*([A-Z]?\d{0,3}[A-Z]?)\b")
# "Complementary PNP type: BC556", "replaces MC1458", "see also": what follows names another part.
NOT_COVERED = re.compile(r"(complement\w*|replac\w*|\bsee\b|related products?|similar to|instead of|pin.compatible with|"
                         r"second source|equivalent)\W{0,12}(?:\w+\W{0,3}){0,4}$", re.I)
FIRST_PAGE = 2500       # characters of page one where a manufacturer names what the sheet covers
# The head of page one, where a sheet lists the types it documents ("MJE2955T / MJE3055T", "BD135 - BD136
# BD139 - BD140"). A part of another series counts only there: further down a sheet names the parts it
# is measured against ("Fits OP07, 5534A sockets", at 959 characters on the OP27 sheet).
HEADER = 400
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


KINDS = ("document sitemap", "document page", "product pages", "wayback")
CDX = "https://web.archive.org/cdx/search/cdx"
HREF = re.compile(r'href="([^"]+)"')
PAGE_TITLE = re.compile(r"<title>([^<]*)</title>", re.I)


def fetch_text(url: str, entry: dict) -> str:
    r = http.get(url, ua=PROJECT_UA, delay=float(entry.get("delay", http.DELAY)), max_bytes=64 << 20)
    if not r.ok:
        print(f"  {url}: {r.why or r.status}", file=sys.stderr)
        return ""
    body = r.body
    if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf-8", "replace")


def listing(source: str, entry: dict) -> dict[str, str]:
    """Every data sheet the source lists, with the name its listing files it under when that is not in
    the file name ("" otherwise). Three shapes of listing:

    document sitemap  the sitemaps name the PDFs themselves (onsemi, NXP);
    document page     one or a few pages link every PDF (THAT's data sheet page, JJ's downloads);
    product pages     the sitemaps name product pages, and each links its own sheet (Linear Systems,
                      whose PDFs are named by a hash: the page's title says which part it is)."""
    keep = re.compile(entry["keep"])
    kind = entry.get("kind")
    out: dict[str, str] = {}
    if kind == "document sitemap":
        for sm in entry["sitemaps"]:
            out |= {u: "" for u in LOC.findall(fetch_text(sm, entry)) if keep.search(u)}
    elif kind == "document page":
        for page in entry["pages"]:
            out |= {u: "" for u in (urljoin(page, h) for h in HREF.findall(fetch_text(page, entry)))
                    if keep.search(u)}
    elif kind == "product pages":
        locs = [u for sm in entry["sitemaps"] for u in LOC.findall(fetch_text(sm, entry))]
        subs = [u for u in locs if u.endswith(".xml") and re.search(entry.get("sitemaps_keep", "$^"), u)]
        locs += [u for sm in subs for u in LOC.findall(fetch_text(sm, entry))]   # one level of index
        pages = sorted({u for u in locs if not u.endswith(".xml") and re.search(entry["pages_keep"], u)})
        link, strip = re.compile(entry["sheet_link"]), entry.get("title_strip", "")
        cache = datasheets_cache(source)
        cache.mkdir(parents=True, exist_ok=True)
        for page in pages:
            kept = cache / (re.sub(r"[^A-Za-z0-9]+", "_", page.split("://", 1)[-1]) + ".html.gz")
            if kept.exists():
                html_ = gzip.decompress(kept.read_bytes()).decode("utf-8", "replace")
            else:
                html_ = fetch_text(page, entry)
                if not html_:
                    continue
                kept.write_bytes(gzip.compress(html_.encode("utf-8")))
            m, t = link.search(html_), PAGE_TITLE.search(html_)
            if m and keep.search(m.group(1)):
                out.setdefault(m.group(1), re.sub(strip, "", t.group(1)).strip() if t and strip else "")
    return dict(sorted(out.items()))


def wayback(entry: dict) -> dict[str, dict]:
    """The data sheets the Internet Archive holds under a maker's own addresses, for a maker whose site
    refuses scripts (ST, Analog Devices): one CDX query per address prefix lists every PDF captured
    there. Addresses whose captures are the same file (tl072.pdf, tl072a.pdf, tl072b.pdf) are one
    sheet: the shortest name stands for it and the others are the maker's own statement that it serves
    that sheet for those parts. The sheet is read from the archived copy; the maker's address is what
    is published, with the copy beside it."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for prefix in entry["prefixes"]:
        q = (f"{CDX}?url={prefix}&matchType=prefix&filter=statuscode:200&filter=mimetype:application/pdf"
             "&collapse=urlkey&fl=original,timestamp,digest&output=json")
        try:
            got = json.loads(fetch_text(q, entry) or "[]")[1:]
        except ValueError:
            got = []
        for original, stamp, digest in got:
            url = re.sub(r"^https?://([^/:]+)(:\d+)?", lambda m: "https://" + m.group(1).lower(), original)
            url = url.split("?")[0].rstrip(".")
            # Renesas' /document/dst/<part>-data-sheet addresses serve PDFs without saying so in the name.
            if (url.lower().endswith(".pdf") or entry.get("pdf_suffix") is False) and re.search(entry.get("keep", ""), url):
                groups.setdefault(digest, []).append((url, f"https://web.archive.org/web/{stamp}id_/{original}"))
    out: dict[str, dict] = {}
    for members in groups.values():
        members = sorted(set(members), key=lambda m: (len(head(m[0])), m[0]))
        url, copy = members[0]
        if url not in out:
            out[url] = {"copy": copy, "also": sorted({m[0] for m in members[1:]} - {url})}
    return out


def renamed(h: str, entry: dict, parts: set[str]) -> str:
    """A file name the maker wrote without its prefix, given it back: Linear Technology filed the LT1028
    as 1028fd.pdf (the number, then the sheet's revision letters). `numbered: [LT, LTC, LTM]` names
    the prefixes to try; the first that makes a known part wins."""
    m = re.fullmatch(r"(\d{3,5})F[A-Z]{0,2}", h)
    if m:
        for p in entry.get("numbered", []):
            if p + m.group(1) in parts:
                return p + m.group(1)
    return h


def a_family(h: str, parts: set[str]) -> bool:
    """A sheet named after a family (ST's l78.pdf, l79l.pdf): some known part starts with the name."""
    return bool(re.search(r"\d", h)) and 3 <= len(h) <= 6 and any(p.startswith(h) for p in parts)


def wanted(urls: dict[str, str] | list[str], entry: dict, parts: set[str]) -> list[str]:
    """The sheets whose file name starts with a part this project knows, or with the type of one. A
    source small enough to read whole (`all: true`) gives every sheet it lists."""
    if entry.get("all"):
        return list(urls)
    out = []
    for u in urls:
        h = head(u, entry.get("strip", ""))
        h2 = re.sub(r"[^A-Z0-9]", "", h)
        if h in parts or h2 in parts or base_part(h2) in parts:
            out.append(u)
    return out


def same_series(name: str, sheet_head: str, digits: int = 2) -> bool:
    """BF245B on the BF245A-B-C sheet, BC548C on bc546-d: the letters of the head and the first digits.
    A maker that numbers its series by three (THAT's 1240 series is 1240, 1243 and 1246, and its 1250
    another product) says so with `series: 3`."""
    # A JEDEC number's series is all its digits but the last: 2N4391-2N4393 is the 2N439 series and
    # 2N4351 another part; 3N163 and 3N164 share one sheet.
    h = re.match(rf"(\d[A-Z]+\d+(?=\d)|[A-Z]+\d{{{digits}}})", sheet_head)
    return bool(h) and name.startswith(h.group(1))


def is_a_part(name: str) -> bool:
    """A name the extractor's families recognise, or the dictionary judged real. S12, LED1 and BIT0 are in
    some census list and on every other data sheet as a parameter or a pin: not parts."""
    return bool(family_of(name)) or norm(name) in KNOWN


def nearest(tok: str, parts: set[str]) -> str:
    """The longest known part an ordering code starts with, letters dropped one at a time from the end:
    LM317LZ is an LM317L before it is an LM317, BC547BTA a BC547B."""
    for k in range(1, 4):
        if (len(tok) > k and tok[-k:].isalpha() and tok[:-k] in parts and tok[-k - 1].isalnum()
                and re.search(r"[A-Z]", tok[:-k])):                  # 45A is 45 amperes, not a part "45"
            return tok[:-k]
    b = base_part(tok)
    return b if b != tok and b in parts else ""


# A family written with a lower-case x where its digits vary: TSV91x, SMAJxxA, TL07xx, 1N4x48.
WILD = re.compile(r"(?<![A-Za-z0-9])(\d?[A-Z]{1,6}\d*)(x{1,3})([A-Z0-9]{0,3})(?![A-Za-z0-9])")   # also 1N4x48


def listed(text: str, parts: set[str], prefix: str = "") -> tuple[set[str], list[re.Pattern]]:
    """The parts a sheet's head lists, and the families it writes with an x."""
    names = {canonical(m.group(1)) or "" for m in TOKEN.finditer(text)}
    names |= {prefix + n for n in names if prefix and re.fullmatch(r"\d{3,5}[A-Z]{0,2}", n)}
    wild = [re.compile(rf"{w.group(1)}[0-9A-Z]{{{len(w.group(2))},{len(w.group(2)) + 1}}}{w.group(3)}[A-Z]{{0,3}}$")
            for w in WILD.finditer(text)]
    return names & parts, wild


def covered(pages: list[str], parts: set[str], sheet_head: str = "", prefix: str = "",
            heads: tuple[str, ...] = (), series: int = 2, own_only: bool = False,
            title: str = "") -> dict[str, tuple[str, int]]:
    """The known parts a sheet documents, and how that was seen: on its first page, or only in its text
    (an ordering table). A name that follows "complementary to" or "replaces" is another part's.

    Two ways in. A part of the sheet's own series (BF245C on the BF245A-B-C sheet) needs its first page
    or two mentions. Any other part needs its first page, more than one mention, and to be recognisably a
    part: a sheet's first page names its related products once, and its register tables name S12 and
    LED1 dozens of times.

    A maker that writes its prefix apart from the number ("THAT 1646", or "1646" alone on a THAT sheet)
    is read with its `prefix`: the number is that maker's part. A sheet named after several parts
    (THAT_1606-1646) has them all as `heads`; a maker whose sheets name companion products by number on
    their first page (THAT's 1570 sheet, the 1510 it pairs with) is read `own_only`: its sheets cover
    the series they are named after and nothing else."""
    found: dict[str, tuple[str, int]] = {}
    counts: Counter = Counter()
    heads_all = {h for h in (sheet_head, *heads) if h}
    first: set[str] = set()
    header, wild = listed((pages[0][:HEADER] if pages else "") + "\n" + title, parts, prefix)
    header |= {h for h in (sheet_head, *heads) if h}
    for i, text in enumerate(pages):
        for m in TOKEN.finditer(text):
            tok = canonical(m.group(1)) or ""
            if prefix and re.fullmatch(r"\d{3,5}[A-Z]{0,2}", tok):
                tok = prefix + tok
            if not tok or not re.search(r"\d", tok) or (not re.search(r"[A-Z]", tok) and not (own_only and tok in heads_all)):
                continue                     # 103 is a capacitor code and a page number before it is a part,
                                             # unless the sheet is filed under it (JJ's 6550)
            # The name itself when it is a part: LM317L is not an LM317, though search folds it there.
            names = {tok} if tok in parts else {n for n in (nearest(tok, parts),) if n}
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
        own = any(n == h or same_series(n, h, series) for h in (sheet_head, *heads) if h)
        if own_only and not own:
            continue
        # Within the series, a name the head does not list, nor a variant of one it lists (TL431A under
        # "TL431"), nor one of a family it writes with an x (TSV912 under "TSV91x"), is held to the head
        # too: the AD623 sheet measures itself against the AD620.
        # ... or a member of the family the sheet is named after (ST's l78.pdf heads "L78": L7805, L7812)
        in_head = (n in header or any(len(h) >= 4 and n.startswith(h) for h in header)
                   or any(w.match(n) for w in wild)
                   or any(len(h) >= 3 and re.search(r"\d", h) and n.startswith(h) and re.fullmatch(r"\d{2}[A-Z]{0,4}", n[len(h):])
                          for h in heads_all))
        if own and not own_only and not in_head:
            own = False
        if (own and (n in first or c >= 2)) or (in_head and c >= 2 and is_a_part(n)):
            found[n] = ("first page" if n in first else "text", c)
    # A type whose grades the sheet covers, two or more of them, is the sheet's too: BF245 on the
    # BF245A-B-C sheet, BC547 beside BC547A/B/C. One grade alone (TIP31C) says nothing about the others.
    for base in {n[:-1] for n in found if re.fullmatch(r".*\d[A-C]", n)} & parts - set(found):
        grades = [n for n in found if n[:-1] == base and n[-1] in "ABC"]
        if len(grades) >= 2:
            found[base] = (found[grades[0]][0], sum(found[g][1] for g in grades))
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
    held_by = wayback(entry) if entry.get("kind") == "wayback" else {}
    urls = {u: "" for u in held_by} if held_by else listing(source, entry)
    if held_by:
        strip = entry.get("strip", "")
        def wanted_here(u: str) -> bool:
            # the name, the known part it is an ordering code of (1ss356tw11 -> 1SS356), or a family
            hs = {renamed(re.sub(r"[^A-Z0-9]", "", head(x, strip)), entry, parts) for x in (u, *held_by[u]["also"])}
            return bool((hs | {nearest(h, parts) for h in hs}) & parts) or (
                bool(entry.get("families")) and any(a_family(h, parts) for h in hs))
        todo = [u for u in urls if wanted_here(u)]
    else:
        todo = wanted(urls, entry, parts)
    prefix = entry.get("prefix", "")
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
            resp = http.get(held_by[url]["copy"] if held_by else url, ua=PROJECT_UA, delay=delay, max_bytes=40 << 20)
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
        names = [urls.get(url)] if urls.get(url) else re.split(entry.get("split", "_"), head(url, entry.get("strip", "")))
        also = [head(a, entry.get("strip", "")) for a in (held_by.get(url) or {}).get("also", [])]
        names += also
        names = [renamed(re.sub(r"[^A-Z0-9]", "", n.upper()), entry, parts) for n in names if re.search(r"\d", n)] or [""]
        names = [n if not prefix or n.startswith(prefix) else prefix + n for n in names]
        sheet_head = names[0]
        found = covered(pages, parts, sheet_head, prefix, tuple(names[1:]), int(entry.get("series", 2)),
                        bool(entry.get("own_only")), " ".join((meta.get("title") or "").split()))
        text = "\n".join(pages[:1])
        rev = REVISION.search(text)
        title = title_of(pages, meta, sheet_head) if entry.get("titles", True) else ""
        docs[(url,)] = {"url": url, "maker": entry.get("maker", ""), "title": title,
                        "revision": rev.group(1) if rev else "", "pages": len(pages), "bytes": size,
                        "sha256": sha, "covers": len(found), "checked": today(),
                        "copy": (held_by.get(url) or {}).get("copy", "")}
        for k in [k for k in covers if k[1] == url]:
            del covers[k]
        for part, (seen, times) in found.items():
            covers[(part, url)] = {"part": part, "url": url, "seen": seen, "times": times}
        for part in {n for n in (re.sub(r"[^A-Z0-9]", "", a) for a in also) if re.search(r"[A-Z]", n)} & parts - set(found):
            # The maker serves this very file at an address named after the part (tl072a.pdf).
            covers[(part, url)] = {"part": part, "url": url, "seen": "its own address", "times": 0}
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
    names = a.source or [s for s, e in reg.items() if (e or {}).get("kind") in KINDS
                         and e.get("status") == "active"]
    for s in names:
        e = reg.get(s) or {}
        if e.get("kind") not in KINDS:
            print(f"{s}: not a source the harvest reads ({', '.join(KINDS)})", file=sys.stderr)
            return 2
        if e.get("status") in ("paused", "blocked"):
            print(f"{s}: {e['status']} — see its notes in the registry; not asked", file=sys.stderr)
            continue
        print(f"{s}: {run(s, e, a.limit, a.list_only, a.reread)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
