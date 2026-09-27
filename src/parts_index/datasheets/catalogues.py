"""What a manufacturer's own product list says about each part it makes, read whole from the list itself.

    pidx datasheets catalogue [--source diotec_products] [--refresh]

Some manufacturers publish their whole range as the tables their own site draws its product lists from:
Diotec one table per product family (23), Toshiba one per parametric category (68, the discontinued
ones among them), Infineon one per product table (930). Each row names a part, the maker's data sheet
for it, and whether it is still made. So a few dozen or a few hundred requests say what thousands of
product pages would, and the part-to-sheet link is the maker's own statement rather than something
read out of a PDF.

Only the parts this project knows are kept. Each table is kept compressed in the private tree, so a
parser fix costs no second visit; `--refresh` asks again. The sentence a maker wrote about a part stays
on its page.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from parts_index.core import http
from parts_index.core.config import datasheet_catalogue, datasheets_cache
from parts_index.core.ledger import today
from parts_index.datasheets.harvest import PROJECT_UA, known, registry

FIELDS = ("part", "source", "maker", "category", "status", "name", "title", "revision", "url", "page", "checked")
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


class Fetcher:
    """One table at a time, at the source's pace, kept so it is asked for once."""

    def __init__(self, source: str, entry: dict, refresh: bool = False):
        self.dir = datasheets_cache(source)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.delay = float(entry.get("delay", http.DELAY))
        self.refresh = refresh
        self.asked = self.kept = 0

    def text(self, url: str) -> str:
        kept = self.dir / (re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:180] + ".gz")
        if kept.exists() and not self.refresh:
            self.kept += 1
            return gzip.decompress(kept.read_bytes()).decode("utf-8", "replace")
        self.asked += 1
        r = http.get(url, ua=PROJECT_UA, delay=self.delay, max_bytes=64 << 20)
        if not r.ok:
            print(f"  {url}: {r.why or r.status} — left for the next run", file=sys.stderr)
            return ""
        body = r.body.decode("utf-8", "replace")
        kept.write_bytes(gzip.compress(body.encode("utf-8")))
        return body

    def json(self, url: str):
        t = self.text(url)
        try:
            return json.loads(t) if t.strip() else None
        except ValueError:
            return None


def row(part: str, source: str, entry: dict, **kw) -> dict:
    return {"part": part, "source": source, "maker": entry.get("maker", ""), "checked": today()} | kw


# --- Diotec -------------------------------------------------------------------------------------------
DIOTEC = "https://diotec.com"
DIOTEC_FAMILY = re.compile(r'href="/en/productlist/([A-Z0-9-]+)\.html"')
DIOTEC_NAME = re.compile(r'<button class="listTrigger">([^<]+)</button>')
DIOTEC_SHEET = re.compile(r'href="(/request/datasheet/[^"]+\.pdf)"')
DIOTEC_LIFE = ("active", "end of life", "engineering sample", "not recommended for new design", "last time buy")


