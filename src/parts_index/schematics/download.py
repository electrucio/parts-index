"""The download stage for a source whose URLs are already known.

Some sources are not crawled and do not need to be: their URLs were gathered once and live in a list
under `core.config.source_list`. This stage walks that list, fetches whatever the ledger does not hold
yet, and stores each file under `core.config.downloads` named `<sha1(url)[:10]>_<file name>` — the name
the OCR tree already uses, so a file is found from its ledger key alone and no local path is ever
recorded anywhere.

A source opts into this stage with a `list:` block in the registry, where a crawled one has `crawl:`:

    audiocircuit:
      kind: factory
      status: active
      list:
        role: schematic                      # what these documents are when the list does not say
        figures: true                        # for an HTML page, also fetch the images it shows
        cdn: '\\.bp\\.blogspot\\.com$'         # hosts other than the page's whose images belong to it

Politeness is `core.http`'s and is not re-implemented here: robots.txt, one request per host every few
seconds, back-off on 429 and 5xx, a size cap. A refusal that will not change — 404, robots.txt, a page
served where a PDF was promised — is written to the ledger as `skip_reason` and never retried. A
transient failure leaves no stamp at all, so the next run picks it up. Nothing is fetched twice:
`Ledger.done` decides, and the ledger is saved every few items, so an interrupted run keeps its work.

    pidx schematics download --source audiocircuit [--limit 20] [--dry]
    pidx schematics download --source tagboard --source dirtbox --detach     # hours: lock + log
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

import yaml

from parts_index.core import http
from parts_index.core.config import downloads, schematics_registry, schematics_state, source_list
from parts_index.core.jobs import detach, only_one, run_log, wait_for_all
from parts_index.core.ledger import Ledger

DOCUMENT_KINDS = ("pdf", "gif", "jpeg", "png", "tiff", "bmp", "kicad_sch", "kicad_legacy", "eagle_sch",
                  "eagle_brd", "geda_sch", "ltspice_asc", "spice_net")
IMAGE_KINDS = ("gif", "jpeg", "png", "tiff", "bmp")
FILE_EXT = re.compile(r"\.(pdf|gif|jpe?g|png|tiff?|bmp|zip|sch|kicad_sch|brd)(\?|$)", re.I)
IMAGE_EXT = re.compile(r"\.(gif|jpe?g|png|tiff?|bmp)(\?|$)", re.I)
# Names that belong to the furniture of a page, never to a schematic.
FURNITURE = re.compile(r"(?i)(logo|icon|sprite|banner|button|avatar|spacer|pixel|badge|emoji|gravatar|"
                       r"paypal|donate|facebook|twitter|rss|arrow|bullet|smiley)")
MIN_IMAGE = 2500          # under this an image is a bullet or a spacer, not a drawing
MARKUP = re.compile(rb"<(a|body|frame|table|p)\b", re.I)   # a page that never says <html>, as old sites do
MIN_SIDE = 400            # a drawing published smaller than this is a preview of one, not the drawing
# Blogger puts the size it serves an image at in the path: /s1600/, /s320/, /w72-h72-p-k-no-nu/. The
# layout blogs show a preview that links the full-size file, and a strip of other posts' thumbnails.
BLOGGER_SIZE = re.compile(r"/(?:s(\d{1,5})|w(\d{1,5})-h(\d{1,5}))[^/]*/[^/]+$")
MODULE = "parts_index.schematics.download"      # how a detached run starts itself again
PERMANENT = (400, 401, 403, 404, 405, 410, 451)
SAVE_EVERY = 25


class _Links(HTMLParser):
    """The images a page shows and the files it links, in the order they appear.

    The standard library rather than a parser dependency: what this stage needs from a page is two
    attributes of two tags, and the pages it reads are ordinary blog posts.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img":
            src = a.get("src") or a.get("data-src") or a.get("data-lazy-src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[0].strip().split(" ")[0]
            if src:
                self.images.append(src)
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])


def declared_size(url: str) -> int | None:
    """The longest side the host says it is serving, when the URL declares one. None when it does not."""
    m = BLOGGER_SIZE.search(urlparse(url).path)
    if not m:
        return None
    return max(int(n) for n in m.groups() if n)


