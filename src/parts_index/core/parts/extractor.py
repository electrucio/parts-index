"""Part numbers (transistors, ICs, valves, diodes, optos, BBDs) out of OCR or plain text.

    extract(text, isolated=False, allow_bare=False) -> [Hit]      one string: a block, a paragraph, a whole HTML page
    extract_page(page)                              -> [Hit]      one OCR page record {"w","h","blocks":[{"box","text","conf"}]}
    count_designators(blocks) / count_values(blocks)              "this looks like a circuit" signals (passives are not indexed)

FAMILIES, canonical(), VALUE, NOISE and FENDER_OK come from spice-library/research/audio-docs-parts/mine_audio_docs.py (2026-09-19);
this is the copy to maintain. Added here, measured on 60 magazine issues: OCR digit repairs (IN4148 -> 1N4148 was 28 % of the diodes),
split tokens (BC 109), slash lists (BC107/8/9), designators that VALUE let through (IC12, TR3), numeric-only valves and loose
families need context or the dictionary, package suffixes folded into base_part.

data/parts/known_parts.csv and rejected_tokens.txt are the dictionary (parts judged real / not real); `--snapshot` rebuilds them
from the model library and the classified audio-document parts under the private data root. Without them everything still works,
only with fewer `high` confidences.
"""
import csv
import re
import sys
from collections import namedtuple

from parts_index.core.config import known_parts, rejected_tokens, staging

Hit = namedtuple("Hit", "part base raw family kind conf fixed block")      # conf: high | medium | low ; block: index in the page or None

FAMILIES = [   # (family, kind guess, regex on the upper-cased token, strict numbering scheme?)
    ("JEDEC diode", "diode", r"1N\d{2,4}[A-Z]{0,2}", True),
    ("JEDEC transistor", "bjt/jfet/mosfet", r"[23]N\d{3,4}[A-Z]?", True),
    ("JIS transistor", "bjt", r"2S[ABCD]\d{2,4}[A-Z]{0,2}", True),
    ("JIS FET", "jfet/mosfet", r"2S[JK]\d{2,4}[A-Z]{0,3}", True),
    ("Pro Electron transistor", "bjt", r"B[CDFLSUX][A-Z]?\d{2,3}[A-Z]?(?:-\d{2})?", True),
    ("Pro Electron germanium", "bjt-ge/diode-ge", r"(?:A[CDFU][YZ]?1\d{2}|O[ACD]\d{2,3}|AA[YZ]?1\d{2}|GD\d{3}|GT\d{3})[A-Z]?", True),
    ("Pro Electron diode", "diode/zener", r"B(?:A[TVSWXY]|Z[XVTYDW]|Y[VWXT])\d{2,3}[A-Z]?(?:-?C?\d+V?\d*)?", True),
    ("power / small-signal transistor", "bjt", r"(?:MJ[EDLWFH]?(?=[1-9])|TIP|MPS[AUHLW]?|MPF|PN|ZTX|KS[ACPE]|KT[CAD]|NJW|NJL|FJ[ALP]|BU[XTVL]?|D4[45]H|SS[89]0|S[89]0)\d{2,5}[A-Z]{0,2}", True),
    ("JFET / MOSFET", "jfet/mosfet", r"(?:J\d{3}|PF\d{4}|BF\d{3}[ABC]?|U\d{3}|LS[KJ]\d{2,3}[A-C]?|IRF[A-Z]{0,2}\d{2,4}[A-Z]{0,2}|IRL[A-Z]{0,2}\d{2,4}[A-Z]?|BS\d{3}|BSS\d{2,3}|VN\d{2,4}[A-Z]{0,2}|VP\d{4}|ZV[NP]\d{4}[A-Z]?|"
                                     r"(?:ECX|ECF|ECW|ALF|BUZ|FQ[PAU]|ST[PWB]|IXT[HPQ]|FD[PBNS])\d{2,4}[A-Z\d]{0,6}|AO[TD]?\d{4}[A-Z]?)", False),
    ("valve, European", "tube", r"(?:E(?:ABC|AA|BC|BF|CC|CF|CH|CL|F|FF|L|LL|M|Y|Z)\d{2,3}[A-Z]?|(?:PCL|UCL|PCC|PCF|PL|UL|UF|UY|PY)\d{2,3}|[EG]Z\d{2}|KT\d{2,3}|CV\d{3,4}|6[PNH]\d{1,2}[PSCE])", True),
    ("op-amp / analogue IC", "opamp/ic", r"(?:TL0[6-8]\d[A-Z]{0,3}|TLE?2\d{3}[A-Z]{0,2}|TL[4-7]\d{2}[A-Z]?|TLC\d{3,4}[A-Z]?|NE55\d{2}[A-Z]{0,2}|NE5\d\d|SA5\d\d|LM\d{3,5}[A-Z]{0,3}|LF\d{3}[A-Z]?|LT\d{4}[A-Z]?|LTC\d{4}|LME\d{5}|OPA\d{3,4}[A-Z]?|OP\d{2,3}[A-Z]?|AD\d{3,4}[A-Z]{0,3}|"
                                        r"INA\d{3}|SSM\d{4}|THAT\d{3,4}[A-Z]?|RC\d{4}[A-Z]?|JRC\d{4}[A-Z]?|NJM\d{4}[A-Z]?|MC\d{4,5}[A-Z]?|UA\d{3,4}[A-Z]?|CA3\d{3}[A-Z]?|MAX\d{3,4}|ICL\d{4}|"
                                        r"TDA\d{4}[A-Z]?|TBA\d{3}[A-Z]?|TAA\d{3}[A-Z]?|TCA\d{3}[A-Z]?|SL\d{3,4}[A-Z]?|ZN4\d{2}[A-Z]?|LA\d{4}|UPC\d{3,4}[A-Z]?|BA\d{4,5}[A-Z]?|AN\d{3,4}|HA\d{4,5}|STK\d{3,4}[A-Z-]*\d*|TA\d{4}[A-Z]?|M5\d{3,4}[A-Z]?|XR\d{4}|SG\d{4}|UC\d{4}|"
                                        r"V[23]\d{3}[A-Z]?|CEM\d{4}|SSI\d{4}|AS\d{4}|IR\d{4}|DRV\d{3}|BUF\d{3}|DG\d{3}|ADG\d{3,4})", False),
    ("delay / BBD / digital audio", "digital-audio", r"(?:MN\d{4}|PT\d{4}[A-Z]?|SAD\d{3,4}|TDA\d{4}|R5\d{3}|BL\d{4}|V3\d{3}|FV-?1|CD\d{4}[A-Z]{0,3}|HEF4\d{3}[A-Z]{0,2}|CD4\d{3}[A-Z]{0,3}|74[A-Z]{1,4}\d{2,4}[A-Z]?|SN74[A-Z]{0,4}\d{2,4}[A-Z]?|SPN\d|ES5\d{4}|YM\d{4})", False),
    ("regulator", "regulator", r"(?:[ULM]{0,2}A?7[89][LM]?(?:05|06|08|09|10|12|15|18|20|24|33|52|62)[A-Z]{0,2}|LM[123]17[A-Z]{0,3}|LM[123]37[A-Z]{0,2}|LT108\d|LT308\d|TL43[01][A-Z]?|LD1\d{3}|L78\d\d|L79\d\d|LR8|TL783|VB408)", True),
    ("optocoupler / LDR", "opto", r"(?:VTL5C\d(?:/\d)?|NSL-?\d{2}[A-Z\d-]*|4N\d{2}|H11[A-Z]\d|CNY\d{2}|MOC\d{4}|PC8\d{2}|TLP\d{3}|LCR\d{4}|ORP\d{2}|VT\d{3,4}[A-Z]?|CLM\d{4})", False),
    # Modern analogue silicon. Everything above was read off magazines of 1960-1990 and stops there, so
    # eight TI application notes full of ADS7822 and ADS1286 yielded not one part. Each pattern here was
    # checked against TI's own catalogue — the 21,817 parts of the ti_datasheets census — and against
    # every name this corpus has already published: none of them matches a token that nothing vouches
    # for. ISO is spelled narrowly on purpose, because ISO9001 and ISO14001 are on half the documents.
    ("modern op-amp", "opamp/ic", r"(?:THS\d{4}|PGA\d{3,4}|LM[HPV]\d{3,4})[A-Z]{0,3}", False),
    ("data converter / reference / isolation", "ic",
     r"(?:ADS\d{3,4}[A-Z]?\d{0,2}|DAC\d{4,5}|ADC\d{4,5}|REF\d{2,5}|AMC\d{4}|MCP\d{4,5}|ISOW\d{4}|ISO[67]\d{3})[A-Z]{0,3}", False),
    ("modern power IC", "regulator", r"(?:TPS7A\d{2,4}|TPS\d{4,6}|UCC\d{4,5})[A-Z]{0,3}", False),
    ("modern audio IC", "ic-audio", r"TPA\d{3,4}[A-Z]{0,3}", False),
    ("valve, American", "tube", r"(?:\d{1,2}[A-HJ-MPS-Z][A-Z]{0,2}\d{1,2}(?:[A-Z]{1,3})?|5881|6550[A-C]?|7025|7027A?|7189A?|7199|7247|7355|7581A?|7591A?|7868|8417|6146[AB]?|300B|2A3|211|845|811A?|807|6080|6AS7G?A?|5751|5814A?|6189|6201|12BH7A?)", False),
]
FAMILIES = [(f, k, re.compile(rx), strict) for f, k, rx, strict in FAMILIES]

