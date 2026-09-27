"""Every data sheet an archive or a catalogue links for a part, read from pages this project already holds.

    pidx datasheets links [--source frank_pocnet]

Frank Philipse's tube archive files 21,450 data sheets under 11,700 valve types, several per type and
each with the company that printed it: a 12AX7 has sheets from General Electric, Tung-Sol, Sylvania,
Brimar, RFT and more. The census kept one link per type, which answered "does this valve exist"; a
reader who wants to compare what three factories said about the same valve needs all of them, and the
archive's own index pages — already cached by the census, so no request is made — list them.

What leaves the page is the row: the type as the archive writes it, the maker it names, the link, the
size, the language when the archive gives one. "12AX7 (= ECC83)" is the archive's own statement that it
filed an ECC83 sheet under 12AX7; the sheet is listed under both, and says so.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from parts_index.core.config import census_cache, datasheet_links
from parts_index.core.ledger import today
from parts_index.core.parts import catalogue

FIELDS = ("part", "maker", "maker_text", "url", "bytes", "lang", "filed_as", "also", "source", "checked")

FRANK = "https://frank.pocnet.net/"
FRANK_ROW = re.compile(
    r'<tr>\s*<td>\s*(?P<type>[^<]*?)\s*(?:<a[^>]*>.*?</A>\s*)?<td>\s*(?P<maker>[^<]*?)\s*<td>\s*[^<]*?\s*'
    r'<td[^>]*>\s*<a href="(?P<url>[^"]+\.pdf)">[^<]*</a>\s*\((?P<bytes>\d+) bytes\)\s*(?:\((?P<lang>[a-z]{2})\))?',
    re.S | re.I)
EQUAL = re.compile(r"^(?P<type>\S+)\s*\(=\s*(?P<also>[^)]+)\)")
# The archive's names for makers the catalogue knows, where the name is not already one of their aliases.
# "RCA (HB3)" is RCA's own tube handbook HB-3; the bracket says which book the sheet came from.
FRANK_MAKERS = {"rca (hb3)": "rca", "rca (rc30)": "rca", "ge": "general-electric", "tungsram": "tungsram"}


def maker_id(text: str) -> str:
    t = text.strip().lower()
    if t in FRANK_MAKERS:
        return FRANK_MAKERS[t]
    mid, _ = catalogue.maker_of(text)
    return mid


def read_frank(pages: list[Path]) -> list[dict]:
    out, seen = [], set()
    for p in sorted(pages):
        html = p.read_text(encoding="latin-1")
        for m in FRANK_ROW.finditer(html):
            filed = " ".join(m["type"].split())
            eq = EQUAL.match(filed)
            part = (eq["type"] if eq else filed.split(" ")[0]).upper()
            also = " ".join(a.strip().upper() for a in re.split(r"[,/;]| or ", eq["also"])) if eq else ""
            url = m["url"] if m["url"].startswith("http") else FRANK + m["url"].lstrip("/")
            if (part, url) in seen or not part:
                continue
            seen.add((part, url))
            out.append({"part": part, "maker": maker_id(m["maker"]), "maker_text": m["maker"].strip(),
                        "url": url, "bytes": m["bytes"], "lang": m["lang"] or "", "filed_as": filed,
                        "also": also, "source": "frank_pocnet", "checked": today()})
    return out


READERS = {"frank_pocnet": lambda: read_frank(list(census_cache("frank_pocnet").glob("sheets*.html")))}


def write(source: str, rows: list[dict]) -> Path:
    p = datasheet_links(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["part"], r["maker_text"], r["url"])):
            w.writerow(r)
    tmp.replace(p)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx datasheets links")
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    a = ap.parse_args(argv)
    for s in a.source or list(READERS):
        if s not in READERS:
            print(f"{s}: no reader", file=sys.stderr)
            return 2
        rows = READERS[s]()
        p = write(s, rows)
        named = sum(1 for r in rows if r["maker"])
        print(f"{s}: {len(rows)} data sheets for {len({r['part'] for r in rows})} types, "
              f"{named} with a maker the catalogue knows -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
