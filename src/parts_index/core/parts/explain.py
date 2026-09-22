"""Why does looking up this part give nothing? Say which of the answers is missing, and whose fault it is.

    pidx parts explain 6V6 TTC004B C3M0280090D

Two failures look identical from outside — the index read the part and threw it away, or no document
here has it — and they need opposite work. This asks all four places the project can answer from
(docs/COVERAGE.md) and prints a verdict, so the difference takes a second instead of an argument.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from parts_index.core.config import (
    dataset_table,
    models_dir,
    parts_census,
    schematics_parts,
    spice_definitions,
)
from parts_index.core.parts import extractor as ex


def _index_rows(part: str) -> dict | None:
    f = schematics_parts()
    if not f.exists():
        return None
    with open(f, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if ex.norm(r["part"]) == ex.norm(part):
                return r
    return None


def _census_row(part: str) -> dict | None:
    f = parts_census()
    if not f.exists():
        return None
    with open(f, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if ex.norm(r["part"]) == ex.norm(part):
                return r
    return None


def _model(part: str) -> str:
    d = models_dir() / "parts"
    for f in d.glob(f"*/{part}.yaml") if d.exists() else []:
        return f"a published recipe at {f.relative_to(models_dir().parent.parent)}"
    f = spice_definitions()                      # the vendor libraries held here, 388 MB of them
    if f.exists():
        needle = f'"name": "{part.upper()}"'.encode()
        alt = f'"name": "{part}"'.encode()
        with open(f, "rb") as fh:
            for line in fh:
                if needle in line or alt in line:
                    d = json.loads(line)
                    return f"a {d.get('type', '?')} definition from {d.get('source', '?')}"
    return ""


def _repos(part: str) -> str:
    f = dataset_table("part_repos")
    if not f.exists():
        return ""
    hits = []
    with open(f, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):                       # one row per part and repository
            if ex.norm(r.get("part", "")) == ex.norm(part):
                hits.append(r.get("url", ""))
    if not hits:
        return ""
    return f"{len(hits)} open-source project{'s' if len(hits) > 1 else ''} ({hits[0]})"


def explain(part: str) -> list[str]:
    out = [f"{part}"]
    tok = ex.canonical(part.upper()) or part.upper()
    fam = ex.family_of(tok)
    label = ex.extract(part, isolated=True, pending=True)
    prose = ex.extract(f"the {part} in the circuit")
    if label and label[0].family == ex.PENDING:
        read = "on its own, nothing — the census knows it, so a page that agrees publishes it as high"
    elif label:
        read = f"{label[0].conf} ({label[0].family})" + (f", in prose {prose[0].conf}" if prose else ", nothing in prose")
    else:
        read = "nothing, on a label or in prose"
    out.append(f"  read as        {read}")
    out.append(f"  family         {fam[0] + (', strict' if fam[2] else ', loose') if fam else 'none covers it'}")
    where = [name for name, hit in (("the dictionary", ex.norm(tok) in ex.KNOWN),
                                    ("the reject list", tok in ex.REJECTED)) if hit]
    cen = _census_row(part)
    if cen:
        where.append(f"the census ({cen['source']}, {cen['url']})")
    out.append(f"  known from     {', '.join(where) if where else 'nothing — only its shape'}")

    idx = _index_rows(part)
    answers = []
    if idx:
        answers.append(f"{idx['documents']} documents in the index ({idx['sources'].split()[0]} and others)"
                       if len(idx["sources"].split()) > 1 else f"{idx['documents']} documents in the index")
    if cen:
        answers.append("a data sheet through the census")
    m = _model(part)
    if m:
        answers.append(m)
    r = _repos(part)
    if r:
        answers.append(r)
    out.append(f"  can answer     {'; '.join(answers) if answers else 'nothing at all'}")

    if idx and int(idx["documents"]) > 0:
        verdict = "fine — the index has it"
    elif label and label[0].family == ex.PENDING:
        verdict = "coverage: it reads on a page that agrees, no document here does"
    elif label and label[0].conf == "high":
        verdict = "coverage: it reads correctly, no document here contains it"
    elif label:
        verdict = f"extractor: it reads as {label[0].conf}, and only high is published"
    else:
        verdict = "extractor: nothing reads it — no family covers this token"
    if not idx and answers:
        verdict += f" — but {len(answers)} other answer{'s' if len(answers) > 1 else ''} to give"
    out.append(f"  verdict        {verdict}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx parts explain", description=__doc__.splitlines()[0])
    ap.add_argument("part", nargs="+")
    a = ap.parse_args(argv)
    for part in a.part:
        print("\n".join(explain(part)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
