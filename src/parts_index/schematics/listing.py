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

A dead site has no listing of its own, and asking it is how you learn it is dead. What it published is
still readable in the Wayback Machine, and the CDX API will say what it held: a source with a `wayback:`
block is listed from there instead, one row per document the archive holds a good capture of.

A site that publishes a sitemap has already written the list, and a `sitemap:` block says to read it
rather than walk the site. It is the polite way in and usually the complete one: TI names its own in
robots.txt, and one of the files it points at holds 29,562 documents that no amount of crawling would
have found, because nothing links to most of them from anywhere a crawler starts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urljoin

from parts_index.core import http
from parts_index.core.config import source_list
from parts_index.schematics.download import registry_entry

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
    """-> one batch of rows per brand, as each brand is finished. A batch at a time, because a listing run
    is long and a run that saves only at the end saves nothing when it is interrupted."""
    r = http.get("https://audiocircuit.dk/sitemap.xml", delay=delay)
    if not r.ok:
        raise SystemExit(f"audiocircuit sitemap: {r.status} {r.why}")
    pages = [u for u in SITEMAP_LOC.findall(r.text())
             if re.fullmatch(r"https://audiocircuit\.dk/[a-z0-9._-]+/", u)]
    print(f"{len(pages)} pages in the sitemap", file=sys.stderr)
    fetched = 0
    for page in pages:
        seen_here: set[str] = set()
        brand = ""
        rows = []
        for n in range(MAX_PAGES):
            url = page if n == 0 else f"{page}?eeListID=1&ee=1&eePage={n}"
            if limit and fetched >= limit:
                yield rows
                return
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
        if rows:
            yield rows
            print(f"  {brand or page}: {len(seen_here)}", file=sys.stderr)


CDX = "https://web.archive.org/cdx/search/cdx"
# `id_` asks for the bytes as they were archived, without the banner the Wayback Machine puts on a page.
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
CDX_TIMEOUT = 300           # a page of this index is a database query, not a file


def _cdx(params: list[tuple[str, str]], delay: float) -> list[list[str]]:
    """One CDX query. A list of pairs, not a mapping: `filter` is given more than once."""
    query = "&".join(f"{k}={v}" for k, v in params)
    r = http.get(f"{CDX}?{query}", delay=delay, timeout=CDX_TIMEOUT)
    if not r.ok:
        raise SystemExit(f"wayback cdx: {r.status} {r.why}  ({query})")
    return [line.split(" ") for line in r.text().splitlines() if line.strip()]


def wayback(source: str, cfg: dict):
    """-> one batch per page of the CDX index: every document the archive holds a good capture of.

    `collapse=urlkey` asks for one capture per URL rather than every visit the crawler ever made, which
    is the difference between a few thousand rows and a few hundred thousand.
    """
    domain, types = cfg["domain"], cfg.get("types", ["application/pdf"])
    common = [("url", domain), ("matchType", "domain"), ("collapse", "urlkey"),
              ("filter", "statuscode:200"), ("filter", f"mimetype:({'|'.join(types)})")]

    def lister(delay: float, limit: int = 0):
        # `showNumPages` counts the index's own blocks, before the filters: a page of it can yield
        # anything from nothing to everything, and the count is only there to say when to stop.
        pages = int(_cdx(common + [("showNumPages", "true")], delay)[0][0])
        print(f"{domain}: {pages} pages of CDX index", file=sys.stderr)
        for n in range(pages):
            rows = _cdx(common + [("fl", "original,timestamp,length"), ("page", str(n))], delay)
            batch = [{"url": REPLAY.format(stamp=stamp, url=original), "title": _title_of(original),
                      "kind": cfg.get("kind", "schematic"), "origin": cfg.get("origin", "factory"),
                      "page": original, "archived": stamp, "bytes": int(size) if size.isdigit() else 0,
                      "source": source}
                     for original, stamp, size in (r for r in rows if len(r) == 3)]
            if batch:
                yield batch
            print(f"  page {n + 1}/{pages}: {len(batch)}", file=sys.stderr)
            if limit and n + 1 >= limit:
                return

    return lister


SITEMAP_SIZE = 64 << 20         # an index of a large site, not a page
SITEMAP_DEPTH = 3               # a sitemap index may point at sitemap indexes


def _locs(url: str, delay: float, depth: int = SITEMAP_DEPTH) -> list[str]:
    """Every URL a sitemap names, following the indexes that point at other sitemaps."""
    r = http.get(url, delay=delay, timeout=CDX_TIMEOUT, max_bytes=SITEMAP_SIZE)
    if not r.ok:
        raise SystemExit(f"sitemap: {r.status} {r.why}  ({url})")
    body = r.text()
    found = SITEMAP_LOC.findall(body)
    if "<sitemapindex" in body[:2000] and depth:
        out: list[str] = []
        for inner in found:
            out += _locs(inner, delay, depth - 1)
        return out
    return found


def sitemap(source: str, cfg: dict):
    """-> one batch of rows, from the list the site publishes about itself.

    `keep` is what makes this usable rather than indiscriminate. TI's literature sitemap names every
    document it has, marketing bulletins and processor manuals included; the pattern says which families
    hold a circuit — application notes, reference design guides, and the user guides of the evaluation
    boards, which carry the board's own schematic.
    """
    keep = re.compile(cfg["keep"]) if cfg.get("keep") else None

    def lister(delay: float, limit: int = 0):
        locs = list(dict.fromkeys(_locs(cfg["url"], delay)))    # TI names a document in two of its sitemaps
        print(f"{source}: {len(locs)} URLs in the sitemap", file=sys.stderr)
        wanted = [u for u in locs if not keep or keep.search(u)]
        print(f"  {len(wanted)} of them kept by `keep`", file=sys.stderr)
        yield [{"url": u, "title": u.rsplit("/", 1)[-1].upper(), "kind": cfg.get("kind", "schematic"),
                "origin": cfg.get("origin", "factory"), "page": u, "source": source}
               for u in (wanted[:limit] if limit else wanted)]

    return lister


LISTERS = {"audiocircuit": audiocircuit}


def lister_for(source: str):
    """The lister written for this source, or the one its own sitemap or the Wayback Machine gives."""
    if source in LISTERS:
        return LISTERS[source]
    entry = registry_entry(source)
    if entry.get("sitemap"):
        return sitemap(source, entry["sitemap"])
    if entry.get("wayback"):
        return wayback(source, entry["wayback"])
    raise SystemExit(f"no lister for {source}: it needs one in LISTERS, or a `sitemap:` or `wayback:` block")


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
    ap.add_argument("--source", action="append", required=True,
                    help=f"one of: {', '.join(LISTERS)}, or any source with a `wayback:` block")
    ap.add_argument("--limit", type=int, default=0, help="at most this many listing pages fetched")
    ap.add_argument("--delay", type=float, default=http.DELAY, help="seconds between two requests to one host")
    ap.add_argument("--dry", action="store_true", help="say what would be added and add nothing")
    a = ap.parse_args(argv)
    for source in a.source:
        lister = lister_for(source)
        listed = added = 0
        for batch in lister(a.delay, a.limit):
            listed += len(batch)
            added += append_new(source, batch, a.dry)          # saved as each brand finishes, not at the end
        print(f"{source}: {listed} files listed, {added} of them new{' (dry)' if a.dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