# Parts a manufacturer will still sell you, by their numbering. Two jobs: seeding the code-search
# discovery in schematics/listing.py, which asks GitHub which published designs use a part, and measuring
# a source's `era`.
#
# It has to be narrower than the families above, because one family regex covers both eras: `OPA\d{3,4}`
# matches OPA1612, which TI will ship tomorrow, and OPA37, a Burr-Brown part of the early eighties. So
# this asks for the number as well as the prefix, and the two-digit op-amps fall out.
#
# Counted on 2026-09-25 over the census: 5,787 of TI's 21,817 parts match, 1,411 of the 39,610 that have
# a SPICE model, 102 of Renesas's 14,240 and none at all of Frank Pocnet's 11,724 valves — 6,889 distinct
# parts, and a zero in the valve column, which is the shape you would expect if it measures what it says.
MODERN = re.compile(r"""^(?:
      OPA1\d{3} | OPA2\d{3} | OPA[3-9]\d{2,3}               # the op-amps still in the catalogue
    | THS\d{4} | LMH\d{3,4} | LMP\d{3,4} | LMV\d{3,4}
    | ADA4\d{3} | AD8\d{3}                                  # ADI's current analogue
    | ADS1\d{3} | ADS8\d{3} | DAC\d{4,5} | ADC\d{4,5}       # converters
    | LTC\d{3,4} | LT[13]\d{3}                              # Linear, now ADI
    | MAX[49]\d{3}
    | TPS\d{4,6} | TPS7A\d{2,4} | UCC\d{4,5}                # power
    | TPA\d{3,4} | PCM\d{4} | MUSES\d{4}                    # audio
    | INA\d{3,4} | PGA\d{3,4} | REF\d{2,4} | AMC\d{4} | ISOW?\d{4}
    | MCP\d{4} | LME\d{5} | NJM\d{4} | NJW\d{4}
  )[A-Z0-9-]{0,8}$""", re.X)

TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9/\-]{2,15})(?![A-Za-z0-9])")
BARE = re.compile(r"(?<![A-Za-z0-9.,/\-])(\d{3,5})(?![A-Za-z0-9.,/\-])")
VALUE = re.compile(r"^\d+[RKMUNPVWAHF]\d*$|^\d+(?:K|M|R|UF|NF|PF|MH|UH|V|VA|W|MA|HZ|KHZ|DB|MM|CM)\d*$|^\d{1,2}V\d$|^[RCLQDVTUJPMS]\d{1,3}[A-Z]?$|^(?:19|20)\d\d$"
                   r"|^\d+[RKM]\d*(?:M|W|SM|SW|UF|NF|PF|V|MW|KW|W\d)$|^\d+X\d+[A-Z]{0,2}$|^\d+[A-Z]?\d*(?:UF|NF|PF|MFD|OHM|OHMS|VAC|VDC|WATT|MEG)$|^[AD]C\d{2,3}V$"
                   r"|^(?:IC|TR|VR|RV|SW|TP|CN|CON|JP|PL|SK|TH|LP|FS|RL|RLA|RLY|LS|ZD|LED|VC|TC|FB|TS|XTAL)\d{1,3}[A-Z]?$|^VT\d{1,2}$")
NOISE = re.compile(r"^[5-7][A-HJ-L]\d{1,2}(?:-?[A-C])?$|^A[AB]\d{3,4}$|^AC[02-9]\d{2,3}$|^AC-?(?:4|10|15|30|50|100|120)(?:/\d)?[A-Z]{0,2}$|^\d+X[A-Z]|^PL[12]\d$")     # Fender circuit codes (5E3, 6G15, AA764, AB763, AC568 — but AC1xx is germanium), Vox AC30..AC100, "2xEL84"
FENDER_OK = re.compile(r"^(?:6[ABCDEFGHJKLS][A-Z]?\d|5[ARUVYZ]\d)")                                                  # real 6xx / 5xx valves start like this
GRADE = re.compile(r"^(?P<b>(?:2S[ABCDJK]\d{2,4}[A-Z]?|KT[AC]\d{4}|KS[AC]\d{3,4}))-?(?:GR|BL|O|Y|R|P|F|K|C|E|D|V)$")

REAL_X = re.compile(r"^(?:1X2|2X2|5X4|6X2|6X4|6X5|6X8)[A-Z]{0,3}$")             # the valves that do look like "6 x 4"
NOT_PARTS = {"RS232", "R5232", "RS422", "RS485", "PL259", "SO239", "RG58", "RG59", "RG213", "BNC", "IEEE488", "CV35", "RS423"}      # interfaces, connectors, cable
# real parts that look like a designator (VALUE would drop them)
DESIGNATOR_LIKE = {"J111", "J112", "J113", "J174", "J175", "J176", "J177", "J201", "J202", "J203", "J230", "J231", "J232", "J304", "J305", "J308",
                   "J309", "J310", "U309", "U310", "U401", "U402", "U403", "U404", "U405", "U406", "U430", "U431", "P1086", "P1087"}
# too short or too generic to trust on their own: need the dictionary, or the token alone in its block, or valve words around
LOOSE = re.compile(r"^(?:U\d{3}|J\d{3}|AD\d{3,4}[A-Z]{0,3}|AN\d{3,4}|LA\d{4}|BA\d{4,5}[A-Z]?|OP\d{2,3}[A-Z]?|PT\d{4}[A-Z]?|AS\d{4}|IR\d{4}|PC8\d{2}|VT\d{3,4}[A-Z]?|BS\d{3}|R5\d{3}|BL\d{4}|CD\d{4}|SL\d{3,4}[A-Z]?|TA\d{4}[A-Z]?|HA\d{4,5}|XR\d{4}|SG\d{4}|UC\d{4}|S[89]0\d{2}|PN\d{2,4}|CV\d{3,4})$")
NUMERIC_VALVE = re.compile(r"^\d{3,4}[A-C]?$")
VALVE_WORDS = re.compile(r"\b(?:valves?|tubes?|triodes?|pentodes?|tetrodes?|rectifiers?|heaters?|filaments?|anodes?|plates?|cathodes?|push[\s-]?pull|V\d{1,2}[AB]?)\b", re.I)
BARE_IC = {"741": "UA741", "709": "UA709", "301": "LM301", "308": "LM308", "555": "NE555", "5532": "NE5532", "5534": "NE5534", "4558": "RC4558",
           "4136": "RC4136", "3080": "CA3080", "3130": "CA3130", "3140": "CA3140", "13600": "LM13600", "13700": "LM13700", "386": "LM386", "3900": "LM3900"}

# "this is a circuit": designators and passive values standing alone in a short block (broadened from 03_magazine_pipeline/prune.py)
DESIG = re.compile(r"(?:[RCLQDVTPUJX]\d{1,3}[ABab]?|T[Rr]\d{1,3}|IC\d{1,3}[ABCDabcd]?|V[RT]\d{1,2}|RV\d{1,2}|SW?\d{1,2}[ABab]?|Re\d{1,2}|La\d{1,2}|LED\d{1,2}|ZD\d{1,2})")
UNIT = re.compile(r"(?:\d+(?:[.,]\d+)?\s?(?:[kKM]Ω?|Ω|[µμu]F?|[pn]F?|m?H|[µμ]H|MEG|meg|mfd|MFD|µµF|μμF)(?:/\d+\s?V)?|\d+[kKMRµμunp]\d+|\.\d{1,4})")

