"""Reading a schematic that was never a picture: KiCad, EAGLE, gEDA, LTspice and SPICE netlist sources.

Everything else in this corpus is a drawing. A scan needs OCR, a born-digital PDF needs its text layer
read, and either way a part number arrives as characters that might be wrong. A `.kicad_sch` or an EAGLE
`.sch` is the design itself, and the part number is in a field:

    (property "Value" "OPA1612" ...)                      KiCad, an S-expression
    <part name="U3" deviceset="THS4521" device="DGK"/>     EAGLE 6+, XML

So there is nothing to recognise and nothing to doubt. Measured on LibreVNA's board, the prose extractor
finds five parts in 924 KB and reading the XML by its own fields finds twenty-two.

What comes out is the page record `core.pagesio` already documents, one block per component, so the rest
of the pipeline does not know the difference: `extract_page` sees `U3` and `OPA1612` as the short isolated
labels it handles best, and index, summarise and export follow unchanged. A CAD file is not a new pillar,
it is a document that needs no OCR — like an HTML page, and for a better reason.

    read(path, "kicad_sch")     -> [{"page": 1, "how": "cad", "blocks": [...]}]

There are no coordinates. A box is what a reader of a scan needs to know where a word was; here the
design says what a thing is, and `extract_page` asks only for text and confidence.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from parts_index.core.parts import extractor as vocabulary

KINDS = ("kicad_sch", "kicad_legacy", "eagle_sch", "eagle_brd", "geda_sch", "ltspice_asc", "spice_net")
# Bumped when what a reader keeps or drops changes, so every design already read is read again — through
# the ledger, as rule 5 says, and not by deleting anything. 2: the dictionary guard, 1N4148, 2SC1815.
VERSION = "2"
MAX_PARTS = 20000            # a sane ceiling: the largest board here has 969

# KiCad writes one `(symbol ...)` per placed component, each carrying its Reference and its Value. The
# fields are in no fixed order, so they are read by name rather than by position.
KICAD_SYMBOL = re.compile(r"\(symbol\b", re.S)
KICAD_PROP = re.compile(r'\(property\s+"([^"]+)"\s+"([^"]*)"')
# A value that is the symbol's own name, a power flag or a component value, not a part number. KiCad uses
# these for passives, and a part number is what we are here for; `extract_page` would drop them anyway,
# but not before counting them as blocks nobody wanted to read.
NOT_A_PART = re.compile(r"(?i)^(?:[RCLD]_?small|[RCL]_[a-z_]*|gnd|earth|vcc|vdd|vee|vss|v?\+?\d+(?:\.\d+)?v"
                        r"|power|pwr_flag|conn_\w+|test_?point|mounting\w*|logo|fiducial|jumper|sw_\w+"
                        r"|~|\?|n/?[ac]|np|dnp|do_?not_?populate"
                        # gEDA names the kind of thing in `device=`, and for a passive that is all it says.
                        r"|resistor|polarized_capacitor|capacitor|inductor|coil|diode|led|zener"
                        r"|[np]pn|[np]mos|[np]fet|transistor|crystal|oscillator|switch|fuse|relay"
                        r"|transformer|battery|connector|header\d*|jack|socket|antenna|speaker|none"
                        r"|arduino\w*"
                        r"|input|output|include|generic\w*)$")
# ... and one that is a bare component value: 10k, 100nF, 4u7, 1M5, 1Meg. The digits after the unit are the
# fraction, so there are at most two of them: 1N4148 and 2N3904 are not a nanofarad and a nanohenry, which
# is what `\d*` made of them, and every JEDEC diode and transistor in every design with it.
A_VALUE = re.compile(r"(?i)^\d+[.,]?\d*\s*(?:meg|[kmrunμp]|[kmrunμp]?[fhΩohm]+|v|a|w|hz|khz|mhz|ppm|%)?\d{0,2}$")
# A supply rail written the way boards write it — 3V3, 5V0, +1V8, 12V — which is a valve's shape as well.
A_RAIL = re.compile(r"(?i)^[+-]?\d{1,2}v\d{0,2}$")
# A pin-header size, 2X10 — which is a valve's shape as well, so the dictionary is asked first.
A_HEADER = re.compile(r"(?i)^\d+x\d+(?:mm)?$")
# Nothing a designer typed with these in it is a part: an expression, a parameter, a quoted string.
AN_EXPRESSION = re.compile(r'[={}()"<>]')
# A valve as a valve is written, in capitals: 6V6, 5U4, 12AX7, 0A2. A rail and a rating share the shape.
VALVE_SHAPE = re.compile(r"\d{1,2}[A-Z]{1,2}\d{1,3}[A-Z]{0,3}")
# Reference designators, which say a component is there even when its value is a passive's.
DESIGNATOR = re.compile(r"(?i)^[a-z]{1,3}\d{1,4}[a-z]?$")
# Which designators mean a device worth a part number of its own. A designer who wrote U2 said "this is
# an integrated circuit"; one who wrote J3 said "this is a connector", and a connector's part number is
# real and useless here. Without this pairing LibreVNA offered PINHD-2X10, PJ-014D and BU-1420701851
# alongside its ADL5801. Passives are left out for the same reason: SRN5040 is an inductor.
ACTIVE_REF = re.compile(r"(?i)^(?:U|IC|A|Q|T|TR|VT|V|D|LED|ZD|Z|OK|ISO|M)\d")
# EAGLE ships drawing furniture as parts: a sheet frame, a pin header symbol.
FURNITURE = re.compile(r"(?i)^(?:pinhd|frame|a[0-9][a-z]?-loc|dinal|letter|logo)")


# A package is not a part. EAGLE libraries routinely name the deviceset after the case rather than the
# device — SOT23, SOD-123, SOIC-8, TO-252/DPAK, QFN-0.5MM — and the declared-value path in the extractor
# trusts what a designer typed, so it takes them. Measured over Kitspace's first 556 files: 35 of the 129
# names that came back were packages, a 27% error on that path.
#
# The package is the whole name, or the name's beginning. It was allowed anywhere in the name once, and
# that read ISO7721 as an SO-77, BSC010N04LS as an SC-01, 2SC1815 as an SC-18 and BGA616 as a BGA — 1,201
# of the names the census knows, dropped. A two-digit case number is two digits: SC-70 is a case and
# SC3300 is not, TSOP48 is a case and TSOP4838 is a receiver. TOP250 never matched and still does not.
PACKAGE = re.compile(r"(?i)^(?:SOT-?\d{2,4}|SOD-?\d{2,3}|SOIC-?\d{1,2}|SO-?\d{1,2}|T?SSOP-?\d{0,2}|MSOP-?\d{0,2}"
                     r"|[LTV]?QFP-?\d{0,3}|QFN-?\d{0,3}|BGA-?\d{0,4}|DFN-?\d{0,3}|DIP-?\d{1,2}|TO-?\d{2,3}[A-Z]{0,2}"
                     r"|D2?PAK|TSOP-?\d{1,2}|PLCC-?\d{0,2}|SC-?\d{2})(?!\d)(?:[-_/. ][A-Z0-9/._-]*)?$"
                     r"|^[\d.]+MM$|^LED\d+MM$")
# A package on the end of a part number — L7805SOT89, LM317-TO220, BC547TO92 — comes off, and the part
# stays. It was dropped whole before, and "L7805 arrives on its own from the boards that name it properly"
# was the excuse; it arrives from this board now.
PACKAGE_SUFFIX = re.compile(r"(?i)(?<=[A-Z0-9]{4})(?:[-_/ ]?(?:SOT-?\d{2,4}|SOD-?\d{2,3}|SOIC-?\d{1,2}|T?SSOP-?\d{0,2}"
                            r"|MSOP-?\d{0,2}|[LTV]?QFP-?\d{0,3}|QFN-?\d{0,3}|DFN-?\d{0,3}|DIP-?\d{1,2}|TO-?\d{2,3}[A-Z]{0,2}"
                            r"|D2?PAK|PLCC-?\d{0,2})|[-_/ ](?:SO-?\d{1,2}|SC-?\d{2}))$")


def strip_package(value: str) -> str:
    """The part number without the package a designer hung on the end of it, when there is one."""
    v = value.strip()
    if recognised(v):
        return v                                          # TSOP4838, SMAJ24A: whole names the census knows
    base = PACKAGE_SUFFIX.sub("", v)
    return base if base != v and re.search(r"\d", base) else v


def recognised(value: str) -> bool:
    """Whether something already vouches for this name: the dictionary, the census, or a closed family
    like JIS or JEDEC whose shape admits nothing else. Such a name is never filtered here, whatever it
    looks like — 6X4 looks like a header, 1N4148 like a nanofarad, 2SC1815 like a case — and it is what
    a SPICE model name has to turn into before a design is said to declare it."""
    n = vocabulary.norm(value)
    if not n or n in vocabulary.REJECTED:
        return False
    if n in vocabulary.KNOWN:
        return True
    # The census was read off lists that had to be complete, and it lists 100N, 4U7 and 10 among the
    # parts: a census name shaped like a rating vouches for nothing. 6V6 is one, and the valve rule in
    # `_wanted` is what keeps it.
    if n in vocabulary.CENSUS and (VALVE_SHAPE.fullmatch(value)
                                   or not (A_VALUE.match(value) or A_RAIL.match(value) or A_HEADER.match(value))):
        return True
    family = vocabulary.family_of(value.upper())
    return bool(family and family[2])


def canonical(value: str) -> str:
    """The name as the index will print it: the package off the end, a JIS short form written out, and
    the grade or selection suffix folded away when what is left is a part the vocabulary knows —
    2SC1815GR is a 2SC1815 of the GR gain rank, and C1815 is the same part as a Japanese author writes it."""
    v = strip_package(value)
    if vocabulary.WILDCARD.fullmatch(v.upper()):
        return v                                          # REF33xx names a family, and folding it would name a part
    m = JIS_SHORT.match(v) or JIS_DIODE_SHORT.match(v)
    if m:
        full = ("1" if JIS_DIODE_SHORT.match(v) else "2S") + v.upper()
        if recognised(full):
            return full                                   # C1815 is 2SC1815 even where the dictionary lists both
    # 2SA1015-Y, 2SC1815/GR: the rank behind a separator, which base_part does not see past.
    m = re.fullmatch(r"(.*\d)[-/ ]([A-Z]{1,2})", v.upper())
    if m and recognised(m.group(1)):
        return m.group(1)
    base = vocabulary.base_part(v.upper())
    if base != v.upper() and recognised(base):
        return base
    return v


def _wanted(value: str) -> bool:
    """Whether this value is worth a block of its own: a name, not a rating and not furniture.

    Asked in this order: what the vocabulary vouches for is kept whatever its shape; what is plainly not
    a name — an expression, a rail, a header size — goes; a valve's shape is kept, since a value written
    6V6 or 5U4 on a tube is one; then the ratings and the cases."""
    v = value.strip()
    if not v or len(v) > 40:
        return False
    if recognised(v):
        return True
    if AN_EXPRESSION.search(v) or v[0] in "+-" or A_RAIL.match(v) or A_HEADER.match(v):
        return False
    # 5U4, 0A2, 1R5: a valve nobody listed is still a valve. Written as a valve is written, in capitals;
    # 4u7 is a capacitor, and 1M5 and 2K2 are resistors even in capitals.
    if VALVE_SHAPE.fullmatch(v) and not re.match(r"\d+[KM]\d", v) and vocabulary.family_of(v):
        return True
    return not (NOT_A_PART.match(v) or A_VALUE.match(v) or PACKAGE.match(v))


def _blocks(pairs: list[tuple[str, str]]) -> list[dict]:
    """(reference, value) -> the blocks of one sheet, references first, each named once.

    A reference is its own block because a page with R1, C1 and U1 on it is a page with a circuit on it,
    and that is how `extract_page` decides whether to trust a bare number like 741.

    The two are told apart in the record, with `field`, because only this reader knows which is which and
    the difference decides everything downstream: ADL5801 and R12 are the same shape, and one of them is
    a part. A value block says "a designer typed this name here", which is why `extract_page` may take it
    without a family or a dictionary behind it.
    """
    refs = [(p[0].strip(), "ref") for p in pairs if DESIGNATOR.match(p[0].strip())]
    values = []
    for pair in pairs:
        ref, value, declared = (pair + (None,))[:3]       # a reader may say itself whether a design vouches
        v = canonical(value)
        if not _wanted(v) or FURNITURE.match(v):
            continue
        # A value on an active reference is a part this index is for; any other value is still written
        # down, but only counts if something already recognises it — TL431 on a D reference is real.
        if declared is None:
            declared = bool(ACTIVE_REF.match(ref.strip()))
        # What no design vouches for is still offered to the extractor, whose families may know it —
        # but only if it has the shape of a type number at all. SCHEMATIC1_RV1 is PSpice naming a
        # hierarchy and DDEF is an author naming nothing, and the extractor once made SCHEMATIC1 a part.
        if not declared and (not re.search(r"\d", v) or "_" in v):
            continue
        values.append((v, "value" if declared else ""))
    seen: set[str] = set()
    out = []
    for text, field in refs + values:
        if text not in seen:
            seen.add(text)
            out.append({"text": text, "conf": 1.0, **({"field": field} if field else {})})
    return out


def read_kicad(text: str) -> list[tuple[str, str]]:
    """Every placed component of a .kicad_sch, as (reference, value).

    The file is an S-expression and this does not parse it: a symbol's properties are read from the span
    between one `(symbol` and the next, which is enough because a property never appears outside one.
    """
    starts = [m.start() for m in KICAD_SYMBOL.finditer(text)]
    out = []
    for i, start in enumerate(starts[:MAX_PARTS]):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        props = dict(KICAD_PROP.findall(text[start:end]))
        ref, value = props.get("Reference", ""), props.get("Value", "")
        # An MPN, when the designer wrote one, is the part number itself and beats the Value.
        for field in ("MPN", "Mpn", "mpn", "Manufacturer_Part_Number", "LCSC", "PartNumber"):
            if props.get(field):
                value = props[field]
                break
        if ref or value:
            out.append((ref, value))
    return out


def read_eagle(text: str) -> list[tuple[str, str]]:
    """Every placed part of an EAGLE .sch, as (reference, deviceset).

    `deviceset` is the part number — `<part name="U2" deviceset="THS4521" device="DGK"/>` — and `device`
    is the package, which belongs to the footprint and not to the vocabulary.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for part in root.iter("part"):
        name, ds = part.get("name", ""), part.get("deviceset", "")
        if name or ds:
            out.append((name, ds))
        if len(out) >= MAX_PARTS:
            break
    return out


