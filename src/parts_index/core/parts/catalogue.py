"""What each part is, as far as a document says so: families, the references behind them, and which parts
a manufacturer's own sheet files under which family.

The dictionary (`known_parts.csv`) answers "is this a part, and what kind"; the catalogue answers the next
question a reader has, "and what is that". It is small, hand-kept and English, and everything in it names
its source — an id in `references.csv` — because a family given without one is a guess, and the site
already has a place for guesses: the kind the extractor reads off the shape of a number.

Three tables, one loader each, and `check()` for the rules that keep them joined: every family a part is
filed under exists, every reference cited exists, the hierarchy has no loop, and each device kind of the
site defaults to exactly one family.
"""
from __future__ import annotations

import csv
from functools import cache

import yaml

from parts_index.core.config import documented_families, part_families, part_references


def _rows(path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@cache
def families() -> dict[str, dict]:
    """Every family by id, in file order, each carrying its own id."""
    p = part_families()
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {k: {"id": k, **(v or {})} for k, v in doc.items()}


@cache
def references() -> dict[str, dict]:
    return {r["id"]: r for r in _rows(part_references())}


@cache
def documented() -> dict[str, dict]:
    """Parts a manufacturer's sheet files under a family, by part."""
    return {r["part"]: r for r in _rows(documented_families())}


def lineage(fid: str) -> list[str]:
    """The family and every family above it, nearest first."""
    fams, out = families(), []
    while fid and fid in fams and fid not in out:
        out.append(fid)
        fid = fams[fid].get("broader") or ""
    return out


@cache
def _by_device() -> dict[str, str]:
    return {k: fid for fid, f in families().items() for k in f.get("kinds") or ()}


def family_for(devices: tuple[str, ...] | list[str]) -> str:
    """The family a part defaults to when all that is known is which device kinds it could be.

    One device, its family. Several — a JEDEC 2N number is a BJT, a JFET or a MOSFET and the number cannot
    say which — the nearest family they all sit inside, so the page says "a transistor" rather than
    choosing. Nothing known, nothing said.
    """
    by = _by_device()
    chains = [lineage(by[d]) for d in devices if d in by]
    if not chains:
        return ""
    for fid in chains[0]:
        if all(fid in c for c in chains[1:]):
            return fid
    return ""


def family_of(part: str, devices: tuple[str, ...] | list[str] = ()) -> tuple[str, str]:
    """(family, basis) for a part: what its manufacturer's sheet says, or else what its kind implies."""
    d = documented().get(part)
    if d and d.get("family"):
        return d["family"], "documented"
    fid = family_for(devices)
    return (fid, "kind") if fid else ("", "")


def check(devices: list[str] | None = None) -> list[str]:
    """Everything that would make the catalogue lie or break a link, as one line each."""
    fams, refs, out = families(), references(), []
    seen: dict[str, str] = {}
    for fid, f in fams.items():
        b = f.get("broader")
        if b and b not in fams:
            out.append(f"family {fid}: broader {b} does not exist")
        if b and fid in lineage(b):
            out.append(f"family {fid}: its broader chain loops back to it")
        for r in f.get("refs") or ():
            if r not in refs:
                out.append(f"family {fid}: reference {r} is not in references.csv")
        for k in f.get("kinds") or ():
            if k in seen:
                out.append(f"device kind {k} defaults to both {seen[k]} and {fid}")
            seen[k] = fid
        if not f.get("label") or not f.get("definition"):
            out.append(f"family {fid}: needs a label and a definition")
    for k in devices or ():
        if k not in seen:
            out.append(f"device kind {k} defaults to no family")
    for part, r in documented().items():
        if r["family"] not in fams:
            out.append(f"part {part}: family {r['family']} does not exist")
        for ref in r["refs"].split():
            if ref not in refs:
                out.append(f"part {part}: reference {ref} is not in references.csv")
        if r.get("status") not in ("draft", "reviewed"):
            out.append(f"part {part}: status must be draft or reviewed")
    for rid, r in refs.items():
        if not r.get("url", "").startswith(("https://", "http://")):
            out.append(f"reference {rid}: no usable URL")
    return out
