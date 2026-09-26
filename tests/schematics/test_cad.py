"""Reading a schematic that was never a picture: what a design declares, and what it only draws."""
from __future__ import annotations

from parts_index.core import parts
from parts_index.schematics import cad

KICAD = """(kicad_sch (version 20211123)
  (symbol (lib_id "Amplifier_Operational:OPA192") (at 100 100 0)
    (property "Reference" "U1" (at 0 0 0))
    (property "Value" "OPA192" (at 0 2 0)))
  (symbol (lib_id "Device:R") (at 120 100 0)
    (property "Reference" "R1" (at 0 0 0))
    (property "Value" "10k" (at 0 2 0)))
  (symbol (lib_id "Device:C_Small") (at 130 100 0)
    (property "Reference" "C1" (at 0 0 0))
    (property "Value" "C_Small" (at 0 2 0)))
  (symbol (lib_id "power:GND") (at 140 100 0)
    (property "Reference" "#PWR01" (at 0 0 0))
    (property "Value" "GND" (at 0 2 0)))
  (symbol (lib_id "Analog:ADG1419") (at 150 100 0)
    (property "Reference" "U2" (at 0 0 0))
    (property "Value" "ADG1419" (at 0 2 0))
    (property "MPN" "ADG1419BRMZ" (at 0 4 0)))
)"""

EAGLE = """<?xml version="1.0" encoding="utf-8"?>
<eagle version="9.6.2"><drawing><schematic>
  <parts>
    <part name="U2" library="VNA" deviceset="ADL5801" device="CP"/>
    <part name="U7" library="VNA" deviceset="THS4521IDGKR" device=""/>
    <part name="R14" library="rcl" deviceset="R-EU_" device="R0402" value="4k7"/>
    <part name="J3" library="con" deviceset="PJ-014D" device=""/>
    <part name="FRAME1" library="frames" deviceset="A3L-LOC" device=""/>
    <part name="X1" library="con" deviceset="PINHD-2X10" device=""/>
  </parts>
</schematic></drawing></eagle>"""

LEGACY = """EESchema Schematic File Version 2
LIBS:power
$Comp
L AD8629 U3
U 1 1 541171DA
P 5000 3000
F 0 "U3" H 5000 895 30  0001 C CNN
F 1 "AD8629" H 5000 980 30  0000 C CNN
$EndComp
$Comp
L PWR_FLAG #FLG01
U 1 1 541171DB
P 11000 800
F 0 "#FLG01" H 11000 895 30  0001 C CNN
F 1 "PWR_FLAG" H 11000 980 30  0000 C CNN
$EndComp
$EndSCHEMATC
"""


def page_of(text: str):
    return cad.read(Text(text), "")[0]


class Text:
    """A file, without one."""

    def __init__(self, text):
        self.text = text

    def read_text(self, **kw):
        return self.text


def test_each_format_is_recognised_from_the_file_not_the_name():
    """A .sch belongs to EAGLE and to KiCad before version 6 both, and tdstat's is the second."""
    assert cad.kind_of(KICAD) == "kicad_sch"
    assert cad.kind_of(EAGLE) == "eagle_sch"
    assert cad.kind_of(LEGACY) == "kicad_legacy"
    assert cad.kind_of("%PDF-1.4") == ""


def test_a_kicad_value_is_a_part_and_a_resistor_is_not():
    found = {h.part for h in parts.extract_page(page_of(KICAD))}
    assert "OPA192" in found
    assert "ADG1419BRMZ" in found or "ADG1419" in found      # the MPN field beats the Value
    assert not {"10K", "C_SMALL", "GND"} & found


def test_an_eagle_deviceset_is_the_part_and_the_package_is_not():
    page = page_of(EAGLE)
    found = {h.part for h in parts.extract_page(page)}
    assert {"ADL5801", "THS4521IDGKR"} <= found
    assert "CP" not in found and "R0402" not in found