def read_eagle_brd(text: str) -> list[tuple[str, str]]:
    """Every placed component of an EAGLE board, as (reference, value).

    A board is a layout and not a circuit, so it is second best: it says which parts are on the thing
    and nothing about how they are wired. It is taken for the boards whose schematic was never published
    — 653 of SparkFun and Adafruit's 2,059 `.brd` files have no `.sch` beside them, and without this
    they are invisible. `package` is deliberately unread: that is the case, not the device.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter("element"):
        name, value = el.get("name", ""), el.get("value", "")
        if name or value:
            out.append((name, value))
        if len(out) >= MAX_PARTS:
            break
    return out


# Legacy KiCad, before the S-expressions: a component is a $Comp block, `F 0` holds its reference and
# `F 1` its value. A .sch is EAGLE's extension too, which is why `kind_of` reads the file rather than
# trusting the name — tdstat's TDstatv2.sch is this.
LEGACY_COMP = re.compile(r"^\$Comp$(.*?)^\$EndComp$", re.M | re.S)
LEGACY_FIELD = re.compile(r'^F\s+(\d+)\s+"([^"]*)"', re.M)


def read_kicad_legacy(text: str) -> list[tuple[str, str]]:
    """Every component of a pre-6 KiCad .sch, as (reference, value)."""
    out = []
    for body in (m.group(1) for m in LEGACY_COMP.finditer(text)):
        fields = dict(LEGACY_FIELD.findall(body))
        ref, value = fields.get("0", ""), fields.get("1", "")
        if ref or value:
            out.append((ref, value))
        if len(out) >= MAX_PARTS:
            break
    return out


# gEDA/gschem, the third text format and the one nobody remembers. A component is a `C` line naming its
# symbol, optionally followed by an embedded copy of that symbol in `[ ... ]`, and then by the instance's
# own attributes in `{ ... }`. The embedded symbol carries attributes too — its pins each have their own
# block, and the symbol itself usually declares a `device=` — so the instance's attributes are read only
# after the embedded copy has been cut out, or a resistor's symbol answers for the part beside it.
GEDA_COMP = re.compile(r"^C\s+-?\d+\s+-?\d+\s+\d+\s+\d+\s+\d+\s+(\S+)", re.M)
GEDA_ATTR = re.compile(r"^([a-z_]+)=(.*)$", re.M)


def _no_embedded(span: str) -> str:
    """One component's text with the embedded symbol definition removed. `[` and `]` sit alone on their
    own lines, which is what makes this safe to do by line rather than by nesting."""
    out, inside = [], False
    for line in span.splitlines():
        if line.strip() == "[":
            inside = True
        elif line.strip() == "]":
            inside = False
        elif not inside:
            out.append(line)
    return "\n".join(out)


def read_geda(text: str) -> list[tuple[str, str]]:
    """Every placed component of a gEDA schematic, as (refdes, device).

    `device` is what the part is — ATMEGA32U4, MCP1700 — and `value` is the fallback for the symbols that
    leave it empty. The symbol's own file name is deliberately not used: gEDA's stock library calls them
    resistor-1.sym and opamp-1.sym, which name a kind and not a part.
    """
    found = [(m.start(), m.group(1)) for m in GEDA_COMP.finditer(text)]
    out = []
    for i, (start, _symbol) in enumerate(found[:MAX_PARTS]):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        attrs = dict(GEDA_ATTR.findall(_no_embedded(text[start:end])))
        ref, value = attrs.get("refdes", ""), attrs.get("device") or attrs.get("value") or ""
        if ref or value:
            out.append((ref, value))
    return out


# LTspice, the simulator most of this corpus's authors draw in. An .asc names each placed symbol and then
# its attributes on the lines after it:
#
#     SYMBOL npn 1264 368 R0              the symbol, which for a generic device says only what kind
#     SYMATTR InstName Q1
#     SYMATTR Value 2SC1815               the model: here is the part number
#     SYMBOL Opamps\\LT1001 ...           a vendor symbol names the part itself
#
# LTspice XVII and later save as UTF-16 when a file holds a character outside Latin-1, which a Japanese
# comment makes likely; `_text` undoes that. `.model` and `.subckt` lines in a TEXT directive name the
# devices a sheet defines for itself — 2SK170 written out by hand — and are read as values too.
ASC_SYMBOL = re.compile(r"^SYMBOL\s+(\S+)", re.M)
ASC_ATTR = re.compile(r"^SYMATTR\s+(\w+)\s*(.*)$", re.M)
# A directive sits in a TEXT line after `!`: `TEXT 48 400 Left 2 !.model 2SK170 NJF(...)`, and one TEXT may
# hold several, joined by a literal `\n`.
ASC_MODEL = re.compile(r"(?i)(?:!|\\n)\s*\.(?:model|subckt)\s+([A-Za-z0-9_.+-]+)")
SPICE_MODEL = re.compile(r"(?im)^[!*;\s]*\.(?:model|subckt)\s+([A-Za-z0-9_.+-]+)")
# The symbols LTspice ships for a kind of thing rather than a part. A source's value is a waveform and a
# passive's a rating, and neither is ever a part, so their value is not read at all; a device's value is
# its model, which is read as one. Anything else without a digit in its name is a generic too — `and`,
# `dflop`, `schmitt` — since a vendor symbol always carries a type number.
ASC_SOURCE = re.compile(r"(?i)^(?:voltage|current|bv|bi|e2?|f|g2?|h|load2?|cell|battery|signal|"
                        r"modulate2?|sample|phidet)$")
ASC_PASSIVE = re.compile(r"(?i)^(?:res2?|cap|polcap|ind2?|ferritebead2?|european(?:resistor|cap|polcap|inductor)|"
                         r"varistor|tline|ltline|xtal|sw|csw|fuse)$")
ASC_DEVICE = re.compile(r"(?i)^(?:npn\d?|pnp\d?|nmos\d?|pmos\d?|njf|pjf|mesfet|diode|zener|schottky|"
                        r"varactor|led|opamp2?|universalopamp2?|tl)$")
ASC_GENERIC = re.compile(r"(?i)^(?:and|or|xor|inv|buf1?|dflop|srflop|schmitt|schmtbuf|schmtinv|diffschmt\w*|"
                         r"counter|dac|adc|sine|mesfet)$")
# The one-letter prefix a model name carries for the kind of device it is — Q2N3904, D1N4148, QC1815,
# JK369 — and the JIS short forms a Japanese author writes, C1815 for 2SC1815 and S1588 for 1S1588.
JIS_SHORT = re.compile(r"(?i)^([ABCDFGHJK])(\d{2,4}[A-Z]{0,2})$")
JIS_DIODE_SHORT = re.compile(r"(?i)^S(\d{3,4}[A-Z]{0,2})$")
PART_SHAPE = re.compile(r"(?i)^(?:[A-Z]{1,4}\d{2,5}[A-Z0-9]{0,4}|\d[A-Z]{1,2}\d{2,5}[A-Z]{0,3})$")


def model_name(kind: str, name: str) -> tuple[str, bool]:
    """The part a SPICE model name stands for, and whether something vouches for it.

    A model is named by its author. In OrCAD's own libraries the name is the part number behind a letter
    for the device — Q2N3904, D1N4148 — and in a Toragi author's it is the JIS short form behind the same
    letter, QC1815 for 2SC1815, JK369 for 2SK369; and a good many are QX, DDEF or QNORM, which stand for
    nothing. So the candidates are tried against the vocabulary, longest reading first, and a name nothing
    vouches for is returned as it was and marked undeclared: a later reader may still know it, but no
    design is said to have declared it."""
    name = name.strip()
    candidates = [name]
    if len(name) > 3 and kind and name[0].upper() == kind.upper() and re.search(r"\d", name[1:]):
        candidates.append(name[1:])
    for c in list(candidates):
        m = JIS_SHORT.match(c)
        if m:
            candidates.append(f"2S{c.upper()}")
        m = JIS_DIODE_SHORT.match(c)
        if m:
            candidates.append(f"1{c.upper()}")
    # The reading that says most goes first: 2SC1815 before C1815, 2N3904 before Q2N3904 — the census
    # lists model names too, and Q2N3904 is one, but the part is 2N3904.
    for c in reversed(candidates):
        if recognised(c):
            return c, True
    # Nothing vouches. What is behind the letter is still the better reading when it has a type number's
    # shape — QBFG425W is an author's model of a BFG425W — and it goes on undeclared for the extractor.
    if len(candidates) > 1 and PART_SHAPE.match(candidates[1]):
        return candidates[1], False
    return name, False


def read_ltspice(text: str) -> list[tuple]:
    """Every placed symbol of an LTspice .asc, as (instance name, part, declared), then the models it
    defines. `declared` is True for a vendor's own symbol — LT1001, AD8065 — and for a model the
    vocabulary knows; a model nothing knows is written down undeclared."""
    starts = [(m.start(), m.group(1)) for m in ASC_SYMBOL.finditer(text)]
    out: list[tuple] = []
    for i, (start, symbol) in enumerate(starts[:MAX_PARTS]):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        attrs = dict((k, v.strip()) for k, v in ASC_ATTR.findall(text[start:end]))
        name = symbol.replace("\\", "/").rsplit("/", 1)[-1]
        ref = attrs.get("InstName", "")
        if ASC_SOURCE.match(name) or ASC_PASSIVE.match(name) or ASC_GENERIC.match(name):
            value, declared = "", False
        elif ASC_DEVICE.match(name) or not re.search(r"\d", name):
            value, declared = model_name(ref[:1], attrs.get("Value") or attrs.get("SpiceModel") or "")
        else:
            # A symbol with a type number in its name is a vendor's, or an author's for a part — Opamps/LT1001,
            # or a QC1815A drawn by hand — and vouches for it either way, read as a model name is read.
            value, declared = model_name(ref[:1], attrs.get("Value") or name)
            declared = True
        if ref or value:
            out.append((ref, value, declared))
    out += [("", m, recognised(m)) for m in ASC_MODEL.findall(text)]
    return out


# A SPICE netlist, as PSpice writes one beside an OrCAD design (.net) or as a hand-written deck (.cir):
#
#     Q_Q1         N05113 N04583 N06304 QC1815         PSpice: the part's type, "_", its reference
#     X_U1A        N1 N2 N3 N4 N5 TL072 PARAMS: ...     a subcircuit: its name is the last word
#     D1 1 0 DNORM                                     a deck: no prefix
#
# For a device that takes a model (Q, D, J, M, Z, X) the model is the last word that is not a parameter.
# A passive's value is a rating, and its reference is all that is kept of it.
NET_LINE = re.compile(r"^([A-Za-z])(?:_([A-Za-z]{1,3}\w*)|(\w*))\s+(.+)$")
MODELLED = set("QDJMZXU")


def read_spice(text: str) -> list[tuple]:
    """Every element of a SPICE netlist, as (reference, model, declared), then the models it defines."""
    out: list[tuple] = []
    lines = text.splitlines()
    if lines and not lines[0].lstrip().startswith(("*", ".")):
        lines = lines[1:]                                  # a deck's first line is its title, whatever it says
    for line in lines:
        if not line or line[0] in "*.+;":
            continue
        m = NET_LINE.match(line.strip())
        if not m:
            continue
        kind, prefixed, bare, rest = m.groups()
        ref = prefixed if prefixed is not None else kind + (bare or "")
        words = [w for w in rest.split("PARAMS:")[0].split() if "=" not in w]
        value, declared = model_name(kind, words[-1]) if kind.upper() in MODELLED and len(words) >= 2 else ("", False)
        out.append((ref, value, declared))
        if len(out) >= MAX_PARTS:
            break
    out += [("", m, recognised(m)) for m in SPICE_MODEL.findall(text)]
    return out


def _text(data: bytes) -> str:
    """The text of a design file, whatever it was saved as: UTF-16 from LTspice, CP932 from a Japanese
    Windows, UTF-8 from everything else."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(data) > 3 and data[1:4:2] == b"\x00\x00"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp932", "replace")


