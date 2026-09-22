"""A labelled sample of real pages, so a change to the extractor can be measured instead of admired.

    pidx parts benchmark --build --pages 300     sample pages, label every candidate token on them
    pidx parts benchmark                         score today's extractor against the labels

Why this exists: four full passes over the corpus were tuned by exporting the index and reading the top
of the list of gains. Each pass fixed what was big and missed a whole class that was not — reader service
card numbers, then IC designators read as valves, then ordinals and heater voltages, then product models
off a site's index page. Looking at the head of a sorted list is not measurement.

A row is one decision: on this page, does this token name a component? Both what the extractor returns
and what it throws away are labelled, so the score has a precision side and a recall side. The labels are
committed; the page text they were judged from is not (rule 1), and is re-read from the OCR when needed.

The labels come from a model reading the whole page, and the maintainer corrects them by hand — a row he
has touched carries his name in `judged_by` and is never overwritten by a later run.
"""
from __future__ import annotations

import argparse
import collections
import csv
import random
import re
import sys

from parts_index.core import pagesio
from parts_index.core.config import ocr_map, ocr_root, parts_benchmark, require
from parts_index.core.parts import extractor as parts

FIELDS = ("source", "doc", "page", "token", "label", "kind", "why", "judged_by", "judged_at", "label_v")
# As with the judge: bump when the question changes, and nothing already answered at this version is
# paid for again. The committed file is the record, not the cache — the cache does not travel.
LABEL_VERSION = "benchmark-1"
# Deliberately looser than the extractor: a benchmark that only contained what the extractor already
# finds could never measure what it misses.
CANDIDATE = re.compile(r"^(?:[A-Z]{1,5}-?\d{2,5}[A-Z]{0,3}|\d{1,2}[A-Z]{1,3}\d{1,2}[A-Z]{0,3}|\d{3,5}[A-Z]{0,2})$")
KINDS = ["bjt", "jfet", "mosfet", "diode", "zener", "led", "tube", "opamp", "ic", "regulator", "opto",
         "logic", "passive", "connector", "other", "not_a_component"]

SYSTEM = """You are reading one page of an electronics document — a schematic, a service manual, a
magazine article, a parts list — as OCR text, and deciding what certain tokens on it mean.

For each token say whether, ON THIS PAGE, it names an electronic COMPONENT with its own datasheet: a
transistor, diode, valve, integrated circuit, optocoupler, regulator. The same string can be a component
on one page and not on another, and that is the whole question. Things that are NOT components here:
  * reference designators and their series — R12, IC4, CH1 (channel 1), PA1, S12 (a switch), V2;
  * component VALUES and ratings — 4K7, 100n, 6V3 (a 6.3 V heater), N750 (a capacitor temperature code);
  * page numbers, figure numbers, years, prices, ordinals (100TH), reader service card numbers;
  * product and model names of equipment — an amplifier, a headphone, a bus (S-100), a kit;
  * placeholder names out of example circuits — PART1, MOD1, ACME.
A component reference is usually printed as a label beside a designator, or in the value column of a
parts list, or named in prose as the part a circuit uses.

kind: what it is, from the list, or not_a_component. why: at most twelve words, concrete, quoting what on
the page decided it. When the page does not settle it, say not_a_component: an unproven link is worse
than a missing one."""

# One request per page, carrying that page's text once and every token to be judged on it.
LABEL = {"type": "object", "additionalProperties": False, "required": ["token", "is_component", "kind", "why"],
         "properties": {"token": {"type": "string"}, "is_component": {"type": "boolean"},
                        "kind": {"type": "string", "enum": KINDS}, "why": {"type": "string"}}}
SCHEMA = {"name": "labels", "strict": True, "schema": {"type": "object", "additionalProperties": False,
          "required": ["items"], "properties": {"items": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["key", "labels"],
              "properties": {"key": {"type": "string"},
                             "labels": {"type": "array", "items": LABEL}}}}}}}


def _pages(per_source: int, seed: int = 17):
    """A stratified sample: pages from every source, weighted towards pages that have something on them."""
    random.seed(seed)
    by_source = collections.defaultdict(list)
    with open(ocr_map(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ocr_file"]:
                by_source[r["source"]].append(r)
    for source, docs in sorted(by_source.items()):
        for doc in random.sample(docs, min(per_source, len(docs))):
            try:
                pages = pagesio.read_pages(ocr_root() / doc["ocr_file"])
            except (OSError, ValueError):
                continue
            with_text = [p for p in pages if len(p.get("blocks") or []) >= 12]
            if with_text:
                yield source, doc["doc_key"], random.choice(with_text)


def candidates(page) -> list[str]:
    blocks = [b for b in page.get("blocks") or [] if (b.get("text") or "").strip()]
    seen = {}
    for b in blocks:
        for m in re.finditer(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9/\-]{2,15})(?![A-Za-z0-9])",
                             b["text"].upper()):
            tok = m.group(1).strip("-/")
            if CANDIDATE.match(tok):
                seen.setdefault(tok, b["text"].strip())
    return list(seen)


def page_text(page, limit: int = 6000) -> str:
    return " ".join(b["text"].strip() for b in page.get("blocks") or [] if (b.get("text") or "").strip())[:limit]


