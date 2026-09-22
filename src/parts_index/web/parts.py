"""Everything the site knows about one part, in one small file.

The site is static and has no backend, so a part page is one request. That shapes everything here: the
search index is the smallest thing that can rank and route, and each part's own file carries what its
page needs and not a byte more — already joined, already grouped, already sorted.

Three things are worth doing here rather than in the browser:

**The same sheet is published by several archives.** 1,792 of them, 2,076 extra copies; the Bassman
5F6-A is in three. Sending all three and asking the page to work it out means sending them; grouping by
the checksum here means one result that says "also at el34world, schematicheaven".

**A part can be everywhere.** The 12AX7 is in 2,478 documents. Nobody reads 2,478 links, and sending
them costs more than the rest of the site, so the best `CAP` are sent with the count of what was left.
"Best" is the document that shows the part on a page the classifier judged to be a schematic, and after
that the one that shows it most.

**Uses are one row per page, and a reader wants one row per document.** Twelve pages of one service
manual is one result with twelve page links, not twelve results.
"""
from __future__ import annotations

import csv
from collections import defaultdict

import yaml

from parts_index.core.config import (
    model_part,
    schematics_documents,
    schematics_pages,
    schematics_parts,
    schematics_uses,
)

CAP = 200            # documents sent for one part
PAGE_CAP = 24        # page links inside one document, when there is room for that many
# A budget across the whole part, because a fixed cap per document multiplies. The 1N4148 is in
# everything: at 200 documents and 24 pages each its file came to 303 KB, and the two-hundredth
# document of a diode that is in everything is not a result anybody reads. Spread the same budget and
# the heavy parts get a few pages each while the 89 % that fit in 4 KB are untouched.
LINK_BUDGET = 600
MODEL_KEYS = ("source", "name", "def", "type", "pins", "verbatim", "changes", "symbol")


def rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sources() -> list[str]:
    d = schematics_documents("x").parent
    return sorted(p.stem for p in d.glob("*.csv")) if d.is_dir() else []


def index() -> dict:
    """The whole index, read once: documents and pages by source, uses by part."""
    docs: dict[str, dict] = {}
    pages: dict[str, dict] = {}
    uses: dict[str, list] = defaultdict(list)
    for i, s in enumerate(sources()):
        docs[s] = {r["id"]: r for r in rows(schematics_documents(s))}
        pages[s] = {(r["doc"], r["page"]): r for r in rows(schematics_pages(s))}
        for u in rows(schematics_uses(s)):
            uses[u["part"]].append((i, u))
    return {"sources": sources(), "documents": docs, "pages": pages, "uses": uses}


def model_recipes() -> dict[str, dict]:
    """Every published recipe, by part."""
    root = model_part("x", "y").parent.parent
    out: dict[str, dict] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.glob("*/*.yaml")):
        out[p.stem] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return out


def trim_models(doc: dict) -> dict:
    """The recipe as the page shows it: what each model is, how good it was, and where to get it."""
    out = {"kind": doc.get("kind", ""), "preferred": doc.get("preferred", ""),
           "why": doc.get("preferred_why", ""), "models": []}
    for m in doc.get("models") or []:
        e = {k: m[k] for k in MODEL_KEYS if m.get(k) not in (None, "", [])}
        get = m.get("get") or {}
        e["get"] = {k: get[k] for k in ("url", "member", "installed_with", "file", "how")
                    if get.get(k)}
        v = m.get("verification") or {}
        if v.get("score") is not None:
            e["score"] = v["score"]
            e["rows"] = [v.get("pass", 0), v.get("marginal", 0), v.get("fail", 0)]
        out["models"].append(e)
    if doc.get("datasheet"):
        out["datasheet"] = doc["datasheet"]
    return out


def deep_links(doc: dict) -> int:
    """How many of this copy's page links tell the viewer where on the page to look."""
    return sum(1 for p in doc["p"] if "&zoom=" in p[1])


def page_entry(page: dict | None, u: dict) -> list:
    """One page link: where it is, what is beside the part, and how many times it is on it."""
    return [int(u["page"]), (page or {}).get("url", ""), u["near"], int(u["times"] or 1)]


def part_payload(part: str, idx: dict, recipe: dict | None) -> dict:
    """One part's whole page."""
    by_doc: dict[tuple[int, str], dict] = {}
    for si, u in idx["uses"].get(part, []):
        source = idx["sources"][si]
        key = (si, u["doc"])
        d = by_doc.get(key)
        if d is None:
            doc = idx["documents"][source].get(u["doc"], {})
            d = by_doc[key] = {"s": si, "t": doc.get("title", ""), "u": doc.get("url", ""),
                               "y": doc.get("year", ""), "sha": doc.get("sha", ""),
                               "schematic": 0, "p": []}
        page = idx["pages"][source].get((u["doc"], u["page"]))
        d["schematic"] = max(d["schematic"], int((page or {}).get("schematic") or 0))
        d["p"].append(page_entry(page, u))

    # One sheet published by several archives is one result that names the others. Which copy is kept
    # matters: they differ by the link they offer, and the one that puts the reader on the right part
    # of the right page is worth more than the one that opens the document at the front.
    groups: dict[str, list[dict]] = defaultdict(list)
    singles: list[dict] = []
    for d in by_doc.values():
        (groups[d["sha"]] if d["sha"] else singles).append(d)
    merged: list[dict] = list(singles)
    for copies in groups.values():
        copies.sort(key=lambda d: (-d["schematic"], -deep_links(d), -len(d["p"]), d["s"]))
        first, rest = copies[0], copies[1:]
        if rest:
            first["also"] = sorted({idx["sources"][d["s"]] for d in rest})
        merged.append(first)

    merged.sort(key=lambda d: (-d["schematic"], -sum(p[3] for p in d["p"]), d["t"]))
    shown = merged[:CAP]
    per = min(PAGE_CAP, max(2, LINK_BUDGET // len(shown))) if shown else PAGE_CAP
    for d in shown:
        d["p"].sort(key=lambda p: p[0])
        if len(d["p"]) > per:
            d["more"] = len(d["p"]) - per
            del d["p"][per:]
        d.pop("sha", None)
    # The source names are the same fifty-eight in every part file, so they live once in `parts.json`
    # and a document names its source by position. Repeating them here cost 90 MB across 15,558 files.
    out = {"part": part, "docs": shown,
           "n": {"documents": len(merged), "shown": len(shown),
                 "copies": len(by_doc) - len(merged)}}
    if recipe:
        out["models"] = trim_models(recipe)
    return out


def search_index(idx: dict, recipes: dict) -> list[list]:
    """What the browser loads first: every part, with just enough to rank and route it.

    Tuples rather than objects, because the key names would be most of the file.
    """
    counts = {r["part"]: (int(r["documents"]), int(r["uses"]))
              for r in rows(schematics_parts())}
    out = []
    for part in sorted(set(counts) | set(recipes)):
        docs, uses = counts.get(part, (0, 0))
        out.append([part, docs, uses, len(recipes.get(part, {}).get("models") or [])])
    return out