def largest_of_each(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """One URL per drawing: the biggest the page offers, and no previews of a drawing we already take.

    A layout post shows the drawing small and links it full size, so the same file arrives twice under
    two sizes; the strip of other posts' thumbnails arrives at 72 pixels and belongs to those posts.
    """
    best: dict[str, int] = {}
    for url, _ in candidates:
        name = unquote(urlparse(url).path.rsplit("/", 1)[-1]).lower()
        size = declared_size(url)
        if size is not None:
            best[name] = max(best.get(name, 0), size)
    kept = []
    for url, role in candidates:
        name = unquote(urlparse(url).path.rsplit("/", 1)[-1]).lower()
        size = declared_size(url)
        if size is not None and (size < MIN_SIDE or size < best.get(name, 0)):
            continue
        kept.append((url, role))
    return kept


def safe_name(url: str, kind: str) -> str:
    """The name the OCR tree expects. sha1 of the URL is an identifier here, never a signature."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", unquote(urlparse(url).path.rsplit("/", 1)[-1]))[:90] or "index"
    if kind == "html" and not name.lower().endswith((".htm", ".html")):
        name += ".html"
    return f"{hashlib.sha1(url.encode()).hexdigest()[:10]}_{name}"


def say(*args) -> None:
    """The default log. Flushed, because a run of this stage lasts hours and is watched through its log."""
    print(*args, flush=True)


def registry_entry(source: str) -> dict:
    registry = yaml.safe_load(schematics_registry().read_text(encoding="utf-8")) or {}
    if source not in registry:
        raise SystemExit(f"{source} is not in {schematics_registry().name}; add it before downloading it")
    return registry[source]


def read_list(source: str, limit: int | None = None) -> list[dict]:
    """The URLs gathered for this source, de-duplicated, in the order they were gathered."""
    path = source_list(source)
    if not path.exists():
        raise SystemExit(f"{source} has no URL list at {path}")
    seen: set[str] = set()
    out: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            asset = json.loads(line)
            url = (asset.get("url") or "").split("#")[0]
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(asset | {"url": url})
            if limit and len(out) >= limit:
                break
    return out


@dataclass
class Downloader:
    """One source's download run: the ledger decides what to do, `core.http` does the fetching."""

    source: str
    cfg: dict
    led: Ledger
    delay: float = http.DELAY
    min_image: int = MIN_IMAGE
    dry: bool = False
    log: object = say
    counts: Counter = field(default_factory=Counter)

    def item(self, url: str, role: str, force: bool = False) -> tuple[str, bytes]:
        """Fetch one URL. Returns (type, body), so the caller can look inside an HTML page.

        `force` asks again for something the ledger has, which the crawl stage needs when a page it
        already holds is no longer on disk and its links have to be read again. A refusal recorded
        against that URL still stands: `force` overrides the stamp, never the `skip_reason`.
        """
        row = self.led.get(url)
        if row and row["skip_reason"]:
            self.counts["refused before"] += 1
            return "", b""
        if not force and self.led.done(url, "download"):
            self.counts["already had"] += 1
            return "", b""
        if self.dry:
            self.counts["would fetch"] += 1
            return "", b""

        r = http.get(url, delay=self.delay)
        if r.why == "disallowed by robots.txt":
            return self._skip(url, role, "robots.txt", r)
        if r.status in PERMANENT:
            return self._skip(url, role, f"http {r.status}", r)
        if r.why == "larger than max_bytes":
            # Nothing about this will be different next time, and finding out costs the cap in bytes
            # every run: six radiomanual scans were 720 MB a pass, fetched and thrown away each time.
            return self._skip(url, role, f"larger than {http.MAX_BYTES >> 20} MB", r)
        if not r.ok:
            self.counts["try again next run"] += 1      # transient: no stamp, so the next run retries it
            self.log(f"  later: {r.why or r.status}  {url}")
            return "", b""

        kind = r.kind or ("html" if MARKUP.search(r.body[:20000]) else "")
        if not r.body:
            return self._skip(url, role, "empty", r)
        if kind in IMAGE_KINDS and role == "figure" and len(r.body) < self.min_image:
            return self._skip(url, role, "small image", r, kind)      # a bullet or a spacer, not a drawing
        if "svg" in r.ctype.lower() or url.lower().split("?")[-1].endswith(".svg"):
            return self._skip(url, role, "svg, which nothing here reads", r, kind)
        if FILE_EXT.search(urlparse(url).path) and kind not in DOCUMENT_KINDS:
            return self._skip(url, role, "not the declared file type", r, kind)      # a soft 404 served as a page
        if kind not in DOCUMENT_KINDS and kind != "html":
            return self._skip(url, role, "unknown file type", r, kind)

        path = downloads(self.source) / kind / safe_name(url, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.body)
        self.led.stamp(url, "download", role=role, type=kind, http=r.status, bytes=len(r.body), sha256=r.sha256)
        self.counts[kind] += 1
        return kind, r.body

    def _skip(self, url: str, role: str, reason: str, r, kind: str = "") -> tuple[str, bytes]:
        """Record a refusal that will not change, so no later run spends a request on it."""
        self.led.skip(url, reason, role=role, type=kind, http=r.status or "", bytes=len(r.body) or "")
        self.counts[f"skipped: {reason}"] += 1
        self.log(f"  skip ({reason}): {url}")
        return "", b""

    def figures(self, page_url: str, body: bytes) -> list[tuple[str, str]]:
        """What of a page belongs to it: its own images, and the files it links, on its host or a CDN
        the registry names. A layout blog keeps the drawing itself on Blogger's image host."""
        parser = _Links()
        parser.feed(body.decode("utf-8", "replace"))
        host = urlparse(page_url).netloc
        cdn = re.compile(self.cfg["cdn"]) if self.cfg.get("cdn") else None
        found: dict[str, str] = {}
        for raw, role in [(u, "figure") for u in parser.images] + [(u, "linked") for u in parser.links]:
            url = urljoin(page_url, raw).split("#")[0]
            where = urlparse(url)
            if where.netloc != host and not (cdn and cdn.search(where.netloc)):
                continue
            name = where.path.rsplit("/", 1)[-1]
            if role == "figure" and (not IMAGE_EXT.search(where.path) or FURNITURE.search(name)):
                continue
            if role == "linked" and not FILE_EXT.search(where.path):
                continue
            found.setdefault(url, role)
        return largest_of_each(list(found.items()))


def summary(counts: Counter) -> str:
    return " · ".join(f"{n} {name}" for name, n in sorted(counts.items(), key=lambda kv: -kv[1])) or "nothing to do"


def run(source: str, *, limit: int | None = None, delay: float | None = None, dry: bool = False,
        log=say) -> dict[str, int]:
    entry = registry_entry(source)
    if entry.get("status") != "active":
        raise SystemExit(f"{source} is '{entry.get('status')}' in the registry; set it to active to download it")
    cfg = entry.get("list")
    if cfg is None:
        raise SystemExit(f"{source} has no `list:` block: that is how a source opts into this stage")

    # The pace a host tolerates belongs with the host, not with whoever types the command. Renesas
    # answered a bot challenge at one request every three seconds and is listed here at fifteen.
    delay = cfg.get("delay", http.DELAY) if delay is None else delay
    assets = read_list(source, limit)
    led = Ledger(schematics_state(source))
    job = Downloader(source, cfg, led, delay=delay, dry=dry, log=log)
    log(f"{source}: {len(assets)} URLs in the list, {len(led)} already in the ledger")
    try:
        for i, asset in enumerate(assets, 1):
            role = asset.get("kind") or cfg.get("role") or "document"
            if asset.get("skip"):
                # A list may name a file to record and never fetch — a program archive that goes with an
                # article, listed with its issue so the ledger says it exists. Rule 5 still holds: written once.
                if asset["url"] not in led and not dry:
                    led.skip(asset["url"], asset["skip"], role=role)
                job.counts["listed, not fetched"] += 1
                continue
            kind, body = job.item(asset["url"], role)
            if kind == "html" and body and cfg.get("figures"):
                for url, role in job.figures(asset["url"], body):
                    job.item(url, role)
            if i % SAVE_EVERY == 0 and not dry:
                led.save()
                log(f"  {i}/{len(assets)}  {summary(job.counts)}")
    finally:
        if not dry:
            led.save()
    # The list is read once, at the start. Saying what it holds now is what tells a run apart from a
    # source: audiocircuit reported itself done against a list that had grown to three times its size.
    left = sum(1 for a in read_list(source) if a["url"] not in led)
    log(f"{source}: {summary(job.counts)}" + (f" · {left} of the list still to fetch" if left else ""))
    return dict(job.counts) | {"left": left}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics download", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", required=True, help="a source with a `list:` block (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N URLs of the list")
    ap.add_argument("--delay", type=float, default=None,
                    help=f"seconds between requests to one host; overrides the source's own (default {http.DELAY})")
    ap.add_argument("--dry", action="store_true", help="say what would be fetched and fetch nothing")
    ap.add_argument("--detach", action="store_true", help="run it in the background, under a lock, into a log")
    ap.add_argument("--after", action="append", help="wait for that job to finish first, by its log's name (repeatable)")
    ap.add_argument("--wait-hours", type=float, default=24.0, help="how long to wait for it before giving up")
    args = ap.parse_args(argv)

    # Sources given together run in one process, in order, because they usually share a host.
    name = "download_" + "-".join(args.source)
    if args.detach:
        given = list(argv) if argv is not None else sys.argv[1:]
        pid = detach(MODULE, [a for a in given if a != "--detach"], name)
        say(f"{name}: running as {pid}. Watch it with  tail -f {run_log(name)}")
        return 0
    late = wait_for_all(args.after or [], timeout=args.wait_hours * 3600)
    if late:
        raise SystemExit(f"{late} is still running after the wait ran out; nothing was fetched")
    with only_one(name):
        for source in args.source:
            run(source, limit=args.limit or None, delay=args.delay, dry=args.dry)
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
