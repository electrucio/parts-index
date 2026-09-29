"""Reading part numbers: what each letter says, and the numbers no scheme may claim."""
import pytest

from parts_index.core.parts import catalogue, schemes
from parts_index.web.parts import KIND_MAP

# Two American valves with revised versions, a Soviet valve's shorter namesake, and an EPROM.
KNOWN = {"1X2": ("tube",), "12B4": ("tube",), "6N2": ("tube",), "27C64": ()}


def read(part, kind):
    d = schemes.decode(part, KIND_MAP.get(kind, ()), KNOWN)
    return (d.scheme, [(s.text, s.meaning.split(" (")[0].split(" —")[0]) for s in d.segments]) if d else None


def test_every_scheme_reads_its_own_example_and_cites_what_exists():
    assert schemes.check(set(catalogue.references()), set(catalogue.families())) == []


@pytest.mark.parametrize("part,kind,scheme,pieces", [
    ("BC548B", "bjt", "pro-electron", ["B", "C", "548", "B"]),
    ("BCY70", "bjt", "pro-electron", ["B", "C", "Y", "70"]),
    ("AC128", "bjt-ge", "pro-electron", ["A", "C", "128"]),
    ("BZX55C5V6", "zener", "pro-electron", ["B", "Z", "X", "55", "C", "5V6"]),
    ("BC327-25", "bjt", "pro-electron", ["B", "C", "327", "25"]),
    ("OC71", "bjt-ge", "mullard-semiconductor", ["O", "C", "71"]),
    ("2N3904", "bjt/jfet/mosfet", "jedec", ["2", "3904"]),
    ("2N2646", "bjt/jfet/mosfet", "jedec", ["2", "2646"]),
    ("1N4148", "diode", "jedec", ["1", "4148"]),
    ("2SC1815GR", "bjt", "jis-c7012", ["2", "C", "1815", "GR"]),
    ("2SK170BL", "jfet/mosfet", "jis-c7012", ["2", "K", "170", "BL"]),
    ("2SK30A", "jfet/mosfet", "jis-c7012", ["2", "K", "30", "A"]),
    ("1S1588", "diode", "jis-c7012", ["1", "", "1588"]),
    ("12AX7A", "tube", "retma-tube", ["12", "AX", "7", "A"]),
    ("6SN7GTB", "tube", "retma-tube", ["6", "SN", "7", "GTB"]),
    ("0A2", "tube", "retma-tube", ["0", "A", "2"]),
    ("ECC83", "tube", "mullard-philips-tube", ["E", "CC", "83"]),
    ("EL34", "tube", "mullard-philips-tube", ["E", "L", "34"]),
    ("GZ34", "tube", "mullard-philips-tube", ["G", "Z", "34"]),
    ("PL500", "tube", "mullard-philips-tube", ["P", "L", "500"]),
    ("E88CC", "tube", "mullard-philips-tube", ["E", "88", "CC"]),
    ("6N2P", "tube", "soviet-tube", ["6", "N", "2", "P"]),              # a 6N2 exists, and it is a valve too
    ("6P14P", "tube", "soviet-tube", ["6", "P", "14", "P"]),
    ("6N2PEV", "tube", "soviet-tube", ["6", "N", "2", "P", "EV"]),
    ("6SH9P", "tube", "soviet-tube", ["6", "SH", "9", "P"]),
    ("6J1B", "tube", "soviet-tube", ["6", "J", "1", "B"]),
    ("1X2A", "tube", "retma-tube", ["1", "X", "2", "A"]),         # the American 1X2 revised, not a Soviet subminiature
    ("12B4A", "tube", "retma-tube", ["12", "B", "4", "A"]),
])
def test_a_number_reads_letter_by_letter(part, kind, scheme, pieces):
    got = read(part, kind)
    assert got and got[0] == scheme, got
    assert [t for t, _ in got[1]] == [p for p in pieces if p != ""] or [t for t, _ in got[1]] == pieces


