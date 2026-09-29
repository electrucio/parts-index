"""Which way round a transistor is, read off a page somebody found for it.

    pidx datasheets polarity FILE...

Each FILE holds what a search found, one JSON object per line: `part`, `polarity` and `url`. Who found it
does not matter and is not trusted. Each page is fetched through the polite client, its text read — a
PDF's pages or a web page's words — and a row is published only when, where the page prints the part's
number, it says that polarity and never the other (`core.parts.polarity.read_sheet`). What is published
is the part, the polarity, the link, the page's checksum and the few words around the number that say
it, so a reader can check them against the page.

The ledger keeps one row per part and page asked, so a page read once is not fetched again for that part.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from parts_index.core import http
from parts_index.core.config import datasheet_polarity, datasheets_state
from parts_index.core.ledger import Ledger
from parts_index.core.parts import polarity
from parts_index.datasheets.harvest import PROJECT_UA, read_pdf

STAGES = ("fetch", "read")
VERSIONED = ("read",)
FIELDS = ("key", "part", "url", "claimed", "http", "sha256", "fetch_at", "polarity", "words", "read_at", "read_v",
          "skip_reason")
READ_VERSION = "1"
TABLE = ("part", "polarity", "url", "words", "sha256", "checked")
MAX_BYTES = 40 << 20
PACE = (0, 429, 500, 502, 503, 504)
TAG = re.compile(r"<(script|style)\b.*?</\1\s*>|<[^>]+>", re.S | re.I)


def page_text(r: http.Response) -> str:
    """The words of a fetched page: every page of a PDF, or a web page with its markup taken out."""
    if r.body[:4] == b"%PDF":
        try:
            pages, _ = read_pdf(r.body)
        except Exception:                                   # noqa: BLE001 - a broken PDF says nothing
            return ""
        return "\n".join(pages)
    return html.unescape(TAG.sub(" ", r.text()))


def candidates(files: list[Path]) -> list[dict]:
    out, seen = [], set()
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            key = (c.get("part", ""), c.get("url", ""))
            if c.get("polarity") in polarity.CLASS and key[1].startswith("http") and key not in seen:
                seen.add(key)
                out.append(c)
    return out


def say(line: str) -> None:
    print(line, flush=True)


def run(files: list[Path], say=say) -> Counter:
    led = Ledger(datasheets_state("polarity"), stages=STAGES, fields=FIELDS, versioned=VERSIONED)
    pages: dict[str, tuple[http.Response, str]] = {}
    later: set[str] = set()             # hosts that asked us to slow down: not asked again this run
    n = Counter()
    for i, c in enumerate(candidates(files)):
        if i and i % 25 == 0:
            led.save()                                  # a run of hundreds of pages loses nothing it read
        part, url, claimed = c["part"], c["url"], c["polarity"]
        key = f"{url} {part}"
        if led.done(key, "read", version=READ_VERSION):
            n["already read"] += 1
            continue
        host = urlparse(url).netloc
        if host in later:
            n["come back later"] += 1
            continue
        if url not in pages:
            r = http.get(url, ua=PROJECT_UA, max_bytes=MAX_BYTES, retries=1)
            pages[url] = (r, page_text(r) if r.ok else "")
        r, text = pages[url]
        if r.status in PACE:
            # Too fast, or the server is down: not a refusal (CLAUDE.md, rule 3). Nothing is stamped, so
            # the next run asks again, and nothing more is asked of this host in this one.
            later.add(host)
            n["come back later"] += 1
            say(f"  {host}: {r.status}, left for a later run")
            continue
        if not r.ok:
            led.skip(key, (r.why or f"http {r.status}")[:60], part=part, url=url, claimed=claimed, http=r.status)
            n["page not read"] += 1
            continue
        led.stamp(key, "fetch", part=part, url=url, claimed=claimed, http=r.status, sha256=r.sha256)
        words = polarity.read_sheet(text, part, claimed)
        led.stamp(key, "read", version=READ_VERSION, polarity=claimed if words else "", words=words)
        n["says it" if words else "does not say it"] += 1
        say(f"  {part:14} {claimed:10} {'yes' if words else 'no ':4} {url}")
    led.save()
    write(led)
    return n


def write(led: Ledger) -> None:
    """The published table: every part a page was read to say, with the page."""
    rows = sorted(({"part": r["part"], "polarity": r["polarity"], "url": r["url"], "words": r["words"],
                    "sha256": r["sha256"], "checked": r["read_at"]}
                   for r in led.rows.values() if r.get("polarity")), key=lambda r: (r["part"], r["url"]))
    out = datasheet_polarity()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TABLE, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets polarity", description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path, help="JSON lines: part, polarity, url")
    a = ap.parse_args(argv)
    n = run(a.files)
    for k, v in n.items():
        print(f"  {v:6}  {k}")
    print(f"written to {datasheet_polarity()}", file=sys.stderr)
    return 0