def test_a_connector_and_a_sheet_frame_are_not_parts():
    """PJ-014D is a real jack and A3L-LOC is a drawing border. Neither is what this index is for, and
    the designer said which is which by calling one J3 and the other FRAME1."""
    found = {h.part for h in parts.extract_page(page_of(EAGLE))}
    assert not {"PJ-014D", "A3L-LOC", "PINHD-2X10"} & found


def test_a_name_no_dictionary_knows_is_taken_because_a_design_declared_it():
    """ADL5801 is in no family and no catalogue. LibreVNA puts it on its board, and that is the evidence:
    reading that same file as prose finds four parts where reading its fields finds nineteen."""
    hits = [h for h in parts.extract_page(page_of(EAGLE)) if h.part == "ADL5801"]
    assert hits and hits[0].conf == "high" and hits[0].family == "declared in a design"
    assert not {h.part for h in parts.extract(EAGLE)} & {"ADL5801"}      # prose alone does not


def test_legacy_kicad_reads_its_f_fields():
    found = {h.part for h in parts.extract_page(page_of(LEGACY))}
    assert "AD8629" in found and "PWR_FLAG" not in found


def test_a_file_of_another_kind_gives_one_empty_page():
    page = page_of("%PDF-1.4 not a schematic")
    assert page["how"] == "cad" and page["blocks"] == []


WILDCARDS = """<?xml version="1.0"?><eagle version="9"><drawing><schematic><parts>
  <part name="U1" deviceset="ADG44X" device=""/>
  <part name="U2" deviceset="REF33XX" device=""/>
  <part name="U3" deviceset="ADL5801" device=""/>
</parts></schematic></drawing></eagle>"""


def test_a_family_wildcard_is_not_a_part_even_in_a_design():
    """A designer writes ADG44x for "whichever of these we fit". The guard that catches ADS126x in prose
    has to catch it here too: the declared-value path skips the rest of the extractor's judgement."""
    found = {h.part for h in parts.extract_page(page_of(WILDCARDS))}
    assert found == {"ADL5801"}


GEDA = """v 20121123 2
C 50100 49300 1 0 0 EMBEDDEDATmega32U4-1.sym
[
P 52900 51400 52600 51400 1 0 0
{
T 52695 51445 5 8 1 1 0 0 1
pinnumber=27
}
T 50000 49000 5 10 0 1 0 0 1
device=SYMBOL_SAYS_RESISTOR
]
{
T 50200 51500 5 10 1 1 0 0 1
refdes=U1
T 50200 51700 5 10 0 1 0 0 1
device=ATmega32U4
}
C 60000 40000 1 0 0 resistor-1.sym
{
T 60100 40100 5 10 1 1 0 0 1
refdes=R1
T 60100 40300 5 10 0 1 0 0 1
device=RESISTOR
T 60100 40500 5 10 1 1 0 0 1
value=10k
}
C 61000 40000 1 0 0 aat3220.sym
{
T 61100 40100 5 10 1 1 0 0 1
refdes=U2
T 61100 40300 5 10 0 1 0 0 1
device=AAT3220
}
"""


def test_geda_is_the_third_text_format_and_a_sch_as_well():
    """The Bus Pirate's schematic is this, and so is a good deal of open hardware from about 2010."""
    assert cad.kind_of(GEDA) == "geda_sch"


def test_a_geda_component_is_its_device_and_not_its_symbols_own_attributes():
    """A gEDA file embeds a copy of each symbol, pins and all, and the symbol declares a `device=` too.
    Read naively, the resistor symbol inside U1 answers for U1."""
    pairs = cad.read_geda(GEDA)
    assert pairs == [("U1", "ATmega32U4"), ("R1", "RESISTOR"), ("U2", "AAT3220")]
    found = {h.part for h in parts.extract_page(page_of(GEDA))}
    assert found == {"ATMEGA32U4", "AAT3220"}       # RESISTOR and 10k are what the thing is, not which


