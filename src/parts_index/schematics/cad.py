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

KINDS = ("kicad_sch", "kicad_legacy", "eagle_sch", "eagle_brd", "geda_sch", "ltspice_asc", "spice_net")
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
                        r"|~|\?|n/?[ac]|dnp|do_?not_?populate"
                        # gEDA names the kind of thing in `device=`, and for a passive that is all it says.
                        r"|resistor|polarized_capacitor|capacitor|inductor|coil|diode|led|zener"
                        r"|[np]pn|[np]mos|[np]fet|transistor|crystal|oscillator|switch|fuse|relay"
                        r"|transformer|battery|connector|header\d*|jack|socket|antenna|speaker|none"
                        r"|arduino\w*"
                        r"|input|output|include|generic\w*)$")
# ... and one that is a bare component value: 10k, 100nF, 4u7, 1M5.
A_VALUE = re.compile(r"(?i)^\d+[.,]?\d*\s*(?:[kmrunμp]|[kmrunμp]?[fhΩohm]+|v|a|w|hz|khz|mhz|ppm|%)?\d*$")
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
# names that came back were packages, a 27% error on that path. Rule 4 settles it, and the cost is small:
# L7805SOT89 goes with them, and L7805 arrives on its own from the boards that name it properly.
#
# SMA is deliberately absent. SMAJ24A and SMAJ60A are Littelfuse TVS diodes, real parts whose names begin
# with a package.
# A JIS transistor or FET — 2SA1015, 2SC1815, 2SK170 — contains `SC` and two digits and is not an SC-70.
PACKAGE = re.compile(r"(?i)^(?!2S[ABCDJK]\d)[A-Z0-9/_-]*?"
                     r"(?:SOT-?\d{2,4}|SOD-?\d{3}|SOIC-?\d{1,2}|SO-?\d{1,2}|SSOP-?\d{1,2}|TSSOP-?\d{1,2}"
                     r"|MSOP-?\d{1,2}|[LTV]?QFP|QFN|BGA|DFN|DIP-?\d{1,2}|TO-?\d{2,3}|DPAK|TSOP|PLCC"
                     r"|SC-?\d{2})[A-Z0-9/._-]*$"
                     r"|^\d+X\d+(?:MM)?$|^[\d.]+MM$|^LED\d+MM$")


def _wanted(value: str) -> bool:
    """Whether this value is worth a block of its own: a name, not a rating and not furniture."""
    v = value.strip()
    return (bool(v) and len(v) <= 40 and not NOT_A_PART.match(v) and not A_VALUE.match(v)
            and not PACKAGE.match(v))


def _blocks(pairs: list[tuple[str, str]]) -> list[dict]:
    """(reference, value) -> the blocks of one sheet, references first, each named once.

    A reference is its own block because a page with R1, C1 and U1 on it is a page with a circuit on it,
    and that is how `extract_page` decides whether to trust a bare number like 741.

    The two are told apart in the record, with `field`, because only this reader knows which is which and
    the difference decides everything downstream: ADL5801 and R12 are the same shape, and one of them is
    a part. A value block says "a designer typed this name here", which is why `extract_page` may take it
    without a family or a dictionary behind it.
    """
    refs = [(r.strip(), "ref") for r, _ in pairs if DESIGNATOR.match(r.strip())]
    values = []
    for ref, value in pairs:
        v = value.strip()
        if not _wanted(v) or FURNITURE.match(v):
            continue
        # A value on an active reference is a part this index is for; any other value is still written
        # down, but only counts if something already recognises it — TL431 on a D reference is real.
        values.append((v, "value" if ACTIVE_REF.match(ref.strip()) else ""))
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
# The symbols LTspice ships for a kind of thing rather than a part: their name is never a part number.
ASC_GENERIC = re.compile(r"(?i)^(?:res|res2|cap|polcap|ind|ind2|voltage|current|bv|bi|e|e2|f|g|g2|h|"
                         r"npn\d?|pnp\d?|nmos\d?|pmos\d?|njf|pjf|diode|zener|schottky|varactor|led|"
                         r"opamp\d?|universalopamp\d?|sw|csw|tline|ltline|xtal|lm\d{0,3}|"
                         r"cell|battery|load\d?|ferritebead\d?|mesfet|tl)$")


def read_ltspice(text: str) -> list[tuple[str, str]]:
    """Every placed symbol of an LTspice .asc, as (instance name, part), then the models it defines."""
    starts = [(m.start(), m.group(1)) for m in ASC_SYMBOL.finditer(text)]
    out = []
    for i, (start, symbol) in enumerate(starts[:MAX_PARTS]):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        attrs = dict((k, v.strip()) for k, v in ASC_ATTR.findall(text[start:end]))
        name = symbol.replace("\\", "/").rsplit("/", 1)[-1]
        value = attrs.get("Value") or attrs.get("SpiceModel") or ""
        if not value and not ASC_GENERIC.match(name):
            value = name                                   # a vendor symbol: LT1001, AD8065, TL431
        ref = attrs.get("InstName", "")
        if ref or value:
            out.append((ref, value))
    out += [("", m) for m in ASC_MODEL.findall(text)]
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


def read_spice(text: str) -> list[tuple[str, str]]:
    """Every element of a SPICE netlist, as (reference, model), then the models it defines."""
    out = []
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
        value = words[-1] if kind.upper() in MODELLED and len(words) >= 2 else ""
        out.append((ref, value))
        if len(out) >= MAX_PARTS:
            break
    out += [("", m) for m in SPICE_MODEL.findall(text)]
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