def load() -> list[dict]:
    f = parts_benchmark()
    if not f.exists():
        return []
    with open(f, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save(rows: list[dict]) -> None:
    f = parts_benchmark()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["source"], r["doc"], int(r["page"]), r["token"])):
            w.writerow({k: r.get(k, "") for k in FIELDS})


def build(per_source: int = 6, budget: float = 12.0, model: str = "gpt-5", say=print) -> dict:
    """Sample pages, ask for a label on every candidate token, and merge with what is already labelled.
    A row the maintainer has judged is never overwritten."""
    from parts_index.core import llm

    require(ocr_map(), "building the benchmark")
    existing = {(r["doc"], r["page"], r["token"]): r for r in load()}
    done_pages = {(r["doc"], r["page"]) for r in existing.values()
                  if r.get("label_v") == LABEL_VERSION or not r.get("judged_by", "").startswith("gpt")}
    items, sources, decisions, skipped = [], {}, 0, 0
    for source, doc, page in _pages(per_source):
        toks = candidates(page)
        if not toks:
            continue
        if (doc, str(page["page"])) in done_pages:
            skipped += 1
            continue                                    # labelled already, at this version
        key = f"{doc}|{page['page']}"
        sources[key] = source
        decisions += len(toks)
        items.append({"key": key, "tokens": toks, "page_text": page_text(page)})
    say(f"{len(items)} pages to label, {decisions} token decisions ({skipped} pages already done)")
    answers = llm.ask_batch("benchmark", SYSTEM, items, SCHEMA, model=model, budget=budget,
                            per_call=1, effort="low", workers=24, say=say)
    today = __import__("datetime").date.today().isoformat()
    rows = dict(existing)
    for it in items:
        a = answers.get(it["key"])
        if not a:
            continue
        doc, page_no = it["key"].rsplit("|", 1)
        for lab in a.get("labels", []):
            tok = lab["token"].upper()
            was = existing.get((doc, page_no, tok))
            if was and was.get("judged_by") and not was["judged_by"].startswith("gpt"):
                continue                                    # a hand judgement stands
            rows[(doc, page_no, tok)] = {"source": sources[it["key"]], "doc": doc, "page": page_no,
                                         "token": tok,
                                         "label": "part" if lab["is_component"] else "not_part",
                                         "kind": lab["kind"], "why": lab["why"], "judged_by": model,
                                         "judged_at": today, "label_v": LABEL_VERSION}
    save(list(rows.values()))
    parts_n = sum(1 for r in rows.values() if r["label"] == "part")
    return {"pages already labelled": skipped, "rows": len(rows), "labelled a part": parts_n, "labelled not a part": len(rows) - parts_n,
            "spent": round(llm.spent("benchmark"), 2)}


def score(say=print) -> dict:
    """Run today's extractor over the benchmark's pages and compare with the labels."""
    rows = load()
    if not rows:
        raise SystemExit("no benchmark yet: run `pidx parts benchmark --build`")
    want = collections.defaultdict(dict)
    for r in rows:
        want[(r["doc"], r["page"])][r["token"]] = r
    by_doc = collections.defaultdict(set)
    for doc, page_no in want:
        by_doc[doc].add(int(page_no))
    files = {}
    with open(ocr_map(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["doc_key"] in by_doc:
                files[r["doc_key"]] = r["ocr_file"]
    tp = fp = fn = tn = 0
    misses, wrong = [], []
    for doc, page_nos in by_doc.items():
        if doc not in files:
            continue
        try:
            pages = {int(p["page"]): p for p in pagesio.read_pages(ocr_root() / files[doc])}
        except (OSError, ValueError):
            continue
        for page_no in page_nos:
            page = pages.get(page_no)
            if page is None:
                continue
            got = {h.part for h in parts.extract_page(page) if h.conf == "high"}
            got |= {h.raw.upper() for h in parts.extract_page(page) if h.conf == "high"}
            for token, r in want[(doc, str(page_no))].items():
                said_yes, is_yes = token in got, r["label"] == "part"
                if said_yes and is_yes:
                    tp += 1
                elif said_yes and not is_yes:
                    fp += 1
                    wrong.append((token, r["why"], r["source"]))
                elif not said_yes and is_yes:
                    fn += 1
                    misses.append((token, r["why"], r["source"]))
                else:
                    tn += 1
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    say(f"  {tp + fp + fn + tn} labelled decisions on {len(want)} pages")
    say(f"  precision {prec:.1%}   recall {rec:.1%}   ({tp} right, {fp} wrong, {fn} missed)")
    if wrong:
        say("  published and should not be:")
        for t, why, src in wrong[:15]:
            say(f"    {t:12} {src:18} {why[:60]}")
    if misses:
        say("  missed and should be published:")
        for t, why, src in misses[:15]:
            say(f"    {t:12} {src:18} {why[:60]}")
    return {"precision": round(prec, 4), "recall": round(rec, 4), "right": tp, "wrong": fp, "missed": fn}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx parts benchmark", description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="sample pages and label them (spends money)")
    ap.add_argument("--per-source", type=int, default=6, help="documents sampled per source")
    ap.add_argument("--budget", type=float, default=12.0, help="dollars this run may spend")
    ap.add_argument("--model", default="gpt-5")
    a = ap.parse_args(argv)
    if a.build:
        for k, v in build(a.per_source, a.budget, a.model).items():
            print(f"  {v:>10}  {k}")
    else:
        score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
