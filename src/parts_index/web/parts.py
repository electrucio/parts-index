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

**A page link carries the line that says what the part does there.** `summarise` wrote one per
published use — "preamp stage V1A in the Trainwreck Express amplifier" — and the kind of use it is: a
circuit, a technique, a reference table, an advert, a mention, or not a component at all. The line goes
beside the link, because "page 47" is a link and not yet an answer; the kind sends a document whose
every page only mentions or sells the part below the ones that use it.

And three answers to "where is it used" are three different questions, so they travel apart: a project
page or a factory sheet is a circuit somebody built, a magazine page is an article about one, and a
GitHub repository is a board somebody is making now. The site folds each group on its own, and each
source inside it on its own, which is what keeps a part with three thousand hits readable.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict

import yaml

from parts_index.core.config import (
    census_registry,
    dataset_table,
    datasheet_catalogue,
    datasheet_covers,
    datasheet_documents,
    datasheet_links,
    datasheet_pages,
    datasheets_table,
    known_parts,
    model_part,
    parts_census,
    schematics_documents,
    schematics_lines,
    schematics_pages,
    schematics_registry,
    schematics_uses,
    wanted_parts,
)
from parts_index.core.parts import catalogue, schemes
from parts_index.core.parts.extractor import base_part, canonical, family_of

REPO_CAP = 200        # GitHub projects listed for one part
# The kinds of use `summarise` tells apart, and which of them is a use at all. A page that only names the
# part as an alternative, sells it, or holds a number that is not a component is not where a reader
# looking for a circuit wants to start, so a document whose every summarised page is one of those
# sorts after the rest. A page not summarised yet says nothing either way.
NOT_A_USE = frozenset(("mention", "advert", "none"))

# The kinds of source whose documents the site shows. A forum's attachments and the bundles a publisher
# hands out whole (diyAudio, Toragi's zips) are indexed and stay indexed, but whether they belong on the
# site is still undecided, so the build leaves them out of every page and count. A GitHub repository is
# shown whatever source found it: it is a board somebody is making, and the page lists it as one.
SHOWN_KINDS = frozenset(("site", "factory", "reference", "magazine", "book"))
REPO_HOST = "https://github.com/"


def shown(kind: str, url: str) -> bool:
    """Whether a document of this kind of source, at this address, is published on the site."""
    return kind in SHOWN_KINDS or url.startswith(REPO_HOST)

# The vocabulary the curation uses, which is the one the previous site offered, with its labels in
# English. Order is the order of the menu: the devices an analog-audio circuit is made of, then the
# support parts, then everything that is not a semiconductor.
DEVICES: list[tuple[str, str]] = [
    ("tube", "Valves"),
    ("bjt", "Silicon BJT"),
    ("bjt-ge", "Germanium BJT"),
    ("jfet", "JFET"),
    ("mosfet", "MOSFET"),
    ("diode", "Diodes"),
    ("diode-ge", "Germanium diodes"),
    ("zener", "Zeners"),
    ("led", "LEDs"),
    ("opamp", "Op-amps"),
    ("ota", "OTAs"),
    ("comparator", "Comparators"),
    ("vca", "VCAs, compandors and multipliers"),
    ("mic-preamp", "Microphone preamps"),
    ("ic-audio", "Audio power ICs"),
    ("digital-audio", "Digital audio and BBD"),
    ("logic", "CMOS logic"),
    ("regulator", "Regulators"),
    ("smps", "Switching controllers"),
    ("opto", "Optocouplers"),
    ("control", "Control and utility"),
    ("passive", "Passives and hardware"),
]

