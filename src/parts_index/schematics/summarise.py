"""One line per published use: what that part is doing on that page.

    pidx schematics summarise [--source esp] [--limit N] [--workers 4] [--detach] [--dry]

`uses/<source>.csv` answers "where is this part used" with a document and a page number, which is a
link and not yet an answer. This stage writes the sentence that goes beside it — "preamp stage V1A in
the Trainwreck Express amplifier", "diode D1 in the Oceanid compressor parts list" — read off the OCR
by the model on the maintainer's own machine (`core.llm.ask_local`), which costs hours rather than
money and so can see the whole corpus.

**One call per page, one line per part on it.** Asked use by use the model repeats itself and costs
two and a half times as much; asked about the page alone it writes one line that suits none of the
parts. Asked for all of a page's parts at once it has to divide the page between them, which is what a
page of circuit ideas, a book of small circuits or a service-manual sheet with several boards needs.

**The excerpt is built to contain every part asked about.** A fixed cut of the page text drops parts
that sit past it, and the model then truthfully answers that they are not there: `excerpt` takes the
head of the page, where the title and the lead are, plus a window around each part, and marks the gaps.

**Where, not what.** The model is reliable about where a part sits — the circuit, the stage, the board,
the list — and unreliable about what the device is for, which it will guess from the type number when
the page does not say. The prompt asks for the first and forbids the second; the residue is the known
weakness of this stage.

It runs on what `export` has published, so the order is export, summarise, export again: the first
export decides which uses are worth a link, this stage writes their lines, and the second carries them
into `lines/<source>.csv`. Answers are cached per page under the private root by `core.llm`, so an
interrupted run of days resumes where it stopped and a finished one costs nothing. `VERSION` is in the
cache key: bump it to have the corpus read again, and the old answers stay on disk beside the new.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

import yaml

from parts_index.core import llm
from parts_index.core.config import (
    index_db,
    index_db_uri,
    require,
    schematics_documents,
    schematics_pages,
    schematics_registry,
    schematics_uses,
    summarise_preview,
)
from parts_index.core.jobs import detach, only_one, run_log

VERSION = "summarise-3"
TASK = "summarise-pages"
MODEL = os.environ.get("PIDX_LLM_MODEL", "local")
MODULE = "parts_index.schematics.summarise"
KINDS = ("project", "technique", "reference", "advert", "mention", "none")
LINE_CHARS = 240                   # a hard stop, not a target: the prompt asks for 22 words
CARRY_GAP = 2                      # a continuation page is next door, not ten pages away
MAX_PARTS = 24                     # a page with more than this is a catalogue; asking about all of it
                                   # spends the answer on a list nobody reads to the end

SYSTEM = """You are given one page of an electronics document and the parts that were read on it. For \
each part write one line, to be shown to somebody searching for that part under the link to this page, \
telling them whether this use is worth opening.

**The header says how the page was read, and it changes what you are looking at.** A scan read by OCR \
gives words roughly in order but broken, and a schematic's labels arrive scrambled. A page whose text was \
taken from the file is not a scan: it reads in order, and it is a web page or a born-digital document, so \
it arrives wrapped in the furniture around the article - a navigation menu, a sidebar, a blogroll, a list \
of tags or labels, links to other posts, and readers' comments underneath. [...] marks text left out.

The bracket after each part says how many times it was read on the page. A part read once, where the \
parts of the circuit are read several times each, is usually a mention rather than a use.

**A page often holds more than one circuit** - a magazine page of circuit ideas, a book of small \
circuits, a service manual sheet with several boards, an article with adverts around it. Work out what \
is on the page first, then put each part where it belongs. Parts in different circuits must not get \
the same line.

**Say where the part sits, not what kind of device it is.** You may be wrong about the device, and the \
reader already knows it. Write "input stage of the C-299 preamplifier", not "JFET in the input stage". \
Name its function only where the page says it - a label, a designator, a sentence.

**Ask first where on the page the number is.** Two situations are not a use of a component in a circuit \
on this page, and they are not the same thing:

  * kind `none` - the number is not a reference to a component at all: it sits in a navigation menu, a \
