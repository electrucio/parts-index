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
    sheet = "V1 V2 V3 R1 R2 C1 C2 5687 6336A 6528 12AX7".split()          # a drawing, designators and all
    assert [h.part for h in parts.extract_page(mkpage(sheet))] == ["5687", "6336A", "6528", "12AX7"]
    # …but a bare number off a page with no circuit on it is a number. 6336A keeps its letter.
    assert [h.part for h in parts.extract_page(mkpage("V1 5687 6336A 12AX7".split()))] == ["6336A", "12AX7"]


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
    page = mkpage("IC1 IC2 R1 R2 C1 MC33274 TL072".split())
    assert [(h.part, h.conf) for h in parts.extract_page(page)] == [("MC33274", "medium"), ("TL072", "high")]
    with_census(monkeypatch, {"MC33274": "ic"})                      # …and the census says it exists
    assert [(h.part, h.conf) for h in parts.extract_page(page)] == [("MC33274", "high"), ("TL072", "high")]
    # On its own it stays where its family left it: a list is not evidence about *this* token.
    assert [h.conf for h in parts.extract("MC33274", isolated=True)] == ["medium"]


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
    bom = mkpage("Q1 Q2 R1 R2 C1 TTC004B 2SC3334".split())   # a circuit, and another transistor on it
    assert [h.part for h in parts.extract_page(bom)] == ["TTC004B", "2SC3334"]
    assert parts.extract("TTC004B", isolated=True) == []     # but never off a bare token


def test_the_census_alone_does_not_speak_for_a_three_character_token():
    """AB1 and AB2 are real Philips valves. 'Class AB1' is what the books say, on every other page."""
    assert got("operating in class AB1 with a pair of 6L6") == ["6L6"]
    assert got("class AB2 push-pull") == []
    # A name only the census knows waits for the page, whatever its length — DL92 and DF91 are valves
    # and nothing else here reads them, so a drawing with valves on it is what publishes them.
    assert got("a DL92 and a DF91") == []
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 R1 C1 DL92 DF91 12AX7".split()))] == [
        "DL92", "DF91", "12AX7"]
    assert got("a 1T4 and a 3S4") == []
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 1T4 3S4 12AX7".split()))] == ["1T4", "3S4", "12AX7"]


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


def test_a_valve_that_is_also_an_ic_designator_needs_the_page_to_be_about_valves():
    """1C4 and 1C6 are battery valves, and they are IC4 and IC6 with the I read as a one. They came out
    published beside a CA3130 and a 2N5459 on a page with no valve on it."""
    assert [h.part for h in parts.extract_page(mkpage("1N914 2N5459 CA3130 1C6 1C4 R1 C1".split()))] == [
        "1N914", "2N5459", "CA3130"]
    # And not on a valve page either: 1C1 came out on 125 documents in the first full export, every one
    # of them an IC designator. The dictionary may still say otherwise; the census alone may not.
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 1C6 1C4 12AX7 6V6".split()))] == ["12AX7", "6V6"]


def test_a_truth_table_is_not_a_page_full_of_valves():
    """1010 and 1110 are both real valve type numbers and both rows of a truth table. Two tokens that are
    each waiting for the page to agree may not agree with one another — only a part that is already
    settled counts as evidence. A closed numbering scheme is different: its shape is vetted already."""
    assert [h.part for h in parts.extract_page(mkpage("1010 1110 0101 0011 A B C OUT".split()))] == []
    sheet = "V1 V2 R1 R2 C1 1010 12AX7 6SN7".split()                      # on a drawing it is a valve again
    assert [h.part for h in parts.extract_page(mkpage(sheet))] == ["1010", "12AX7", "6SN7"]


def test_a_bare_number_needs_a_circuit_on_the_page_not_just_company():
    """Radio-TV Experimenter prints a reader service card: 1007, 1010, 1048, 1110 … every one of them a
    valve type in the census, on a page of prose with no designator on it."""
    service_card = "V1 valve 1007 1010 1048 1049 1110 1138 1221".split()
    assert [h.part for h in parts.extract_page(mkpage(service_card))] == []
    schematic = "V1 V2 R1 R2 C1 C2 Q1 5687 12AX7".split()
    assert [h.part for h in parts.extract_page(mkpage(schematic))] == ["5687", "12AX7"]


def test_the_names_this_corpus_prints_for_something_else():
    """Each of these is a real type in the census, and each one loses to what the corpus actually prints.
    Found by exporting the index once and reading the biggest gains: 100TH on 254 documents, S100 on 361,
    6V3 on 96, 1C1 on 125, PART1 on 135 — every one of them wrong, and 6V6 is the same shape as 6V3."""
    assert got("our 100th issue and the 75th anniversary") == []          # Eimac triodes, and ordinals
    assert got("an S-100 bus card with N750 capacitors") == []            # a bus and a temperature code
    assert [h.part for h in parts.extract_page(mkpage("PART1 MOD1 R1 C1 2N3904".split()))] == ["2N3904"]
    heaters = "V1 V2 12AX7 6V6 6V3 1V2 R1 C1 R2".split()
    assert [h.part for h in parts.extract_page(mkpage(heaters))] == ["12AX7", "6V6"]   # 6V3 is 6.3 volts
    assert [h.part for h in parts.extract_page(mkpage("V1 V2 R1 R2 C1 3V4 12AX7".split()))] == ["3V4", "12AX7"]


def test_the_shortest_names_in_the_census_are_not_names_here():
    """Frank's archive holds valves called 10, 50, E, CA, CH1, PA1 and LD1 — every one of them real, and
    every one of them something else on a page here: a number, a letter, channel 1, a designator. The
    first full export published 10 on 1,129 documents and CA on 1,121 before this."""
    noisy = "V1 V2 12AX7 6V6 10 50 E CA CH1 PA1 LD1 22 R1 C1".split()
    assert [h.part for h in parts.extract_page(mkpage(noisy))] == ["12AX7", "6V6"]


