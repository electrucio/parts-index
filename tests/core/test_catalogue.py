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