PACKAGES = """<?xml version="1.0"?><eagle version="9"><drawing><schematic><parts>
  <part name="U1" deviceset="SOT23" device=""/>
  <part name="U2" deviceset="SOIC-8" device=""/>
  <part name="D1" deviceset="SOD-123" device=""/>
  <part name="Q1" deviceset="TO-252/DPAK" device=""/>
  <part name="U3" deviceset="QFN-0.5MM" device=""/>
  <part name="D2" deviceset="SMAJ24A" device=""/>
  <part name="U4" deviceset="AD8319" device=""/>
</parts></schematic></drawing></eagle>"""


def test_a_package_is_not_a_part_however_confidently_a_library_names_one():
    """EAGLE libraries name the deviceset after the case rather than the device, and the declared-value
    path trusts what a designer typed. 35 of the 129 names Kitspace's first 556 files returned were
    packages. SMAJ24A stays: it is a Littelfuse TVS diode whose name happens to start with a package."""
    found = {h.part for h in parts.extract_page(page_of(PACKAGES))}
    assert found == {"SMAJ24A", "AD8319"}


BOARD = """<?xml version="1.0"?><eagle version="9.6.2"><drawing><board>
  <elements>
    <element name="U1" library="adi" package="SOIC8" value="OPA1612" x="10" y="10"/>
    <element name="R4" library="rcl" package="0402" value="10k" x="12" y="10"/>
    <element name="U2" library="ti" package="QFN16" value="TPA3255" x="14" y="10"/>
  </elements>
</board></drawing></eagle>"""


def test_a_board_is_told_from_a_schematic_by_what_is_inside_it():
    """Both are `<eagle` and both are read here, but a board is a layout: `<board>` says which."""
    assert cad.kind_of(BOARD) == "eagle_brd"
    assert cad.kind_of(EAGLE) == "eagle_sch"


def test_a_board_gives_the_parts_on_it_and_not_their_packages():
    """Second best, and the only copy for 653 of SparkFun and Adafruit's 2,059 board files: it says what
    is fitted and nothing about how it is wired."""
    found = {h.part for h in parts.extract_page(page_of(BOARD))}
    assert found == {"OPA1612", "TPA3255"}      # not SOIC8, not QFN16, not 10k


# --- LTspice and SPICE netlists: the Toragi archives are full of both -----------------------------------
ASC = """Version 4
SHEET 1 1280 680
WIRE 272 160 176 160
SYMBOL npn 208 112 R0
SYMATTR InstName Q1
SYMATTR Value 2SC1815
SYMBOL res 288 32 R0
SYMATTR InstName R1
SYMATTR Value 4.7k
SYMBOL Opamps\\\\LT1001 400 96 R0
SYMATTR InstName U1
SYMBOL Opamps\\\\opamp2 500 96 R0
SYMATTR InstName U2
SYMATTR Value TL072
SYMBOL voltage 64 160 R0
SYMATTR InstName V1
SYMATTR Value 12
TEXT 48 400 Left 2 !.model 2SK170 NJF(Beta=40m Vto=-0.4)
"""

# A PSpice netlist as OrCAD wrote it beside TR0205A's design, and a hand deck from TR9604S1.
PSPICE_NET = """* source CE3
Q_Q1         N05113 N04583 N06304 QC1815
V_V1         N04583 0 DC 0.718Vdc AC 1Vac
R_R1         N05113 N03123  1k
X_U1A        N1 N2 N3 N4 N5 TL072 PARAMS: GAIN=1
R_R2         0 N06304  100
"""
DECK = """Q1 amplifier - Voltage Drive

VS 1 0 DC 1V
D1 1 0 DNORM
Q2 2 1 0 2SA1015
.DC VS -0.8V 0.7V  0.004V
.MODEL DNORM D(IS=1E-14)
.END
"""


