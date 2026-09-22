"""Gather a source's file URLs again, from the site's own listing, and add what is new to its list.

    pidx schematics list --source audiocircuit [--limit 20] [--dry]

`download` walks the list under `core.config.source_list`; this is where that list comes from when it
ages or turns out to be short. It only ever **appends**: a URL already listed keeps its place and its
ledger row, so a re-listing costs nothing for what is already held and a download that is running reads
its own copy undisturbed.

audiocircuit: the sitemap names one page per brand, and each brand page shows a hundred files at a time
behind `?eeListID=1&ee=1&eePage=N`. The list gathered in September took page 0 only, so 48 of the 358
brands stopped at exactly a hundred files — Akai alone has 789. Walk the pages until one brings nothing
new, which is how the site says there is no more.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urljoin

from parts_index.core import http
from parts_index.core.config import source_list

PAGE_SIZE_GUESS = 100
MAX_PAGES = 60

SITEMAP_LOC = re.compile(r"<loc>([^<]+)</loc>")
PDF_HREF = re.compile(r'href="([^"]+\.pdf)"', re.I)
TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def _unescape(s: str) -> str:
    import html

    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _brand(html_text: str, url: str) -> str:
    m = TITLE.search(html_text)
    name = _unescape(m.group(1)) if m else ""
    name = re.sub(r"\s*(Schematics|Service Manuals?|and|&)\s*", " ", name).strip(" -–|")
    return name or url.rstrip("/").rsplit("/", 1)[-1].title()


def _title_of(pdf_url: str) -> str:
    stem = pdf_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[-_]+", " ", stem).strip()


def audiocircuit(delay: float, limit: int = 0):
    """-> rows, in the order the site shows them."""
    r = http.get("https://audiocircuit.dk/sitemap.xml", delay=delay)
    if not r.ok:
        raise SystemExit(f"audiocircuit sitemap: {r.status} {r.why}")
    pages = [u for u in SITEMAP_LOC.findall(r.text())
             if re.fullmatch(r"https://audiocircuit\.dk/[a-z0-9._-]+/", u)]
    print(f"{len(pages)} pages in the sitemap", file=sys.stderr)
    rows, fetched = [], 0
    for page in pages:
        seen_here: set[str] = set()
        brand = ""
        for n in range(MAX_PAGES):
            url = page if n == 0 else f"{page}?eeListID=1&ee=1&eePage={n}"
            if limit and fetched >= limit:
                return rows
            resp = http.get(url, delay=delay)
            fetched += 1
            if not resp.ok:
                break
            body = resp.text()
            brand = brand or _brand(body, page)
            found = [urljoin(url, h) for h in PDF_HREF.findall(body)]
            fresh = [u for u in found if u not in seen_here]
            if not fresh:
                break
            seen_here.update(fresh)
            rows += [{"url": u, "title": _title_of(u), "brand_hint": brand, "kind": "schematic",
                      "origin": "factory", "page": page, "source": "audiocircuit"} for u in fresh]
            if len(found) < PAGE_SIZE_GUESS:
                break
        if seen_here:
            print(f"  {brand or page}: {len(seen_here)}", file=sys.stderr)
    return rows


LISTERS = {"audiocircuit": audiocircuit}


def append_new(source: str, rows: list[dict], dry: bool = False) -> int:
    """Add the rows whose URL the list does not have yet. Returns how many were added."""
    path = source_list(source)
    have = set()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    have.add((json.loads(line).get("url") or "").split("#")[0])
    new = [r for r in rows if r["url"].split("#")[0] not in have]
    if new and not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:       # append only: a running download is reading it
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics list", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", required=True, help=f"one of: {', '.join(LISTERS)}")
    ap.add_argument("--limit", type=int, default=0, help="at most this many listing pages fetched")
    ap.add_argument("--delay", type=float, default=http.DELAY, help="seconds between two requests to one host")
    ap.add_argument("--dry", action="store_true", help="say what would be added and add nothing")
    a = ap.parse_args(argv)
    for source in a.source:
        if source not in LISTERS:
            raise SystemExit(f"no lister for {source}; there is one for {', '.join(LISTERS)}")
        rows = LISTERS[source](a.delay, a.limit)
        added = append_new(source, rows, a.dry)
        print(f"{source}: {len(rows)} files listed, {added} of them new{' (dry)' if a.dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
