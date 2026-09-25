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