# What each kind the data actually carries means in that vocabulary. A part number whose family cannot
# be pinned down belongs to every kind it could be — `2N3904` and `2N5457` are both JEDEC and the
# pattern cannot tell a transistor from a JFET, so a JEDEC number answers to all three. Guessing one
# would hide the other, and the list is a way of finding things, not a claim about the part.
KIND_MAP: dict[str, tuple[str, ...]] = {
    "bjt": ("bjt",), "transistor": ("bjt",), "bjt-ge": ("bjt-ge",),
    "bjt/jfet/mosfet": ("bjt", "jfet", "mosfet"),
    "jfet": ("jfet",), "mosfet": ("mosfet",), "jfet/mosfet": ("jfet", "mosfet"),
    "bjt-ge/diode-ge": ("bjt-ge", "diode-ge"),
    "diode": ("diode",), "diode-ge": ("diode-ge",), "zener": ("zener",),
    "diode/zener": ("diode", "zener"), "led": ("led",),
    "tube": ("tube",), "vacuum_tube": ("tube",),
    "opamp": ("opamp",), "opamp/ic": ("opamp", "ic-audio", "control"),
    "ota": ("ota",), "comparator": ("comparator",), "vca": ("vca",),
    "mic-preamp": ("mic-preamp",), "ic-audio": ("ic-audio",),
    "digital-audio": ("digital-audio",), "logic": ("logic",),
    "ic": ("control",), "control": ("control",),
    "regulator": ("regulator",), "smps": ("smps",),
    "opto": ("opto",), "optocoupler": ("opto",),
    "battery": ("passive",), "connector": ("passive",), "crystal_oscillator": ("passive",),
    "display": ("passive",), "ferrite_bead": ("passive",), "fuse": ("passive",),
    "motor": ("passive",), "relay": ("passive",), "sensor": ("passive",),
    "switch": ("passive",), "thermistor": ("passive",), "module": ("passive",),
    "power_module": ("passive",),
}
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


def wanted() -> dict[str, list[dict]]:
    """Parts somebody vouches for that the index has nothing of its own for, by part.

    A shop that still sells it, a factory databook that published it, an article that discusses it.
    Without these a reader who looks one up is told nothing at all, and "sold by musikding.de under
    Transistoren / Germanium Transistoren / Selektiert" is an answer. They are also the project's own
    list of what to look for next.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows(wanted_parts()):
        out[r["part"]].append({k: r[k] for k in ("source", "category", "note") if r.get(k)})
    return out


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
    on rather than at a document about one. Ordered by stars, because 287 projects place a TL072 and
    what a reader wants is the five of them anybody has looked at. A project that has been deleted is
    dropped; one that has been renamed travels under the name it answers to now.
    """
    host = "https://github.com/"
    stats = {r["url"].replace(host, "").lower(): r for r in rows(dataset_table("repo_stats"))}
    out: dict[str, list[list]] = defaultdict(list)
    for r in rows(dataset_table("part_repos")):
        repo = r["url"].replace(host, "").strip("/")
        s = stats.get(repo.lower())
        if s and s["status"] == "gone":
            continue
        out[r["part"]].append([
            ((s or {}).get("moved_to") or "").replace(host, "") or repo,
            int(r["sheets"] or 1),
            int((s or {}).get("stars") or 0),
            int((s or {}).get("forks") or 0),
            int((s or {}).get("watchers") or 0),
        ])
    for v in out.values():
        v.sort(key=lambda x: (-x[2], -x[1], x[0]))
    return out


def sources() -> list[str]:
    d = schematics_documents("x").parent
    return sorted(p.stem for p in d.glob("*.csv")) if d.is_dir() else []


def index() -> dict:
    """The whole index, read once: documents and pages by source, uses by part."""
    docs: dict[str, dict] = {}
    pages: dict[str, dict] = {}
    lines: dict[str, dict] = {}
    uses: dict[str, list] = defaultdict(list)
    kind = kinds()
    for i, s in enumerate(sources()):
        docs[s] = {r["id"]: r for r in rows(schematics_documents(s))}
        pages[s] = {(r["doc"], r["page"]): r for r in rows(schematics_pages(s))}
        lines[s] = {(r["doc"], r["page"], r["part"]): (r["kind"], r["line"])
                    for r in rows(schematics_lines(s))}
        for u in rows(schematics_uses(s)):
            if shown(kind.get(s, ""), (docs[s].get(u["doc"]) or {}).get("url", "")):
                uses[u["part"]].append((i, u))
    idx = {"sources": sources(), "kinds": kind, "documents": docs, "pages": pages, "lines": lines,
           "uses": uses, "repos": repos(), "wanted": wanted(),
           "wanted_kind": {r["part"]: r["kind"] for r in rows(wanted_parts()) if r.get("kind")},
           "dictionary": dictionary_kinds()}
    idx["listed_by"], idx["listings"] = census_listings()
    idx["catalogued"] = catalogued()
    idx["sheets"] = archive_sheets()
    idx["harvested"] = harvested_sheets()
    idx["databook"] = databook_pages()
    idx["books"] = {r[4] for rs in idx["databook"].values() for r in rs}
    idx["first"] = first_seen(idx)
    return idx