def test_the_letters_say_what_the_standard_says():
    m = [meaning for _, meaning in read("BC548B", "bjt")[1]]
    assert m[0].startswith("silicon") and m[1].startswith("transistor") and m[3].startswith("not Pro Electron")
    assert read("AC128", "bjt-ge")[1][0][1].startswith("germanium")
    assert dict(read("ECC83", "tube")[1])["CC"] == "a small-signal triode + a small-signal triode"
    assert "Noval" in dict(read("ECC83", "tube")[1])["83"]
    assert "Magnoval" in dict(read("PL500", "tube")[1])["500"]
    assert "N-channel" in dict(read("2SK170BL", "jfet/mosfet")[1])["K"]


@pytest.mark.parametrize("part,kind", [
    ("AD633", "opamp"),          # A germanium, D audio power: letter for letter, and an Analog Devices multiplier
    ("AD633", ""),               # a part of unknown kind is read by no scheme
    ("KT88", "tube"),            # Marconi-Osram's kinkless tetrode, not a K-heater Philips valve
    ("10BP4", "tube"),           # a picture tube: its first number is not a heater voltage
    ("7025", "tube"),            # an EIA four-digit number says nothing on its own
    ("300B", "tube"),
    ("TL072", "opamp"),
    ("4N25", "opto"),            # not a JEDEC 1N/2N/3N number
    ("OC000H", "bjt-ge"),        # no serial number starts with 0
    ("PL001", "tube"),
    ("2K41", "tube"),            # a klystron: no receiving valve has 41 elements
    ("27C64N", "tube"),          # an EPROM the dictionary filed as a valve: 27C64 is a part of its own
])
def test_numbers_no_scheme_may_claim(part, kind):
    assert read(part, kind) is None



def test_a_form_that_needs_the_known_parts_is_skipped_without_them():
    assert schemes.decode("6J1B", ("tube",)) is None
    assert schemes.decode("6J1B", ("tube",), frozenset()).scheme == "soviet-tube"


def test_no_transistor_filed_as_germanium_is_named_silicon():
    """Under Pro Electron the first letter is the material: A germanium, B silicon. The dictionary had BC109,
    BC169, BC177, BCY70, BCY71 and BUX48 as germanium, which put them in the site's germanium filter."""
    from parts_index.core.config import known_parts
    from parts_index.web.parts import rows
    wrong = []
    for r in rows(known_parts()):
        if r["kind"] not in ("bjt-ge", "bjt-ge/diode-ge"):
            continue
        d = schemes.decode(r["name"], ("bjt-ge",), frozenset())
        if d and d.scheme == "pro-electron" and d.segments[0].text == "B" and d.segments[1].text in "CDFLSU":
            wrong.append(r["name"])
    assert wrong == []


@pytest.mark.parametrize("part,kind,family", [
    ("ECC83", "tube", "triode"),              # C + C: two triodes
    ("ECL82", "tube", "tube"),                # a triode and a power pentode share only "tube"
    ("GZ34", "tube", "tube-rectifier"),
    ("6N2P", "tube", "triode"),
    ("2SK170BL", "jfet/mosfet", "fet"),
    ("2SC1815", "bjt", "bjt"),
    ("BZX55C5V6", "zener", "zener"),
    ("BC548", "bjt", "bjt"),                  # "transistor, low power" names no structure; the kind does
    ("1N914", "diode", "diode"),
])
def test_the_letters_of_a_name_can_narrow_its_family(part, kind, family):
    devices = KIND_MAP.get(kind, ())
    d = schemes.decode(part, devices, KNOWN)
    assert catalogue.family_of(part, devices, d.families if d else None)[0] == family


def test_a_name_never_moves_a_part_out_of_the_family_its_kind_gives():
    # A 1N number read as "a diode" filed as a zener stays a zener: the name is less precise, not contrary.
    assert catalogue.family_of("1N5231", KIND_MAP["zener"], ["diode"]) == ("zener", "kind")


@pytest.mark.parametrize("part,kind,said", [
    ("2SC1815GR", "bjt", "NPN"), ("2SD669A", "bjt", "NPN"), ("2SA1015", "bjt", "PNP"),
    ("2SB56", "bjt-ge", "PNP"), ("2SK170", "jfet/mosfet", "N-channel"), ("2SJ74", "jfet/mosfet", "P-channel"),
    ("1S1588", "diode", ""), ("BC548B", "bjt", ""),
])
def test_a_japanese_name_says_which_way_round_the_transistor_is(part, kind, said):
    assert schemes.decode(part, KIND_MAP[kind], KNOWN).polarity == said