sidebar, a blogroll, a tag or label list, an index or contents list, a readers' requests column; or it is \
a piece of equipment, a loudspeaker, a record or an instrument named by its model number; or it is a \
marking on a drawing - a resistor value, a test point, a step number - that happens to read like a type \
number. Say where it really appears.
  * kind `mention` - a real component, named on this page but not used in the circuit here: an \
alternative, a substitute, a comparison, something the author decided against, or a part suggested in a \
comment. Say what it is offered as, and for what. These lines are worth having.

A line that puts a part in a circuit it is not in is worse than no line.

Answer with one JSON object, nothing else:
{"page": "...", "parts": [{"part": "...", "kind": "...", "line": "..."}, ...]}

page: at most 18 words naming what is on the page as a whole. Where it holds several circuits, say so \
and name them.

One entry per part given, in the order given, using exactly the part number as given.

kind is one of: project (a circuit somebody built or can build), technique (how a circuit works, a \
measurement, a design method), reference (a table, a parts list, a datasheet page, an index, a \
catalogue), advert (an advertisement or a price list), mention (a real part named here but not used in the circuit on this page), none (the number is \
not a reference to a component at all).

line: at most 22 words, and shorter where the page gives you less. The circuit or section it sits \
in, what that circuit is for, and the designator or the neighbouring part where the page shows it. Room \
to be specific is not room to pad: say more only where you have more to say. Do not begin \
by repeating the part number. Never write "this page", "the article" or "the circuit shown". Where the page does not \
place it in a circuit, use `mention` or `none` as above and say where it does appear - a vaguer line is \
better than a role you cannot see.

Every other part number you name must appear in the text in front of you. Do not name a device because \
the circuit usually uses one. Use the document title only where the page text agrees with it."""


# --- the excerpt ------------------------------------------------------------------------------------
def _norm(word: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", word.upper())


def excerpt(text: str, parts, head: int = 110, around: int = 70, cap: int = 6000,
            web: bool = False) -> tuple[str, list]:
    """The head of the page plus a window around every part, merged, with `[...]` where text is left out.

    The head is there because that is where a page says what it is — the title, the standfirst, the
    first paragraph. On a web page it is the navigation and the sidebar instead, and a part number read
    out of it belongs to nothing, so on a web page the head is marked as what it is rather than left to
    look like the top of an article.

    Returns the excerpt and the parts it could not find at all — which are worth knowing: a part the
    page text does not contain is either an OCR box the index kept and this text did not, or a use that
    should never have been published."""
    words = text.split()
    norm = [_norm(w) for w in words]
    keep = set(range(min(head, len(words))))
    missing = []
    for part in parts:
        key = _norm(part)
        hits = [i for i, w in enumerate(norm) if key and (w == key or (len(key) > 3 and key in w))]
        if not hits:
            missing.append(part)
            continue
        for i in hits[:3]:
            keep.update(range(max(0, i - around), min(len(words), i + around + 1)))
    if not keep:
        return text[:cap], missing
    out, last = [], None
    if web and keep:
        out.append("[top of the web page - navigation, sidebar, tag lists:]")
    for i in sorted(keep):
        left_the_head = web and last is not None and last < head <= i
        if left_the_head:
            out.append("[end of the page furniture, the page itself follows:]")
        elif last is not None and i > last + 1:
            out.append("[...]")
        out.append(words[i])
        last = i
    joined = " ".join(out)
    if len(joined) > cap:
        if around > 25:
            return excerpt(text, parts, head, around - 20, cap, web)
        joined = joined[:cap]
    return joined, missing


READ_AS = {"text": "text taken from the file - a web page or a born-digital document, not a scan",
           "ocr": "a scan read by OCR"}


def source_names() -> dict:
    """What each source is, from the registry. `el34world` tells the model nothing; "EL34 World -
    schematics, a factory-schematic site" tells it what kind of page it is about to read."""
    with open(schematics_registry(), encoding="utf-8") as f:
        reg = yaml.safe_load(f) or {}
    return {k: f"{(v or {}).get('title', k)} - {(v or {}).get('kind', 'site')}" for k, v in reg.items()}


