"""The crawl stage: walk a site from its start pages and take the documents it shows.

Where `download` is handed a list of URLs, this stage finds them. Breadth-first from the start pages,
inside the site's own host, along the paths the registry allows:

    tubecad:
      kind: site
      status: active
      crawl:
        start: ['https://www.tubecad.com/']
        allow: '^/(20\\d\\d|articles|index)'     # paths worth following, on the site's own host
        deny: '^/store'                         # optional, tried before `allow`
        cdn: 'i\\d\\.wp\\.com'                    # where the site keeps its images, when not on its host
        max: 800                                # pages a run fetches before stopping; 0 is until done
        figures: true                           # take the images a page shows (the default)

Everything fetched goes through `download.Downloader`, so one piece of code decides what is stored,
what is refused for good and what is left for the next run, and the ledger is the same. A page is
read from the copy this stage keeps whenever there is one, so resuming a crawl costs a request only
for the pages whose file is gone — which is every page the old pipeline fetched, because its cache
was deleted when the project moved. After this run they are on disk and a resume is nearly free.

What it never follows: another host, a path the registry does not allow, and the machinery of a site
rather than its content — tag and category listings, feeds, comment links, carts, logins, search and
forums, which is `NEVER` below.

    pidx schematics crawl --source tubecad [--max 0] [--detach] [--after download_audiocircuit]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

from parts_index.core import http
from parts_index.core.config import downloads, schematics_state
from parts_index.core.jobs import detach, only_one, run_log, wait_for_all
from parts_index.core.ledger import Ledger, today
from parts_index.schematics.download import Downloader, registry_entry, safe_name, say, summary

MODULE = "parts_index.schematics.crawl"
# The machinery of a site rather than its content, and archives we do not open.
NEVER = re.compile(r"(?i)/(tag|tags|category|categories|author|feed|comments?|wp-json|wp-admin|wp-login|cart|"
                   r"checkout|account|login|search|forum|forums|phpbb|viewtopic|share|print)(/|$|\?)|"
                   r"[?&](replytocom|share|print|lang|sort|filter|add-to-cart)=|"
                   r"\.(zip|exe|rar|7z|mp3|mp4|avi|mov|wav|iso|hex|bin|tar|gz)$")
IMAGE_EXT = re.compile(r"\.(gif|png|jpe?g|tiff?|webp)(\?|$)", re.I)
# Stricter than the download stage's: a crawler meets every ornament a site owns, not just a blog post's.
JUNK_IMAGE = re.compile(r"(?i)(logo|icon|sprite|banner|button|avatar|spacer|pixel|badge|emoji|gravatar|paypal|"
                        r"donate|facebook|twitter|rss|arrow|bullet|bg[_-]|background|header|footer|thumb)")
BLOGGER_SIZE = re.compile(r"/(s\d{2,4}|w\d+-h\d+)(-[a-z]+)?/")
# A quote cannot be inside an href, because it would have ended the attribute. When one comes out anyway
# the page was saved as MHTML and served as .htm: its quoted-printable `src=3D"http://..."` parses into a
# value that still carries the quote. See `resolved`.
MALFORMED = re.compile(r'["<>]')
MIN_WIDTH = 120           # a page that says an image is narrower than this is showing a thumbnail
MIN_IMAGE = 900           # line art is small: the floor is lower here than for a blog's photographs
SAVE_EVERY = 25


class _Page(HTMLParser):
    """What a page offers: its title, where it links, and the images it shows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[str] = []
        self.frames: list[str] = []
        self.images: list[dict] = []
        self._reading_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("a", "area") and a.get("href"):
            self.links.append(a["href"])
        elif tag in ("frame", "iframe") and a.get("src"):
            self.frames.append(a["src"])
        elif tag == "img":
            self.images.append(a)
        elif tag == "title":
            self._reading_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._reading_title = False

    def handle_data(self, data):
        if self._reading_title:
            self.title += data


def image_src(attrs: dict) -> str:
    """The biggest version of an image a page offers, out of the several ways it can offer one."""
    src = attrs.get("data-orig-file") or ""
    if not src and attrs.get("srcset"):
        src = attrs["srcset"].split(",")[-1].split()[0]        # the last candidate is the largest
    return src or attrs.get("data-src") or attrs.get("data-lazy-src") or attrs.get("src") or ""


