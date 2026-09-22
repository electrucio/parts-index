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
    schematics_registry,
    schematics_uses,
)
from parts_index.core.jobs import detach, only_one, run_log

VERSION = "summarise-1"
TASK = "summarise-pages"
MODEL = os.environ.get("PIDX_LLM_MODEL", "local")
MODULE = "parts_index.schematics.summarise"
KINDS = ("project", "technique", "reference", "advert", "none")
MAX_PARTS = 24                     # a page with more than this is a catalogue; asking about all of it
                                   # spends the answer on a list nobody reads to the end

SYSTEM = """You are given one page of an electronics document and the parts that were read on it. For \
each part write one line, to be shown to somebody searching for that part under the link to this page, \
telling them whether this use is worth opening.

The text is OCR and is noisy: schematic labels arrive scrambled and out of order, a parts list arrives \
as a run of numbers, and [...] marks text left out. The designators printed beside each part are given \
where they are known.

**A page often holds more than one circuit** - a magazine page of circuit ideas, a book of small \
circuits, a service manual sheet with several boards, an article with adverts around it. Work out what \
is on the page first, then put each part where it belongs. Parts in different circuits must not get \
the same line.

**Say where the part sits, not what kind of device it is.** You may be wrong about the device, and the \
reader already knows it. Write "input stage of the C-299 preamplifier", not "JFET in the input stage". \
Name its function only where the page says it - a label, a designator, a sentence.

Answer with one JSON object, nothing else:
{"page": "...", "parts": [{"part": "...", "kind": "...", "line": "..."}, ...]}

page: at most 12 words naming what is on the page as a whole. Where it holds several circuits, say so \
and name them.

One entry per part given, in the order given, using exactly the part number as given.

kind is one of: project (a circuit somebody built or can build), technique (how a circuit works, a \
measurement, a design method), reference (a table, a parts list, a datasheet page, an index, a \
catalogue), advert (an advertisement or a price list - including equipment for sale listed by its type \
number), none (the page does not say what this part is doing there).

line: at most 14 words. The circuit or section it sits in, and what that circuit is for. Do not begin \
by repeating the part number. Never write "this page", "the article" or "the circuit shown". Where the \
page does not say, use kind none and say where it appears instead - a vaguer line is better than a \
role you cannot see.

Every other part number you name must appear in the text in front of you. Do not name a device because \
the circuit usually uses one. Use the document title only where the page text agrees with it."""


# --- the excerpt ------------------------------------------------------------------------------------
def _norm(word: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", word.upper())


def excerpt(text: str, parts, head: int = 110, around: int = 70, cap: int = 6000) -> tuple[str, list]:
    """The head of the page plus a window around every part, merged, with `[...]` where text is left out.

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
    for i in sorted(keep):
        if last is not None and i > last + 1:
            out.append("[...]")
        out.append(words[i])
        last = i
    joined = " ".join(out)
    if len(joined) > cap:
        if around > 25:
            return excerpt(text, parts, head, around - 20, cap)
        joined = joined[:cap]
    return joined, missing


def prompt(page: dict) -> str:
    listed = "\n".join(
        f"  {p['part']}  (read {p['times']}x{', beside ' + p['near'] if p['near'] else ''})"
        for p in page["parts"])
    return (f"DOCUMENT: {page['title']}\nSOURCE: {page['source']} ({page['role']})\nPAGE: {page['page']}\n"
            f"PARTS TO WRITE A LINE FOR:\n{listed}\n\nPAGE TEXT:\n{page['excerpt']}")


# --- the answer -------------------------------------------------------------------------------------
def read_answer(text: str, asked: list[str]) -> dict:
    """The model's text -> {"page": line, "parts": {PART: {kind, line}}}, or raise so it is asked again.

    Lenient about what came back and strict about what is kept: an entry for a part nobody asked about
    is dropped, a kind this project does not use becomes `none`, and a line longer than a line is cut.
    An answer that names none of the parts asked about is not an answer."""
    body = json.loads(text[text.index("{"):text.rindex("}") + 1])
    want = {p.upper(): p for p in asked}
    parts = {}
    for entry in body.get("parts") or []:
        part = want.get(str(entry.get("part", "")).upper())
        line = " ".join(str(entry.get("line", "")).split())[:160]
        if not part or not line:
            continue
        kind = str(entry.get("kind", "")).lower()
        parts[part] = {"kind": kind if kind in KINDS else "none", "line": line}
    if not parts:
        raise ValueError(f"no part of {asked[:3]} answered")
    return {"page": " ".join(str(body.get("page", "")).split())[:160], "parts": parts,
            "v": VERSION, "missing": sorted(set(asked) - set(parts))}


# --- what to ask about ------------------------------------------------------------------------------
def sources() -> list[str]:
    with open(schematics_registry(), encoding="utf-8") as f:
        return sorted((yaml.safe_load(f) or {}).get("sources", {}))


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
        rows = dict(db.execute(
            "select p.page_no, t.text from pages p join documents d on d.doc_id = p.doc_id "
            "join page_text t on t.page_id = p.page_id where d.source = ? and d.doc_key = ?",
            (group[0]["source"], key)).fetchall())
        for page in group:
            text = rows.get(page["page"])
            if not text:
                notext += 1
                continue
            page["parts"] = page["parts"][:MAX_PARTS]
            page["excerpt"], page["absent"] = excerpt(text, [p["part"] for p in page["parts"]])
            out.append(page)
    db.close()
    if notext:
        say(f"  {notext} pages have no text in the index and cannot be read")
    return out


def key_of(page: dict) -> str:
    return f"{VERSION}|{page['source']}|{page['key']}|{page['page']}"


# --- the run ----------------------------------------------------------------------------------------
def run(which: list[str] | None = None, limit: int = 0, workers: int = 4, dry: bool = False,
        say=print) -> dict:
    require(index_db(), "summarising pages")
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
        # Room for the page line and one line per part. A page of two dozen parts needs four times the
        # answer of a page with three, and an answer cut off in the middle is an answer thrown away.
        items = [{"key": key_of(p), "prompt": prompt(p), "asked": [q["part"] for q in p["parts"]],
                  "max_tokens": 120 + 45 * len(p["parts"])} for p in pages]
        have = llm.cached(TASK, MODEL)
        todo = [it for it in items if it["key"] not in have]
        say(f"{source}: {len(pages)} pages, {uses} uses, {len(todo)} pages to ask")
        if dry:
            continue
        counts["asked"] += len(todo)
        answers = llm.ask_local(TASK, SYSTEM, items, model=MODEL, workers=workers, say=say,
                                parse=lambda text, item: read_answer(text, item["asked"]))
        counts["answered"] += sum(1 for it in items if it["key"] in answers)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics summarise", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only this source; repeat for several")
    ap.add_argument("--limit", type=int, default=0, help="at most this many pages per source")
    ap.add_argument("--workers", type=int, default=4, help="calls in flight (the server has four slots)")
    ap.add_argument("--dry", action="store_true", help="say what would be asked, ask nothing")
    ap.add_argument("--detach", action="store_true", help="run in the background, under a lock, into a log")
    args = ap.parse_args(argv)
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