def test_ltspice_names_the_part_in_its_value_or_its_vendor_symbol():
    pairs = {(r, v): d for r, v, d in cad.read_ltspice(ASC)}
    assert pairs[("Q1", "2SC1815")] and pairs[("U1", "LT1001")] and pairs[("U2", "TL072")]
    assert pairs[("", "2SK170")]                                # a model the sheet defines for itself
    assert ("V1", "") in pairs and ("R1", "") in pairs          # a source's waveform and a rating are never read


def test_a_generic_ltspice_symbol_is_not_a_part():
    pairs = cad.read_ltspice("Version 4\nSHEET 1 10 10\nSYMBOL npn 0 0 R0\nSYMATTR InstName Q9\n")
    assert pairs == [("Q9", "", False)]


def test_a_pspice_netlist_gives_the_model_of_each_device():
    pairs = {(r, v): d for r, v, d in cad.read_spice(PSPICE_NET)}
    assert pairs[("Q1", "2SC1815")] and pairs[("U1A", "TL072")]   # QC1815 is the author's name for 2SC1815
    assert ("R1", "") in pairs and ("V1", "") in pairs          # a passive or a source keeps its reference only


def test_a_deck_skips_its_title_and_reads_its_models():
    pairs = {(r, v): d for r, v, d in cad.read_spice(DECK)}
    assert ("Q1", "amplifier") not in pairs                      # the title line, which looks like an element
    assert pairs[("Q2", "2SA1015")] and not pairs[("D1", "DNORM")] and not pairs[("", "DNORM")]


def test_ltspice_and_netlists_are_recognised_from_the_file():
    assert cad.kind_of(ASC) == "ltspice_asc"
    assert cad.kind_of(PSPICE_NET) == "spice_net" and cad.kind_of(DECK) == "spice_net"
    assert cad.kind_of("README\nThis archive holds the programs.\nRun make.\n") == ""
    utf16 = ASC.encode("utf-16")                                 # as LTspice XVII saves a Japanese comment
    assert cad.kind_of(cad._text(utf16)) == "ltspice_asc"
    assert cad._text("回路図".encode("cp932")) == "回路図"


def test_the_client_sniffs_them_too():
    from parts_index.core.http import Response
    assert Response(200, "", body=ASC.encode("utf-16")).kind == "ltspice_asc"
    assert Response(200, "", body=PSPICE_NET.encode()).kind == "spice_net"
    assert Response(200, "", body=b"Readme: nothing here\n").kind == ""


def test_a_design_read_from_disk_arrives_as_one_page(tmp_path):
    f = tmp_path / "amp.asc"
    f.write_bytes(ASC.encode("utf-16"))
    page = cad.read(f, "ltspice_asc")[0]
    texts = {b["text"]: b.get("field", "") for b in page["blocks"]}
    assert page["how"] == "cad" and texts["2SC1815"] == "value" and texts["TL072"] == "value"
    assert "4.7k" not in texts and "Q1" in texts


def test_a_jis_transistor_is_not_mistaken_for_an_sc_package():
    """2SC1815 holds `SC18`, which the package filter read as an SC-70-style case and dropped — every
    Japanese transistor and FET in every design, until the Toragi netlists showed it."""
    for part in ("2SC1815", "2SA1015", "2SK170", "2SJ74", "2SD669A", "2SB649"):
        assert not cad.PACKAGE.match(part), part
    assert cad.PACKAGE.match("SC-70") and cad.PACKAGE.match("SOT23")


def test_an_ltspice_directive_after_a_bang_or_a_newline_is_read():
    text = "Version 4\nSHEET 1 1 1\nTEXT 0 0 Left 2 !.model 2SK170 NJF(Beta=40m)\\n.subckt MYOPA 1 2 3\n"
    found = {v: d for _, v, d in cad.read_ltspice(text)}
    assert found["2SK170"] and "MYOPA" in found and not found["MYOPA"]