def without_fragment(url: str) -> str:
    return urldefrag(url)[0]


def resolved(base: str, href: str) -> str:
    """Where a link points, absolute and without its fragment, or "" when it can point nowhere.

    A URL that no server can answer still costs a crawl its time: four attempts and, with the back-off
    between them, three minutes of the one turn its host gets. sm0vpo spent an hour on twelve of them.
    """
    url = without_fragment(urljoin(base, href))
    return "" if MALFORMED.search(url) else url


def same_page(url: str) -> str:
    """/audio/alpha10 and /audio/alpha10/ are one page, so a crawl visits it once."""
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def remember(led: Ledger, url: str) -> None:
    """Write down a page this crawl found and has not reached, so a later run starts from it.

    The queue used to live in memory and die with the run, which is why resuming meant walking the site
    again from its front page. A row with nothing stamped on it is exactly what the ledger already means
    by "known, not downloaded", so the frontier is kept where everything else about an item is kept.
    """
    if led.get(url) is None:
        led.row(url)["role"] = "page"


def frontier(led: Ledger) -> list[str]:
    """What a previous run left in the queue: the pages it knew of and never walked.

    A page is walked once its links are in the ledger, which is what `crawl_at` says and what the file
    on disk does not: most pages are read from the copy we keep, so nothing is downloaded and no
    download stamp lands. Reading this without `crawl_at` left sm0vpo and diyaudioheaven looking like
    they owed fifteen pages each after their queues had emptied.
    """
    return [key for key, r in led.rows.items()
            if r["role"] == "page" and not r["crawl_at"] and not r["download_at"] and not r["skip_reason"]]


def body_of(job: Downloader, source: str, url: str) -> tuple[bytes, int]:
    """The page, from the copy we keep when there is one. Returns (body, requests spent).

    Asking again for a page whose file has gone is the last resort, and after this run it stops being
    needed: the page is marked as walked and its links are in the ledger.
    """
    kept = downloads(source) / "html" / safe_name(url, "html")
    if kept.exists():
        return kept.read_bytes(), 0
    kind, body = job.item(url, "project_page", force=True)
    return (body if kind == "html" else b""), 1


