"""What a manufacturer's own catalogue says a part is: the category it files it under, whether it is still
made, and the data sheet that documents it — title and revision.

    pidx datasheets register [--source ti_products] [--limit N]

The catalogue is asked about the parts this index holds and nothing else, one page at a time at the
pace its robots.txt asks for, and the ledger remembers each answer so a part is never asked for twice.
Only facts leave the page: "General-purpose op amps", "ACTIVE", "TL07xx Low-Noise, FET-Input Operational
Amplifiers", "W". The sentence the manufacturer wrote to describe the part is its own writing and stays
on its page, which is linked.

The first 60 KB of each page — the head and the data-sheet link, which is all the reader needs — is
kept compressed in the private tree, so a parser fix costs a re-read and not another visit.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import re
import sys

import yaml

from parts_index.core import http
from parts_index.core.config import (
    datasheets_cache,
    datasheets_registry,
    datasheets_state,
    datasheets_table,
    parts_census,
    schematics_parts,
)
from parts_index.core.ledger import Ledger, today

STAGES = ("fetch", "read")
VERSIONED = ("read",)
FIELDS = ("key", "url", "http", "bytes", "fetch_at", "read_at", "read_v", "skip_reason")
READ_VERSION = "2"  # 2: pages cut before the data sheet link are fetched again
KEEP = 60_000
# `title` is the data sheet's own; `name` the title the maker gives the product on its page, where it
# gives one and the data sheet's is not there to read.
TABLE = ("part", "source", "maker", "category", "status", "name", "title", "revision", "url", "page", "checked")

META = re.compile(r'<meta\s+name="(description|PartNumber|gpnFamily|status)"\s+content="([^"]*)"', re.S)
SHEET = re.compile(r'<a\s[^>]*navtitle="data sheet"[^>]*>(.*?)</a\s*>', re.S)
SHEET_HREF = re.compile(r'href="([^"]+)"')
TITLE = re.compile(r"^(?P<title>.+?)\s+datasheet(?:\s+\(Rev\.\s*(?P<rev>[A-Z0-9]+)\))?$", re.I)


def registry() -> dict:
    p = datasheets_registry()
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def read_ti(page: str) -> dict:
    """The facts a TI product page states about its part, or {} when it is not one."""
    meta = {k: html.unescape(v).strip() for k, v in META.findall(page)}
    if not meta.get("PartNumber"):
        return {}
    out = {"page_part": meta["PartNumber"], "status": meta.get("status", "")}
    fam = meta.get("gpnFamily", "")
    out["category"] = fam.split("_", 1)[1] if "_" in fam else fam      # "1562_General-purpose op amps"
    for m in SHEET.finditer(page):
        t = TITLE.match(text(m.group(1)))
        if t:
            href = SHEET_HREF.search(m.group(0))
            out.update(title=t["title"], revision=t["rev"] or "", url=href.group(1) if href else "")
            break
    return out


REN_CRUMB = re.compile(r'<nav[^>]*breadcrumb[^>]*>(.*?)</nav>', re.S)
REN_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
REN_STATUS = re.compile(r'class="[^"]*product__label[^"]*">([^<]+)<')
REN_NAME = re.compile(r'<h2 class="subtitle">(.*?)</h2>', re.S)
REN_SHEET = re.compile(r'href="(/en/document/dst/[^"?]+)')
REN_TITLE = re.compile(r"<title>\s*([^<]*?)\s+-\s", re.S)


def read_renesas(page: str) -> dict:
    """The facts a Renesas product page states: category from the breadcrumb, status, the product's title
    and the data sheet link. The page names the data sheet only "Datasheet", so it has no title here."""
    t = REN_TITLE.search(page)
    if not t:
        return {}
    out = {"page_part": text(t.group(1))}
    crumb = REN_CRUMB.search(page)
    items = [text(i) for i in REN_ITEM.findall(crumb.group(1))] if crumb else []
    items = [i for i in items if i]
    if len(items) >= 2:
        out["category"] = items[-2]
    st = REN_STATUS.search(page)
    if st:
        out["status"] = text(st.group(1)).upper()
    nm = REN_NAME.search(page)
    if nm:
        out["name"] = text(nm.group(1))
    sh = REN_SHEET.search(page)
    if sh:
        out["url"] = "https://www.renesas.com" + sh.group(1)
    return out


READERS = {"ti_products": read_ti, "renesas_products": read_renesas}


def wanted(source: str, entry: dict) -> list[str]:
    """The parts of this catalogue the index holds, most printed first — the order a reader would ask."""
    listed = set()
    with open(parts_census(entry["census"]), encoding="utf-8") as f:
        listed = {r["part"] for r in csv.DictReader(f)}
    with open(schematics_parts(), encoding="utf-8") as f:
        docs = {r["part"]: int(r["documents"]) for r in csv.DictReader(f)}
    return sorted((p for p in listed if p in docs), key=lambda p: (-docs[p], p))


def load_table() -> dict[tuple[str, str], dict]:
    p = datasheets_table()
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {(r["part"], r["source"]): r for r in csv.DictReader(f)}


def save_table(rows: dict[tuple[str, str], dict]) -> None:
    p = datasheets_table()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TABLE, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: rows[k].get(c, "") for c in TABLE})
    tmp.replace(p)


def cut_short(page: str, row: dict | None, keep: int | None) -> bool:
    """Whether the copy kept holds less of the page than today's limit would: the server sent more
    than was kept, and the limit has since been raised past it."""
    served = int((row or {}).get("bytes") or 0)
    return len(page) < served and (keep is None or len(page) < keep)


def run(source: str, entry: dict, limit: int = 0, reread: bool = False) -> dict:
    led = Ledger(datasheets_state(source), stages=STAGES, fields=FIELDS, versioned=VERSIONED)
    table = load_table()
    reader = READERS[source]
    cache = datasheets_cache(source)
    cache.mkdir(parents=True, exist_ok=True)
    counts = {"asked": 0, "read": 0, "missing": 0, "cached": 0}
    delay = float(entry.get("delay", http.DELAY))
    for part in wanted(source, entry):
        if limit and counts["asked"] >= limit:
            break
        r = led.get(part)
        if r and r["skip_reason"]:
            continue
        if led.done(part, "read", version=READ_VERSION) and not reread:
            continue
        url = entry["page"].format(part=part, lower=part.lower())
        kept = cache / f"{part.replace('/', '_')}.html.gz"
        keep = int(entry.get("keep", KEEP)) or None
        page = ""
        if led.done(part, "fetch") and kept.exists():
            page = gzip.decompress(kept.read_bytes()).decode("utf-8", "replace")
            counts["cached"] += 1
            if cut_short(page, r, keep) and not (reader(page) or {}).get("url"):
                page = ""  # the copy kept stops before the data sheet link, and today more is kept
        if not page:
            counts["asked"] += 1
            resp = http.get(url, delay=delay, max_bytes=2 << 20)
            if resp.status == 404:
                led.skip(part, "no product page (404)", url=url, http=404)
                counts["missing"] += 1
                continue
            if not resp.ok:
                print(f"  {part}: {resp.why or resp.status} — left for the next run", file=sys.stderr)
                continue
            page = resp.text(keep)
            kept.write_bytes(gzip.compress(page.encode("utf-8")))
            led.stamp(part, "fetch", url=url, http=resp.status, bytes=len(resp.body))
        facts = reader(page)
        if facts and facts.get("page_part", "").upper() == part.upper():
            table[(part, source)] = {
                "part": part, "source": source, "maker": entry.get("maker", ""),
                "category": facts.get("category", ""), "status": facts.get("status", ""),
                "name": facts.get("name", ""),
                "title": facts.get("title", ""), "revision": facts.get("revision", ""),
                "url": facts.get("url", ""), "page": url, "checked": today()}
            counts["read"] += 1
        led.stamp(part, "read", version=READ_VERSION)
        if (counts["asked"] + counts["cached"]) % 50 == 0:
            led.save()
            save_table(table)
    led.save()
    save_table(table)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets register")
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many pages asked for, per source")
    ap.add_argument("--reread", action="store_true", help="read the cached pages again with today's parser")
    a = ap.parse_args(argv)
    reg = registry()
    names = a.source or [s for s, e in reg.items() if (e or {}).get("status") == "active"]
    for s in names:
        if s not in reg or s not in READERS:
            print(f"{s}: not a registered source with a reader", file=sys.stderr)
            return 2
        c = run(s, reg[s], a.limit, a.reread)
        print(f"{s}: asked {c['asked']}, re-read {c['cached']} from the cache, read {c['read']}, no page {c['missing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
