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
from urllib.parse import quote, urlparse

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


# --- Vishay ------------------------------------------------------------------------------------------
VISHAY = "https://www.vishay.com"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def next_data(page: str) -> dict:
    m = NEXT_DATA.search(page)
    try:
        return json.loads(m.group(1))["props"]["pageProps"] if m else {}
    except (ValueError, KeyError):
        return {}


def vishay_names(r: dict) -> list[str]:
    """The part numbers a gateway row names: its part-number column when it has one, otherwise the
    series label split on commas ("BAT54, BAT54A, BAT54C, BAT54S"); a range ("BAS40-00 to BAS40-06")
    names only its ends."""
    label = str(r.get("P1009") or r.get("P1001") or "")
    return [n.strip().upper() for n in re.split(r",|/|\bto\b", label) if re.fullmatch(r"\s*[A-Za-z0-9-]{3,24}\s*", n)]


def read_vishay(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The main gateways (/en/diodes/) link their sub-gateways, whose page data list one row per product:
    its docid and its part numbers. Only products naming a known part are asked for further: the product
    page (/en/product/<docid>/) gives the data sheet and the maker's category."""
    parts = known()
    wanted: dict[str, set[str]] = {}
    for gw in entry["gateways"]:
        main = next_data(get.text(f"{VISHAY}/en/{gw}/"))
        subs = set()
        for g in main.get("getGatewayPage") or []:
            for sel in (g.get("node") or {}).get("selectors") or []:
                for link in sel.get("links") or []:
                    u = (link.get("selectorUrl") or "").strip("/")
                    if u:
                        subs.add(u if "/" in u else f"{gw}/{u}")
        for sub in sorted(subs):
            for r in next_data(get.text(f"{VISHAY}/en/{sub}/")).get("paramResults") or []:
                names = set(vishay_names(r)) & parts
                if names and r.get("P1000"):
                    wanted.setdefault(str(r["P1000"]), set()).update(names)
    for docid, names in sorted(wanted.items()):
        page = f"{VISHAY}/en/product/{docid}/"
        pp = next_data(get.text(page))
        sheet = next((d for d in pp.get("pCorResults") or [] if d.get("type") == "datsht"), None)
        cat_ = ((pp.get("getcatId") or [{}])[0].get("node") or {}).get("categoryName", "")
        for n in sorted(names):
            yield row(n, source, entry, category=cat_, url=(f"{VISHAY}/docs/{docid}/{sheet['file_name']}.{sheet['file_ext']}"
                      if sheet and sheet.get("file_name") else ""), page=page)


# --- Nisshinbo Micro Devices (New JRC) --------------------------------------------------------------
NISSHINBO = "https://www.nisshinbo-microdevices.co.jp"
NISSHINBO_SHEET = re.compile(r'<dl class="products-detail-download">.*?<a class="e-btn" href="([^"]+\.pdf)"', re.S)


def read_nisshinbo(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The English page sitemap names each product page after the product (spec/?product=njm4558); the
    page's download block links the data sheet. robots.txt keeps scripts off the PDFs themselves, so the
    link is published and the sheet is never fetched."""
    parts = known()
    pages = [u for u in LOC.findall(get.text(f"{NISSHINBO}/sitemap_en_page.xml")) if "/spec/?product=" in u]
    for page in sorted(pages):
        name = page.rsplit("=", 1)[-1].upper()
        if name not in parts:
            continue
        m = NISSHINBO_SHEET.search(get.text(page))
        yield row(name, source, entry, url=NISSHINBO + m.group(1) if m else "", page=page)


# --- SeCoS -------------------------------------------------------------------------------------------
SECOS = "https://www.secosgmbh.com"


def read_secos(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """/api/product/<category> gives a whole category, as the site's own script asks for it: each part
    (`pn`) with its data sheet. The categories are the ones that script names, listed in the registry."""
    for path in entry["categories"]:
        for p in (get.json(f"{SECOS}/api/product/{path}") or {}).get("data") or []:
            if not isinstance(p, dict) or not p.get("pn"):
                continue
            url = ((p.get("datasheet") or {}).get("url") or "").split("?")[0]
            yield row(str(p["pn"]).upper(), source, entry, url=url)


# --- Taiwan Semiconductor ----------------------------------------------------------------------------
TSC = "https://services.taiwansemi.com/api"


def read_tsc(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The product filter's skeleton gives the category tree; products_v2 gives each leaf category with
    every part's status, family and data sheet (the site's own export asks for them all at once)."""
    tree = (get.json(f"{TSC}/product-filter-skeleton?language=EN&is_with_filterable_properties=true") or {})
    leaves: list[tuple[str, str]] = []

    def walk(recs, trail):
        for r in recs or []:
            subs = (r.get("sub_categories") or {}).get("records") or []
            here = [*trail, r.get("name", "")]
            if subs:
                walk(subs, here)
            else:
                leaves.append((r["slug"], " > ".join(here[-2:])))

    walk(((tree.get("data") or {}).get("category_tree") or {}).get("records"), [])
    for slug, where in leaves:
        q = f"{TSC}/products_v2?is_with_datasheet=true&category={slug}&limit=100000&page=1&properties=%7B%7D"
        for p in ((get.json(q) or {}).get("data") or {}).get("records") or []:
            if p.get("name"):
                yield row(p["name"].upper(), source, entry, category=where, status=p.get("status") or "",
                          url=quote(p.get("datasheet") or "", safe=":/%?=&"))


# --- TT Electronics (Semelab) ------------------------------------------------------------------------
TT = "https://www.ttelectronics.com"


def tt_names(label: str) -> list[str]:
    """The parts a sheet's name packs: "2N6766 IRF250" is two, "BDX66 A,B,C" is BDX66 and its A, B and
    C grades."""
    out: list[str] = []
    for tok in re.split(r"[\s,]+", label.strip()):
        if re.fullmatch(r"[A-Z]{1,2}", tok) and out:
            base = re.sub(r"[A-Z]{1,2}$", "", out[-1]) if re.search(r"\d[A-Z]{1,2}$", out[-1]) else out[-1]
            out.append(base + tok)
        elif re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok):   # "19" in a sheet's name is not a part
            out.append(tok.upper())
    return out


def read_tt(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The data sheet search asks /api/search/resource for type 8 (data sheets) and gets every one in a
    page of 2,000: its name and file. Only the product lines in the registry are kept."""
    q = f"{TT}/api/search/resource?typ=8&subtyp=&prod=&loc=&kywrd=&srt=&pgsz=2000&pgnum=0"
    for r in (get.json(q) or {}).get("resultList") or []:
        if r.get("productDisplay") not in entry["products"] or not r.get("fileVideoURL"):
            continue
        for n in tt_names(r.get("resourceName") or ""):
            yield row(n, source, entry, category=r["productDisplay"], url=TT + r["fileVideoURL"])


# --- Kexin -------------------------------------------------------------------------------------------
KEXIN = "https://www.kexin.com.cn"
FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def trust_issuer(source: str, entry: dict) -> None:
    """Kexin's server leaves out the intermediate certificate. It is fetched once from the address the
    certificate names (`ca_issuer`), added to the usual roots, and the host is verified against that."""
    import ssl

    import certifi
    bundle = datasheets_cache(source) / "ca-bundle.pem"
    if not bundle.exists():
        r = http.get(entry["ca_issuer"], ua=PROJECT_UA, max_bytes=1 << 20)
        if not r.ok:
            return
        pem = r.body.decode() if r.body.startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(r.body)
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(Path(certifi.where()).read_text() + "\n" + pem)
    http.trust(urlparse(KEXIN).netloc, str(bundle))


def read_kexin(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """/en/products carries the whole catalogue in the page's own data (Next.js flight chunks): each row a
    part, its family and category, and its data sheet."""
    if entry.get("ca_issuer"):
        trust_issuer(source, entry)
    text = "".join(json.loads(f'"{c}"') for c in FLIGHT.findall(get.text(f"{KEXIN}/en/products")))
    at = text.find('"rows":[')
    if at < 0:
        return
    rows, _ = json.JSONDecoder().raw_decode(text[at + 7:])
    for r in rows:
        if isinstance(r, dict) and r.get("part"):
            # Its family column misfiles parts (BAT54 under bridge rectifiers), so it is not taken.
            yield row(str(r["part"]).upper(), source, entry, url=r.get("datasheet") or "")


# --- KEC ---------------------------------------------------------------------------------------------
KEC = "https://www.keccorp.com"
KEC_ROW = re.compile(r'product_view\.asp\?idx=(\d+)">([^<]+)</a>')


def read_kec(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """The product finder's table, fetched by GET as the page itself does, 16 rows a page for each top
    category in the registry. A row names the part and its idx; image_product.asp?idx= serves the sheet."""
    for cat_id, label in entry["categories"].items():
        seen: set[str] = set()
        for page in range(1, 500):              # the pager shows ten pages at a time: read until a page is empty
            html_ = get.text(f"{KEC}/en/include/finder.asp?part_idx={cat_id}&sunsu=&search_v=&page={page}")
            found = KEC_ROW.findall(html_)
            if not found or {i for i, _ in found} <= seen:
                break
            seen |= {i for i, _ in found}
            for idx, name in found:
                has_sheet = f"image_product.asp?idx={idx}&gu=1" in html_
                yield row(name.strip().upper(), source, entry, category=label,
                          url=f"{KEC}/kr/product/image_product.asp?idx={idx}&gu=1" if has_sheet else "",
                          page=f"{KEC}/en/product/product_view.asp?idx={idx}")


# --- CDIL --------------------------------------------------------------------------------------------
CDIL = "https://www.cdil.com"
CDIL_ITEM = re.compile(r'<a href="(/[a-z-]+/[^"]+)" class="product hentry.*?<div class="product-title">([^<]+)</div>', re.S)
CDIL_SHEET = re.compile(r'href="(/s/[^"]+\.pdf)"', re.I)


def read_cdil(source: str, entry: dict, get: Fetcher) -> Iterator[dict]:
    """Each category page lists its products with the types each one's title names ("2N5088 2N5089");
    only products naming a known part are opened, and their page links the sheet under /s/."""
    parts = known()
    for category in entry["categories"]:
        for href, title in CDIL_ITEM.findall(get.text(f"{CDIL}/{category}")):
            names = {n.upper() for n in re.split(r"[\s,/]+", html.unescape(title))
                     if re.search(r"\d", n) and re.search(r"[A-Za-z]", n)} & parts
            if not names:
                continue
            sheets = [u for u in CDIL_SHEET.findall(get.text(CDIL + href)) if "warranty" not in u.lower()]
            for n in sorted(names):
                yield row(n, source, entry, category=category.replace("-", " "),
                          url=CDIL + sheets[0] if sheets else "", page=CDIL + href)


READERS: dict[str, Callable[[str, dict, Fetcher], Iterator[dict]]] = {
    "cdil_products": read_cdil,
    "kec_products": read_kec,
    "kexin_products": read_kexin,
    "tt_datasheets": read_tt,
    "secos_products": read_secos,
    "tsc_products": read_tsc,
    "nisshinbo_products": read_nisshinbo,
    "vishay_gateways": read_vishay,
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
