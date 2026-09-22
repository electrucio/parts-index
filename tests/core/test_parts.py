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


# --- what the census settles ------------------------------------------------------------------------
def mkpage(ts):
    return {"w": 1000, "h": 1000, "blocks": [{"box": [0, 0, 9, 9], "text": t, "conf": 0.99} for t in ts]}


def test_a_valve_whose_name_is_also_a_value_needs_the_page():
    """6V6 is the most used output valve there is, and it reads as 6.6 V. It was in no document at all."""
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 12AX7 6V6 R1 C1".split()))] == ["12AX7", "6V6"]
    assert [h.part for h in parts.extract_page(mkpage("R1 R2 4K7 6V6 10K 2K2 100n".split()))] == []
    assert [h.part for h in parts.extract_page(mkpage(["the output valves are a pair of 6V6"]))] == ["6V6"]


def test_numeric_valve_names_come_from_the_census_not_a_hand_written_list():
    """5687, 6336A, 6528, 7236: real valves that no pattern covers and the list of twenty did not have."""
    got = [h.part for h in parts.extract_page(mkpage("V1 5687 6336A 6528 12AX7 R1".split()))]
    assert got == ["5687", "6336A", "6528", "12AX7"]
    assert [h.conf for h in parts.extract_page(mkpage("V1 5687 12AX7".split()))] == ["high", "high"]


def test_the_census_does_not_overrule_the_family():
    """7815 and 7995 are valve types as well as regulators. On a regulator page they are regulators."""
    assert got("a 7815 regulator") == ["7815"]
    assert [h.kind for h in parts.extract("a 7815 regulator")] == ["regulator"]      # not a valve


def test_the_census_overrules_the_reject_list():
    """The LLM pass that built rejected_tokens.txt threw away real valves: 1S5, 3S4, 1T4, 1R5."""
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 1S5 3S4 1T4".split()))] == ["1S5", "3S4", "1T4"]


def test_a_census_part_is_high_only_when_something_else_on_the_page_agrees():
    page = mkpage("6336A R1 R2 C1 C2".split())                  # one valve name, nothing else valve-like
    assert [h.part for h in parts.extract_page(page)] == []


def with_census(monkeypatch, rows):
    monkeypatch.setattr(parts, "CENSUS", {parts.norm(k): (k, v) for k, v in rows.items()})


def test_a_loose_family_the_census_confirms_becomes_publishable(monkeypatch):
    """MC33274 and MC33078 are the same vendor and the same numbering. Only one was in the dictionary,
    so only one was ever published; a loose family plus a list that says the part exists is enough."""
    with_census(monkeypatch, {})
    assert [h.conf for h in parts.extract("MC33274", isolated=True)] == ["medium"]      # family alone
    with_census(monkeypatch, {"MC33274": "ic"})
    assert [(h.part, h.conf) for h in parts.extract("MC33274", isolated=True)] == [("MC33274", "high")]


def test_a_semiconductor_list_does_not_settle_a_valve_reading(monkeypatch):
    """The one distinction that matters: 7815 is a regulator and a valve type. A list of semiconductors
    may not decide a token the valve family claimed, nor a tube list one the regulator family claimed."""
    with_census(monkeypatch, {"7815": "tube"})
    assert [(h.part, h.kind) for h in parts.extract("a 7815 regulator")] == [("7815", "regulator")]
    with_census(monkeypatch, {"6CB6": "bjt"})              # a valve, miscalled a transistor by the list
    hits = {h.part: h.conf for h in parts.extract_page(mkpage("V1 V2 6CB6 12AX7".split()))}
    assert hits["6CB6"] == "medium" and hits["12AX7"] == "high"     # the page settles it, not the wrong list


def test_the_census_never_diverts_a_token_the_old_rules_already_settled(monkeypatch):
    with_census(monkeypatch, {"4N25": "opto", "1N4148": "diode"})
    assert got("1N4148 2N3055 4N25") == ["1N4148", "2N3055", "4N25"]


def test_a_part_no_family_covers_at_all(monkeypatch):
    with_census(monkeypatch, {})
    assert got("TTC004B") == []                              # no family in the world covers Toshiba's TT-
    with_census(monkeypatch, {"TTC004B": "bjt"})
    assert [(h.part, h.conf) for h in parts.extract("TTC004B", isolated=True)] == [("TTC004B", "high")]


def test_the_census_alone_does_not_speak_for_a_three_character_token():
    """AB1 and AB2 are real Philips valves. 'Class AB1' is what the books say, on every other page."""
    assert got("operating in class AB1 with a pair of 6L6") == ["6L6"]
    assert got("class AB2 push-pull") == []
    assert got("a DL92 and a DF91") == ["DL92", "DF91"]              # four characters, and only the census knows them
    assert got("a 1T4 and a 3S4") == ["1T4", "3S4"]                  # three, but digit-letter-digit is a valve name


def test_the_stray_stroke_rule_does_not_eat_the_germanium_transistors():
    """0D3 among D1 D2 D4 is the diode D3 with a stroke of its symbol read as a 0 — that stays. But the
    same rule was dropping OC44 and OC71 on every page with two capacitor designators on it, which is
    every schematic, and those are the transistors half of fuzz pedals are built from."""
    page = mkpage("OC71 OC44 C70 C72 R1 Q1 2N3904".split())
    assert [h.part for h in parts.extract_page(page)] == ["OC71", "OC44", "2N3904"]
    assert [h.part for h in parts.extract_page(mkpage("D1 D2 D4 0D3 R1 R2 12AX7".split()))] == ["12AX7"]


def test_a_numeric_part_in_a_closed_numbering_scheme_can_reach_the_gate():
    """7805 is the most used regulator there is and was in no document: numeric tokens were capped at
    medium, and only high is published. The regulator scheme is closed, so let the page decide."""
    assert [h.part for h in parts.extract_page(mkpage("7805 7812 C1 C2 R1".split()))] == ["7805", "7812"]
    assert [h.part for h in parts.extract_page(mkpage("IC1 7805 100n 10k".split()))] == ["7805"]   # regulator words
    assert [h.part for h in parts.extract_page(mkpage("R1 R2 7805 4k7".split()))] == []            # nothing agrees
    assert got("costs 7815") == [] and got("a 7815 regulator") == ["7815"]


def test_a_truth_table_is_not_a_page_full_of_valves():
    """1010 and 1110 are both real valve type numbers and both rows of a truth table. Two tokens that are
    each waiting for the page to agree may not agree with one another — only a part that is already
    settled counts as evidence. A closed numbering scheme is different: its shape is vetted already."""
    assert [h.part for h in parts.extract_page(mkpage("1010 1110 0101 0011 A B C OUT".split()))] == []
    assert [h.part for h in parts.extract_page(mkpage("V1 1010 12AX7 6SN7".split()))] == ["1010", "12AX7", "6SN7"]
