"""Find, for every wanted part, each definition in the model catalogue that could be its model.

    pidx models match

Reads every definition the indexer found (`config.spice_definitions()`) and writes, per part, the
candidates the curation then chooses from (`config.spice_matches()`). Nothing here judges a model: it
only decides which definitions are *for* a part, and says how each one was matched so the curation and
the site can weigh a near miss differently from an exact name.

Matching is by normalised name (upper case, alphanumerics only), after dropping the SPICE prefix
vendors glue on (Q2N3904, D1N4148, J2N5457, X..., M...; before a letter only the definition's own
device letter, so Motorola's Qmj15001 is MJ15001 and MPSA18 stays MPSA18):

  exact   same name                               2N3904 ~ Q2N3904
  suffix  name = part + short tag (≤4, not digit)  2N3904C (Cordell), 12AX7_JJ
  grade   part = name + one grade letter           BC549 for BC549C, 2N2222 for 2N2222A
  alias   any of the above against an alias        ECC83 for 12AX7

Records whose device type contradicts the kind (a D model for a BJT) are dropped, and so is a model
that lives inside another definition's subcircuit.

Ported from the old pipeline's `tools/coverage.py`; `tests/models/test_match.py` holds its behaviour.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from parts_index.core.config import (
    model_wanted,
    require,
    spice_curated,
    spice_definitions,
    spice_matches,
    wanted_parts,
)

TYPE_OK = {
    "bjt": {"NPN", "PNP", "SUBCKT"},
    "bjt-ge": {"NPN", "PNP", "SUBCKT"},
    "jfet": {"NJF", "PJF", "SUBCKT"},
    "mosfet": {"VDMOS", "NMOS", "PMOS", "SUBCKT"},
    "diode": {"D", "SUBCKT"}, "diode-ge": {"D", "SUBCKT"},
    "zener": {"D", "SUBCKT"}, "led": {"D", "SUBCKT"},
}
for _ok in TYPE_OK.values():
    _ok.add("ENCRYPTED")        # a wholly encrypted vendor file, indexed by its file name: type unknown
PREFIXES = ("Q", "D", "J", "M", "X", "U", "T", "V")
# Kinds whose parts are components we draw ourselves, not devices anybody publishes a model of.
NOT_MATCHED = {"non_native"}
# What each definition keeps from the catalogue: enough to find it again and to judge it.
KEEP = ("source", "file", "name", "kind", "type", "pins", "encrypted", "mfg", "parent")


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


# The SPICE element letter a vendor puts before a part's name, by the device the definition is. Before
# a digit any of PREFIXES is a prefix, as `2N3904` cannot start a name otherwise; before a letter only
# the letter of the definition's own device counts, because MPSA18 (a transistor) and DAN217 (a diode
# array) are part numbers that begin with M or D. A part that does start with its own device's letter,
# like the MOSFET MTP3055, gains a second key and keeps its own, which costs nothing unless a wanted
# part is called TP3055. Motorola's `Qmj15001` is the MJ15001.
ELEMENT_OF_TYPE = {"NPN": "Q", "PNP": "Q", "D": "D", "NJF": "J", "PJF": "J",
                   "NMOS": "M", "PMOS": "M", "VDMOS": "M", "SUBCKT": "X"}


def keys_of(name: str, type: str | None = None) -> set[str]:
    """The names a definition answers to: itself, and itself without the SPICE prefix a vendor glued
    on — before a digit whatever the letter, before a letter only its own device's letter."""
    n = norm(name)
    ks = {n}
    if len(n) > 2 and n[0] in PREFIXES and n[1].isdigit():
        ks.add(n[1:])
    elif len(n) > 3 and n[1].isalpha() and n[0] == ELEMENT_OF_TYPE.get((type or "").upper()):
        ks.add(n[1:])
    return ks


def match(part_n: str, key: str) -> str | None:
    if key == part_n:
        return "exact"
    if len(part_n) < 3:
        return None
    if key.startswith(part_n):
        tail = key[len(part_n):]
        if 0 < len(tail) <= 4 and not tail[0].isdigit():
            return "suffix"
    if part_n.startswith(key) and len(part_n) - len(key) == 1 \
            and part_n[-1] in "ABCGLRS" and len(key) >= 4:
        return "grade"
    return None


# --- what is wanted ----------------------------------------------------------------------------------
def flatten(wanted: dict):
    """Yield (kind, group, entry) for every part in a wanted mapping. A `complement:` named only as a
    field (MJL3281A's MJL1302A) becomes a part of its own, with the priority of the part that names it."""
    listed = set()
    for body in wanted.values():
        items = body if isinstance(body, list) else [e for v in body.values() for e in v]
        listed |= {str(e["part"]).upper() for e in items}
    for kind, body in wanted.items():
        groups = [("", body)] if isinstance(body, list) else list(body.items())
        for group, items in groups:
            for e in items:
                yield kind, group, e
                comp = e.get("complement")
                if comp and str(comp).upper() not in listed:
                    listed.add(str(comp).upper())
                    yield kind, group, {"part": comp, "priority": e.get("priority"),
                                        "note": f"complement of {e['part']}"}


