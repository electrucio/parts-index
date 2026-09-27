"""The pages of old databooks that head a part: RCA's 1966 transistor manual, Motorola's and National's
data books, as the Internet Archive holds bitsavers' scans of them.

    pidx datasheets databooks [--source archive_databooks] [--limit N] [--list-only] [--reread]

A databook is a maker's data sheets bound together, and for a part that went out of production before
makers kept PDFs on the web it is often the only sheet there is — several makers' sheets for the same
type, decades apart, which is the redundancy a later reading of specifications needs. The archive has
already read each scan: `_djvu.xml` holds its text page by page, and `_page_numbers.json` the number
printed on each page. So nothing is OCR'd here and no PDF is fetched.

A page covers a part when the part heads it: named in its first lines, where a sheet puts its type. A
page that heads many parts is an index or a selection guide, not a sheet, and covers none. What is
published is the link to the page, the book and the maker; the text stays in the private tree.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import re
import sys
from urllib.parse import quote, unquote, urljoin

from parts_index.core import http
from parts_index.core.config import datasheet_pages, datasheets_state, datasheets_text, schematics_parts
from parts_index.core.ledger import Ledger, today
from parts_index.core.parts import catalogue
from parts_index.core.parts.extractor import canonical, family_of
from parts_index.datasheets.harvest import PROJECT_UA, TOKEN, is_a_part, known, nearest, read_pdf, registry

ARCHIVE = "https://archive.org"
STAGES = ("fetch", "read")
VERSIONED = ("read",)
FIELDS = ("key", "url", "http", "bytes", "fetch_at", "read_at", "read_v", "skip_reason")
READ_VERSION = "3"  # 3: JIS names the OCR misread (25A1770, 2S41770) are read as JIS
PAGE_FIELDS = ("part", "book", "leaf", "printed", "maker", "title", "year", "checked", "kind", "link")
TABLE_PAGES = 2         # in a tabulation, the first pages a part is listed on are enough to find it
HEAD_LINES = 6          # a sheet names its type in its first lines
MAX_HEADS = 4           # a page heading more parts than this is an index or a selector guide
MAX_ON_PAGE = 12        # nor is a page naming more than this anywhere on it a sheet
NOT_A_SHEET = re.compile(r"\b(index|selection|selector|chart|cross.?reference|contents|replacement guide)\b", re.I)
YEAR = re.compile(r"(?<!\d)(19[3-9]\d|20[0-2]\d)(?!\d)")   # also "1997年版"
LINE = re.compile(r"<LINE>(.*?)</LINE>", re.S)
WORD = re.compile(r"<WORD[^>]*>([^<]*)</WORD>")


def books(entry: dict) -> list[dict]:
    """The items the registry names, or every item the archive's search finds for its query, kept when its
    title says it is a semiconductor book and not one of the kinds the registry leaves out."""
    if entry.get("items"):
        return [{"identifier": i, "title": ""} for i in entry["items"]]
    if entry.get("pages"):              # PDF books linked from a site's own pages (worldradiohistory)
        keep = re.compile(entry["keep"], re.I)
        out: dict[str, dict] = {}
        for page in entry["pages"]:
            r = http.get(page, ua=PROJECT_UA, delay=float(entry.get("delay", http.DELAY)), max_bytes=16 << 20)
            for href in re.findall(r'href="([^"]+\.pdf)"', r.text(None) if r.ok else "", re.I):
                url = urljoin(page, href.strip())
                if keep.search(url):
                    name = re.sub(r"\.pdf$", "", unquote(url.rsplit("/", 1)[-1]), flags=re.I)
                    out[url] = {"identifier": url, "title": re.sub(r"[-_]+", " ", name).strip(), "pdf": True}
        return list(out.values())
    q = (f"{ARCHIVE}/advancedsearch.php?q={quote(entry['query'])}&fl%5B%5D=identifier&fl%5B%5D=title"
         f"&rows=10000&output=json")
    r = http.get(q, ua=PROJECT_UA, delay=float(entry.get("delay", http.DELAY)), max_bytes=32 << 20)
    docs = json.loads(r.body or b"{}").get("response", {}).get("docs", []) if r.ok else []
    keep, drop = re.compile(entry["include"], re.I), re.compile(entry["exclude"], re.I)
    drop_id = re.compile(entry.get("exclude_ids") or "$^")
    drop_title = re.compile(entry.get("exclude_titles") or "$^")
    return [d for d in docs if keep.search(d.get("title", "")) and not drop.search(d.get("title", ""))
            and not drop_id.search(d["identifier"]) and not drop_title.search(d.get("title", ""))]


def maker_of(title: str) -> str:
    """The maker a title names: "components :: rca :: dataBooks :: …" is RCA's; outside bitsavers, the
    longest organisation name or alias the title contains as words ("Philips Data Handbook …")."""
    parts = [p.strip() for p in title.split("::")]
    vendor = parts[1] if parts and parts[0] == "components" and len(parts) > 1 else parts[0]
    vendor = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", vendor).lower()
    found = catalogue.maker_of(vendor)[0] if "::" in title else ""
    if found:
        return found
    low = f" {re.sub(r'[^a-z0-9]+', ' ', title.lower())} "
    names = [(len(a), mid) for mid, m in catalogue.makers().items()
             for a in [m.get("name", "").lower(), *(m.get("aliases") or [])] if a and len(a) >= 3
             and f" {re.sub(r'[^a-z0-9]+', ' ', a)} " in low]
    return max(names)[1] if names else ""


def read_pages(xml: str) -> list[str]:
    """The text of each page of a `_djvu.xml`, line by line."""
    out = []
    for obj in xml.split("<OBJECT")[1:]:
        lines = [" ".join(html.unescape(w) for w in WORD.findall(line)) for line in LINE.findall(obj)]
        out.append("\n".join(x for x in lines if x.strip()))
    return out


# How the archive's OCR misreads a JIS name: the S as a 5 and the A as a 4 ("25A1770", "2S41770" in CQ's
# 1997 tables are the 2SA1770). A 2 followed by 5 or S and a class letter, or 4 for A, then digits, is one.
JIS_OCR = re.compile(r"(?<![A-Za-z0-9])2[5S]([ABCDJK4])\s?(\d{2,4}[A-Z]{0,2})(?![A-Za-z0-9])")


def unmangle(text: str) -> str:
    return JIS_OCR.sub(lambda m: "2S" + ("A" if m.group(1) == "4" else m.group(1)) + m.group(2), text)


def names(text: str, parts: set[str]) -> set[str]:
    out = set()
    text = unmangle(text)
    for m in TOKEN.finditer(text):
        tok = canonical(m.group(1)) or ""
        if tok and re.search(r"\d", tok) and re.search(r"[A-Z]", tok):
            n = tok if tok in parts else nearest(tok, parts)
            # "Fig. 78a" is a figure, and a letter and a number (A13, X1000) is a pin or an axis unless
            # the extractor knows it as a family (J203 is a JFET)
            if n and is_a_part(n) and (family_of(n) or not re.fullmatch(r"[A-Z]\d+[A-Z]?", n)):
                out.add(n)
    return out


def heads(page: str, parts: set[str]) -> set[str]:
    """The known parts a page's first lines name — the type a sheet starts with. An index, a selection
    chart or an application circuit's parts list names many parts, and heads none."""
    lines = page.splitlines()
    if NOT_A_SHEET.search("\n".join(lines[:3])) or len(names(page, parts)) > MAX_ON_PAGE:
        return set()
    # A sheet's heading is a short line of its own ("2N140 TRANSISTOR", "POWER TRANSISTOR 2N277"); a
    # part named inside a sentence at the top of a continued page ("such as the 2N408") heads nothing.
    found = set().union(*(names(x, parts) for x in lines[:HEAD_LINES] if len(x.split()) <= 5), set())
    return found if len(found) <= MAX_HEADS else set()


