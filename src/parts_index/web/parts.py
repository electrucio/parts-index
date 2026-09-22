"""Everything the site knows about one part, in one small file.

The site is static and has no backend, so a part page is one request. That shapes everything here: the
search index is the smallest thing that can rank and route, and each part's own file carries what its
page needs and not a byte more — already joined, already grouped, already sorted.

Three things are worth doing here rather than in the browser:

**The same sheet is published by several archives.** 1,792 of them, 2,076 extra copies; the Bassman
5F6-A is in three. Sending all three and asking the page to work it out means sending them; grouping by
the checksum here means one result that says "also at el34world, schematicheaven".

**Nothing is cut off.** The 12AX7 is in 1,817 documents across 33 sources, and every one of them is
sent: cutting to the two hundred that rank highest meant 147 factory sheets crowding out Wireless World
and Elektor entirely, which is exactly the part of the answer somebody looking up a valve wants. What
makes that affordable is that a page link is stored as the suffix of its document's URL rather than
whole — every one of the 94,170 of them is — which is 76 % of the URL text in the index, repeated.

**Uses are one row per page, and a reader wants one row per document.** Twelve pages of one service
manual is one result with twelve page links, not twelve results.

And three answers to "where is it used" are three different questions, so they travel apart: a project
page or a factory sheet is a circuit somebody built, a magazine page is an article about one, and a
GitHub repository is a board somebody is making now. The site folds each group on its own, and each
source inside it on its own, which is what keeps a part with three thousand hits readable.
"""
from __future__ import annotations

import csv
from collections import defaultdict

import yaml

from parts_index.core.config import (
    dataset_table,
    known_parts,
    model_part,
    schematics_documents,
    schematics_pages,
    schematics_parts,
    schematics_registry,
    schematics_uses,
)
from parts_index.core.parts.extractor import canonical, family_of

REPO_CAP = 200        # GitHub projects listed for one part
MODEL_KEYS = ("source", "name", "def", "type", "pins", "verbatim", "changes", "symbol")


def rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def part_kind(part: str, recipes: dict, dictionary: dict[str, str]) -> str:
    """What sort of device this part is, from the surest source that knows.

    Three of them, in order: the curation, which decided; the part dictionary, which was judged; and the
    extractor's family patterns, which recognise the shape of a number. The last is a guess and says so
    — `2N3904` and `2N5457` are both JEDEC, one a transistor and one a JFET, and the family cannot tell
    them apart. 93 % of parts get an answer this way.
    """
    if part in recipes:
        return recipes[part].get("kind", "")
    if part in dictionary:
        return dictionary[part]
    fam = family_of(canonical(part) or part)
    return fam[1] if fam else ""


def dictionary_kinds() -> dict[str, str]:
    """The kind a human gave each part in the dictionary."""
    return {r["name"]: r["kind"] for r in rows(known_parts()) if r.get("kind")}


def kinds() -> dict[str, str]:
    """What each source is — a site, a factory archive, a magazine, a book — from the public registry."""
    reg = schematics_registry()
    if not reg.exists():
        return {}
    entries = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    return {k: (v or {}).get("kind", "") for k, v in entries.items()}


def repos() -> dict[str, list[list]]:
    """Open-source projects that place each part, from the dataset distilled in `data/datasets/`.

    The third answer to "where is it used", and the only one that points at a board somebody is working
    on rather than at a document about one.
    """
    path = dataset_table("part_repos")
    out: dict[str, list[list]] = defaultdict(list)
    for r in rows(path):
        out[r["part"]].append([r["url"].replace("https://github.com/", ""), int(r["sheets"] or 1)])
    for v in out.values():
        v.sort(key=lambda x: (-x[1], x[0]))
    return out


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
    return {"sources": sources(), "kinds": kinds(), "documents": docs, "pages": pages,
            "uses": uses, "repos": repos()}


def model_recipes() -> tuple[dict[str, dict], list[str]]:
    """Every published recipe, by part, and the parts that have more than one.

    A part is filed under one kind, but five are filed under two — BC109, BC177, BCY70, BCY71 and BUX48,
    each curated once as silicon and once as germanium. They are silicon: under the Pro-Electron naming
    convention the first letter says so, A for germanium and B for silicon. Until the curation is merged
    the one with more candidates is used, and the collision is reported rather than resolved in silence,
    which is what keying by part name alone did — and it kept the wrong one, `bjt-ge` sorting last.
    """
    root = model_part("x", "y").parent.parent
    out: dict[str, dict] = {}
    clashes: list[str] = []
    if not root.is_dir():
        return out, clashes
    for p in sorted(root.glob("*/*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        seen = out.get(p.stem)
        if seen is None:
            out[p.stem] = doc
            continue
        clashes.append(p.stem)
        if len(doc.get("models") or []) > len(seen.get("models") or []):
            out[p.stem] = doc
    return out, clashes


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


def page_entry(page: dict | None, u: dict, doc_url: str) -> list:
    """One page link: where it is, what is beside the part, and how many times it is on it.

    The link is stored as what to add to the document's own URL — `#page=47&zoom=200,55,523&h=792` —
    because that is what it is. All 94,170 of them are a suffix of it, and writing them whole was three
    quarters of the URL text in a part's page. Anything that is not a suffix is kept whole, and the
    reader can tell which by whether it starts with a scheme.
    """
    url = (page or {}).get("url", "")
    if doc_url and url.startswith(doc_url):
        url = url[len(doc_url):]
    return [int(u["page"]), url, u["near"], int(u["times"] or 1)]


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
        d["p"].append(page_entry(page, u, d["u"]))

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
    shown = merged
    for d in shown:
        d["p"].sort(key=lambda p: p[0])
        d.pop("sha", None)
    # The source names are the same fifty-eight in every part file, so they live once in `parts.json`
    # and a document names its source by position. Repeating them here cost 90 MB across 15,558 files.
    out = {"part": part, "docs": shown,
           "n": {"documents": len(merged), "shown": len(shown),
                 "copies": len(by_doc) - len(merged)}}
    gh = idx["repos"].get(part) or []
    if gh:
        out["repos"] = gh[:REPO_CAP]
        out["n"]["repos"] = len(gh)
    if recipe:
        out["models"] = trim_models(recipe)
    return out


def search_index(idx: dict, recipes: dict) -> tuple[list[list], list[str]]:
    """What the browser loads first: every part, with just enough to rank, filter and route it.

    Tuples rather than objects, because the key names would be most of the file, and the kind is an
    index into a vocabulary of about thirty rather than the word itself, for the same reason.
    """
    counts = {r["part"]: (int(r["documents"]), int(r["uses"]))
              for r in rows(schematics_parts())}
    dictionary = dictionary_kinds()
    vocabulary: list[str] = []
    seen: dict[str, int] = {}
    out = []
    for part in sorted(set(counts) | set(recipes)):
        docs, uses = counts.get(part, (0, 0))
        kind = part_kind(part, recipes, dictionary)
        if kind not in seen:
            seen[kind] = len(vocabulary)
            vocabulary.append(kind)
        out.append([part, docs, uses, len(recipes.get(part, {}).get("models") or []), seen[kind]])
    return out, vocabulary
