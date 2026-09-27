"""The catalogue: families, their references, and the parts a manufacturer's sheet files under them."""
import pytest

from parts_index.core.parts import catalogue
from parts_index.web.parts import DEVICES, KIND_MAP


def test_the_published_catalogue_holds_together():
    assert catalogue.check([k for k, _ in DEVICES]) == []


@pytest.mark.parametrize("kind,family", [
    ("tube", "tube"),
    ("bjt-ge", "bjt"),
    ("bjt/jfet/mosfet", "transistor"),     # a JEDEC 2N number: the name cannot say which structure
    ("jfet/mosfet", "fet"),                # JIS 2SK: a field-effect transistor, junction or insulated gate
    ("diode/zener", "diode"),
    ("opamp/ic", "ic"),                    # an analogue IC of some sort
    ("bjt-ge/diode-ge", "discrete"),
    ("battery", "other"),
    ("", ""),
])
def test_a_kind_defaults_to_the_family_its_devices_share(kind, family):
    assert catalogue.family_for(KIND_MAP.get(kind, ())) == family


def test_a_manufacturers_sheet_outranks_the_kind():
    # A 2N number reads as "some transistor" by its shape; Central Semiconductor's sheet says the 2N2646 is
    # a unijunction transistor, and that is the answer returned — with the basis, so the page can say why.
    assert catalogue.family_of("2N2646", KIND_MAP["bjt/jfet/mosfet"]) == ("ujt", "documented")
    assert catalogue.family_of("2N3904", KIND_MAP["bjt/jfet/mosfet"]) == ("transistor", "kind")
    assert catalogue.family_of("NOTAPART") == ("", "")


def test_lineage_runs_up_to_the_top():
    assert catalogue.lineage("bbd") == ["bbd", "processing", "ic"]
    assert catalogue.lineage("nothing") == []


@pytest.mark.parametrize("text,maker,lineage", [
    ("Texas Instruments (National Semiconductor)", "texas-instruments", ["national"]),
    ("onsemi (ex-Fairchild)", "onsemi", ["fairchild"]),
    ("fairchild (onsemi-hosted)", "fairchild", ["onsemi"]),
    ("Renesas (ex Intersil / RCA)", "renesas", ["intersil"]),      # RCA is too short a name to look for in prose
    ("Motorola (cross-reference only)", "motorola", []),
    ("Soviet (bilingual receiving-tube handbook)", "", []),
])
def test_a_datasheet_maker_line_names_the_publisher_and_its_lineage(text, maker, lineage):
    assert catalogue.maker_of(text) == (maker, lineage)


def test_a_relation_reads_both_ways_and_a_shared_sheet_lists_every_other_part():
    rel = {(r[0], r[1], r[2]) for r in catalogue.related("TL072")}
    assert ("next_generation_of", "TL072H", "in") in rel                     # TI: the H is the next generation
    assert ("same_datasheet", "TL074", "both") in rel and ("same_datasheet", "TL071", "both") in rel
    assert ("replacement_for", "2SK170", "out") in {(r[0], r[1], r[2]) for r in catalogue.related("LSK170")}
    assert catalogue.related("NOTAPART") == []