# --- the vocabulary guard: what the project already knows is never filtered ------------------------------
def test_nothing_the_dictionary_or_the_census_knows_is_dropped_by_a_filter():
    """The filters are shapes, and a shape is wrong somewhere: 2SC1815 looked like an SC-18 case, 1N4148
    like a nanofarad, 6X4 like a pin header. So every name the vocabulary vouches for goes through, and
    this runs the whole of it — 2,191 dictionary names and the census behind them — to say so."""
    from parts_index.core.parts import extractor as x
    dropped = sorted(n for n, _ in x.KNOWN.values() if len(n) <= 40 and not cad._wanted(n))
    assert dropped == [], dropped[:40]
    # The census is another matter: it lists 100N, 4U7 and 10 as parts, read off lists that had to be
    # complete, and a name shaped like a rating is left to the shape rules. Every other census name goes through.
    rating = lambda n: (cad.A_VALUE.match(n) or cad.A_RAIL.match(n) or cad.A_HEADER.match(n)) and not cad.VALVE_SHAPE.fullmatch(n)  # noqa: E731
    dropped = sorted(n for n, _ in x.CENSUS.values() if len(n) <= 40 and not rating(n) and not cad._wanted(n))
    assert dropped == [], dropped[:40]


def test_the_shapes_that_once_swallowed_real_parts():
    for part in ("1N4148", "2N3904", "4N35", "6N137", "2SC1815", "2SA1015", "2SK170", "2SJ74",
                 "ISO7721", "BSC010N04LS", "BGA616", "TSOP4838", "TOP250", "6X4", "6V6", "5U4", "0A2"):
        assert cad._wanted(part), part
    for not_a_part in ("4u7", "1M5", "1Meg", "100nF", "10k", "3V3", "+5V", "5V0", "2X10", "SOT23", "SO-8",
                       "SC-70", "SC70", "TO-220", "DIP-8", "QFN-16", "TSOP48", "BGA-256", "{Rload}",
                       "V=V(vd)-V(vm)", "SINE(0 1 1k)", "-1", '""', "NP"):
        assert not cad._wanted(not_a_part), not_a_part


def test_a_package_on_the_end_comes_off_and_the_part_stays():
    assert cad.strip_package("L7805SOT89") == "L7805"
    assert cad.strip_package("LM317-TO220") == "LM317"
    assert cad.strip_package("BC547TO92") == "BC547"
    assert cad.strip_package("MC34063A-SO8") == "MC34063A"
    assert cad.strip_package("TSOP4838") == "TSOP4838"          # the census knows it whole
    assert cad.strip_package("SMAJ24A") == "SMAJ24A"


def test_a_spice_model_name_becomes_the_part_it_stands_for_or_stays_undeclared():
    assert cad.model_name("Q", "QC1815") == ("2SC1815", True)
    assert cad.model_name("Q", "Q2N3904") == ("2N3904", True)
    assert cad.model_name("D", "D1N4148") == ("1N4148", True)
    assert cad.model_name("J", "Jk369") == ("2SK369", True)
    assert cad.model_name("J", "JK30") == ("2SK30", True)
    assert cad.model_name("Q", "Q2SA1576A") == ("2SA1576A", True)
    assert cad.model_name("D", "DS1588") == ("1S1588", True)     # the census knows the JIS diode
    assert cad.model_name("X", "TL072") == ("TL072", True)
    for junk in ("QX", "DDEF", "QNORM", "JNDEF", "IDEAL", "SCHEMATIC1_RV1", "OP_10MHz"):
        assert cad.model_name(junk[:1], junk) == (junk, False), junk