# The census sources that list parts as a publisher of their data sheets does: a manufacturer's own
# catalogue, or an archive of the sheets themselves. A model library is also in the census, and it says
# a model exists, not who makes the part.
LISTING_KINDS = ("manufacturer catalogue", "datasheet archive")


def census_listings() -> tuple[dict[str, list[list]], dict[str, dict]]:
    """Which catalogues list each part today, with the link, and what each catalogue is.

    "Texas Instruments lists it today" is not "Texas Instruments designed it" — TI lists every National
    part since 2011 — so the page says listed, and the organisation's own record says the rest.
    """
    reg = yaml.safe_load(census_registry().read_text(encoding="utf-8")) if census_registry().exists() else {}
    out: dict[str, list[list]] = defaultdict(list)
    meta = {}
    for src, e in (reg or {}).items():
        if (e or {}).get("kind") not in LISTING_KINDS:
            continue
        meta[src] = {"title": e.get("title", src), "kind": e["kind"], "maker": e.get("maker", "")}
        for r in rows(parts_census(src)):
            out[r["part"]].append([src, r["url"]])
    return out, meta


CATALOGUE_FIELDS = ("source", "maker", "category", "status", "title", "revision", "url", "page", "checked", "name")


def catalogued() -> dict[str, list[list[str]]]:
    """What each manufacturer's catalogue says about a part, from the data-sheet register."""
    out: dict[str, list[list[str]]] = defaultdict(list)
    d = datasheet_catalogue("x").parent
    for f in [datasheets_table(), *(sorted(d.glob("*.csv")) if d.is_dir() else ())]:
        for r in rows(f):
            out[r["part"]].append([r.get(k, "") for k in CATALOGUE_FIELDS])
    return out


def archive_sheets() -> dict[str, list[list[str]]]:
    """Every data sheet an archive lists, by part: under the type it is filed as, and under the type the
    archive says it equals ("12AX7 (= ECC83)" is an ECC83 sheet too)."""
    out: dict[str, list[list[str]]] = defaultdict(list)
    d = datasheet_links("x").parent
    for f in sorted(d.glob("*.csv")) if d.is_dir() else ():
        for r in rows(f):
            note = r.get("lang", "") and f"in {r['lang']}"
            out[r["part"]].append([r["url"], r["maker"], r["maker_text"], "", r["source"], note])
            for other in (r.get("also") or "").split():
                if other != r["part"]:
                    out[other].append([r["url"], r["maker"], r["maker_text"], "", r["source"],
                                       "; ".join(x for x in (note, f"filed as {r['filed_as']}") if x)])
    return out


def harvested_sheets() -> dict[str, list[list[str]]]:
    """The makers' own sheets the harvest read, by every part each was found to cover."""
    out: dict[str, list[list[str]]] = defaultdict(list)
    d = datasheet_covers("x").parent
    for f in sorted(d.glob("*.csv")) if d.is_dir() else ():
        docs = {r["url"]: r for r in rows(datasheet_documents(f.stem))}
        for r in rows(f):
            doc = docs.get(r["url"], {})
            title = doc.get("title", "")
            if title and doc.get("revision") and not re.search(r"\bRev", title, re.I):
                title += f", revision {doc['revision']}"
            seen = {"first page": "named on its first page", "its own address":
                    "served at an address named after this part"}.get(r["seen"], "in its tables")
            row = [r["url"], doc.get("maker", ""), "", title, f.stem, seen]
            out[r["part"]].append(row + [doc["copy"]] if doc.get("copy") else row)
    return out