# --- modern analogue silicon -------------------------------------------------------------------------
# The families were read off magazines of 1960-1990 and stopped there. Eight TI application notes full
# of ADS7822 and ADS1286 yielded not one part, which is the bias measured rather than argued: 291 of the
# corpus's 18,542 names belong to a family newer than 1995.

MODERN = "the ADS8681 converter, a DAC8563, a REF5025 reference, an AMC1311 and an ISO7741 isolator, " \
         "a THS4521 amplifier, a PGA280, an LMH6629, a TPS7A4700 regulator and a TPA3255 output stage"


def test_modern_analogue_families_are_seen():
    assert parts.extract(MODERN)                     # every one of them was invisible before 2026-09-24
    found = {h.part for h in parts.extract(MODERN)}
    for p in ("ADS8681", "DAC8563", "REF5025", "AMC1311", "ISO7741",
              "THS4521", "PGA280", "LMH6629", "TPS7A4700", "TPA3255"):
        assert p in found, p


def test_the_standards_a_document_cites_are_not_parts():
    """ISO9001 and ISO14001 are on half the application notes ever written."""
    found = {h.part for h in parts.extract("certified to ISO9001 and ISO14001, with a 12-bit ADC")}
    assert found == set()


def test_a_family_named_with_a_wildcard_is_not_a_device():
    """A data sheet writes ADS126x for "any of these". You cannot buy one."""
    found = {h.part for h in parts.extract("The ADS126x family and the REF60xx references")}
    assert found == set()


def test_an_evaluation_board_reports_the_chip_it_carries():
    found = {h.part for h in parts.extract("Connect the ADS1298REVM, then power the ADS7056EVM")}
    assert found == {"ADS1298R", "ADS7056"}


def test_a_loose_shape_the_census_knows_is_raised_by_company_like_any_open_scheme():
    """AD817 was read on 16 pages and published on none: ADxxx is a loose shape, so without the
    dictionary it stayed low, while AD817AN, which the dictionary happened to hold, was on 91. The
    census knows the type, so beside another IC on the page it is three pieces of evidence like
    MC33274 — and a package suffix (ARZ) is looked up by its base."""
    def mkpage(words):
        return {"blocks": [{"text": w, "conf": 1.0} for w in words]}
    got = {h.part: h.conf for h in parts.extract_page(mkpage("U1 AD817ARZ U2 OPA1612AID R1 10k".split()))}
    assert got["AD817ARZ"] == "high" and got["OPA1612AID"] == "high"
    got = {h.part: h.conf for h in parts.extract_page(mkpage("U1 AD817 R1 R2 C1 C2 J1".split()))}
    assert got["AD817"] == "medium"                                   # the census alone: not published
    assert [h.part for h in parts.extract("U1 AD817ARZ-REEL7", isolated=True)] == []   # an order code is not a name


def test_a_board_named_with_a_hyphen_is_the_part_without_it():
    """ADS850-EVM, ATMEGA16U2-EVAL: taking EVM off left ADS850- published as a part of its own."""
    found = {h.part for h in parts.extract("Use the ADS850-EVM and the ADS1241-EVM")}
    assert not any(p.endswith("-") for p in found)
    assert "ADS1241" in found


def test_a_label_a_marked_value_and_a_family_are_not_parts():
    """Measured on the export of 2026-09-27: IN3 on 1,767 documents (input 3, and a Soviet indicator lamp in
    the dictionary), 6K8 on 1,121 (6.8 kilohm, and a valve type), 1N400X on 122 (any of seven diodes)."""
    def got(text):
        return {h.part for h in parts.extract(text, isolated=True)}
    for word in ("IN3", "LED4", "CH16", "6K8", "1R5", "4K7", "1N400X", "1N4XXX"):
        assert got(word) == set(), word
    assert got("6K8GT") == {"6K8GT"}          # the valve, named as a valve
    assert got("1N4007") == {"1N4007"}


def test_a_page_of_labels_does_not_vouch_for_a_valve_it_does_not_have():
    """IN3, read as a valve, was the company that published 6K8 on eurorack modules."""
    def mkpage(words):
        return {"blocks": [{"text": w, "conf": 1.0} for w in words]}
    found = [h.part for h in parts.extract_page(mkpage("IN1 IN2 IN3 6K8 TL072 R1 R2 C1".split()))]
    assert "6K8" not in found and "IN3" not in found and "TL072" in found


def test_a_valve_named_like_a_size_needs_another_valve_beside_it():
    """1X2 is a TV's EHT rectifier and HEADER 1X2 on 388 pages of TI application notes."""
    def mkpage(words):
        return {"blocks": [{"text": w, "conf": 1.0} for w in words]}
    assert "1X2" not in [h.part for h in parts.extract_page(mkpage("J1 1X2 TPS54160 R1 C1".split()))]
    assert "1X2B" in [h.part for h in parts.extract_page(mkpage("V1 6BQ6GTB V2 1X2B 6CG7".split()))]


def test_a_postcode_is_not_a_valve():
    """Every Elby document ends "Bridport, TAS 7262, Australia", and 7262 is a valve type in the census."""
    assert [h.part for h in parts.extract("Bridport, TAS 7262, Australia", pending=True)] == []


def test_a_design_that_declares_a_designator_as_its_value_declares_no_part():
    page = {"blocks": [{"text": "LED1", "conf": 1.0, "field": "value"}, {"text": "TL072", "conf": 1.0, "field": "value"}]}
    assert [h.part for h in parts.extract_page(page)] == ["TL072"]