def test_ltspice_sources_passives_and_gates_carry_no_part_and_a_vendor_symbol_does():
    text = """Version 4
SHEET 1 10 10
SYMBOL voltage 0 0 R0
SYMATTR InstName V1
SYMATTR Value SINE(0 1 1k)
SYMBOL bv 0 0 R0
SYMATTR InstName B1
SYMATTR Value V=V(vd)-V(vm)
SYMBOL res 0 0 R0
SYMATTR InstName R1
SYMATTR Value {Rload}
SYMBOL Digital\\and 0 0 R0
SYMATTR InstName A1
SYMBOL Opamps\\LM358 0 0 R0
SYMATTR InstName U1
SYMBOL npn 0 0 R0
SYMATTR InstName Q1
SYMATTR Value QC1815A
SYMBOL njf 0 0 R0
SYMATTR InstName J1
SYMATTR Value 2SK170
"""
    pairs = {r: (v, d) for r, v, d in cad.read_ltspice(text)}
    assert pairs["V1"] == ("", False) and pairs["B1"] == ("", False) and pairs["R1"] == ("", False)
    assert pairs["A1"] == ("", False)
    assert pairs["U1"] == ("LM358", True)                        # the bug: `lm\d{0,3}` called this generic
    assert pairs["Q1"] == ("2SC1815A", True) or pairs["Q1"][0].startswith("2SC1815")
    assert pairs["J1"] == ("2SK170", True)                       # a JFET's model, declared on a J reference
    page = cad.read(cad.__class__ and type("T", (), {"read_text": lambda self, **k: text})(), "ltspice_asc")[0]
    fields = {b["text"]: b.get("field", "") for b in page["blocks"]}
    assert fields["2SK170"] == "value" and fields["LM358"] == "value"
    assert "SINE(0 1 1k)" not in fields and "{Rload}" not in fields and "and" not in fields


def test_an_undeclared_model_reaches_the_extractor_as_text_and_a_declared_one_as_a_value():
    from parts_index.core import parts
    net = "* source X\nQ_Q1 1 2 3 QC1815\nQ_Q2 4 5 6 QX\nX_U1 1 2 3 4 5 SCHEMATIC1_RV1\nD_D1 1 0 DS1588\n"
    page = cad.read(net, "spice_net")[0]
    fields = {b["text"]: b.get("field", "") for b in page["blocks"]}
    assert fields["2SC1815"] == "value" and fields["1S1588"] == "value"
    assert "QX" not in fields and "SCHEMATIC1_RV1" not in fields      # no digit, or a hierarchy: never offered
    found = {h.part for h in parts.extract_page(page)}
    assert "2SC1815" in found and "QX" not in found and "SCHEMATIC1" not in found


def test_a_grade_suffix_and_a_short_form_come_out_as_the_part_the_index_prints():
    assert cad.canonical("2SC1815GR") == "2SC1815" and cad.canonical("2SA1015-Y") == "2SA1015"
    assert cad.canonical("C1815") == "2SC1815" and cad.canonical("S1588") == "1S1588"
    assert cad.canonical("TL072CP") == "TL072"
    assert cad.canonical("ADL5801") == "ADL5801"                # nothing to fold, nothing known: as typed
    page = cad.read("Version 4\nSHEET 1 1 1\nSYMBOL npn 0 0 R0\nSYMATTR InstName Q1\nSYMATTR Value 2SC1815GR\n",
                    "ltspice_asc")[0]
    from parts_index.core import parts
    assert {h.part for h in parts.extract_page(page)} == {"2SC1815"}     # not 2SC1815G, as it once was


def test_an_authors_model_of_an_unknown_part_is_offered_by_its_type_number_and_not_declared():
    assert cad.model_name("Q", "QBFG425W") == ("BFG425W", True)  # the census knows the transistor, not the model
    assert cad.model_name("Q", "QABCD9999X") == ("ABCD9999X", False)
    assert cad.model_name("Q", "QNORM") == ("QNORM", False)      # NORM is nobody's type number


def test_a_census_name_shaped_like_a_rating_vouches_for_nothing():
    for rating in ("100n", "4u7", "10", "100N"):
        assert not cad._wanted(rating), rating