def merge(wanted: dict, extra: dict) -> dict:
    """`extra` added under `wanted`, skipping parts `wanted` already lists: the first list to name a
    part keeps its entry, so a hand-written line is never replaced by a generated one."""
    listed = {str(e["part"]).upper() for body in wanted.values()
              for e in (body if isinstance(body, list) else [x for v in body.values() for x in v])}
    for kind, body in extra.items():
        groups = {"": body} if isinstance(body, list) else body
        for group, items in groups.items():
            items = [e for e in items if str(e["part"]).upper() not in listed]
            listed |= {str(e["part"]).upper() for e in items}
            base = wanted.setdefault(kind, [] if isinstance(body, list) else {})
            if isinstance(base, list):
                base.extend(items)
            else:
                base.setdefault(group or "listed", []).extend(items)
    return wanted


def from_csv(path: Path) -> dict:
    """`data/parts/wanted.csv` as a wanted mapping: one list per kind, aliases separated by spaces."""
    out: dict = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("part") or not r.get("kind"):
                continue
            e = {"part": r["part"], "priority": int(r["priority"]) if r.get("priority") else None}
            aliases = (r.get("aliases") or "").split()
            if aliases:
                e["aliases"] = aliases
            out.setdefault(r["kind"], []).append(e)
    return out


def from_curated(root: Path) -> dict:
    """Every part the curation has already reached, so it is looked for again when the catalogue
    grows. Its kind and group come from its own record."""
    out: dict = {}
    for p in sorted(root.glob("*/*/part.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("part") and d.get("kind"):
            out.setdefault(d["kind"], {}).setdefault(d.get("group") or "curated", []).append(
                {"part": d["part"], "priority": d.get("priority")})
    return out


def load_wanted() -> dict:
    """The hand-written list first, then the generated one, then whatever was curated before."""
    wanted = yaml.safe_load(model_wanted().read_text(encoding="utf-8")) or {}
    if wanted_parts().exists():
        merge(wanted, from_csv(wanted_parts()))
    if spice_curated().exists():
        merge(wanted, from_curated(spice_curated()))
    return wanted


# --- the matching ------------------------------------------------------------------------------------
def names_wanted(wanted: dict) -> set[str]:
    """The first three characters of every name a part may be found under: a definition whose keys
    share none of them cannot match anything, so it need not be held in memory."""
    out = set()
    for _, _, e in flatten(wanted):
        for nm in [e["part"], *(e.get("aliases") or []), *(e.get("stand_in") or [])]:
            n = norm(str(nm))
            if n:
                out.add(n[:3])
    return out


def load_definitions(path: Path, heads: set[str] | None = None) -> list[dict]:
    recs = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if heads is not None and not any(k[:3] in heads for k in keys_of(r["name"], r.get("type"))):
                continue
            recs.append({k: r.get(k) for k in KEEP})
    return recs


def find(wanted: dict, recs: list[dict]) -> dict:
    """{part: {kind, group, priority, candidates: [...]}} for every wanted part."""
    by_key = defaultdict(list)
    prefixes = defaultdict(list)          # first 3 chars -> keys, for suffix/grade
    for i, r in enumerate(recs):
        for k in keys_of(r["name"], r["type"]):
            by_key[k].append(i)
    for k in by_key:
        prefixes[k[:3]].append(k)

    found = {}
    for kind, group, e in flatten(wanted):
        if kind in NOT_MATCHED:
            continue
        part = str(e["part"])
        names = [part] + [str(a) for a in e.get("aliases", []) or []]
        # stand_in: models of *other* parts declared equivalent in the wanted list (with the reason in
        # the note); used only when the part has no model under its own names, exact names only, and
        # labelled so the curation and the site show they are stand-ins
        stand = [str(a) for a in e.get("stand_in", []) or []]
        cands, seen = [], set()
        for nm in names + [None] + stand:
            if nm is None:
                if cands:
                    break
                continue
            pn = norm(nm)
            if not pn:
                continue
            for k in prefixes.get(pn[:3], []):
                how = match(pn, k)
                if not how or (nm in stand and how != "exact"):
                    continue
                for i in by_key[k]:
                    r = recs[i]
                    if i in seen:
                        continue
                    ok = TYPE_OK.get(kind)
                    if ok and r["type"] not in ok:
                        continue
                    if kind not in TYPE_OK and r["kind"] != "subckt":
                        continue            # ICs, valves, blocks: only subckts
                    if r.get("parent"):          # model internal to a subckt
                        continue
                    seen.add(i)
                    cands.append({"source": r["source"], "file": r["file"],
                                  "name": r["name"], "kind": r["kind"],
                                  "type": r["type"], "pins": r["pins"],
                                  "match": how if nm == part else
                                  f"{'stand-in' if nm in stand else 'alias'}:{nm}/{how}",
                                  "encrypted": r["encrypted"], "mfg": r.get("mfg")})
        found[part] = {"kind": kind, "group": group,
                       "priority": e.get("priority"), "candidates": cands}
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    wanted = load_wanted()
    recs = load_definitions(require(spice_definitions(), "matching parts to models"), names_wanted(wanted))
    found = find(wanted, recs)
    out = spice_matches()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(found, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    with_any = sum(1 for v in found.values() if v["candidates"])
    by_source = Counter(c["source"] for v in found.values() for c in v["candidates"])
    print(f"{with_any:,} of {len(found):,} wanted parts have at least one candidate "
          f"({sum(by_source.values()):,} definitions from {len(by_source)} sources) -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
