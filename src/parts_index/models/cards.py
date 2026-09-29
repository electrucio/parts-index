"""What each recipe model's card cannot represent, because the parameter that carries it is not there.

    pidx models cards [--kind bjt]

A Gummel-Poon card without CJC has no collector capacitance: simulated, its Cob is zero, and a data
sheet's "Cob ≤ 4 pF" would be met by a model that does not model it. So each card is read for the
parameters that carry the behaviours a data sheet specifies, and the part's record says, per model, which
of them are absent. A zero counts as absent: for these parameters SPICE reads zero as "none" or as
"infinite", which is the same thing here. The page then shows `n.m. card: CJC` where a value would
otherwise stand, and lists what each card lacks.

It also notes what one simulator reads differently from the others (`DIALECT`), from what the three
were seen to do on the whole bipolar population (docs/simulation-and-datasheets.md).

Only which parameters are absent is published, never a parameter's value (CLAUDE.md rule 2).
Subcircuits, cards built on another (`AKO:`) and families other than those below are recorded by family
alone: nothing is claimed about what they lack.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

from parts_index.bench import record
from parts_index.core.config import require, spice_models_root, spice_recipe_locations
from parts_index.models import behaviours
from parts_index.models import found as F

VERSION = "cards-1"

# The parameters looked for, by family, in the order the page lists them.
CHECKED = {
    "gummel-poon": ("TF", "CJE", "CJC", "TR", "VAF", "IKF", "RB", "KF", "XTB"),
    "jfet": ("CGS", "CGD", "LAMBDA", "KF", "VTOTC", "BETATCE"),
    "diode": ("CJO", "TT", "BV", "RS", "KF"),
}
# A data sheet's row (by canonical symbol) that a card of the family cannot represent unless one of these
# parameters is there. An empty tuple: the family has no parameter for it at all — a Gummel-Poon card
# models no breakdown (unless it carries a BV… extension) and a level-1 JFET none.
NEEDS: dict[str, dict[str, tuple[str, ...]]] = {
    "gummel-poon": {
        "cob": ("CJC",), "cib": ("CJE",), "ft": ("TF", "CJE", "CJC"),
        # the output admittance and the voltage feedback ratio are the Early effect seen at 1 kHz
        "hoe": ("VAF",), "hre": ("VAF",),
        "td": ("TF", "TR", "CJE", "CJC"), "tr": ("TF", "TR", "CJE", "CJC"),
        "ts": ("TF", "TR", "CJE", "CJC"), "tf": ("TF", "TR", "CJE", "CJC"),
        "vbrceo": (), "vbrcbo": (), "vbrebo": (),
    },
    "jfet": {
        "ciss": ("CGS", "CGD"), "crss": ("CGD",), "coss": ("CGD",), "gos": ("LAMBDA",),
        "vbrgss": (), "vbrgds": (),
    },
    "diode": {"cd": ("CJO",), "trr": ("TT",), "vbr": ("BV",)},
}

# What one simulator reads differently from the other two, and what gives it away in a card.
AMPERE_UNIT = re.compile(r"(?<=[\d.])A(?:MPS?)?(?=[\s),]|$)", re.I)       # IKF=10A: ngspice reads atto
CATALOGUE = ("MFG", "VCEO", "ICRATING", "IAVE", "VPK", "IPK", "TYPE")      # LTspice's; ngspice refuses
JFET_EXTENSIONS = ("ISR", "NR", "ALPHA", "VK")                             # LTspice's; ngspice ignores
LTSPICE_DIODE = ("RON", "ROFF", "VFWD", "VREV", "ILIMIT", "REVILIMIT", "EPSILON", "REVEPSILON")
DIALECT = {
    "unit-a": "a unit after a number (IKF=10A): ngspice reads the A as atto",
    "catalogue-fields": "LTspice's catalogue fields (mfg=, Vceo=, …): ngspice refuses the card",
    "nk-above-1": "NK above 1: ngspice clamps it to 1",
    "jfet-extensions": "LTspice's JFET extensions (isr, nr, alpha, vk): ngspice ignores them",
    "ltspice-diode": "LTspice's ideal-diode parameters (Ron, Roff, Vfwd…): only LTspice reads them",
}

RX_HEAD = re.compile(r"^\.MODEL\s+\S+\s+(AKO:\s*\S+\s+)?([A-Z]+)\s*(.*)$", re.S)
RX_PARAM = re.compile(r"([A-Z_][A-Z0-9_]*)\s*=\s*(\{[^}]*\}|\S+)")


def card_params(body: str) -> tuple[str, bool, dict[str, str]] | None:
    """(device type, built on another card, parameters as written) of a `.model` statement."""
    lines = F.code_lines(body)
    if len(lines) != 1:
        return None
    m = RX_HEAD.match(lines[0])
    if not m:
        return None
    text = m.group(3).replace("(", " ").replace(")", " ").replace(",", " ")
    return m.group(2), bool(m.group(1)), dict(RX_PARAM.findall(text))


def number(v: str) -> float | None:
    """A parameter's value as a number, or None when it is an expression or a name."""
    x = F.value(AMPERE_UNIT.sub("", v))
    try:
        return float(x)
    except ValueError:
        return None


