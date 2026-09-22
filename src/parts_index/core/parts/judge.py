"""Decide, once and with evidence, which census names mean a component *in this corpus*.

    pidx parts judge --collect          walk the corpus and gather the evidence for every such name
    pidx parts judge --ask              put the evidence to a model and write data/parts/verdicts.csv

The census says a string exists as a type number somewhere in the world. It cannot say whether the
string, where this corpus prints it, is that part: 6V3 is a valve and it is the 6.3 V heater on every
valve drawing; CH1 is a valve and it is channel 1; ACME is a model in a SPICE example; MH40 is a valve
and a headphone. Every false link the census produced was one of these, and four rounds of hand-written
patterns did not converge on them — each round fixed what was big and missed the next class.

So the judgement is made per name rather than per pattern, from what the corpus actually shows: the
lines it appears in, the designators printed beside it, how many unrelated sources have it, how often it
stands alone as a label. That is the evidence a person would want, and it is what a model is given.

The result is `data/parts/verdicts.csv`, committed: the name, the verdict, the reason, who judged it and
when. A verdict the maintainer edits by hand is never overwritten. The extractor reads the file and stays
deterministic — no model is ever in the path of anything the site serves.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import re
import sys

from parts_index.core import pagesio
from parts_index.core.config import ocr_map, ocr_root, parts_verdicts, require, scratch
from parts_index.core.parts import extractor as parts

FIELDS = ("name", "verdict", "kind", "why", "documents", "sources", "judged_by", "judged_at", "judge_v")
# Bump this when the question changes — the prompt, the evidence gathered, the rules a verdict follows.
# Nothing else re-asks: a name already in data/parts/verdicts.csv at this version is never paid for
# twice, whatever machine the work moves to, because the file is committed and the cache is not.
JUDGE_VERSION = "judge-1"
EVIDENCE = "judge_evidence.json"
MAX_CONTEXTS = 5

SYSTEM = """You are told a string, and what a corpus of electronics documents does with it. A list of
type numbers says the string names a real component somewhere in the world. Your question is different:
where THIS corpus prints it, does it mean that component?

Say no when the corpus shows it is something else:
  * a reference designator or a series of them — CH1 is channel 1, PA1 and LD1 are designators, S12 a switch;
  * a value or a rating — 6V3 is a 6.3 V heater, N750 a capacitor temperature coefficient, 4K7 a resistor;
  * a number that is a page, a figure, a year, a price, an ordinal, a reader service card entry;
  * the model name of equipment — an amplifier, a headphone, a bus, a kit;
  * a placeholder out of an example circuit — PART1, MOD1, ACME;
  * OCR damage: a string that only ever appears as a misreading of something else.
Say yes when the contexts show it used as a component: printed beside a designator on a drawing, in the
value column of a parts list, or named in prose as the part a circuit uses.

The evidence is what decides, not the string's plausibility as a type number — assume it is a real type
number somewhere, because the census already said so. Weigh: does it stand alone as a label on pages that
have circuits on them, or only inside prose and tables of something else? Do the designators beside it
match the kind of part it is meant to be? Is it spread thinly over unrelated sources in a way that
suggests a common word or number?