def prompt(page: dict, names: dict | None = None, earlier: str = "") -> str:
    listed = "\n".join(
        f"  {p['part']}  (read {p['times']}x{', beside ' + p['near'] if p['near'] else ''})"
        for p in page["parts"])
    source = (names or {}).get(page["source"], page["source"])
    return (f"DOCUMENT: {page['title']}\nURL: {page['key']}\n"
            f"SOURCE: {source} ({page['role']})\nPAGE: {page['page']}\n"
            f"READ AS: {READ_AS.get(page.get('read_as'), READ_AS['ocr'])}\n"
            f"PARTS TO WRITE A LINE FOR:\n{listed}\n\n{earlier}PAGE TEXT:\n{page['excerpt']}")


# --- the answer -------------------------------------------------------------------------------------
TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def loads(text: str) -> dict:
    """The JSON object in the model's answer, repaired if it needs the one repair models need.

    A trailing comma before a closing brace is the mistake this model actually makes, in about one
    answer in fifty — enough to lose a couple of thousand pages over the corpus, and not a reason to
    ask again. Nothing else is repaired: an answer that is wrong in some other way should fail loudly
    and be asked again rather than be guessed at."""
    body = text[text.index("{"):text.rindex("}") + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return json.loads(TRAILING_COMMA.sub(r"\1", body))


def chains_of(pages: list[dict]) -> list[list[dict]]:
    """The pages of one document, in order, are one chain. Documents are independent of each other."""
    by_doc: dict[tuple, list[dict]] = defaultdict(list)
    for page in pages:
        by_doc[(page["source"], page["key"])].append(page)
    return [sorted(group, key=lambda p: p["page"]) for group in by_doc.values()]


def carried(page: dict, earlier: list) -> str:
    """What the pages just before this one turned out to be.

    A magazine article runs over several pages and only the first names it: without this, page 24 is
    "P.E. Aurora music-inspired light and colour control system" and pages 25 to 28 are four unrelated
    thyristor circuits. With it they are all the Aurora, and the model drops the name again when the
    article ends — it was asked to keep it only while the page is plainly the same one.

    Only pages within `CARRY_GAP` count. Half the pairs in the queue are next door to each other, but
    the queue holds only the pages that carry a published use, so the page before this one in it can be
    forty pages earlier in the issue, and that is not a continuation of anything."""
    near = [(it, a) for it, a in earlier if 0 < page["page"] - it["page"] <= CARRY_GAP]
    if not near:
        return ""
    lines = "\n".join(f"  p.{it['page']}: {a.get('page', '')}" for it, a in near)
    return ("EARLIER PAGES OF THIS DOCUMENT (an article often runs over several pages and only the first\n"
            "names it; keep a name only while this page is plainly the same article):\n" + lines + "\n\n")


def read_answer(text: str, asked: list[str]) -> dict:
    """The model's text -> {"page": line, "parts": {PART: {kind, line}}}, or raise so it is asked again.

    Lenient about what came back and strict about what is kept: an entry for a part nobody asked about
    is dropped, a kind this project does not use becomes `none`, and a line longer than a line is cut.
    An answer that names none of the parts asked about is not an answer."""
    body = loads(text)
    want = {p.upper(): p for p in asked}
    parts = {}
    for entry in body.get("parts") or []:
        part = want.get(str(entry.get("part", "")).upper())
        line = " ".join(str(entry.get("line", "")).split())[:LINE_CHARS]
        if not part or not line:
            continue
        kind = str(entry.get("kind", "")).lower()
        parts[part] = {"kind": kind if kind in KINDS else "none", "line": line}
    if not parts:
        raise ValueError(f"no part of {asked[:3]} answered")
    return {"page": " ".join(str(body.get("page", "")).split())[:LINE_CHARS], "parts": parts,
            "v": VERSION, "missing": sorted(set(asked) - set(parts))}


# --- what to ask about ------------------------------------------------------------------------------
def sources() -> list[str]:
    """Every source in the registry, which is a flat mapping of id to entry."""
    with open(schematics_registry(), encoding="utf-8") as f:
        return sorted(yaml.safe_load(f) or {})


def published(source: str) -> list[dict]:
    """The pages of a source that carry a published use, each with its parts, in export order."""
    uses, docs = schematics_uses(source), schematics_documents(source)
    if not uses.exists() or not docs.exists():
        return []
    with open(docs, newline="", encoding="utf-8") as f:
        known = {r["id"]: r for r in csv.DictReader(f)}
    pages: dict[tuple, dict] = {}
    with open(uses, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            doc = known.get(r["doc"])
            if not doc:
                continue
            page = pages.setdefault((doc["key"], r["page"]), {
                "source": source, "doc": r["doc"], "key": doc["key"], "title": doc["title"],
                "role": doc["role"], "page": int(r["page"]), "parts": []})
            page["parts"].append({"part": r["part"], "times": r["times"] or 1, "near": r["near"]})
    return list(pages.values())


def with_text(pages: list[dict], say=print) -> list[dict]:
    """Carry the page text out of the index database and build each excerpt. Pages the database has no
    text for are dropped: there is nothing to read them from."""
    by_key: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        by_key[page["key"]].append(page)
    out, notext = [], 0
    db = sqlite3.connect(index_db_uri(), uri=True)
    for key, group in by_key.items():
        rows, method = {}, None
        for page_no, text, text_method in db.execute(
                "select p.page_no, t.text, d.text_method from pages p join documents d on d.doc_id = p.doc_id "
                "join page_text t on t.page_id = p.page_id where d.source = ? and d.doc_key = ?",
                (group[0]["source"], key)):
            rows[page_no], method = text, text_method
        for page in group:
            text = rows.get(page["page"])
            if not text:
                notext += 1
                continue
            page["parts"] = page["parts"][:MAX_PARTS]
            page["read_as"] = "text" if method == "text" else "ocr"
            page["excerpt"], page["absent"] = excerpt(text, [p["part"] for p in page["parts"]],
                                                      web=page["read_as"] == "text")
            out.append(page)
    db.close()
    if notext:
        say(f"  {notext} pages have no text in the index and cannot be read")
    return out


def room_for(parts: int) -> int:
    """How long an answer about this many parts is allowed to be.

    An answer cut off in the middle is an answer thrown away, asked again on the next run and thrown
    away again, so the cap is generous: it costs nothing unless it is used, and the model stops when it
    has said what it has to say. A page of two dozen parts needs several times the answer of a page
    with one, and a page with one still needs room for the page line and the JSON around it."""
    return min(400 + 80 * parts, 2600)


def key_of(page: dict) -> str:
    """What identifies this question: the stage version, the page, and the parts being asked about.

    The parts have to be in it. Without them a page answered today is skipped for ever, and the part
    the extractor learns to read tomorrow never gets a line — rule 5 skips an item when its stamp
    matches the input, and the input here is the page *and* what was asked of it. With them, an
    extractor change re-asks exactly the pages whose part list changed and nothing else."""
    asked = ",".join(sorted(p["part"] for p in page["parts"]))
    stamp = hashlib.sha256(asked.encode("utf-8")).hexdigest()[:8]
    return f"{VERSION}|{page['source']}|{page['key']}|{page['page']}|{stamp}"


def parse_key(key: str) -> tuple[str, str, str, int]:
    """(version, source, document, page) out of a cache key, whatever version wrote it.

    The key gained a field when the asked parts went into it, and the cache keeps what earlier versions
    wrote, so a reader that assumes today's shape trips over its own history."""
    version, source, rest = key.split("|", 2)
    bits = rest.rsplit("|", 2)
    doc, page = (bits[0], bits[1]) if len(bits) == 3 else rest.rsplit("|", 1)
    return version, source, doc, int(page)


def cached_lines(say=None) -> dict:
    """Every page this stage has answered, for `export` to carry into `lines/<source>.csv`. Empty
    without the private root, which is what a clone without the corpus gets.

    The model's name comes from the environment, so a reader started without `PIDX_LLM_MODEL` would
    otherwise find an empty cache and report, wrongly, that nothing has been answered. When the
    configured model has nothing and exactly one other model does, that is the run being read."""
    try:
        have = llm.cached(TASK, MODEL)
        if have:
            return have
        others = [m for m in llm.models_in(TASK) if m != MODEL]
        if len(others) == 1:
            if say:
                say(f"(no answers under {MODEL!r}; reading the {others[0]!r} ones)")
            return llm.cached(TASK, others[0])
        return have
    except OSError:
        return {}


def preview(say=print) -> int:
    """Write every line answered so far, with the link the site would show beside it.

    A run over the corpus takes days and the real export happens at the end of it, so this is the window
    into one in flight: open the CSV, read what the model is making of the pages, and stop it early if
    it is making a mess of them. Private, because it is a working artefact of a run, not the export."""
    ids, links = {}, {}
    for f in sorted(schematics_pages("x").parent.glob("*.csv")):
        source = f.stem
        docs = schematics_documents(source)
        if not docs.exists():
            continue
        with open(docs, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                ids[(source, r["key"])] = r["id"]
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                links[(source, r["doc"], r["page"])] = r["url"]

    rows = []
    for key, answer in cached_lines(say).items():
        version, source, doc, page = parse_key(key)
        if version != VERSION:
            continue
        url = links.get((source, ids.get((source, doc), ""), str(page)), doc)
        for part, e in (answer.get("parts") or {}).items():
            rows.append([source, part, e["kind"], e["line"], url])
    rows.sort(key=lambda r: (r[0], r[1]))
    out = summarise_preview()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(("source", "part", "kind", "line", "url"))
        w.writerows(rows)
    say(f"{len(rows):,} lines from {len({r[4] for r in rows}):,} pages -> {out}")
    return len(rows)


# --- the run ----------------------------------------------------------------------------------------
def run(which: list[str] | None = None, limit: int = 0, workers: int = 4, dry: bool = False,
        say=print) -> dict:
    require(index_db(), "summarising pages")
    names = source_names()
    counts = {"pages": 0, "uses": 0, "asked": 0, "answered": 0, "absent": 0}
    for source in which or sources():
        pages = with_text(published(source), say=say)
        if not pages:
            continue
        if limit:
            pages = pages[:limit]
        uses = sum(len(p["parts"]) for p in pages)
        counts["pages"] += len(pages)
        counts["uses"] += uses
        counts["absent"] += sum(len(p["absent"]) for p in pages)
        chains = [[{"key": key_of(p), "page": p, "asked": [q["part"] for q in p["parts"]],
                    "max_tokens": room_for(len(p["parts"]))} for p in group]
                  for group in chains_of(pages)]
        items = [it for chain in chains for it in chain]
        have = llm.cached(TASK, MODEL)
        todo = [it for it in items if it["key"] not in have]
        say(f"{source}: {len(pages)} pages in {len(chains)} documents, {uses} uses, {len(todo)} to ask")
        if dry:
            continue
        counts["asked"] += len(todo)
        answers = llm.ask_local_chains(
            TASK, SYSTEM, chains, model=MODEL, workers=workers, say=say,
            build=lambda item, earlier: prompt(item["page"], names, carried(item["page"], [
                (e["page"], a) for e, a in earlier])),
            parse=lambda text, item: read_answer(text, item["asked"]))
        counts["answered"] += sum(1 for it in items if it["key"] in answers)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics summarise", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only this source; repeat for several")
    ap.add_argument("--limit", type=int, default=0, help="at most this many pages per source")
    ap.add_argument("--workers", type=int, default=4, help="calls in flight (the server has four slots)")
    ap.add_argument("--dry", action="store_true", help="say what would be asked, ask nothing")
    ap.add_argument("--preview", action="store_true",
                    help="write what has been answered so far, with its links, and stop")
    ap.add_argument("--detach", action="store_true", help="run in the background, under a lock, into a log")
    args = ap.parse_args(argv)
    if args.preview:
        preview()
        return 0
    name = "summarise-" + ("-".join(args.source) if args.source else "all")
    if args.detach:
        given = sys.argv[1:] if argv is None else argv
        pid = detach(MODULE, [a for a in given if a != "--detach"], name)
        print(f"summarise running as {pid}, watch it with: tail -f {run_log(name)}")
        return 0
    with only_one(name):
        counts = run(args.source, args.limit, args.workers, args.dry)
    print(f"{counts['pages']:,} pages, {counts['uses']:,} uses, {counts['answered']:,} pages answered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
