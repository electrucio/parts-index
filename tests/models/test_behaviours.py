"""The vocabulary the sheet's rows, the cards and the authors' headers meet in."""
import json

from parts_index.core import config
from parts_index.models import behaviours as B


def test_the_site_reads_the_same_vocabulary():
    """The site's tests check every claim has its words; they read this fixture, so it must be current."""
    fixture = json.loads((config.tests_fixtures() / "behaviours.json").read_text(encoding="utf-8"))
    assert fixture == B.vocabulary()


def test_every_row_claim_and_limit_names_a_known_behaviour():
    for table in B.SYMBOLS.values():
        assert set(table.values()) <= set(B.BEHAVIOURS)
    assert set(B.CLAIMS.values()) <= set(B.BEHAVIOURS)
    assert set(B.LIMITS.values()) <= set(B.BEHAVIOURS)


def test_the_same_symbol_can_measure_different_things_in_two_kinds():
    assert B.of_row("jfet", "idss") == "dc" and B.of_row("mosfet", "idss") == "leakage"
    assert B.of_row("bjt-ge", "cob") == "capacitance"
    assert B.of_row("tube", "gm") is None                  # no vocabulary for valves yet


def test_small_signal_gain_is_dc_like_at_a_kilohertz_and_a_frequency_response_at_a_hundred_megahertz():
    assert B.of_row("bjt", "hfe", {"F": 1e3}) == "dc"
    assert B.of_row("bjt", "hfe", {"F": 100e6}) == "frequency"
