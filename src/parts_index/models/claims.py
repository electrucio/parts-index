"""What each recipe model's author declares it models, does not model, and was written for.

    pidx models claims [--kind opamp] [--stats]

Many model files open with a note on what the model reproduces: "The following parameters are accurately
modeled: open loop gain and phase vs frequency … slew rate", "Noise is not modeled", "Distortion is not
characterized", "Simulator: PSPICE". A data sheet specifying distortion and a model whose author says it
does not model distortion should meet on the page, so these notes are read into the vocabulary of
`models/behaviours.py`.

What is published is derived, never quoted (CLAUDE.md rules 1–2): the claim ids, the simulator named, and
a pointer — the file's sha256 and the line range of the note — so a reader can open the sentence in their
own copy. A note line that names nothing the vocabulary knows is counted (`other`), and its text stays here.

The note read is the run of comment lines directly above the model's definition, and the comment lines
that open a subcircuit's body. A note that heads a library of many models (`scope: file`) is kept apart:
it may speak of another model in the same file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter

from parts_index.bench import record
from parts_index.core.config import require, spice_models_root, spice_recipe_locations
from parts_index.models import found as F
from parts_index.models.index import model_text

VERSION = "claims-1"
MAX_LINES = 300

# The words a note uses for a behaviour, to the claim id (`behaviours.CLAIMS`). One line can name several.
TERMS: list[tuple[str, re.Pattern]] = [(cid, re.compile(rx, re.I)) for cid, rx in (
    ("distortion", r"\bdistortion|\bTHD\b"),
    ("noise-1f", r"1/f"),
    ("current-noise", r"current noise"),
    ("noise", r"(?<!current )\bnoise\b|voltage (and current )?noise"),
    ("slew", r"\bslew"),
    ("gain-phase", r"gain and phase|\bAol\b"),
    ("gain-asymmetry", r"asymmetric(al)? gain|gain asymmetry"),
    ("open-loop-gain", r"open[- ]loop gain(?! and phase)"),
    ("bandwidth", r"bandwidth|\bGBW\b"),
    ("settling", r"settling"),
    ("step-response", r"step response"),
    ("cmrr", r"\bCMRR\b|common[- ]mode rejection"),
    ("psrr", r"\bPSRR?\b|supply rejection"),
    ("supply-current", r"quiescent current|supply current|\bIq\b|\bIsy\b"),
    ("current-limit", r"short[- ]circuit|current limit|\bIsc\b"),
    ("output-swing", r"output (voltage )?swing|output clamp|clamps? to (the )?rails|output voltage limit"),
    ("output-current", r"output current(?!s? limit)"),
    ("overload-recovery", r"over(load|drive) recovery"),
    ("phase-reversal", r"phase reversal"),
    ("output-impedance", r"output impedance|\bZo\b"),
    ("input-impedance", r"input (differential |common[- ]mode )?(impedance|capacitance)|\bZi[dc]\b"),
    ("input-range", r"common[- ]mode (input )?(voltage )?range|input (voltage )?range|common mode volt range"),
    ("offset", r"offset voltage|input offset(?! current)|\bVos\b"),
    ("bias-current", r"bias current|offset current|\bI ?bias\b"),
    ("temperature", r"temperature|\bdrift\b"),
)]

# A list's heading, and whether what follows it is modelled.
HEADINGS: list[tuple[bool, re.Pattern]] = [(yes, re.compile(rx, re.I)) for yes, rx in (
    (False, r"\bnot modell?ed\s*:|parameters (which|that) are not modell?ed|following (parameters|features) "
            r"are not modell?ed|will not provide accurate simulation of|not included\s*:"),
    (True, r"parameters modell?ed include|following (parameters|features) are (accurately |also )?modell?ed|"
           r"features modell?ed are|macro-?model simulated parameters|simulates typical values for the "
           r"following|modell?ed parameters\s*:|this model includes\s*:"),
)]
# A sentence about what is or is not modelled, anywhere in the note; it overrides a list's polarity.
NOT = re.compile(r"\b(is|are)\s+not\s+(modell?ed|characteri[sz]ed|included|simulated|supported)\b|"
                 r"\bnot modell?ed\s*:?\s*\w", re.I)
YES = re.compile(r"\b(is|are)\s+(accurately\s+)?(modell?ed|characteri[sz]ed|included|simulated|accurate)\b", re.I)
SENTENCE = re.compile(r"\b(is|are|will|was|were|should|can|may)\b", re.I)
END = re.compile(r"end notes|node assignments|copyright|connections\s*:|pin ?out|\|\s*\|", re.I)

LIMITS: list[tuple[str, re.Pattern]] = [(lid, re.compile(rx, re.I)) for lid, rx in (
    ("vos-static", r"\b(vos|offset)\b[^.]*\bstatic\b"),
    ("ib-static", r"\b(ib|bias current)\b[^.]*\bstatic\b"),
    ("25c-only", r"(25\s*\W?\s*c|room temperature)[^.]*\bonly\b|\bonly\b[^.]*\b25\s*\W?\s*c\b|"
                 r"modell?ed at (ambient |nominal )?(room temperature|\+?25\s*\W?\s*c|ta\s*=\s*25)"),
    ("worst-case", r"simulates the worst case"),
    ("typical-only", r"simulates typical values"),
    ("single-channel", r"single device only|for (a )?single (device|channel|amplifier)"),
)]
# Named, not guessed: "Simulator: PSPICE", "Use PSPICE (or SPICE 2G6…)", "for LTspice", a TopSPICE banner.
SIMULATOR = re.compile(r"simulator\s*[:=]\s*([A-Za-z][\w .-]*)|\buse (pspice|spice ?2g6|spice ?3|ltspice)\b|"
                       r"\bfor (ltspice|pspice|topspice|simetrix)\b|\b(topspice|simetrix)\b", re.I)
SIMULATORS = {"pspice": "pspice", "spice2": "spice2", "spice 2": "spice2", "spice2g6": "spice2",
              "spice 2g6": "spice2", "spice3": "spice3", "spice 3": "spice3", "simetrix": "simetrix",
              "topspice": "topspice", "hspice": "hspice", "tina-ti": "tina-ti", "ltspice": "ltspice"}


def comment(line: str) -> str | None:
    """The text of a comment line, or None for a line of code. A blank line is an empty comment."""
    s = line.strip()
    if not s:
        return ""
    return s.lstrip("*").strip() if s.startswith("*") else None


def header(lines: list[str], first: int, last: int) -> list[tuple[int, str]]:
    """(line number, text) of the note over a definition at lines first..last (1-based): the comment
    lines directly above it, back to the first line of code, and those that open its body."""
    out: list[tuple[int, str]] = []
    i = first - 2
    while i >= 0 and first - 1 - i <= MAX_LINES:
        c = comment(lines[i])
        if c is None:
            break
        out.append((i + 1, c))
        i -= 1
    out.reverse()
    j = first                                 # the definition's own line, then its continuations
    while j < last and lines[j].lstrip().startswith("+"):
        j += 1
    while j < last:
        c = comment(lines[j])
        if c is None:
            break
        out.append((j + 1, c))
        j += 1
    return out


def spans(numbers: list[int]) -> list[list[int]]:
    """Consecutive line numbers as [first, last] ranges."""
    out: list[list[int]] = []
    for n in numbers:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def terms(text: str) -> list[str]:
    return [cid for cid, rx in TERMS if rx.search(text)]


def parse(note: list[tuple[int, str]]) -> dict:
    """What a note declares: {yes, no, limits, simulator, other, lines} — lines the ones that said it."""
    yes: set[str] = set()
    no: set[str] = set()
    limits: set[str] = set()
    used: list[int] = []
    other = 0
    simulator = ""
    listing: bool | None = None                # inside a list headed modelled (True) / not modelled (False)
    # a sentence broken over two lines ("… are" / "not included.") is read as one
    joined: list[tuple[int, str]] = []
    for n, text in note:
        if joined and re.search(r"\b(is|are)\s*$", joined[-1][1], re.I) and re.match(r"not\b", text, re.I):
            joined[-1] = (joined[-1][0], joined[-1][1] + " " + text)
        else:
            joined.append((n, text))
    for n, text in joined:
        if not text:
            continue
        if END.search(text):
            listing = None
            continue
        hit = False
        m = SIMULATOR.search(text)
        if m and not simulator:
            name = next(g for g in m.groups() if g).strip().lower().rstrip(".")
            simulator = SIMULATORS.get(name, SIMULATORS.get(name.split()[0], ""))
            hit = hit or bool(simulator)
        for lid, rx in LIMITS:
            if rx.search(text):
                limits.add(lid)
                hit = True
        heading = next((y for y, rx in HEADINGS if rx.search(text)), None)
        if heading is not None:
            listing = heading
            used.append(n)
            # a heading can carry its first items on the same line ("Not Modeled: noise, distortion")
            rest = re.split(r":", text, maxsplit=1)
            items = terms(rest[1]) if len(rest) > 1 else []
            (yes if heading else no).update(items)
            continue
        found = terms(text)
        if "25c-only" in limits and re.search(r"25\s*\W?\s*c|room temperature|ta\s*=\s*25", text, re.I):
            found = [x for x in found if x != "temperature"]     # "modeled at 25 °C" models no temperature
        if NOT.search(text):
            no.update(found)
            hit = hit or bool(found)
        elif YES.search(text) and not SENTENCE.search(re.sub(YES, "", text)):
            yes.update(found)
            hit = hit or bool(found)
        elif listing is not None and not SENTENCE.search(text):
            (yes if listing else no).update(found)
            hit = hit or bool(found)
            if not found:
                other += 1
        elif listing is not None:
            listing = None                     # a sentence ends a list
        if hit:
            used.append(n)
    yes -= no                                  # a model said not to model something does not model it
    out: dict = {}
    if yes:
        out["yes"] = sorted(yes)
    if no:
        out["no"] = sorted(no)
    if limits:
        out["limits"] = sorted(limits)
    if simulator:
        out["simulator"] = simulator
    if out:
        out["lines"] = spans(sorted(set(used)))
        if other:
            out["other"] = other
    return out


def read_model(text: str, name: str) -> dict:
    """The claims of the definition `name` in a file's text (the last one of that name, as `found` reads)."""
    lines = text.splitlines()
    sp = F.spans(text)
    if name.lower() not in sp:
        return {}
    first, last = sp[name.lower()]
    note = header(lines, first, last)
    out = parse(note)
    if out:
        top = note[0][0] if note else first
        own = {nm.lower() for _, nm, _ in F.closure(F.blocks(text), name)}
        others = [k for k, (a, _) in sp.items() if k not in own and a > last]
        # the note runs from the top of a file that goes on to define other models: it heads the
        # library, and may be about any of them
        if top <= 2 and others:
            out["scope"] = "file"
    return out