def databook_pages() -> dict[str, list[list[str]]]:
    """The databook pages that head each part, as sheets: a link to the page itself."""
    out: dict[str, list[list[str]]] = defaultdict(list)
    d = datasheet_pages("x").parent
    for f in sorted(d.glob("*.csv")) if d.is_dir() else ():
        # A sheet runs over several pages and names its part in each running head: the first page of each
        # run of consecutive pages is the one linked.
        seen: set[tuple[str, str, int]] = set()
        for r in sorted(rows(f), key=lambda r: (r["part"], r["book"], int(r["leaf"]))):
            key = (r["part"], r["book"], int(r["leaf"]))
            seen.add(key)
            if (key[0], key[1], key[2] - 1) in seen:
                continue
            page = f", p. {r['printed']}" if r.get("printed") else f", leaf {r['leaf']}"
            title = " ".join(x for x in (r["title"], page.lstrip(", ")) if x)
            url = (f"{r['link']}#page={r['leaf']}" if r.get("link")
                   else f"https://archive.org/details/{r['book']}/page/n{int(r['leaf']) - 1}")
            what = "a line in a tabulation" if r.get("kind") == "table" else "a page of a databook"
            out[r["part"]].append([url, r.get("maker", ""), "", title, f.stem,
                                   what + (f" ({r['year']})" if r.get("year") else "")])
    return out


def datasheets(part: str, idx: dict, recipe: dict | None) -> list[list[str]]:
    """Every data sheet known for a part, one row per link: link, maker id, maker as written, title,
    where it came from, a note.

    Several sources, several makers, and all of them kept: a later reader that measures a model against
    three factories' sheets of the same valve can tell a typo in one from a real difference. The same link
    from two sources is one row, the first source kept.
    """
    out, seen = [], set()

    def add(url, maker, text, title, via, note="", copy=""):
        if url and url not in seen:
            seen.add(url)
            out.append([url, maker, text, title, via, note] + ([copy] if copy else []))

    ds = (recipe or {}).get("datasheet") or {}
    if ds.get("url"):
        m, _ = catalogue.maker_of(ds.get("maker", ""))
        add(ds["url"], m, ds.get("maker", ""), " · ".join(str(x) for x in (ds.get("doc"), ds.get("date")) if x),
            "models", "the sheet the models were measured against")
    for c in idx.get("catalogued", {}).get(part, []):
        src, maker, _cat, _st, title, rev = c[:6]
        add(c[6], maker, "", f"{title}, revision {rev}" if title and rev else title, src)
    for src, url in idx.get("listed_by", {}).get(part, []):
        if url.lower().split("?")[0].endswith(".pdf") or "/lit/gpn/" in url:
            add(url, idx.get("listings", {}).get(src, {}).get("maker", ""), "", "", src)
    for row in idx.get("harvested", {}).get(part, []):
        add(*row)
    for row in idx.get("sheets", {}).get(part, []):
        add(*row)
    for row in idx.get("databook", {}).get(part, []):
        add(*row)
    return out


def first_seen(idx: dict) -> dict[str, list]:
    """The oldest dated document in the index that prints each part: year, title, source, link.

    A floor, not a date of birth. The index holds what was scanned, and a part is older than the first
    magazine here that happened to print it; the page says so, and links the page so it can be checked.
    """
    out: dict[str, list] = {}
    for part, us in idx["uses"].items():
        best = None
        for si, u in us:
            doc = idx["documents"][idx["sources"][si]].get(u["doc"]) or {}
            y = (doc.get("year") or "")[:4]
            if not y.isdigit():
                continue
            if best is None or int(y) < best[0]:
                best = [int(y), doc.get("title", ""), si, doc.get("url", "")]
        if best:
            out[part] = best
    return out


VARIANT_DOCS = 5      # documents a variant nothing else vouches for must be printed in to be listed


def vouched(idx: dict, recipes: dict, search: list[list]) -> set[str]:
    """Numbers worth listing as a variant of a type: a curated recipe, the dictionary or a manufacturer's
    catalogue says they exist, or enough documents print them that they are not one misread.

    BC548BIC and 12AX7BLK fold onto their types as neatly as BC548C does, and each is on one or two pages:
    what the OCR made of a line, not a part anybody sells.
    """
    docs = {r[0]: r[1] for r in search}
    return (set(recipes) | set(idx.get("dictionary", {})) | set(idx.get("listed_by", {}))
            | {p for p, d in docs.items() if d >= VARIANT_DOCS})


