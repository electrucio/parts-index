"""Carry across the parts somebody decided are worth having, and who decided.

    pidx migrate wanted --from <catalog directory>

The index knows a part because it read it off a schematic or found a model for it. That misses the
parts a person would look up and find nothing: the ones a shop still sells, the ones a factory databook
published, the ones an article discusses. Three lists of those were built by the old pipeline and have
been sitting in a YAML nobody reads.

Published as `data/parts/wanted.csv` so a part with no documents and no model still has a page that says
why it is listed — "sold by musikding.de under Transistoren / Germanium Transistoren / Selektiert" is an
answer, and a bare name is not. It doubles as the project's own list of what to look for next.

**A fourth list is deliberately left out.** `wanted_survey` ranks parts by how many open-source projects
place them, and it is 423 regulators deep in 3.3 V LDOs for microcontroller boards — real parts,
popular, and outside the analog-audio focus this index keeps.

What crosses is the fact and not the copy: who lists the part, under which category, its polarity and
gain where they are stated outright. A shop's product description is its own writing and stays where it
is.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import yaml

from parts_index.core.config import wanted_parts

FIELDS = ("part", "kind", "source", "category", "note", "priority", "aliases")
# The three lists, and what to call the thing that vouches for each part.
LISTS = {
    "wanted_musikding": "musikding.de",
    "wanted_databooks": "databook",
    "wanted_audio_docs": "audio documents",
}
SHOP = re.compile(r"musikding\.de:\s*([^;]+);\s*(.*)", re.S)
DATABOOK = re.compile(r"([^:]+\(\d{4}\)):\s*([^;]+);\s*(.*)", re.S)
DOCS = re.compile(r"audio docs:\s*([^;]+);\s*(.*)", re.S)
POLARITY = re.compile(r"\b(NPN|PNP)\b", re.I)
GAIN = re.compile(r"(?:Hfe|Verst\w*rkungsfaktor)[^0-9]{0,30}(\d+)\s*(?:bis|-|–|to)\s*(\d+)", re.I)
PAGES = re.compile(r"(\d+)\s+magazine pages")
MAKER = re.compile(r"\[([^\]]+)\]\s*$")


def facts(body: str) -> str:
    """The things a description states outright, and nothing it merely says well."""
    out = []
    m = POLARITY.search(body)
    if m:
        out.append(m.group(1).upper())
    m = GAIN.search(body)
    if m:
        out.append(f"hFE {m.group(1)}–{m.group(2)}")
    return ", ".join(out)


def entry(kind: str, item: dict, list_name: str) -> dict | None:
    """One row: the part, who vouches for it, and why — never their prose."""
    part = str(item.get("part") or "").strip()
    if not part:
        return None
    note = str(item.get("note") or "")
    source, category, extra = LISTS[list_name], "", ""

    m = SHOP.match(note)
    if m:
        category, extra = m.group(1).strip(), facts(m.group(2))
    elif (m := DATABOOK.match(note)):
        source, category = m.group(1).strip(), m.group(2).strip()
        pages = PAGES.search(m.group(3))
        extra = f"{pages.group(1)} magazine pages mention it" if pages else ""
    elif (m := DOCS.match(note)):
        category, body = m.group(1).strip(), m.group(2)
        maker = MAKER.search(body)
        extra = f"made by {maker.group(1).strip()}" if maker else ""

    return {
        "part": part,
        "kind": kind,
        "source": source,
        "category": category,
        "note": extra,
        "priority": item.get("priority") or "",
        "aliases": " ".join(str(a) for a in (item.get("aliases") or [])),
    }


def read(path: Path, list_name: str) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for kind, items in doc.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                row = entry(str(kind), item, list_name)
                if row:
                    out.append(row)
    return out


def promote(root: Path) -> dict:
    rows: dict[tuple[str, str], dict] = {}
    counts: dict[str, int] = {}
    for name in LISTS:
        path = root / f"{name}.yaml"
        if not path.exists():
            continue
        found = read(path, name)
        counts[name] = len(found)
        for r in found:
            rows.setdefault((r["part"].upper(), r["source"]), r)
    out = wanted_parts()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for key in sorted(rows):
            w.writerow(rows[key])
    counts["rows"] = len(rows)
    counts["parts"] = len({k[0] for k in rows})
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="root", required=True, help="the old catalog directory")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        print(f"{root} is not here", file=sys.stderr)
        return 1
    c = promote(root)
    for name in LISTS:
        if name in c:
            print(f"  {name:22s} {c[name]:5,}")
    print(f"{c['rows']:,} rows for {c['parts']:,} parts -> {wanted_parts()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
