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