_PREFIX = r"(?:BC|BD|BF|BFY|BFX|BSX|BU|2N|1N|2S[ABCDJK]|LM|LF|TL|NE|TDA|TBA|CA|UA|MC|MN|OC|OA|AC|AD|AF|ECC|EL|EF|KT|MPSA?|TIP|ZTX|OPA?)"
SPLIT =re.compile(rf"(?<![A-Za-z0-9])({_PREFIX})[  ](\d{{2,5}}[A-Z]?)(?![A-Za-z0-9])")
NOT_SPLIT = re.compile(r"^(?:AC|AD|OP|EL|CA|MC|LF)$")          # "AC 240", "AD 1975", "OP 27" (opus), "EL 34" is fine but "EL 2" is not: these need >= 3 digits
LOOKALIKE = str.maketrans({"µ": "U", "μ": "U", "А": "A", "В": "B", "С": "C", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "Т": "T", "Х": "X",
                           "—": "-", "–": "-", "‐": "-", "‑": "-"})


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _load():
    known, rejected = {}, set()
    f = known_parts()
    if f.exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            known[r["name"]] = (r["part"], r["kind"])
    f = rejected_tokens()
    if f.exists():
        rejected = set(f.read_text(encoding="utf-8").split())
    return known, rejected


KNOWN, REJECTED = _load()          # norm(name or alias) -> (canonical part, kind) ; tokens an LLM pass judged not to be components


def _load_census():
    """Optional. Without it the extractor behaves exactly as it did before there was a census."""
    try:
        from parts_index.core.parts import census
        return census.load()
    except (ImportError, OSError, KeyError):
        return {}


CENSUS = _load_census()            # norm(part) -> (part as written, kind), from a list that had to be complete


def _load_verdicts():
    """Names the census lists that this corpus prints for something else. Judged once, with the evidence,
    and committed — see core.parts.judge. Optional: without the file the census speaks for itself."""
    try:
        from parts_index.core.parts.judge import load
        return {norm(name) for name, r in load().items() if r["verdict"] != "component"}
    except (ImportError, OSError, KeyError):
        return set()


NOT_HERE = _load_verdicts()        # the census knows the type; this corpus means something else by it
PENDING = "census, needs the page"        # a census part whose token shape is also something else
PENDING_SCHEME = "closed scheme, needs the page"   # a number inside a strict numbering scheme, 7805
WAITING = (PENDING, PENDING_SCHEME)                # settled by settle_census(), on different evidence


GENERIC_KINDS = {"ic", "semiconductor"}     # a model library says a part exists, not always what it is


def _kind_agrees(family_kind, census_kind):
    """'bjt/jfet/mosfet' agrees with 'bjt'. A census kind that only says "a semiconductor" agrees with any
    family but a valve, which is the distinction that matters: 7815 is a valve type and a regulator, and
    a semiconductor list must not be what settles a token the valve family claimed, or the other way."""
    fam, cen = set(family_kind.split("/")), set(census_kind.split("/"))
    if cen & GENERIC_KINDS or fam & GENERIC_KINDS:
        return ("tube" in fam) == ("tube" in cen)
    return bool(fam & cen)


def _ambiguous(tok):
    """A token the census knows, whose shape is also a resistor value, a designator, a circuit code or a
    bare number. 6V6 is a valve and 6.6 V; 1R5 is a valve and 1.5 ohm; 7805 is a regulator and a year."""
    return bool(VALUE.match(tok) or NOISE.match(tok) or NUMERIC_VALVE.match(tok))


# Which ambiguous tokens the census may argue about at all. Digit-letter-digit is how American and
# European valve names are built — 6V6, 1R5, 12BE6, 35W4 — and it is not how a designator or a value is
# built. Measured: without this line the census resurrected R10, R12, C10 and C12 as valve types on every
# valve schematic (they are real type names, and Frank lists them), along with 400, 800, 105 and the year
# 1960, which between them outnumbered every real part it recovered. A designator, a plain value and a
# bare number keep the behaviour they had before there was a census.
RESCUABLE = re.compile(r"^\d{1,2}[A-Z]{1,3}\d{1,2}[A-Z]{0,3}$|^(?!19|20)\d{4}[A-C]?$")
#                          6V6, 1R5, 12BE6, 35W4          5687, 6336A, 6528 — but never a year
#
# What is NOT here, deliberately: the lists of particular strings this file grew in one afternoon —
# heater voltages, placeholder model names, ordinals, bus names. Each came from one observed mistake and
# each missed the next one: four full passes over the corpus and the errors kept arriving, all of them
# the same shape (a real type number that in *this* corpus means something else). That is a judgement
# about a vocabulary, not a pattern, so it is made once per string, with the evidence, and committed in
# data/parts/verdicts.csv — see core.parts.judge. This module stays deterministic and testable.


def family_of(tok):
    return next(((f, k, strict) for f, k, rx, strict in FAMILIES if rx.fullmatch(tok)), None)


def canonical(tok):
    """EL34s -> EL34, MN-3005 -> MN3005, 2SA1943-O -> 2SA1943, IRF610-ND -> IRF610. None: not a part-like token."""
    t = tok.upper()
    t = re.sub(r"(?<=\d)S$", "", t) if re.fullmatch(r"[A-Z0-9]*\d[A-Z]{0,2}\dS|[A-Z]{1,4}\d{2,5}S", t) else t      # plurals: EL34s, 12AX7s, BC109s
    t = re.sub(r"^([A-Z]{2,5})-(?=\d)", r"\1", t)             # MN-3005, KSA-2240A, IRFP-240R — but not S-100, the bus
    t = re.sub(r"-(?:ND|T|TR|TP|AP|BU|G|E3|PBF)$", "", t)       # distributor / lead-free suffixes
    m = GRADE.match(t)
    if m:
        t = m.group("b")
    if "-" in t and not re.match(r"^(?:NSL|VTL|BZ|BC|LT|LM|AD|OPA|THAT|STK|FV)", t):
        return None                                             # J23-4, R59-60, PM-700: connector pins, ranges, product names
    return t


