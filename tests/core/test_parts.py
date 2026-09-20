"""Part extractor — the strings that went wrong at least once."""
import pytest

from parts_index.core.parts import extractor as parts


def got(text, **kw):
    return [h.part for h in parts.extract(text, **kw)]


@pytest.mark.parametrize("text,expected", [
    ("1N4148 2N3055 4N25", ["1N4148", "2N3055", "4N25"]),                       # look like 1n / 2n / 4n values
    ("IN4148 lN4004 ZN3904", ["1N4148", "1N4004", "2N3904"]),                   # OCR: I, l, Z for a leading digit
    ("ZN414", ["ZN414"]),                                                       # a real Ferranti part, not 2N414
    ("TLO72 NES534 2N3O55 BC1O9", ["TL072", "NE5534", "2N3055", "BC109"]),      # O/S inside the digits
    ("BC 109 and LM 386, TDA 2030", ["BC109", "LM386", "TDA2030"]),             # split tokens
    ("AC 240 volts, AD 1975", []),                                              # ... but not mains voltage or a year
    ("BC107/8/9 BFY50/51/52 2N3904/2N3906", ["BC107", "BC108", "BC109", "BFY50", "BFY51", "BFY52", "2N3904", "2N3906"]),
    ("VTL5C3/2", ["VTL5C3/2"]),                                                 # owns its slash
    ("MN-3005 2SA1943-O EL34s IRF610-ND", ["MN3005", "2SA1943", "EL34", "IRF610"]),
    ("R12 C3 IC12 TR3 VR1 SW2 TP4 100n 4k7 10K5 2V5 1975 J23-4", []),           # designators, values, years, connector pins
    ("5E3 AB763 6G15 AC30", []),                                                # Fender circuit codes, Vox model
    ("AC128 AC187 OC71 OA91", ["AC128", "AC187", "OC71", "OA91"]),              # germanium, not Vox
    ("J201 U310", ["J201", "U310"]),                                            # real parts that look like designators
    ("U101 J3", []),
    ("74LS00 CD4049UBE", ["74LS00", "CD4049UBE"]),                              # not an American valve
    ("µA741 uA741", ["UA741", "UA741"]),
    ("the 807 valve in push-pull", ["807"]), ("pay 807 pounds", []),            # numeric valves need valve words
    ("a 7815 regulator", ["7815"]), ("costs 7815", []),
    ("300B KT88 EF86 6SN7GT", ["300B", "KT88", "EF86", "6SN7GT"]),
])
def test_extract(text, expected):
    assert got(text) == expected


def test_base_part():
    b = {h.part: h.base for h in parts.extract("BC109C TL072CP 2SK170BL NE5534AN 6L6GC 12AX7A LM317T BF245A 300B")}
    assert b == {"BC109C": "BC109", "TL072CP": "TL072", "2SK170": "2SK170", "NE5534AN": "NE5534", "6L6GC": "6L6", "12AX7A": "12AX7",
                 "LM317T": "LM317", "BF245A": "BF245", "300B": "300B"}


def test_bare_numbers_only_on_circuit_pages():
    assert got("uses a 741 and a 5534") == []
    assert got("uses a 741 and a 5534", allow_bare=True) == ["UA741", "NE5534"]


def test_isolated_label():
    assert got("807", isolated=True) == ["807"]
    assert [h.conf for h in parts.extract("1N4148")] == ["high"] and [h.conf for h in parts.extract("IN4148")] == ["medium"]


def test_page():
    page = {"w": 1000, "h": 1400, "blocks": [{"box": [0, 0, 10, 10], "text": t, "conf": c} for t, c in
            [("R1", .99), ("R2", .99), ("C1", .98), ("C2", .97), ("TR1", .99), ("TR2", .99), ("10k", .99), ("BC109", .95), ("741", .9), ("2N3055", .5)]]}
    assert parts.count_designators(page["blocks"]) == 6 and parts.count_values(page["blocks"]) == 1
    assert [h.part for h in parts.extract_page(page)] == ["BC109", "UA741"]          # 2N3055 read with confidence 0.5 is dropped; 741 read at 0.9 stays (4+ chars need 0.85, shorter 0.90)


def test_hex_dump_is_not_valves():
    page = {"blocks": [{"box": [0, 0, 1, 1], "text": t, "conf": 0.99} for t in "1C00 1C80 1C90 1CA0 1D20 1D30 6V6GT".split()]}
    assert [h.part for h in parts.extract_page(page)] == ["6V6GT"]


def test_switch_sections_are_not_diodes():
    assert got("S1A S1D S2A A13") == []


@pytest.mark.parametrize("text,expected", [
    ("10K5M 22K1W 1K5SM 6K8UF 4X10K 3X6 8X3 25A25K", []),                       # resistor specs and multiplications, not valves
    ("6X4 6X5GT 2X2", ["6X4", "6X5GT", "2X2"]),                                 # ... but these valves are real
    ("AC117V AC150V DC24V", []), ("PL259 RS232 R5232 SO239", []),
    ("7995 7815 regulator 7912", ["7815", "7912"]),
    ("TL0725M TL872 TL072 TL074CN TL431", ["TL072", "TL074CN", "TL431"]),
    ("2AX7 2AX7A 6L66C 12AX71", ["12AX7", "12AX7A", "6L6GC", "12AX7"]),         # valve misreads repaired
])
def test_qa_round_1(text, expected):
    assert got(text) == expected


def test_designator_misread_needs_siblings():
    mk = lambda ts: {"blocks": [{"box": [0, 0, 1, 1], "text": t, "conf": 0.99} for t in ts]}
    assert [h.part for h in parts.extract_page(mk("D1 D2 D4 0D3 R1 R2 12AX7".split()))] == ["12AX7"]       # 0D3 is diode D3
    assert [h.part for h in parts.extract_page(mk("V1 V2 0D3 5U4GB".split()))] == ["0D3", "5U4GB"]          # a real regulator valve
    assert [h.part for h in parts.extract_page(mk("IC1 IC3 C1 C2 1C2 TL072".split()))] == ["TL072"]         # 1C2 is IC2


def test_qa_round_2():
    assert got("BFS61 BFT66 BSV57") == ["BFS61", "BFT66", "BSV57"]                # real parts, not OCR damage
    assert got("BS2B MS-123 MS-566 IN400J") == []                                 # no daring repairs
    assert got("2NI265 TIPI41 IN914") == ["2N1265", "TIP141", "1N914"]
    assert got("J-304") == [] and got("J201") == ["J201"]
    mk = lambda ts: {"blocks": [{"box": [0, 0, 1, 1], "text": t, "conf": 0.99} for t in ts]}
    assert [h.part for h in parts.extract_page(mk("06 18 E0 3D8 0A AC".split()))] == []                       # a lone "valve" in a hex dump
    assert [h.part for h in parts.extract_page(mk("12AX7 6V6GT 6BM8 V1 V2".split()))] == ["12AX7", "6V6GT", "6BM8"]      # ... but fine among valves
    assert [h.part for h in parts.extract_page(mk("J301 J302 J304 R1 Q1 2N3904".split()))] == ["2N3904"]      # a row of jacks
    assert [h.part for h in parts.extract_page(mk("J201 J201 Q1 R1".split()))] == ["J201", "J201"]


def test_postcodes_are_not_transistors():
    assert got("Grassington, North Yorks. BD23 5AA") == [] and got("Bristol BS1 4DJ") == []
    assert got("BC107 BD139 BF245") == ["BC107", "BD139", "BF245"]