def run(only_kind: str | None = None, stats: bool = False) -> Counter:
    locations = json.loads(require(spice_recipe_locations(), "reading the recipes' headers").read_text(encoding="utf-8"))
    root = spice_models_root()
    led = record.ledger()
    c: Counter = Counter()
    texts: dict[str, tuple[str, str] | None] = {}
    for key, models in sorted(locations.items()):
        kind, part = key.split("/", 1)
        if only_kind and kind != only_kind:
            continue
        todo = {m["hash"]: m for m in models if m["hash"] and m["file"].startswith("sources/")}
        dig = record.digest(sorted((h, m["file"], m["name"]) for h, m in todo.items()))
        if led.fresh(key, "claims", VERSION, dig) and not stats:
            c["fresh"] += 1
            continue
        out = {}
        for h, m in sorted(todo.items()):
            if m["file"] not in texts:
                try:
                    raw = (root / m["file"]).read_bytes()
                    texts[m["file"]] = (model_text(raw, m["file"]), hashlib.sha256(raw).hexdigest())
                except OSError:
                    texts[m["file"]] = None
            got = texts[m["file"]]
            if got is None:
                c["unreadable"] += 1
                continue
            cl = read_model(got[0], m["name"])
            if not cl:
                continue
            cl["sha256"] = got[1]
            out[h] = cl
            c["models with a note"] += 1
            for cid in cl.get("no", []):
                c[f"no {cid}"] += 1
            for cid in cl.get("yes", []):
                c[f"yes {cid}"] += 1
            for lid in cl.get("limits", []):
                c[f"limit {lid}"] += 1
            if cl.get("simulator"):
                c[f"for {cl['simulator']}"] += 1
            c["file scope"] += cl.get("scope") == "file"
        if stats:
            continue
        c["written" if record.write_section(kind, part, "claims", out) else "unchanged"] += 1
        led.stamp(key, "claims", version=VERSION, claims_in=dig)
    if not stats:
        led.save()
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", help="only one kind (opamp, bjt, …)")
    ap.add_argument("--stats", action="store_true", help="count what would be read and write nothing")
    a = ap.parse_args(argv)
    c = run(a.kind, a.stats)
    if not a.stats:
        print(f"{c['written']:,} parts written, {c['unchanged']:,} unchanged, {c['fresh']:,} already done")
    print(f"{c['models with a note']:,} models declare something ({c['file scope']:,} in a note heading a library)")
    for prefix in ("no ", "yes ", "limit ", "for "):
        got = sorted(((k[len(prefix):], n) for k, n in c.items() if k.startswith(prefix)), key=lambda x: -x[1])
        print(f"{prefix.strip() or 'no'}: " + ", ".join(f"{k} {n:,}" for k, n in got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