why: at most fifteen words, quoting the evidence that decided it. When the evidence does not settle it,
say no: an unproven link is worse than a missing one."""

VERDICTS = ["component", "not_a_component"]
SCHEMA = {"name": "verdicts", "strict": True, "schema": {"type": "object", "additionalProperties": False,
          "required": ["items"], "properties": {"items": {"type": "array", "items": {
              "type": "object", "additionalProperties": False,
              "required": ["key", "verdict", "kind", "why"],
              "properties": {"key": {"type": "string"},
                             "verdict": {"type": "string", "enum": VERDICTS},
                             "kind": {"type": "string"}, "why": {"type": "string"}}}}}}}


def census_only(token: str) -> bool:
    """A name the extractor would publish on the census's word alone: no family knows its shape and the
    dictionary has never heard of it. Every false link measured so far was one of these."""
    return (parts.norm(token) in parts.CENSUS and not parts.family_of(token)
            and parts.norm(token) not in parts.KNOWN)


def collect(per_source: int = 60, say=print) -> dict:
    """Walk a sample of the corpus and gather, per census-only name, what the pages show of it."""
    require(ocr_map(), "collecting evidence")
    random.seed(23)
    by_source = collections.defaultdict(list)
    with open(ocr_map(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ocr_file"]:
                by_source[r["source"]].append(r)
    found: dict[str, dict] = {}
    docs = 0
    for source, rows in sorted(by_source.items()):
        for doc in random.sample(rows, min(per_source, len(rows))):
            try:
                pages = pagesio.read_pages(ocr_root() / doc["ocr_file"])
            except (OSError, ValueError):
                continue
            docs += 1
            for page in pages:
                blocks = [b for b in page.get("blocks") or [] if (b.get("text") or "").strip()]
                if not blocks:
                    continue
                labels = [b["text"].strip() for b in blocks if len(b["text"].strip()) <= 14]
                designators = [t for t in labels if parts.DESIG.fullmatch(t)]
                for i, b in enumerate(blocks):
                    text = b["text"].strip()
                    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9/\-]{2,15})(?![A-Za-z0-9])",
                                         text.upper()):
                        tok = parts.canonical(m.group(1).strip("-/")) or ""
                        if not tok or not census_only(tok):
                            continue
                        d = found.setdefault(tok, {"n": 0, "alone": 0, "sources": collections.Counter(),
                                                   "contexts": [], "near": collections.Counter()})
                        d["n"] += 1
                        d["sources"][source] += 1
                        if len(text) <= 14:
                            d["alone"] += 1
                        if len(d["contexts"]) < MAX_CONTEXTS and len(text) > len(tok):
                            d["contexts"].append(text[:160])
                        for des in designators[:60]:
                            d["near"][re.sub(r"\d+$", "", des.upper())] += 1
    out = scratch() / EVIDENCE
    out.parent.mkdir(parents=True, exist_ok=True)
    keep = {t: {"n": d["n"], "alone": d["alone"], "sources": dict(d["sources"].most_common(6)),
                "contexts": d["contexts"], "near": dict(d["near"].most_common(6))}
            for t, d in found.items() if d["n"] >= 2}
    out.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    say(f"{docs} documents read, {len(found)} census-only names seen, {len(keep)} of them more than once")
    return {"documents": docs, "names": len(keep), "written to": str(out)}


def load() -> dict[str, dict]:
    f = parts_verdicts()
    if not f.exists():
        return {}
    with open(f, newline="", encoding="utf-8") as fh:
        return {r["name"].upper(): r for r in csv.DictReader(fh)}


def ask(budget: float = 15.0, model: str = "gpt-5-mini", redo: bool = False, say=print) -> dict:
    """Put the collected evidence to a model and write the verdicts.

    Only names not already judged at JUDGE_VERSION are asked about, so ingesting new material costs a
    judgement on the new names and nothing else. `redo` asks again about everything, which is what a
    changed question needs — or bump JUDGE_VERSION, which does it for the next run and says why."""
    from parts_index.core import llm

    path = scratch() / EVIDENCE
    if not path.exists():
        raise SystemExit("no evidence yet: run `pidx parts judge --collect` first")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    known = load()
    items, already = [], 0
    for name, d in sorted(evidence.items()):
        was = known.get(name)
        if was and (not was.get("judged_by", "").startswith("gpt")      # a hand judgement stands
                    or (was.get("judge_v") == JUDGE_VERSION and not redo)):
            already += 1
            continue
        claim = parts.CENSUS.get(parts.norm(name))
        items.append({"key": name, "name": name,
                      "the census calls it": claim[1] if claim else "",
                      "times seen": d["n"], "alone as a label": d["alone"],
                      "sources": d["sources"], "designators on those pages": d["near"],
                      "lines it appears in": d["contexts"]})
    answers = llm.ask_batch("judge", SYSTEM, items, SCHEMA, model=model, budget=budget,
                            per_call=12, effort="low", workers=24, say=say)
    today = __import__("datetime").date.today().isoformat()
    rows = dict(known)
    for it in items:
        a = answers.get(it["key"])
        if not a:
            continue
        d = evidence[it["key"]]
        rows[it["key"]] = {"name": it["key"], "verdict": a["verdict"], "kind": a["kind"],
                           "why": a["why"], "documents": d["n"],
                           "sources": " ".join(sorted(d["sources"])), "judged_by": model,
                           "judged_at": today, "judge_v": JUDGE_VERSION}
    out = parts_verdicts()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for name in sorted(rows):
            w.writerow({k: rows[name].get(k, "") for k in FIELDS})
    yes = sum(1 for r in rows.values() if r["verdict"] == "component")
    return {"already judged, not asked again": already, "names judged": len(rows), "a component here": yes,
            "not a component here": len(rows) - yes, "spent": round(llm.spent("judge"), 2)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx parts judge", description=__doc__.splitlines()[0])
    ap.add_argument("--collect", action="store_true", help="walk the corpus and gather the evidence")
    ap.add_argument("--ask", action="store_true", help="put the evidence to a model (spends money)")
    ap.add_argument("--per-source", type=int, default=60, help="documents read per source when collecting")
    ap.add_argument("--budget", type=float, default=15.0, help="dollars this run may spend")
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--redo", action="store_true", help="ask again about names already judged")
    a = ap.parse_args(argv)
    if a.collect:
        for k, v in collect(a.per_source).items():
            print(f"  {v:>10}  {k}")
    if a.ask:
        for k, v in ask(a.budget, a.model, a.redo).items():
            print(f"  {v:>10}  {k}")
    if not (a.collect or a.ask):
        rows = load()
        yes = sum(1 for r in rows.values() if r["verdict"] == "component")
        print(f"  {len(rows)} names judged, {yes} a component here, {len(rows) - yes} not")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