def variant_groups(names, keep: set[str] | None = None) -> dict[str, list[str]]:
    """The numbers that fold onto each type: BC548 -> BC548A, BC548B, BC548C."""
    out: dict[str, list[str]] = defaultdict(list)
    for p in names:
        if keep is not None and p not in keep:
            continue
        b = base_part(p)
        if b != p:
            out[b].append(p)
    return {k: sorted(v) for k, v in out.items()}


def all_names(idx: dict, recipes: dict) -> list[str]:
    """Every part the search index will hold: printed, curated or vouched for."""
    return sorted(set(idx["uses"]) | set(recipes) | set(idx.get("wanted_kind", {})))


def known_kinds(idx: dict, recipes: dict, names) -> dict[str, tuple[str, ...]]:
    """Every number the project knows, with the device kinds it answers to.

    The naming schemes ask two questions of it: is a shorter number a part of its own (1X2A is the 1X2,
    revised), and is it a part of another kind (27C64N is an EPROM). A catalogue that says only
    "semiconductor" answers the first and says no valve to the second.
    """
    out: dict[str, tuple[str, ...]] = {}
    for src in idx.get("listings", {}):
        for r in rows(parts_census(src)):
            out.setdefault(r["part"], KIND_MAP.get(r.get("kind", ""), ()))
    dictionary = idx.get("dictionary", {})
    for p in names:
        devs = KIND_MAP.get(part_kind(p, recipes, dictionary) or idx.get("wanted_kind", {}).get(p, ""), ())
        if devs or p not in out:             # a kind the index cannot tell does not erase the catalogue's
            out[p] = devs
    return out


def kind_of(part: str, recipe: dict | None, idx: dict) -> str:
    """The same answer `part_kind` gives the search index, from what one part's page already has."""
    if recipe:
        return recipe.get("kind", "")
    k = idx.get("dictionary", {}).get(part)
    if k:
        return k
    fam = family_of(canonical(part) or part)
    return fam[1] if fam else idx.get("wanted_kind", {}).get(part, "")


# The suffixes that change a part's package, its packing or its selection and leave the part itself: a
# sheet of the type documents all of them. Each list is kept narrow on purpose — LM317L, 78L05, LM358A and
# 6L6GC are other parts (less current, another die, a better grade, another rating), so L, A and G are
# never folded, and a suffix not listed here keeps the part alone.
KIN_STEPS = (
    ("grade", re.compile(r"(?P<t>2S[ABCDJK]\d{2,4})-?(?:GR|BL|Y|O|R|P|E|F|K|V|G)")),      # 2SC1815GR
    ("grade", re.compile(r"(?P<t>(?:BC|BCY|BF|MPS|MPSA|PN)\d{2,4})[ABC]")),                 # BC547B
    ("packing", re.compile(r"(?P<t>.*\d[A-Z]{0,2})(?:TR|TA|TB|TAP|RL|RLG|ZL|ZLG|BU|BK|CT)")),  # 1N4002TR, BC547BTA
    ("package", re.compile(r"(?P<t>[A-Z]{2,5}\d{3,5}[AB]?)(?:C?(?:D|N|P|M|DR|DD|DT|CN|CP|CD|ID|IN|IP|BE|BP|HA|HT|C))")),
    # Japanese makers letter their packages: L is a SIP, D a DIP, M an SOP, E an EMP (NJM4556AL, NJM2068MD).
    # Here L is a package; on an LM317L it is another part, so the step is kept to these makers' prefixes.
    ("package", re.compile(r"(?P<t>(?:NJM|NJU|UPC|BA|M5|AN|TA|HA|LA)\d{3,5}[A-Z]?)"
                           r"(?:L|D|M|E|V|R|DV|MD|LD|SD|FP|F|G|H|S|DD|FD|FTI)")),
    ("brand", re.compile(r"(?P<t>\d{1,2}[A-Z]{1,2}\d{1,2})(?:EH|LPS|WA|WB|WC|WXT)")),       # 12AX7EH
)
# The makers' names for a bare number the drawings print: 7812 is ST's L7812, onsemi's MC7812, TI's
# UA7812; 74HC04 TI's SN74HC04; 4013B TI's CD4013B, NXP's HEF4013B, onsemi's MC14013B.
GENERIC = (
    (re.compile(r"7[89]M?\d{2}[A-Z]{0,2}"), ("L", "MC", "UA", "LM", "KA", "KIA", "NJM")),
    (re.compile(r"78L\d{2}[A-Z]{0,2}|79L\d{2}[A-Z]{0,2}"), ("L", "MC", "UA", "LM", "KA", "KIA", "NJM")),
    (re.compile(r"74[A-Z]{0,4}\d{2,4}[A-Z]{0,2}"), ("SN", "MM", "CD", "M", "TC", "HD", "MC", "NLV")),
    (re.compile(r"4\d{3}[A-Z]{0,3}"), ("CD", "HEF", "MC1", "TC", "NJU")),
)
# A 4000-series name printed without its B: CD4011 is filed as CD4011B or CD4011BE.
BUFFERED = re.compile(r"(?:CD|HEF|MC1)4\d{3,4}")