def read_diotec(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """/request/family/<FAM>/products/en: one row per article, its first cell the name and the sheet.
    A cell lists the competitors' names the maker cross-references; those are not its parts."""
    for fam in sorted(set(DIOTEC_FAMILY.findall(get.text(f"{DIOTEC}/en/all-products.html")))):
        data = get.json(f"{DIOTEC}/request/family/{fam}/products/en") or {}
        for cells in data.get("data", []):
            name, sheet = DIOTEC_NAME.search(str(cells[0])), DIOTEC_SHEET.search(str(cells[0]))
            if not name:
                continue
            status = next((str(c) for c in cells[1:] if str(c).strip().lower() in DIOTEC_LIFE), "")
            part = name.group(1).strip()
            yield row(part.upper(), source, entry, status=status,   # a family code ("T") says nothing to a reader
                      url=DIOTEC + sheet.group(1) if sheet else "", page=f"{DIOTEC}/en/product/{part}.html")


# --- Toshiba ------------------------------------------------------------------------------------------
TOSHIBA = "https://toshiba.semicon-storage.com"
TOSHIBA_MENU = re.compile(r'id="menuCategory"[^>]*value="([^"]*)"')


def toshiba_codes(get: Fetcher) -> dict[str, str]:
    """Every parametric table, current and discontinued, with its place in the menu."""
    m = TOSHIBA_MENU.search(get.text(f"{TOSHIBA}/parametric/product?code=param_304"))
    menu = json.loads(html.unescape(m.group(1))) if m else []
    by_id = {x["id"]: x for x in menu}
    places: dict[str, set[str]] = {}
    for x in menu:
        code = re.search(r"code=([\w-]+)", x.get("link") or "")
        if code:
            parent = by_id.get(x.get("parentID"), {}).get("category", "")
            label = " > ".join(c for c in (parent, x["category"]) if c)
            places.setdefault(code.group(1), set()).add(html.unescape(label).replace("\xa0", " ").rstrip(" »")
                                                     .replace(" > Not Recommended for New Design and EOL announced", ""))
    # A discontinued list hangs from several branches of the menu; which one a part belongs to is then
    # not known, and no category is better than a wrong one.
    return {code: next(iter(p)) if len(p) == 1 else "" for code, p in places.items()}


def cell(r: dict, key) -> dict:
    return next((c["values"][0] for c in r.get("cells", []) if c.get("key") == key and c.get("values")), {})


def read_toshiba(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """/parametric/rest/getHeaderData and getRowData per table: the header says which column is the data
    sheet and which the life cycle; the row gives the part and a docget link to the sheet."""
    q = "region=apc&lang=en&code="
    for code, where in sorted(toshiba_codes(get).items()):
        head = get.json(f"{TOSHIBA}/parametric/rest/getHeaderData?{q}{code}") or {}
        label = {h["key"]: re.sub(r"<[^>]+>", "", h.get("label", {}).get("name", "")).strip()
                 for h in head.get("headers", [])}
        sheet = next((k for k, v in label.items() if v == "Datasheet"), None)
        life = next((k for k, v in label.items() if v.lower() == "life-cycle"), None)
        for r in (get.json(f"{TOSHIBA}/parametric/rest/getRowData?{q}{code}") or {}).get("rows", []):
            url = cell(r, sheet).get("link", {}).get("path", "") if sheet is not None else ""
            yield row(r["name"].upper(), source, entry, category=where,
                      status=cell(r, life).get("value", "") if life is not None else "",
                      url=url.replace("&returnFlg=false", ""),
                      page=f"{TOSHIBA}/info/lookup.jsp?pid={r['name']}&region=apc&lang=en")


# --- Infineon -----------------------------------------------------------------------------------------
INFINEON = "https://www.infineon.com"


def read_infineon(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The row sitemap names every product table; /dataApi/en/product-table/<slug>.product-table.en.json
    gives each part in it with its family, its ordering codes' status and its data sheet. A table built
    from a collection rather than a family answers empty, and its parts wait for another way in."""
    slugs = sorted({u.rsplit("/", 1)[-1] for u in LOC.findall(get.text(f"{INFINEON}/en.sitemap.row-sitemap.xml"))
                    if "/product-table/" in u})
    for slug in slugs:
        for p in get.json(f"{INFINEON}/dataApi/en/product-table/{slug}.product-table.en.json") or []:
            if not isinstance(p, dict) or not p.get("ispnName"):
                continue
            ds = p.get("dataSheet") or {}
            status = sorted({(o.get("productStatusInfo") or "") for o in p.get("opns") or []} - {""})
            yield row(p["ispnName"].upper(), source, entry, category=p.get("familyName", ""),
                      status=" / ".join(status), title=ds.get("documentDisplayName", ""),
                      url=ds.get("assetDmPath", ""), page=p.get("pageUrl", ""))


READERS: dict[str, Callable[[str, dict, Fetcher], Iterator[dict]]] = {
    "diotec_products": read_diotec,
    "toshiba_parametric": read_toshiba,
    "infineon_tables": read_infineon,
}


def write(source: str, rows: dict[str, dict]) -> Path:
    p = datasheet_catalogue(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: rows[k].get(c, "") for c in FIELDS})
    tmp.replace(p)
    return p


def run(source: str, entry: dict, refresh: bool = False) -> dict:
    parts = known()
    get = Fetcher(source, entry, refresh)
    out: dict[str, dict] = {}
    listed = 0
    for r in READERS[source](source, entry, get):
        listed += 1
        if r["part"] in parts and (r["part"] not in out or (r["url"] and not out[r["part"]]["url"])):
            out[r["part"]] = r
    write(source, out)
    return {"asked": get.asked, "kept": get.kept, "listed": listed, "known": len(out),
            "with a sheet": sum(1 for r in out.values() if r["url"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets catalogue")
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="ask for every table again")
    a = ap.parse_args(argv)
    reg = registry()
    names = a.source or [s for s in READERS if (reg.get(s) or {}).get("status") == "active"]
    for s in names:
        if s not in READERS or s not in reg:
            print(f"{s}: not a registered catalogue with a reader", file=sys.stderr)
            return 2
        if reg[s].get("status") in ("paused", "blocked"):
            print(f"{s}: {reg[s]['status']} — see its notes in the registry; not asked", file=sys.stderr)
            continue
        print(f"{s}: {run(s, reg[s], a.refresh)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
