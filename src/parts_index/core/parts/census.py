"""The census: which part numbers exist, according to somebody whose job was to list them all.

The extractor knows the *shape* of a type number. It cannot know that 6V6 is a valve and 4K7 a resistor,
that 5687 and 6336A exist while BCS47 does not, or that the K1298 on a Japanese sheet means 2SK1298.
That is not pattern knowledge, it is vocabulary, and it has to come from a document that had to be
complete: a data sheet archive, a manufacturer's numerical index, a selector book.

    pidx parts census                       read every active source, then rewrite data/parts/census.csv
    pidx parts census --source frank_pocnet --limit 20      try one source, twenty pages of it
    pidx parts census --read                parse the pages already cached; ask the network for nothing

A source is an entry in `data/parts/census_sources.yaml` plus an adapter below. An adapter says where to
start (`seeds`), which further index pages a page points at (`more`), and which type numbers a page
vouches for (`entries`). Politeness, the ledger, the cache and the merge are shared.

The fetched pages are third-party content and stay in the private cache (rule 1). What is committed is
the census: a list of facts — this type number exists, this kind of part it is — each with the public URL
of the page that says so. That URL is the point twice over: it is the evidence for the fact, and it is a
reference link the index can offer when somebody searches for that part.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin

import yaml

from parts_index.core import http
from parts_index.core.config import (
    census_cache,
    census_registry,
    census_state,
    model_sources,
    model_state,
    parts_census,
    spice_definitions,
)
from parts_index.core.ledger import CENSUS_FIELDS, CENSUS_STAGES, CENSUS_VERSIONED, Ledger

READ_VERSION = "census_read-1"
FIELDS = ("part", "kind", "source", "url")


@dataclass(frozen=True)
class Entry:
    part: str        # the type number as the list writes it
    kind: str        # tube, bjt, jfet, diode, opamp ... the vocabulary of known_parts.csv
    url: str         # the public page that vouches for it


# --- frank.pocnet.net: Frank Philipse's electron tube data sheets ------------------------------------
# An A-Z index (sheets0.html ... sheetsZ.html), each letter cut into pages of 500 entries that link on to
# one another (sheets6.html -> sheets61.html ... sheets66.html). Every entry is a link to the data sheet
# PDF, and the file name is the type number: no OCR anywhere in this, which is why it is the first source.
FRANK_INDEX = re.compile(r'href="(sheets[0-9A-Za-z]+\.html)"')
FRANK_SHEET = re.compile(r'href="(sheets/[^"]+/([^"/]+)\.pdf)"', re.I)


def _frank_seeds(entry: dict) -> list[str]:
    base = entry["index_url"]
    return [urljoin(base, f"sheets{c}.html") for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"]


def _frank_more(url: str, html: str) -> list[str]:
    return [urljoin(url, m) for m in FRANK_INDEX.findall(html)]


def _frank_entries(url: str, html: str) -> list[Entry]:
    out = []
    for href, name in FRANK_SHEET.findall(html):
        part = unquote(name).strip()
        if part:
            out.append(Entry(part, "tube", urljoin(url, href)))
    return out



# --- the SPICE model libraries already held here -----------------------------------------------------
# 75 vendors' model files, indexed for the model pillar: every top-level definition is named after the
# part it models, so the index of them is a semiconductor vocabulary this project already owns. It needs
# filtering, because a library also holds internal sub-circuits, passives and test fixtures. Three signals
# say a name is a part: the definition has a real device type, or the vendor named the file after it, or
# the extractor's own families recognise the shape. Anything without one of the three is left out.
PASSIVE_SOURCES = {"murata", "tdk", "coilcraft", "wurth", "nichicon", "nichia", "littelfuse",
                   "z101-led-spice-model", "tedyapo-led-modeling"}
DEVICE_KIND = {"NPN": "bjt", "PNP": "bjt", "NJF": "jfet", "PJF": "jfet", "VDMOS": "mosfet",
               "NMOS": "mosfet", "PMOS": "mosfet", "D": "diode"}
SHAPE = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9][A-Z0-9/.-]{3,17}$")   # letters and digits both, never a word
INTERNAL = re.compile(r"^(?:DI|PH|X|XX|SW|LIB|TMP|TEST)[_-]|[_-]$")
DEVICE_LETTER = re.compile(r"^[QDJMX](?=[0-9]?[A-Z]{1,3}\d)")           # LTspice writes Q2N6544 for 2N6544


def _model_file_urls() -> dict[tuple[str, str], str]:
    """(source, file name) -> the vendor URL it was fetched from, so a census row can carry its evidence."""
    out = {}
    for led in sorted(model_state("*").parent.glob("*.csv")):
        source = led.stem
        with open(led, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                url = r.get("key") or r.get("url") or ""
                # A ledger key is a URL for anything fetched, but a model copied in by hand is keyed
                # `manual:raw/...`, which is a local path and may never be published (rule 6). Such a
                # file falls back to the vendor's own page, or the part leaves the census.
                if url.startswith("http"):
                    out[(source, url.rsplit("/", 1)[-1].lower())] = url
    return out


def _source_homes() -> dict[str, str]:
    out = {}
    for f in sorted(model_sources().glob("*.yaml")):
        try:
            out[f.stem] = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("home_url", "")
        except Exception:                                        # noqa: BLE001 - a broken entry is not fatal here
            continue
    return out


def spice_definitions_entries(entry: dict) -> list[Entry]:
    from parts_index.core.parts.extractor import family_of

    path = spice_definitions()
    if not path.exists():
        return []
    urls, homes = _model_file_urls(), _source_homes()
    found: dict[str, dict] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("parent") is not None:
                continue
            source = d.get("source") or ""
            name = (d.get("name") or "").strip().upper()
            if source in PASSIVE_SOURCES or not SHAPE.match(name) or INTERNAL.search(name):
                continue
            file_name = (d.get("file") or "").rsplit("/", 1)[-1]
            stem = file_name.rsplit(".", 1)[0].upper()
            names = [name]
            if DEVICE_LETTER.match(name) and family_of(name[1:]):
                names.append(name[1:])
            for n in names:
                r = found.setdefault(n, {"kinds": set(), "stem": False, "url": ""})
                r["kinds"].add(DEVICE_KIND.get(d.get("type") or "", ""))
                r["stem"] = r["stem"] or norm(stem) == norm(n)
                r["url"] = r["url"] or urls.get((source, file_name.lower())) or homes.get(source, "")
    out = []
    for name, r in found.items():
        kinds = {k for k in r["kinds"] if k}
        if not (kinds or r["stem"] or family_of(name)):
            continue
        out.append(Entry(name, sorted(kinds)[0] if len(kinds) == 1 else ("ic" if not kinds else "semiconductor"),
                         r["url"]))
    return out


# --- a manufacturer's list of its own parts --------------------------------------------------------
# TI publishes a sitemap of its data sheets: one URL per part, at /lit/gpn/<part>. That is this census's
# contract met exactly — somebody whose job was to be complete about a vocabulary, and a public URL that
# vouches for each name and is the reference link at the same time. 21,817 parts on 2026-09-24.
#
# It says which parts exist and nothing about what they are, so every entry is "semiconductor", which is
# generic on purpose: it agrees with any family but a valve. A list of TI's catalogue must never be what
# settles a token the valve family claimed.
GPN = re.compile(r"<loc>\s*(https?://[^<\s]*?/lit/gpn/([^<\s/]+))\s*</loc>", re.I)


def _gpn_seeds(entry: dict) -> list[str]:
    return [entry["index_url"]]


def _gpn_entries(url: str, xml: str) -> list[Entry]:
    out = []
    for href, name in GPN.findall(xml):
        part = unquote(name).strip()
        if part:
            out.append(Entry(part, "semiconductor", href))
    return out


LOCAL_ADAPTERS = {"spice_definitions": spice_definitions_entries}


ADAPTERS = {
    "frank_pocnet": (_frank_seeds, _frank_more, _frank_entries),
    "ti_datasheets": (_gpn_seeds, lambda url, xml: [], _gpn_entries),
}


# --- the shared half --------------------------------------------------------------------------------
def registry() -> dict:
    return yaml.safe_load(census_registry().read_text(encoding="utf-8")) or {}


def active(only: list[str] | None = None) -> list[str]:
    reg = registry()
    return [s for s, e in reg.items() if (only and s in only) or (not only and e.get("status") == "active")]


def _cache_file(source: str, url: str) -> Path:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1] or "index.html")
    return census_cache(source) / name


def _readable(r) -> bool:
    """Whether this reply is an index we can parse. HTML, or the XML of a sitemap — a manufacturer that
    publishes a list of its own parts publishes it as one, and `kind` has no name for XML."""
    return r.kind == "html" or r.body[:200].lstrip().lower().startswith(b"<?xml")


def read_source(source: str, *, fetch: bool = True, limit: int = 0, delay: float = http.DELAY) -> list[Entry]:
    """Walk one source's index pages — from the cache when they are there, from the site when they are
    not — and return everything it vouches for. Stamps the ledger so a second run asks for nothing."""
    entry = registry()[source]
    if source in LOCAL_ADAPTERS:
        return LOCAL_ADAPTERS[source](entry)              # already here: nothing to fetch, nothing to cache
    seeds, more, parse = ADAPTERS[source]
    led = Ledger(census_state(source), stages=CENSUS_STAGES, fields=CENSUS_FIELDS, versioned=CENSUS_VERSIONED)
    queue, seen, fetched, found = list(seeds(entry)), set(), 0, []
    while queue:
        url = queue.pop(0)
        if url in seen or led.get(url) and led.get(url)["skip_reason"]:
            continue
        seen.add(url)
        path = _cache_file(source, url)
        if path.exists():
            html = path.read_text(encoding="utf-8", errors="replace")
        elif not fetch or (limit and fetched >= limit):
            continue
        else:
            r = http.get(url, delay=delay)
            fetched += 1
            if not r.ok or not _readable(r):
                led.skip(url, (r.why or f"http {r.status}")[:60], url=url, http=r.status)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.body)
            html = r.text()
            led.stamp(url, "fetch", url=url, http=r.status, bytes=len(r.body), sha256=r.sha256)
        here = parse(url, html)
        found += here
        led.stamp(url, "read", version=READ_VERSION, n_parts=len(here))
        queue += [u for u in more(url, html) if u not in seen]
    led.save()
    return found


def build(only: list[str] | None = None, *, fetch: bool = True, limit: int = 0,
          delay: float = http.DELAY) -> dict[str, int]:
    """Read every active source and rewrite the census. One row per (part, source): two lists that both
    know a type is a fact worth more than one that only appears in the corpus."""
    rows: dict[tuple[str, str], Entry] = {}
    counts = {}
    for source in active(only):
        found = read_source(source, fetch=fetch, limit=limit, delay=delay)
        dropped = sum(1 for e in found if not e.url)
        found = [e for e in found if e.url]
        # A census row is two things at once: a fact, and the page that vouches for it. Without the
        # second it is neither evidence a reader can check nor a link the site can offer, so it is not
        # a row. 442 came out this way on 2026-09-22, all from model sources with no home_url recorded;
        # filling those in `data/models/sources/` brings the parts back on the next build.
        if dropped:
            counts[f"{source}: no public link, left out"] = dropped
        counts[source] = len({e.part for e in found})
        for e in found:
            rows.setdefault((e.part.upper(), source), e)
    # A source not run keeps what it said: its file is simply not rewritten.
    by_source: dict[str, list[Entry]] = {}
    for (_, source), e in sorted(rows.items()):
        by_source.setdefault(source, []).append(e)
    for source, entries in by_source.items():
        out = parts_census(source)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            for e in entries:
                w.writerow({"part": e.part, "kind": e.kind, "source": source, "url": e.url})
    counts["total rows"] = len(rows) + sum(1 for r in load_rows() if r["source"] not in by_source)
    counts["distinct parts"] = len({p for p, _ in rows})
    return counts


def load_rows() -> list[dict]:
    """Every source's census, in one list. One file each, so no single one outgrows what may live here."""
    out = []
    for f in sorted(parts_census().parent.glob("*.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            out += list(csv.DictReader(fh))
    return out


def norm(s: str) -> str:
    """The extractor's own spelling of a token. Defined here too, and deliberately: the extractor imports
    this module, so this module imports nothing from it. One line is cheaper than a cycle."""
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def load() -> dict[str, tuple[str, str]]:
    """norm(part) -> (part as written, kind), for the extractor. Absent census: an empty dict, and
    everything still works the way it did before there was one."""
    out = {}
    for r in load_rows():
        out.setdefault(norm(r["part"]), (r["part"], r["kind"]))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="pidx parts census", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--read", action="store_true", help="parse the pages already cached; fetch nothing")
    ap.add_argument("--limit", type=int, default=0, help="at most this many pages fetched, per source")
    ap.add_argument("--delay", type=float, default=http.DELAY, help="seconds between two requests to one host")
    a = ap.parse_args(argv)
    counts = build(a.source, fetch=not a.read, limit=a.limit, delay=a.delay)
    for name, n in counts.items():
        print(f"  {n:8}  {name}")
    print(f"written to {parts_census().parent}")
    return 0