def crawl(source: str, *, budget: int | None = None, delay: float = http.DELAY, refresh: bool = False,
          log=say) -> dict:
    entry = registry_entry(source)
    if entry.get("status") != "active":
        raise SystemExit(f"{source} is '{entry.get('status')}' in the registry; set it to active to crawl it")
    cfg = entry.get("crawl")
    if cfg is None:
        raise SystemExit(f"{source} has no `crawl:` block: that is how a source opts into this stage")

    host = urlparse(cfg["start"][0]).netloc
    hosts = {host, host.removeprefix("www."), "www." + host.removeprefix("www.")}
    allow = re.compile(cfg["allow"])
    deny = re.compile(cfg["deny"]) if cfg.get("deny") else None
    cdn = re.compile(cfg["cdn"]) if cfg.get("cdn") else None
    figures = cfg.get("figures", True)
    budget = cfg.get("max", 0) if budget is None else budget

    led = Ledger(schematics_state(source))
    job = Downloader(source, cfg, led, delay=delay, min_image=MIN_IMAGE, log=log)
    waiting = frontier(led)
    queue = deque([without_fragment(u) for u in cfg["start"]] + waiting)
    # A page whose links are already written down is never opened again, with or without its file.
    seen: set[str] = set() if refresh else {same_page(k) for k, r in led.rows.items() if r["crawl_at"]}
    # And a page every other page links to — a site's own front page — is queued once, not once per link.
    queued: set[str] = {same_page(u) for u in queue}

    def enqueue(url: str, first: bool = False) -> None:
        if same_page(url) in seen or same_page(url) in queued:
            return
        queued.add(same_page(url))
        remember(led, url)
        queue.appendleft(url) if first else queue.append(url)
    read = fetched = 0
    log(f"{source}: {len(waiting)} pages waiting from last time, {len(seen)} already walked, "
        f"{len(led)} rows in the ledger{f', budget {budget} pages' if budget else ''}")

    try:
        while queue and (not budget or fetched < budget):
            url = queue.popleft()
            if same_page(url) in seen:
                # The same page under another spelling — qrp-labs links itself over http and answers
                # over https. It is walked once, and both rows say so, or the one left unstamped is
                # read as a page still owed and the frontier never empties.
                if not led.row(url)["crawl_at"]:
                    led.row(url)["crawl_at"] = today()
                    led.dirty = True
                continue
            if MALFORMED.search(url):        # queued by a run from before `resolved` existed
                led.skip(url, "malformed url")
                continue
            seen.add(same_page(url))
            body, spent = body_of(job, source, url)
            fetched += spent
            if not body:
                continue
            read += 1
            page = _Page()
            page.feed(body.decode("utf-8", "replace"))

            for src in page.frames:                       # a frameset keeps its content one hop further
                u = resolved(url, src)
                if u and urlparse(u).netloc in hosts and not NEVER.search(u):
                    enqueue(u, first=True)

            for href in page.links:
                u = resolved(url, href)
                p = urlparse(u)
                if p.scheme not in ("http", "https") or p.netloc not in hosts or NEVER.search(u):
                    continue
                tail = p.path + (f"?{p.query}" if p.query else "")
                if deny and deny.search(tail):
                    continue
                if p.path.lower().endswith(".pdf"):
                    job.item(u, "linked")
                elif IMAGE_EXT.search(p.path):
                    if figures and not JUNK_IMAGE.search(p.path):
                        job.item(u, "figure")             # the full-size image behind a thumbnail
                elif allow.search(tail) and len(p.query) < 80:
                    enqueue(u)

            for attrs in page.images if figures else []:
                src = image_src(attrs)
                if not src or src.startswith("data:"):
                    continue
                u = resolved(url, src)
                p = urlparse(u)
                if not u or (p.netloc not in hosts and not (cdn and cdn.search(p.netloc))):
                    continue
                if JUNK_IMAGE.search(p.path) or p.path.lower().endswith(".svg"):
                    continue
                width = str(attrs.get("width", ""))
                if width.isdigit() and int(width) < MIN_WIDTH:
                    continue
                if "blogger" in p.netloc or "blogspot" in p.netloc:
                    u = BLOGGER_SIZE.sub("/s1600/", u)
                job.item(u, "figure")

            led.row(url)["crawl_at"] = today()       # its links are in the ledger now; never ask again
            led.dirty = True
            if read % SAVE_EVERY == 0:
                led.save()
                log(f"  {read} pages read, {len(queue)} queued  {summary(job.counts)}")
    finally:
        led.save()

    left = len(queue)
    log(f"{source}: {read} pages read, {fetched} of them fetched, {left} left in the queue · {summary(job.counts)}")
    if not left:
        log(f"{source}: the queue is empty — the crawl is complete; say so in the registry")
    return {"pages": read, "fetched": fetched, "queued": left, **job.counts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics crawl", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", required=True, help="a source with a `crawl:` block (repeatable)")
    ap.add_argument("--max", type=int, default=None, help="pages to fetch before stopping; 0 runs until the queue is empty")
    ap.add_argument("--delay", type=float, default=http.DELAY, help=f"seconds between requests to one host (default {http.DELAY})")
    ap.add_argument("--refresh", action="store_true", help="walk pages already walked, to find what a site has added")
    ap.add_argument("--detach", action="store_true", help="run it in the background, under a lock, into a log")
    ap.add_argument("--after", action="append", help="wait for that job to finish first, by its log's name (repeatable)")
    ap.add_argument("--wait-hours", type=float, default=24.0, help="how long to wait for it before giving up")
    args = ap.parse_args(argv)

    name = "crawl_" + "-".join(args.source)
    if args.detach:
        given = list(argv) if argv is not None else sys.argv[1:]
        pid = detach(MODULE, [a for a in given if a != "--detach"], name)
        say(f"{name}: running as {pid}. Watch it with  tail -f {run_log(name)}")
        return 0
    late = wait_for_all(args.after or [], timeout=args.wait_hours * 3600)
    if late:
        raise SystemExit(f"{late} is still running after the wait ran out; nothing was crawled")
    with only_one(name):
        for source in args.source:
            crawl(source, budget=args.max, delay=args.delay, refresh=args.refresh)
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
