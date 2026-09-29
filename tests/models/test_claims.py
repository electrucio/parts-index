"""What a model's author declares, read from the note over it. Every note here is written for the test,
in the styles vendor headers use, and none is a vendor's text."""
import pytest

from parts_index.models import claims as C


def note(*lines):
    return [(i + 1, C.comment("* " + x) if x else "") for i, x in enumerate(lines)]


def test_a_list_of_what_is_modelled_with_a_sentence_saying_what_is_not():
    got = C.parse(note("Our notes on this amplifier", "The following parameters are modeled:",
                       "   open loop gain and phase", "   slew rate", "   input voltage noise", "",
                       "   Offset voltage is static and does not vary", "   Distortion is not characterized"))
    assert got["yes"] == ["gain-phase", "noise", "slew"]
    assert got["no"] == ["distortion"]
    assert got["limits"] == ["vos-static"]
    assert got["lines"] == [[2, 5], [7, 8]]


def test_one_line_sentences_saying_what_is_not_modelled():
    got = C.parse(note("NOTE: this is for single device only", "- Noise is not modeled.",
                       "- Asymmetrical gain is not modeled."))
    assert got["no"] == ["gain-asymmetry", "noise"] and got["limits"] == ["single-channel"]


def test_an_empty_template_declares_nothing():
    assert C.parse(note("BEGIN Notes:", "", "Not Modeled:", "", "Parameters modeled include:", "END Notes")) == {}


def test_the_word_output_in_a_pin_diagram_is_not_a_claim():
    assert C.parse(note("Node assignments", "   non-inverting input", "   | inverting input",
                        "   | | output")) == {}


def test_a_sentence_broken_over_two_lines_is_read_whole():
    assert C.parse(note("Temperature effects are", "not modeled here."))["no"] == ["temperature"]


def test_a_list_of_what_is_not_modelled_and_a_sentence_ends_it():
    got = C.parse(note("THIS MODEL WILL NOT PROVIDE ACCURATE SIMULATION OF:", "OUTPUT IMPEDANCE, DISTORTION",
                       "The bandwidth of this model is lower than the part's", "SLEW RATE"))
    assert got["no"] == ["distortion", "output-impedance"]
    assert "yes" not in got                    # the sentence ended the list, and says nothing modelled


def test_current_noise_is_not_mistaken_for_voltage_noise_and_both_are_read_when_both_are_named():
    assert C.parse(note("Not Modeled:", "  input current noise"))["no"] == ["current-noise"]
    assert C.parse(note("Voltage and current noise density are accurate"))["yes"] == ["current-noise", "noise"]


@pytest.mark.parametrize("line, sim", [("Simulator: PSpice", "pspice"), ("SIMULATOR=SIMETRIX", "simetrix"),
                                       ("Use SPICE 2G6 or later", "spice2"), ("An old TopSPICE banner", "topspice"),
                                       ("Measured against the PSpice result", None)])
def test_the_simulator_a_model_was_written_for_is_read_only_where_it_is_named(line, sim):
    assert C.parse(note(line)).get("simulator") == sim


LIB = """* A library of two models; this note heads the file
* Noise is not modeled.
.SUBCKT AMPA 1 2 3 4 5
R1 1 2 1K
.ENDS
* The second one
.SUBCKT AMPB 1 2 3 4 5
* FEATURES MODELED ARE
* SLEW RATE
* OUTPUT SWING
R1 1 2 1K
.ENDS
"""


def test_a_note_heading_a_library_is_kept_apart_and_a_body_note_is_read():
    a = C.read_model(LIB, "AMPA")
    assert a["no"] == ["noise"] and a["scope"] == "file"
    b = C.read_model(LIB, "AMPB")
    assert b["yes"] == ["output-swing", "slew"] and "scope" not in b
    assert b["lines"] == [[8, 10]]


def test_every_claim_and_limit_the_parser_can_give_is_in_the_vocabulary():
    from parts_index.models import behaviours
    assert {cid for cid, _ in C.TERMS} <= set(behaviours.CLAIMS)
    assert {lid for lid, _ in C.LIMITS} <= set(behaviours.LIMITS)


def test_a_model_made_at_room_temperature_is_one_that_does_not_model_temperature():
    got = C.parse(note("Parts in this library are modeled at ambient room temperature (TA=25C)"))
    assert got["limits"] == ["25c-only"] and "yes" not in got
    assert C.parse(note("Parameters at 25C and +/-15V only."))["limits"] == ["25c-only"]