def family(kind_type: str, params: dict[str, str]) -> str:
    """The model family a card selects: its device type, and LEVEL where the type has several."""
    level = params.get("LEVEL")
    first = level is None or number(level) == 1.0
    if kind_type in ("NPN", "PNP"):
        return "gummel-poon" if first else f"bjt-level-{level.lower()}"
    if kind_type in ("NJF", "PJF"):
        return "jfet" if first else f"jfet-level-{level.lower()}"
    if kind_type == "D":
        return "ltspice-ideal-diode" if any(p in params for p in ("RON", "ROFF", "VFWD")) else "diode"
    return kind_type.lower()


def read(kind: str, body: str) -> dict:
    """What one card lacks and how the simulators differ on it."""
    if kind != "model":
        return {"family": "subckt"}
    parsed = card_params(body)
    if parsed is None:
        return {"family": "unknown"}
    kind_type, ako, params = parsed
    fam = family(kind_type, params)
    out: dict = {"family": fam, "type": kind_type}
    if ako:
        out["family"] = "ako"
        return out
    if fam in CHECKED:
        absent, unknown = [], []
        for p in CHECKED[fam]:
            if p not in params:
                absent.append(p)
                continue
            v = number(params[p])
            if v is None:
                unknown.append(p)
            elif v == 0:
                absent.append(p)
        out["absent"] = absent
        if unknown:
            out["unknown"] = unknown
        if fam == "gummel-poon" and any(p.startswith("BV") for p in params):
            out["breakdown"] = True               # an extension some libraries write and some simulators read
    dialect = []
    if any(AMPERE_UNIT.search(v) for v in params.values()):
        dialect.append("unit-a")
    if any(p in params for p in CATALOGUE):
        dialect.append("catalogue-fields")
    if (number(params.get("NK", "")) or 0) > 1:
        dialect.append("nk-above-1")
    if kind_type in ("NJF", "PJF") and any(p in params for p in JFET_EXTENSIONS):
        dialect.append("jfet-extensions")
    if kind_type == "D" and any(p in params for p in LTSPICE_DIODE):
        dialect.append("ltspice-diode")
    if dialect:
        out["dialect"] = dialect
    return out


def cannot(card: dict, symbol: str) -> tuple[str, ...] | None:
    """The parameters whose absence keeps this card from representing a sheet's row: None when the card
    can (or when nothing is known), an empty tuple when its family has no parameter for it at all."""
    needs = NEEDS.get(card.get("family", ""), {}).get(symbol)
    if needs is None or "absent" not in card:
        return None
    if not needs:
        return None if card.get("breakdown") else ()
    if set(needs) <= set(card["absent"]):
        return needs
    return None


def run(only_kind: str | None = None, only_part: str | None = None) -> Counter:
    locations = json.loads(require(spice_recipe_locations(), "reading the recipes' cards").read_text(encoding="utf-8"))
    files = F.Files(spice_models_root())
    led = record.ledger()
    c: Counter = Counter()
    for key, models in sorted(locations.items()):
        kind, part = key.split("/", 1)
        if behaviours.group(kind) not in ("bjt", "jfet", "diode") or (only_kind and kind != only_kind) \
                or (only_part and part != only_part):
            continue
        todo = {m["hash"]: m for m in models if m["hash"] and m["file"].startswith("sources/")}
        dig = record.digest(sorted(todo))
        if led.fresh(key, "cards", VERSION, dig):
            c["fresh"] += 1
            continue
        out = {}
        for h, m in sorted(todo.items()):
            try:
                chain = F.closure(files.get(m["file"])[0], m["name"])
            except OSError:
                c["unreadable"] += 1
                continue
            if not chain:
                c["not found in its file"] += 1
                continue
            kind_def, _, body = chain[-1]
            out[h] = read(kind_def, body)
            c[f"family {out[h]['family']}"] += 1
            for p in out[h].get("absent", []):
                c[f"no {p}"] += 1
            for d in out[h].get("dialect", []):
                c[d] += 1
        c["written" if record.write_section(kind, part, "cards", out) else "unchanged"] += 1
        led.stamp(key, "cards", version=VERSION, cards_in=dig)
    led.save()
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", help="only one kind (bjt, jfet, diode, …)")
    ap.add_argument("--part", help="only one part")
    a = ap.parse_args(argv)
    c = run(a.kind, a.part)
    print(f"{c['written']:,} parts written, {c['unchanged']:,} unchanged, {c['fresh']:,} already done")
    fams = sorted(((k[7:], n) for k, n in c.items() if k.startswith("family ")), key=lambda x: -x[1])
    print("cards by family: " + ", ".join(f"{k} {n:,}" for k, n in fams))
    gaps = sorted(((k[3:], n) for k, n in c.items() if k.startswith("no ")), key=lambda x: -x[1])
    print("absent: " + ", ".join(f"{k} {n:,}" for k, n in gaps))
    print("dialect: " + ", ".join(f"{d} {c[d]:,}" for d in DIALECT if c[d]))
    for k in ("unreadable", "not found in its file"):
        if c[k]:
            print(f"{k}: {c[k]:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