def kin_names_steps(part: str) -> list[tuple[str, str]]:
    out, p = [], part
    for _ in range(3):
        step = next(((why, m.group("t")) for why, rx in KIN_STEPS if (m := rx.fullmatch(p))), None)
        if not step:
            break
        out.append(step)
        p = step[1]
    return out


def kin_names(part: str) -> list[tuple[str, str]]:
    """The names whose sheets also document this one, and why: the type it is a package, packing, grade
    or brand of (a step at a time, BC547BTA -> BC547B -> BC547), or a maker's name for a bare number."""
    out, p = [], part
    for _ in range(3):
        step = next(((why, m.group("t")) for why, rx in KIN_STEPS if (m := rx.fullmatch(p))), None)
        if not step:
            break
        out.append(step)
        p = step[1]
    # A valve printed bare is filed by its envelope or revision: 5Y3 as 5Y3GT or 5Y3G, 12B4 as 12B4A. The
    # same valve in a smaller or metal bulb; 6L6 against 6L6GC is kept apart, since that one is rerated.
    if re.fullmatch(r"\d{1,2}[A-Z]{1,3}\d{1,2}", part):
        out += [("envelope", part + x) for x in ("GT", "G", "GTA", "GTB", "GA", "GB", "A")]
    if re.fullmatch(r"JRC\d{4}[A-Z]{0,2}", part):          # JRC4558D is sold as NJM4558D
        out.append(("maker's name", "NJM" + part[3:]))
        out += [("maker's name", "NJM" + t[3:]) for _, t in kin_names_steps(part)]
    if BUFFERED.fullmatch(part):
        out += [("maker's name", part + x) for x in ("B", "BE", "BCP", "BP")]
    for rx, prefixes in GENERIC:
        if rx.fullmatch(part):
            stems = [part] + [re.sub(r"[A-Z]{1,2}$", "", part)] * bool(re.search(r"\d[A-Z]{1,2}$", part))
            out += [("maker's name", f + stem) for stem in stems for f in prefixes]
    return list(dict.fromkeys(out))


def kin(part: str, idx: dict, own: list[list[str]]) -> list[list]:
    """The sheets of the names in `kin_names` that are not already this part's own."""
    seen = {r[0] for r in own}
    out = []
    for why, name in kin_names(part):
        rows = [r for r in datasheets(name, idx, None) if r[0] not in seen]
        if rows:
            seen |= {r[0] for r in rows}
            out.append([name, why, rows])
    return out


