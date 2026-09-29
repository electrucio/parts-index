"""What a model is asked to reproduce, in one vocabulary for the three things that speak about it.

A data sheet's row, a model card's parameters and the header its author wrote all say something about the
same behaviours of a part — its DC characteristics, its capacitances, its noise, its distortion. Naming
those behaviours once lets the three meet: a sheet's THD row finds the header that says distortion is not
modelled, and a Cob row finds the card that has no CJC.

The vocabulary is internal. The page never shows a behaviour by name; it shows the sheet's own row and, in
each model's column, the model's value or why there is none. `tests/fixtures/behaviours.json` holds the
same ids for the site's tests, which check that every claim id has its words there.
"""
from __future__ import annotations

BEHAVIOURS = (
    "dc", "leakage", "capacitance", "frequency", "switching", "recovery", "noise", "distortion",
    "temperature", "breakdown", "slew", "supply", "output",
)

# What a kind of part is, for this purpose: the kinds of the recipes, gathered by the rows their sheets
# print and the model families their cards use.
GROUPS = {
    "bjt": ("bjt", "bjt-ge"),
    "jfet": ("jfet",),
    "diode": ("diode", "diode-ge", "zener", "led"),
    "mosfet": ("mosfet",),
    "amplifier": ("opamp", "comparator", "ota", "vca", "mic-preamp", "ic-audio"),
}

# A data sheet's row, by its canonical symbol (as the bench reads it), to the behaviour it measures. The
# same symbol can mean different things in two kinds of part: IDSS is a JFET's DC current and a MOSFET's
# leakage.
SYMBOLS: dict[str, dict[str, str]] = {
    "bjt": {
        "hFE": "dc", "vbe": "dc", "vcesat": "dc", "vbesat": "dc",
        "icbo": "leakage", "iebo": "leakage",
        "ft": "frequency", "cob": "capacitance", "cib": "capacitance",
        "nf": "noise", "en": "noise",
        "td": "switching", "tr": "switching", "ts": "switching", "tf": "switching",
        "vbrceo": "breakdown", "vbrcbo": "breakdown", "vbrebo": "breakdown",
    },
    "jfet": {
        "idss": "dc", "vgsoff": "dc", "vgs": "dc", "gfs": "dc", "gos": "dc",
        "igss": "leakage", "ig": "leakage",
        "ciss": "capacitance", "crss": "capacitance", "coss": "capacitance",
        "en": "noise", "nf": "noise", "ft": "frequency",
        "vbrgss": "breakdown", "vbrgds": "breakdown",
    },
    "diode": {
        "vf": "dc", "ir": "leakage", "cd": "capacitance", "trr": "recovery", "vbr": "breakdown",
    },
    "mosfet": {
        "vgsth": "dc", "rdson": "dc", "gfs": "dc", "idon": "dc", "vdson": "dc", "vsd": "dc",
        "idss": "leakage", "igssf": "leakage", "igssr": "leakage",
        "ciss": "capacitance", "coss": "capacitance", "crss": "capacitance",
        "qg": "capacitance", "qgs": "capacitance", "qgd": "capacitance", "rg": "capacitance",
        "trr": "recovery", "vbrdss": "breakdown",
    },
}

# What a model's author can declare modelled or not modelled, and the behaviour each belongs to. Most of
# these come from op-amp macromodel headers ("The following parameters are accurately modeled: open loop
# gain and phase … slew rate … Distortion is not characterized").
CLAIMS = {
    "offset": "dc", "bias-current": "dc", "open-loop-gain": "dc", "cmrr": "dc", "input-range": "dc",
    "input-impedance": "capacitance",
    "gain-phase": "frequency", "bandwidth": "frequency", "settling": "frequency",
    "step-response": "frequency",
    "slew": "slew",
    "noise": "noise", "noise-1f": "noise", "current-noise": "noise",
    "distortion": "distortion",
    "temperature": "temperature",
    "psrr": "supply", "supply-current": "supply",
    "output-swing": "output", "output-current": "output", "current-limit": "output",
    "overload-recovery": "output", "phase-reversal": "output", "output-impedance": "output",
}

# Qualifications an author attaches rather than a behaviour: an offset that "is static and will not vary",
# a model "valid at 25 °C only".
LIMITS = {
    "vos-static": "dc", "ib-static": "dc", "25c-only": "temperature", "typical-only": "dc",
    "supply-fixed": "supply",
}


def group(kind: str) -> str | None:
    """The group a recipe's kind belongs to, or None for kinds with no vocabulary yet (valves, …)."""
    for g, kinds in GROUPS.items():
        if kind in kinds:
            return g
    return None


def of_row(kind: str, symbol: str, cond: dict | None = None) -> str | None:
    """The behaviour a data-sheet row measures. The small-signal gain h_fe is DC-like at audio
    frequencies and a frequency response at the megahertz the sheets use to state fT through it."""
    g = group(kind)
    if symbol == "hfe" and g == "bjt":
        return "frequency" if (cond or {}).get("F", 0) >= 1e6 else "dc"
    return SYMBOLS.get(g or "", {}).get(symbol)


def vocabulary() -> dict:
    """Everything the site needs to name, as the shared fixture holds it."""
    return {"behaviours": list(BEHAVIOURS), "claims": dict(CLAIMS), "limits": dict(LIMITS)}