def fix_valve(t):
    if re.fullmatch(r"2A[XTUY]7[A-Z]{0,2}", t):
        return "1" + t
    if re.fullmatch(r"\d{1,2}[A-Z]{1,3}\d6[ABC]", t) and family_of(t[:-2] + "G" + t[-1]):      # 6L66C, 6V66T
        return t[:-2] + "G" + t[-1]
    if len(t) >= 5 and t[-1].isdigit() and norm(t[:-1]) in KNOWN and KNOWN[norm(t[:-1])][1] == "tube":
        return t[:-1]
    return None


def _valid(t):
    if norm(t) in KNOWN:
        return True
    f = family_of(t)
    return bool(f and f[2] and re.search(r"\d{3}", t) and re.fullmatch(r"(?:[123]N\d{3,4}[AB]?|2S[ABCDJK]\d{3,4}|[A-Z]{2,4}\d{3,4}[A-C]?)", t))


def fix_ocr(t):
    """Digit/letter confusions, only where a type number has digits, and only if the result is a type number. -> repaired token or None."""
    c = re.sub(r"^[IL](?=N\d{2,4}[A-Z]{0,2}$)", "1", t)                                 # IN4148, lN4004
    if c == t and (re.fullmatch(r"ZN\d{4}[A-Z]?", t) or (re.fullmatch(r"ZN\d{3}[A-Z]?", t) and not re.fullmatch(r"ZN4\d\d[A-Z]?", t))):
        c = "2" + t[1:]                                                                   # ZN3904 -> 2N3904 ; ZN414 / ZN424 are real Ferranti parts
    if c != t:
        return c if _valid(c) else None
    for n in range(1, 5):                                                                 # TLO72, NES534, 2N3O55, BC1O9
        m = re.fullmatch(r"([0-9OILSB]{2,5})([A-Z]{0,3})", t[n:])
        if m and re.fullmatch(r"[123]?[A-Z]+", t[:n]) and re.search(r"[OILSB]", m.group(1)) and re.search(r"\d", m.group(1)):
            c = t[:n] + m.group(1).translate(str.maketrans("OILSB", "01158")) + m.group(2)
            if _valid(c):
                return c
    return None


def expand_slash(tok):
    """BC107/8/9 -> BC107 BC108 BC109 ; BFY50/51/52 ; 2N3904/2N3906 ; a part that owns its slash (VTL5C3/2) stays whole."""
    if "/" not in tok:
        return [tok]
    if family_of(tok.upper()):
        return [tok]
    head, *rest = tok.split("/")
    m = re.fullmatch(r"(.*?)(\d+)([A-Za-z]?)", head)
    out = [head]
    for p in rest:
        if not p:
            continue
        if m and p.isdigit() and len(p) <= len(m.group(2)):
            out.append(m.group(1) + m.group(2)[: len(m.group(2)) - len(p)] + p)
        elif m and re.fullmatch(r"[A-Za-z]", p):
            out.append(m.group(1) + m.group(2) + p)                # BF245A/B/C
        else:
            out.append(p)
    return out


def base_part(t):
    """Package / grade / selection suffix folded away when what is left is still a type number: BC109C -> BC109, TL072CP -> TL072."""
    b = re.sub(r"(?<=\d)[A-Z]{1,3}$", "", t)
    if b != t and len(b) >= 4 and (norm(b) in KNOWN or family_of(b)):
        return b
    if b != t and len(b) == 3 and re.fullmatch(r"\d[A-Z]\d", b) and family_of(b):       # 6L6GC -> 6L6, 5U4GB -> 5U4, 6V6GT -> 6V6
        return b
    return t


def prepare(text):
    text = text.translate(LOOKALIKE)
    return SPLIT.sub(lambda m: m.group(0) if (NOT_SPLIT.match(m.group(1).upper()) and len(re.sub(r"\D", "", m.group(2))) < 3)
                     else m.group(1) + m.group(2), text)


REG_WORDS = re.compile(r"\b(?:regulators?|stabili[sz]ers?|IC\d{1,2}|REG\d?)\b", re.I)
# A data sheet names a whole family by putting an x where the digits vary: ADS126x, REF60xx. It is how
# the vendor writes "any of these", never a device you can buy.
WILDCARD = re.compile(r"[A-Z]{2,4}\d+X{1,2}")
# An evaluation module is a board named after the chip it carries. The chip is the part.
EVM = re.compile(r"(.+?)-?(?:EVM|EVAL|BOOST)$")         # ADS850-EVM is the board for ADS850, not ADS850-