def about(part: str, idx: dict, recipe: dict | None) -> dict:
    """What the part is, as far as something says so — each piece carrying where it came from.

    The name read under the standard that assigned it; the family, from the maker's own sheet when one
    says, from the kind otherwise; who published the sheet the models were measured against, and who
    lists the part today; the oldest dated document here that prints it; and the numbers that are
    grades or packages of the same type. Nothing here is a guess dressed as a fact: a piece that no
    source gives is simply absent, and the page shows nothing for it.
    """
    out: dict = {}
    devices = KIND_MAP.get(kind_of(part, recipe, idx), ())
    d = schemes.decode(part, devices, idx.get("known"))
    if d:
        out["name"] = d.as_dict()
    fid, basis = catalogue.family_of(part, devices, d.families if d else None)
    if fid:
        out["family"] = [fid, basis]
    doc = catalogue.documented().get(part)
    if doc:
        out["documented"] = {"note": doc["note"], "refs": doc["refs"].split(), "status": doc["status"]}
    ds = (recipe or {}).get("datasheet") or {}
    if ds.get("maker"):
        m, lineage = catalogue.maker_of(ds["maker"])
        if m:
            out["maker"] = [m, lineage]
    rel = catalogue.related(part)
    if rel:
        out["related"] = rel
    cat = idx.get("catalogued", {}).get(part)
    if cat:
        out["catalogue"] = cat
    # A databook page is a sheet too, but one of hundreds bound together decades ago: the page lists
    # them apart, after everything else, so a maker's current sheet is not buried under forty of them.
    sheets = datasheets(part, idx, recipe)
    books = idx.get("books", set())
    own = [r for r in sheets if r[4] not in books]
    bound = [r for r in sheets if r[4] in books]
    kinship = []
    for name, why, rs in kin(part, idx, sheets):
        bound += [r[:5] + [f"as {name}" + (f" · {r[5]}" if r[5] else "")] + r[6:] for r in rs if r[4] in books]
        rs = [r for r in rs if r[4] not in books]
        if rs:
            kinship.append([name, why, rs])
    if own:
        out["sheets"] = own
    if bound:
        out["books"] = bound
    if kinship:
        out["kin"] = kinship
    listed = idx.get("listed_by", {}).get(part)
    if listed:
        out["listed"] = listed
    first = idx.get("first", {}).get(part)
    if first:
        out["first"] = first
    groups = idx.get("variants", {})
    base = base_part(part)
    if base != part:
        out["base"] = base
        siblings = [v for v in groups.get(base, []) if v != part]
        if siblings:
            out["variants"] = siblings
    elif groups.get(part):
        out["variants"] = groups[part]
    return out


def catalogue_payload(idx: dict) -> dict:
    """The catalogue, once for the whole site: families, organisations, naming schemes, references and the
    catalogues parts are listed in. A part file names them by id."""
    # Families and a scheme's fields are in the order their files give, which is the order a reader meets
    # them — material before function, diodes before transistors — and JSON objects are written with
    # sorted keys, so both travel as lists.
    def scheme(sc: dict) -> dict:
        out = {x: v for x, v in sc.items() if not x.startswith("_") and x not in ("id", "order", "fields")}
        out["fields"] = [[k, f] for k, f in (sc.get("fields") or {}).items()]
        return out
    return {
        "families": [f for f in catalogue.families().values()],
        "makers": {k: {x: v for x, v in m.items() if x not in ("id", "aliases")} for k, m in catalogue.makers().items()},
        "schemes": {k: scheme(sc) for k, sc in schemes.schemes().items()},
        "refs": {k: {x: r[x] for x in ("title", "author", "url", "consulted", "link")}
                 for k, r in catalogue.references().items()},
        "listings": idx.get("listings", {}),
    }


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
        if m.get("copies"):
            # The same model elsewhere, with the link from each: often the file a collection copied is the
            # vendor's original, and that is where a reader should go.
            e["copies"] = [{"source": c["source"], "name": c["name"],
                            **{k: (c.get("get") or {})[k] for k in ("url", "member", "installed_with")
                               if (c.get("get") or {}).get(k)}} for c in m["copies"]]
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