def load(source: str) -> dict:
    p = datasheet_pages(source)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {(r["part"], r["book"], r["leaf"]): r for r in csv.DictReader(f)}


def save(source: str, rows: dict) -> None:
    p = datasheet_pages(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PAGE_FIELDS, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows, key=lambda k: (k[0], k[1], int(k[2]))):
            w.writerow(rows[k])
    tmp.replace(p)


def run(source: str, entry: dict, limit: int = 0, list_only: bool = False, reread: bool = False) -> dict:
    items = books(entry)
    print(f"{source}: {len(items)} books")
    if list_only:
        return {"books": len(items)}
    parts = known()
    # A tabulation lists every device of its day; only the parts this index holds are kept from it.
    with open(schematics_parts(), encoding="utf-8") as f:
        indexed = {r["part"] for r in csv.DictReader(f)} & parts
    led = Ledger(datasheets_state(source), stages=STAGES, fields=FIELDS, versioned=VERSIONED)
    rows = load(source)
    text_dir = datasheets_text(source)
    text_dir.mkdir(parents=True, exist_ok=True)
    delay = float(entry.get("delay", http.DELAY))
    n = {"fetched": 0, "read": 0, "pages": 0, "failed": 0}
    for item in items:
        ident, title = item["identifier"], item.get("title", "")
        if limit and n["fetched"] >= limit:
            break
        r = led.get(ident)
        if (r and r["skip_reason"]) or (led.done(ident, "read", version=READ_VERSION) and not reread):
            continue
        kept = text_dir / (f"{ident}.json.gz" if not item.get("pdf")
                           else re.sub(r"[^A-Za-z0-9._-]+", "_", unquote(ident.rsplit("/", 1)[-1]))[:150] + ".json.gz")
        if led.done(ident, "fetch") and kept.exists():
            held = json.loads(gzip.decompress(kept.read_bytes()))
        elif item.get("pdf"):
            # No text layer to borrow: the PDF is read here, its text kept private, and the PDF let go.
            resp = http.get(ident, ua=PROJECT_UA, delay=delay, max_bytes=800 << 20)
            n["fetched"] += 1
            if not resp.ok or resp.kind != "pdf":
                n["failed"] += 1
                print(f"  {ident}: {resp.why or resp.status} — left for the next run", file=sys.stderr)
                continue
            try:
                pages, _meta = read_pdf(resp.body)
            except Exception as e:                                        # a broken PDF is not a crash
                led.skip(ident, f"unreadable PDF: {type(e).__name__}"[:60], url=ident, http=resp.status)
                continue
            held = {"title": title, "pages": pages, "printed": {}}
            kept.write_bytes(gzip.compress(json.dumps(held).encode("utf-8")))
            led.stamp(ident, "fetch", url=ident, http=resp.status, bytes=len(resp.body))
        else:
            meta = http.get(f"{ARCHIVE}/metadata/{ident}", ua=PROJECT_UA, delay=delay, max_bytes=16 << 20)
            files = json.loads(meta.body or b"{}").get("files", []) if meta.ok else []
            title = title or json.loads(meta.body or b"{}").get("metadata", {}).get("title", "") if meta.ok else title
            xml = next((f["name"] for f in files if f["name"].endswith("_djvu.xml")), None)
            if not xml:
                led.skip(ident, "no text layer in the archive", url=f"{ARCHIVE}/details/{ident}")
                continue
            resp = http.get(f"{ARCHIVE}/download/{ident}/{quote(xml)}", ua=PROJECT_UA, delay=delay,
                            max_bytes=200 << 20)
            n["fetched"] += 1
            if not resp.ok:
                n["failed"] += 1
                print(f"  {ident}: {resp.why or resp.status} — left for the next run", file=sys.stderr)
                continue
            pages = read_pages(resp.body.decode("utf-8", "replace"))
            nums = next((f["name"] for f in files if f["name"].endswith("_page_numbers.json")), None)
            printed: dict[str, str] = {}
            if nums:
                pr = http.get(f"{ARCHIVE}/download/{ident}/{quote(nums)}", ua=PROJECT_UA, delay=delay)
                if pr.ok:
                    printed = {str(p.get("leafNum")): str(p.get("pageNumber") or "")
                               for p in json.loads(pr.body or b"{}").get("pages", [])}
            held = {"title": title, "pages": pages, "printed": printed}
            kept.write_bytes(gzip.compress(json.dumps(held).encode("utf-8")))
            led.stamp(ident, "fetch", url=f"{ARCHIVE}/details/{ident}", http=resp.status, bytes=len(resp.body))
        title = title or held.get("title", "")
        table = entry.get("mode") == "table"
        # A tabulation is nobody's data sheet: its publisher (CQ, D.A.T.A.) made no part, so no maker.
        maker, year = ("" if table else maker_of(title)), (YEAR.search(title) or [""])[0]
        book = kept.name.removesuffix(".json.gz") if item.get("pdf") else ident
        for k in [k for k in rows if k[1] == book]:
            del rows[k]
        listed: dict[str, int] = {}
        for leaf, page in enumerate(held["pages"], start=1):
            found = (names(page, indexed) if table else heads(page, parts))
            for part in found:
                if table:
                    listed[part] = listed.get(part, 0) + 1
                    if listed[part] > TABLE_PAGES:
                        continue
                rows[(part, book, str(leaf))] = {
                    "part": part, "book": book, "leaf": leaf, "printed": held["printed"].get(str(leaf), ""),
                    "maker": maker, "title": title.split("::")[-1].strip(), "year": year, "checked": today(),
                    "kind": "table" if table else "sheet", "link": ident if item.get("pdf") else ""}
                n["pages"] += 1
        led.stamp(ident, "read", version=READ_VERSION)
        n["read"] += 1
        if n["read"] % 5 == 0:
            led.save()
            save(source, rows)
    led.save()
    save(source, rows)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets databooks")
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many books fetched")
    ap.add_argument("--list-only", action="store_true", help="say how many books the search keeps")
    ap.add_argument("--reread", action="store_true", help="read the kept text again with today's reader")
    a = ap.parse_args(argv)
    reg = registry()
    names = a.source or [s for s, e in reg.items() if (e or {}).get("kind") == "databooks"
                         and e.get("status") == "active"]
    for s in names:
        e = reg.get(s) or {}
        if e.get("kind") != "databooks":
            print(f"{s}: not a databooks source", file=sys.stderr)
            return 2
        print(f"{s}: {run(s, e, a.limit, a.list_only, a.reread)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