def _judge(tok, text, pos, isolated, raw=""):
    """-> (part, family, kind, conf, fixed) or None."""
    fixed = False
    k = KNOWN.get(norm(tok)) or KNOWN.get(norm(base_part(tok)))
    if re.fullmatch(r"[AD]C\d{2,3}V", tok):                      # mains / supply voltages, not germanium transistors
        return None
    if tok in NOT_PARTS or (re.fullmatch(r"\d{1,2}X\d{1,2}[A-Z]{0,3}", tok) and not REAL_X.match(tok)):
        return None
    if WILDCARD.fullmatch(tok) and norm(tok) not in CENSUS and norm(tok) not in KNOWN:
        return None                                             # ADS126x is a family, not a device
    if (m := EVM.fullmatch(tok)) and norm(m.group(1)) in CENSUS:
        tok, fixed = m.group(1), True                           # ADS1298REVM is the board; ADS1298R is the part
    v = fix_valve(tok)
    if v:
        tok, fixed, k = v, True, KNOWN.get(norm(v)) or KNOWN.get(norm(base_part(v)))
    if re.fullmatch(r"S\d{1,2}[A-F]|A\d{1,3}", tok):                # S1a / S1d are switch sections, A13 a connector pin — even if a diode is called S1A
        return None
    if re.fullmatch(r"B[A-Z]\d{1,2}[A-Z]?", tok) and not k:           # BD23 5AA, BS1 4DJ: UK postcodes; Pro Electron numbers have three digits
        return None
    fam = family_of(tok)
    cen = None if norm(tok) in NOT_HERE else CENSUS.get(norm(tok))
    if tok in REJECTED and not k and not cen and not (fam and fam[2]):         # the LLM pass also threw away a few strict type numbers (AC187)
        return None
    if tok in DESIGNATOR_LIKE:
        if "-" in raw:
            return None                                             # J-304 is a jack
        return tok, "JFET / MOSFET", "jfet", "high" if isolated or k else "medium", False
    if REAL_X.match(tok):
        k = k or (tok, "tube")
    sure = (k and not re.fullmatch(r"\d+[RKM]\d+", tok)) or (fam and fam[2]) or re.fullmatch(r"4N[23]\d", tok)     # 1N4148, 2N3055, 4N25 look like "1n..." values to VALUE
    # The census speaks last, and only where nothing else has settled the token. It says which type
    # numbers exist, never which one this token is, so it stays quiet when it contradicts the family:
    # 7815 is a regulator here and a valve type in the census, and the regulator is what this page means.
    if cen is None and not k and not _ambiguous(tok) and norm(tok) not in NOT_HERE:
        cen = CENSUS.get(norm(base_part(tok)))                     # 6L6GCX: the census has the type, not the selection
    if cen and not k and not sure and len(tok) >= 3 and (not fam or _kind_agrees(fam[1], cen[1])):
        if _ambiguous(tok) and not sure:
            if RESCUABLE.match(tok):
                return tok, PENDING, cen[1], "low", fixed          # 6V6 on a page of resistor values is 6.6 V
        else:
            # Whatever its length. A census name is evidence that the type exists, never that this token
            # is it, so the page always has to agree. Measured on the second full export: MH40 and MC1-50
            # are real valves and they came out 228 and 225 times off one headphone site's index page,
            # which lists product models and carries no circuit at all — MC1-50 out of a raw "MC-150".
            # A family that already recognises the shape keeps its own verdict and is raised by the page
            # instead (settle_census); only a name nothing else knows waits here. The length floor above
            # is this branch's too: Frank's archive holds valves called 10, 50, E and CA, and without it
            # they came out on 1,129, 844, 633 and 1,121 documents.
            if fam:
                k = None
            elif len(tok) >= 4 or RESCUABLE.match(tok):
                return tok, PENDING, cen[1], "low", fixed
            # Three characters that are not shaped like a valve name: the census alone may not speak.
            # CH1 is channel 1, PA1 and LD1 and AD1 are designators, and Frank's archive holds a valve
            # called each of them. 1T4 and 3S4 are digit-letter-digit, which nothing else on a drawing is.
        # Three characters is never enough for the census to speak alone. AB1 and AB2 are real Philips
        # valves and "class AB1" is what a valve amplifier book says on every other page; S22 is a valve
        # and a section number; 1C4 and 1C6 are valves and they are also IC4 and IC6 with the I read as a
        # one, which is how they came out published beside a CA3130 on a page with no valve on it. A name
        # shaped like a valve — digit-letter-digit — may still come through, but only where the page
        # agrees; anything else needs its family or the dictionary.
    if len(tok) < 3 or (not sure and (VALUE.match(tok) or (NOISE.match(tok) and not FENDER_OK.match(tok)))):
        return None
    if NOISE.match(tok) and not FENDER_OK.match(tok) and not k:
        return None
    if not (re.search(r"\d", tok) and re.search(r"[A-Z]", tok)) and not (fam and tok.isdigit() or NUMERIC_VALVE.match(tok) and fam):
        return None
    if not fam and not k:
        r = fix_ocr(tok) if "-" not in raw else None             # MS-123 is a model name, not M5123
        if not r:
            return None
        tok, fam, k, fixed = r, family_of(r), KNOWN.get(norm(r)) or KNOWN.get(norm(base_part(r))), True
    if k and not fam:
        return k[0] if norm(k[0]) == norm(tok) else tok, "known name", k[1], "high", fixed
    family, kind, strict = fam
    if NUMERIC_VALVE.match(tok) and tok != "300B":               # 211, 807, 6550, 7815: any number could be one
        words = VALVE_WORDS if kind == "tube" else REG_WORDS
        if not isolated and not words.search(text[max(0, pos - 70): pos + 70]):
            return None
        if strict:
            # 7805, 7812, 7912: the regulator numbering is a closed scheme, so the number itself is not
            # the doubt — whether this page is about regulators is. Answer it where the answer is: in the
            # words beside it, or, for a label on a drawing, by asking the page. Until now these were
            # capped at medium and the gate publishes only high, so 7805 was in no document at all while
            # LM7805 was in 155.
            near = words.search(text[max(0, pos - 70): pos + 70])
            return (tok, family, kind, "high", fixed) if near else (tok, PENDING_SCHEME, kind, "low", fixed)
        return tok, family, kind, "medium" if k or kind != "tube" else "low", fixed
    if LOOSE.match(tok) and not k and not (cen and _kind_agrees(kind, cen[1])):
        return (tok, family, kind, "low", fixed) if isolated else None
    # A loose shape the census knows — AD817, AD8138ARZ by its base — is medium like any open scheme,
    # and settle_census raises it beside company. Until now it was low at best: AD817 was read on 16
    # pages and published on none, while AD817AN, which the dictionary happened to hold, was on 91.
    conf = "high" if k or strict else "medium"
    if family == "valve, American" and not k:
        if not re.fullmatch(r"\d{1,2}[A-Z]{1,3}\d{1,2}(?:G|GT|GTA|GTB|GA|GB|GC|A|B|C|W|WA|WB|WGT|Y)?|\d{3,4}[A-C]?", tok):
            return None                                             # 25A25K, 10DB6A-ish: the generic pattern is too generous
        if VALVE_WORDS.search(text[max(0, pos - 70): pos + 70]):
            conf = "medium"
        elif isolated:
            conf = "low"                                            # settle_valves() decides with the rest of the page
        else:
            return None
    if fixed and conf == "high":
        conf = "medium"
    return tok, family, kind if not k else k[1], conf, fixed


