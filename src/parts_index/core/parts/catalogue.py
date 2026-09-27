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
import re
from functools import cache
from pathlib import Path

import yaml

from parts_index.core.config import (
    documented_families,
    part_families,
    part_makers,
    part_references,
    part_relations,
)


def stamp(path: Path) -> tuple[str, float]:
    """What a cached table is keyed by: where it is and when it last changed, so a test's own data or an
    edit made during a session is read afresh."""
    return str(path), path.stat().st_mtime if path.exists() else 0.0


@cache
def _csv(key: tuple[str, float]) -> tuple[dict, ...]:
    p = Path(key[0])
    if not p.exists():
        return ()
    with open(p, encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


@cache
def _yaml(key: tuple[str, float]) -> dict:
    p = Path(key[0])
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def families() -> dict[str, dict]:
    """Every family by id, in file order, each carrying its own id."""
    return {k: {"id": k, **(v or {})} for k, v in _yaml(stamp(part_families())).items()}


def references() -> dict[str, dict]:
    return {r["id"]: r for r in _csv(stamp(part_references()))}


def documented() -> dict[str, dict]:
    """Parts a manufacturer's sheet files under a family, by part."""
    return {r["part"]: r for r in _csv(stamp(documented_families()))}


# What each relation says, read from the part in the first column. They are directional and never
# transitive: a replacement for a replacement is not a replacement, and "in one datasheet with" is the only
# one that holds both ways.
RELATIONS = ("next_generation_of", "replacement_for", "same_product_as", "same_datasheet")


def relations() -> tuple[dict, ...]:
    return _csv(stamp(part_relations()))


def related(part: str) -> list[list]:
    """Every relation that touches `part`: [relation, other part, "out" or "in", refs, note, status].

    A same-datasheet row names the first part of the sheet as its anchor, so the parts sharing a sheet are
    the rows with the same anchor and the same reference, and each is listed with all the others.
    """
    rows = relations()
    out: list[list] = []
    seen = set()
    for r in rows:
        if r["relation"] == "same_datasheet":
            continue
        refs = r["refs"].split()
        if r["part"] == part:
            out.append([r["relation"], r["other"], "out", refs, r["note"], r["status"]])
        elif r["other"] == part:
            out.append([r["relation"], r["part"], "in", refs, r["note"], r["status"]])
    mine = [(r["other"], r["refs"]) for r in rows if r["relation"] == "same_datasheet" and r["part"] == part]
    for anchor, refs in mine:
        for r in rows:
            if (r["relation"] == "same_datasheet" and (r["other"], r["refs"]) == (anchor, refs)
                    and r["part"] != part and (r["part"], refs) not in seen):
                seen.add((r["part"], refs))
                out.append(["same_datasheet", r["part"], "both", refs.split(), r["note"], r["status"]])
    return out


def makers() -> dict[str, dict]:
    """Every organisation by id, each carrying its own id."""
    return {k: {"id": k, **(v or {})} for k, v in _yaml(stamp(part_makers())).items()}


def _aliases() -> dict[str, str]:
    return {a.lower(): mid for mid, m in makers().items() for a in [m.get("name", ""), *(m.get("aliases") or ())]}


def maker_of(text: str) -> tuple[str, list[str]]:
    """The organisation a datasheet's maker line names, and the others it mentions in brackets.

    The model curation writes the maker as it found it — "Texas Instruments (National Semiconductor)",
    "onsemi (ex-Fairchild)", "fairchild (onsemi-hosted)". The part before the bracket is who published the
    sheet; a known name inside the brackets is lineage, told apart so the page can say "a National
    Semiconductor design, documented today by Texas Instruments".
    """
    al = _aliases()
    head, _, rest = (text or "").partition("(")
    main = al.get(head.strip().lower(), "")
    if not main:
        return "", []                             # lineage of nobody named is not lineage
    others: list[tuple[int, str]] = []
    low = rest.lower()
    # Short names (TI, ST, GE, THAT) are ordinary words or letters inside other words; only a name of six
    # letters or more is looked for inside the brackets.
    for alias, mid in al.items():
        if len(alias) < 6 or mid == main:
            continue
        m = re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", low)
        if m and mid not in (o for _, o in others):
            others.append((m.start(), mid))
    return main, [mid for _, mid in sorted(others)]


def lineage(fid: str) -> list[str]:
    """The family and every family above it, nearest first."""
    fams, out = families(), []
    while fid and fid in fams and fid not in out:
        out.append(fid)
        fid = fams[fid].get("broader") or ""
    return out


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


def shared(fids: list[str]) -> str:
    """The nearest family every one of `fids` sits inside; "" when any is empty or unknown."""
    if not fids or any(not f or f not in families() for f in fids):
        return ""
    chains = [lineage(f) for f in fids]
    return next((f for f in chains[0] if all(f in c for c in chains[1:])), "")


def family_of(part: str, devices: tuple[str, ...] | list[str] = (), named: list[str] | None = None) -> tuple[str, str]:
    """(family, basis) for a part, from the surest thing that says: the manufacturer's sheet, then the
    letters of its name under the standard that assigned them, then the kind it is filed as.

    The name counts only when it is more precise than the kind and agrees with it — a 2SK is a field-effect
    transistor whether the kind says "jfet/mosfet" or nothing, but a name never moves a part out of the
    family its kind puts it in.
    """
    d = documented().get(part)
    if d and d.get("family"):
        return d["family"], "documented"
    by_kind = family_for(devices)
    by_name = shared(named or [])
    if by_name and (not by_kind or by_kind in lineage(by_name)):
        return by_name, "name"
    return (by_kind, "kind") if by_kind else ("", "")


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
    for r in relations():
        if r["relation"] not in RELATIONS:
            out.append(f"relation {r['part']} -> {r['other']}: {r['relation']} is not one of {', '.join(RELATIONS)}")
        if not r["refs"].split():
            out.append(f"relation {r['part']} -> {r['other']}: a relation needs a reference")
        for ref in r["refs"].split():
            if ref not in refs:
                out.append(f"relation {r['part']} -> {r['other']}: reference {ref} is not in references.csv")
        if r.get("status") not in ("draft", "reviewed"):
            out.append(f"relation {r['part']} -> {r['other']}: status must be draft or reviewed")
    orgs = makers()
    seen_alias: dict[str, str] = {}
    for mid, m in orgs.items():
        if not m.get("name"):
            out.append(f"maker {mid}: needs a name")
        for a in m.get("aliases") or ():
            if a != a.lower():
                out.append(f"maker {mid}: alias {a} must be lower case")
            if a in seen_alias and seen_alias[a] != mid:
                out.append(f"maker {mid}: alias {a} also belongs to {seen_alias[a]}")
            seen_alias[a] = mid
        src = m.get("source")
        if (m.get("country") or m.get("founded")) and not src:
            out.append(f"maker {mid}: a country or founding year needs a source")
        for ev in m.get("events") or ():
            if len(ev) != 4:
                out.append(f"maker {mid}: event {ev} is not [year, what, with, source]")
                continue
            if ev[2] and ev[2] not in orgs:
                out.append(f"maker {mid}: event names {ev[2]}, which is not in makers.yaml")
            if not ev[3]:
                out.append(f"maker {mid}: event {ev[:2]} has no source")
        for s_ in [src] + [ev[3] for ev in m.get("events") or () if len(ev) == 4]:
            if s_ and not str(s_).startswith("https://") and s_ not in refs:
                out.append(f"maker {mid}: source {s_} is neither a URL nor in references.csv")
    return out