def page_entry(page: dict | None, u: dict, doc_url: str, line: tuple[str, str] | None) -> list:
    """One page link: where it is, what is beside the part, how many times it is on it, and what it
    does there.

    The link is stored as what to add to the document's own URL — `#page=47&zoom=200,55,523&h=792` —
    because that is what it is. All 94,170 of them are a suffix of it, and writing them whole was three
    quarters of the URL text in a part's page. Anything that is not a suffix is kept whole, and the
    reader can tell which by whether it starts with a scheme.

    The last two are the line `summarise` wrote and the kind of use it read; a page not summarised yet
    ends at the count, and the site treats the missing pair as "not known".
    """
    url = (page or {}).get("url", "")
    if doc_url and url.startswith(doc_url):
        url = url[len(doc_url):]
    out = [int(u["page"]), url, u["near"], int(u["times"] or 1)]
    if line:
        out += [line[1], line[0]]
    return out


def only_named(doc: dict) -> bool:
    """True when every summarised page of this document only mentions or sells the part."""
    kinds = [p[5] for p in doc["p"] if len(p) > 5]
    return bool(kinds) and all(k in NOT_A_USE for k in kinds)


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
        line = idx["lines"].get(source, {}).get((u["doc"], u["page"], part))
        d["p"].append(page_entry(page, u, d["u"], line))

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

    merged.sort(key=lambda d: (-d["schematic"], only_named(d), -sum(p[3] for p in d["p"]), d["t"]))
    shown = merged
    for d in shown:
        d["p"].sort(key=lambda p: p[0])
        d.pop("sha", None)
    # The source names are the same fifty-eight in every part file, so they live once in `parts.json`
    # and a document names its source by position. Repeating them here cost 90 MB across 15,558 files.
    out = {"part": part, "docs": shown,
           "n": {"documents": len(merged), "shown": len(shown),
                 "copies": len(by_doc) - len(merged)}}
    listed = idx["wanted"].get(part) or []
    if listed:
        out_listed = listed
    gh = idx["repos"].get(part) or []
    if gh:
        out["repos"] = gh[:REPO_CAP]
        out["n"]["repos"] = len(gh)
    if listed:
        out["listed"] = out_listed
    if recipe:
        out["models"] = trim_models(recipe)
    info = about(part, idx, recipe)
    if info:
        out["about"] = info
    return out


def device_bits(kind: str) -> int:
    """Which of `DEVICES` this kind answers to, as a bit per device.

    One number instead of a list of words: twenty-two devices fit in an integer, and a part row is read
    fifteen thousand times.
    """
    at = {k: i for i, (k, _) in enumerate(DEVICES)}
    bits = 0
    for d in KIND_MAP.get(kind, ()):
        bits |= 1 << at[d]
    return bits


def search_index(idx: dict, recipes: dict) -> tuple[list[list], list[dict]]:
    """What the browser loads first: every part, with just enough to rank, filter and route it.

    Tuples rather than objects, because the key names would be most of the file.
    """
    # Counted from the uses the site shows, not read from the export's table, which counts every source.
    counts = {part: (len({(si, u["doc"]) for si, u in us}), len(us)) for part, us in idx["uses"].items()}
    dictionary = dictionary_kinds()
    listed_kind = idx.get("wanted_kind", {})
    cache: dict[str, int] = {}
    fam_at = {fid: i for i, fid in enumerate(catalogue.families())}
    out = []
    tally = Counter()
    for part in sorted(set(counts) | set(recipes) | set(listed_kind)):
        docs, uses = counts.get(part, (0, 0))
        kind = part_kind(part, recipes, dictionary) or listed_kind.get(part, "")
        if kind not in cache:
            cache[kind] = device_bits(kind)
        bits = cache[kind]
        for i, (key, _) in enumerate(DEVICES):
            if bits & (1 << i):
                tally[key] += 1
        devs = KIND_MAP.get(kind, ())
        named = schemes.decode(part, devs, idx.get("known"))
        fid, _ = catalogue.family_of(part, devs, named.families if named else None)
        out.append([part, docs, uses, len(recipes.get(part, {}).get("models") or []), bits,
                    fam_at.get(fid, -1)])
    # Every device ships, even the ones nothing answers to, because the bit a part carries is its
    # position here. Dropping the empty ones would renumber the rest, and a filter would quietly select
    # the wrong device — which is what the fixture caught. The site hides an entry with nothing in it.
    menu = [{"key": k, "label": label, "n": tally[k]} for k, label in DEVICES]
    return out, menu