def extract(text, isolated=False, allow_bare=False, block=None, pending=False):
    """Hits in one string, in order, duplicates included (the caller counts). `isolated`: the string is a
    short label, not prose. `pending`: also return the census hits that need a page to settle them, which
    is what extract_page does — on its own a string cannot say whether 6V6 is a valve or 6.6 volts."""
    text = prepare(text)
    up = text.upper()
    hits = []
    for m in TOKEN.finditer(up):
        for piece in expand_slash(m.group(1).strip("-/")):
            tok = canonical(piece)
            if not tok:
                continue
            j = _judge(tok, up, m.start(), isolated, piece)
            if j:
                part, family, kind, conf, fixed = j
                if family in WAITING and not pending:
                    continue
                hits.append(Hit(part, base_part(part), piece, family, kind, conf, fixed, block))
    if allow_bare:
        for m in BARE.finditer(up):
            if m.group(1) in BARE_IC:
                part = BARE_IC[m.group(1)]
                hits.append(Hit(part, part, m.group(1), "bare number", "opamp/ic", "low", False, block))
    return hits


def _short(b):
    return len((b.get("text") or "").strip()) <= 14


def count_designators(blocks):
    return len({b["text"].strip() for b in blocks if _short(b) and DESIG.fullmatch(b["text"].strip())})


def count_values(blocks):
    return sum(1 for b in blocks if _short(b) and UNIT.fullmatch(b["text"].strip()))


def drop_designator_misreads(hits, labels):
    """0D3 next to D1 D2 D4 is the diode D3 with a stroke of its symbol read as 0; 1C2 next to IC1 / C-series is IC2. Both are real valves too."""
    letters = {}
    for t in labels:
        m = re.fullmatch(r"(I?[A-Z]{1,2})(\d{1,3})[A-Za-z]?", t.strip())
        if m:
            letters.setdefault(m.group(1), set()).add(m.group(2))
    present = {t.strip().upper() for t in labels}
    def misread(p):
        m = re.fullmatch(r"([0O1I])([A-Z])(\d{1,2})", p)
        if not m or (m.group(1) in "1I" and m.group(2) != "C"):
            return False
        fam = family_of(p)
        if fam and fam[2]:
            return False                        # OC44, OC71: a strict numbering scheme is not a stray stroke
        meant = ("IC" if m.group(1) in "1I" else m.group(2)) + m.group(3)
        if meant in present:
            return False                        # the designator it would be is already on the page in its own right
        sib = letters.get(m.group(2), set()) | (letters.get("IC", set()) if m.group(2) == "C" else set())
        return len(sib - {m.group(3)}) >= 2
    jacks = {t.strip().upper().replace("-", "") for t in labels if re.fullmatch(r"[JUP]-?\d{3,4}", t.strip().upper())} - DESIGNATOR_LIKE
    series = len(jacks) >= 2
    return [h for h in hits if not misread(h.part) and not (series and h.part in DESIGNATOR_LIKE and any(j[0] == h.part[0] for j in jacks))]


def settle_valves(hits, page_text):
    """An unknown American-valve label stays (medium) only on a page that is about valves: two known valves on it, or valve words."""
    pending = [h for h in hits if h.family == "valve, American" and h.conf == "low"]
    if not pending:
        return hits
    known_tubes = {h.base for h in hits if h.kind == "tube" and norm(h.base) in KNOWN}
    if len(known_tubes) >= 2 or VALVE_WORDS.search(page_text):
        return [h._replace(conf="medium") if h in pending else h for h in hits]
    return [h for h in hits if h not in pending]


KIND_WORDS = {"tube": VALVE_WORDS, "regulator": REG_WORDS}


CIRCUIT_DESIGNATORS = 5      # what `allow_bare` already calls "there is a circuit on this page"


