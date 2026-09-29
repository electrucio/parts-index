"""Which way round a transistor is, and when nothing may be said of it."""
import pytest

from parts_index.core.parts import polarity


def test_a_library_that_disagrees_alone_is_outvoted_and_a_split_says_nothing():
    ten = {f"lib{i}" for i in range(10)}
    # 2N4403: ten libraries, onsemi's among them, say PNP; groups.io's standard.bjt says NPN
    assert polarity.by_libraries({"PNP": ten, "NPN": {"groupsio-ltspice"}}) == ["PNP"]
    # 2N1132: four to three is doubt
    assert polarity.by_libraries({"NPN": {"a", "b", "c", "d"}, "PNP": {"e", "f", "g"}}) == []
    assert polarity.by_libraries({"NPN": {"a", "b"}, "PNP": {"c"}}) == []
    assert polarity.by_libraries({"N-channel": {"a"}}) == ["N-channel"]
    assert polarity.by_libraries({}) == []


def test_a_bipolar_and_a_channel_are_different_questions():
    """J410 is an N-channel JFET in six libraries and an NPN model in one; neither outvotes the other."""
    assert polarity.by_libraries({"N-channel": {"a", "b"}, "NPN": {"c"}}) == ["NPN", "N-channel"]
    assert polarity.settled([["NPN", "name"], ["N-channel", "model"]]) == {"bipolar": "NPN", "fet": "N-channel"}


def test_sources_that_disagree_settle_nothing():
    assert polarity.settled([["PNP", "name"], ["PNP", "model"]]) == {"bipolar": "PNP"}
    assert polarity.settled([["PNP", "name"], ["NPN", "catalogue"]]) == {}


@pytest.mark.parametrize("text,said", [
    ("General Purpose and Low VCE(sat) Transistor > PNP Transistor", "PNP"),
    ("2N7002L 6V N-channel MOSFET", "N-channel"),
    ("P-Channel", "P-channel"),
    ("Silicon NPN Epitaxial Planar", "NPN"),
    ("Bipolar Transistors > Bipolar Transistors", ""),
    ("NPN/PNP general purpose double transistor", ""),
    ("Dual N- and P-channel MOSFET", ""),
    ("N/P-Channel enhancement pair", ""),
    # the 2SC3264's sheet, filed under 2SA1295 too because it names it
    ("Silicon NPN Epitaxial Planar Transistor (Complement to type 2SA1295)", ""),
])
def test_a_catalogue_names_one_polarity_or_none(text, said):
    assert polarity.in_words(text) == said