# How a netlist is recognised without its name: PSpice heads one with `* source`, a deck ends with .END,
# and either way most lines are an element with a reference and at least two nodes.
NET_ELEMENT = re.compile(r"(?m)^[RCLQDJMXVIKEFGHSTUZ](?:_\w+|\w*)\s+\S+\s+\S+")


def looks_like_netlist(text: str) -> bool:
    head = text[:20000]
    elements = len(NET_ELEMENT.findall(head))
    return (head.lstrip().lower().startswith("* source") and elements >= 1) or \
        (elements >= 2 and re.search(r"(?im)^\s*\.(end|model|subckt|tran|ac|dc|op|probe|lib|inc)\b", head) is not None)


def kind_of(text: str) -> str:
    """Which of the three this is, read from the file. `.sch` belongs to EAGLE and to old KiCad both."""
    head = text[:4000].lstrip()
    if head.startswith("(kicad_sch") or "(kicad_sch " in head[:200]:
        return "kicad_sch"
    if head.startswith("EESchema Schematic File"):
        return "kicad_legacy"
    if "<eagle" in head[:2000]:
        # One file format, two documents. `<board>` is a layout and `<schematic>` a circuit, and they
        # are read by different functions because a board has no wires to speak of.
        return "eagle_brd" if "<board" in text[:20000] else "eagle_sch"
    # `v 20121123 2` and then a page of C, P and T lines. The Bus Pirate's schematic is this, and so are
    # a good many open-hardware projects of about 2010.
    if re.match(r"v\s+\d{8}\s+\d", head) and "\nC " in text[:20000]:
        return "geda_sch"
    if re.match(r"Version\s+4", head) and "\nSHEET " in text[:2000]:
        return "ltspice_asc"
    if looks_like_netlist(text):
        return "spice_net"
    return ""


READERS = {"kicad_sch": read_kicad, "kicad_legacy": read_kicad_legacy, "eagle_sch": read_eagle,
           "eagle_brd": read_eagle_brd, "geda_sch": read_geda, "ltspice_asc": read_ltspice,
           "spice_net": read_spice}


def read(path, kind: str) -> list[dict]:
    """-> one page record, in the shape core.pagesio documents. A CAD file is read as a single sheet:
    a hierarchical design is several files, and each arrives here on its own."""
    if hasattr(path, "read_bytes"):
        text = _text(path.read_bytes())
    elif hasattr(path, "read_text"):
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        text = str(path)
    reader = READERS.get(kind) or READERS.get(kind_of(text))
    pairs = reader(text) if reader else []
    return [{"page": 1, "w": 0, "h": 0, "how": "cad", "blocks": _blocks(pairs)}]