def settle_census(hits, page_text, n_desig=0):
    """A census part whose token is also a value or a bare number is published only on a page that is
    about that kind of part: two other parts of the same kind on it, or the words for one.

    A token that is *only* digits asks more: a circuit on the page. Measured on 200 magazine issues —
    1007, 1010, 1048, 1049, 1110, 1138, 1221, 1229, 1231, a run of four-digit numbers off a reader
    service card in Radio-TV Experimenter, every one of them also a valve type in the census, on pages
    with no designator at all. 12BE6 and 5687 keep their letters and their evidence; a number alone
    keeps neither."""
    out = []
    for h in hits:
        if h.family not in WAITING:
            # A family read the shape and said medium, because its numbering scheme is open. If a list
            # that had to be complete also holds the part, and the page carries another of its kind,
            # that is three pieces of evidence and the gate can have it: MC33274 and MC33078 are one
            # vendor and one scheme, and only the one in the dictionary was ever published.
            known_as = norm(h.part) if norm(h.part) in CENSUS else norm(h.base)      # AD8138ARZ: the census has the type, not the package
            if h.conf == "medium" and known_as in CENSUS and _kind_agrees(h.kind, CENSUS[known_as][1]):
                company = {x.base for x in hits if x.base != h.base and _kind_agrees(x.kind, h.kind)
                           and (x.conf == "high" or x.family not in WAITING)}
                if company:
                    h = h._replace(conf="high")
            out.append(h)
            continue
        words = KIND_WORDS.get(h.kind)
        # What may corroborate depends on what the doubt is. A number inside a closed numbering scheme is
        # already vetted by its shape, so two of them make a page about that kind of part: 7805 beside
        # 7812 is not a coincidence. A census name has no such vetting, so it needs evidence that is not
        # itself waiting — otherwise the binary patterns 1010 and 1110 in a truth table, both of which are
        # valve type numbers, vouch for one another on a page with no valve on it at all.
        circuit = n_desig >= CIRCUIT_DESIGNATORS
        if h.family == PENDING and h.part.isdigit() and not circuit:
            continue
        # Company is counted by kind the same way the census is trusted by kind: a model library that
        # says only "a semiconductor" is company for another semiconductor, and never for a valve.
        settled = {x.base for x in hits if _kind_agrees(x.kind, h.kind) and x.family not in WAITING}
        if h.family == PENDING_SCHEME:
            enough = len({x.base for x in hits if _kind_agrees(x.kind, h.kind)}) >= 2   # 7805 beside 7812
        else:
            enough = len(settled) >= 2 or (circuit and len(settled) >= 1)     # only the census knows it
        if enough or (words and words.search(page_text)):
            out.append(h._replace(family="closed scheme" if h.family == PENDING_SCHEME else "census",
                                  conf="high"))
    return out


def drop_hex_dumps(hits):
    """Memory listings in the computing pages (1C00 1C80 1D20 ...) read as American valves: five or more on a page and none of them is one."""
    hexy = {h.part for h in hits if h.family == "valve, American" and re.fullmatch(r"[0-9A-F]{4}", h.part) and norm(h.base) not in KNOWN}
    return [h for h in hits if h.part not in hexy] if len(hexy) >= 5 else hits


# A name a designer typed into a component's value field, once nothing else has recognised it. Letters
# and digits both, and long enough not to be a designator by accident — the reader has already said this
# block is a value and not a reference, which is the part no pattern could tell: ADL5801 and R12 are the
# same shape. See `schematics/cad.py`.
DECLARED = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z][A-Z0-9][A-Z0-9/.-]{2,18}$")


def extract_page(page, min_conf=0.85):
    """One OCR page record -> hits with their block index. Bare IC numbers (741, 5534) only count on a page that has a circuit on it."""
    blocks = [b for b in page.get("blocks") or [] if (b.get("text") or "").strip()]
    allow_bare = count_designators(blocks) >= 5
    hits = []
    for i, b in enumerate(blocks):
        t = b["text"].strip()
        if b.get("conf", 1) < (0.90 if len(t) <= 4 else min_conf):
            continue
        found = extract(t, isolated=_short(b), allow_bare=allow_bare, block=i, pending=True)
        if (not found and b.get("field") == "value" and DECLARED.match(t.upper())
                and not WILDCARD.fullmatch(t.upper())):          # ADG44x and REF33xx are families, as ever
            # Nothing here knows this name and a design says it is one. ADL5801, SI5351C and RFSA3714 are
            # in no family and no catalogue, and LibreVNA puts all three on its board.
            up = t.upper()
            found = [Hit(up, base_part(up), t, "declared in a design", "ic", "high", False, i)]
        hits += found
    page_text = " ".join(b["text"] for b in blocks)
    hits = settle_census(hits, page_text, count_designators(blocks))
    hits = drop_designator_misreads(drop_hex_dumps(hits), [b["text"] for b in blocks if _short(b)])
    return settle_valves(hits, page_text)


def snapshot():
    """spice-library dictionary -> known_parts.csv + rejected_tokens.txt (library parts and aliases, parts an LLM pass judged real / not real)."""
    import json
    rows, rejected = {}, set()
    SPICE = staging("spice-library")                       # until the model library is ported
    lib = json.load(open(SPICE / "catalog/library.json"))
    for p in lib["parts"]:
        rows[norm(p["part"])] = (p["part"], p["kind"], "library")
    for a, t in lib["aliases"].items():
        kind = next((p["kind"] for p in lib["parts"] if p["part"] == t), "")
        if len(norm(a)) >= 4 and re.search(r"[A-Z]", norm(a)):
            rows.setdefault(norm(a), (t, kind, "library alias"))
    for r in csv.DictReader(open(SPICE / "research/audio-docs-parts/parts_classified.csv", encoding="utf-8")):
        if r["real"] in ("known", "yes") and r["conf"] != "low":
            p = r["base_part"] or r["part"]
            rows.setdefault(norm(p), (p, r["llm_kind"] or r["kind"], "audio docs"))
        elif r["real"] == "no":
            rejected.add(r["part"].upper())
    with open(known_parts(), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "part", "kind", "from"])
        w.writerows([n, *v] for n, v in sorted(rows.items()))
    rejected_tokens().write_text("\n".join(sorted(rejected)) + "\n", encoding="utf-8")
    print(f"{len(rows)} known names, {len(rejected)} rejected tokens")


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    else:
        for h in extract(" ".join(sys.argv[1:]) or sys.stdin.read()):
            print(h)
