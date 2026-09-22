"""The three pieces of the rule this stage is built on, each of which came from a real failure."""
import json

import pytest

from parts_index.schematics import summarise


# --- the excerpt has to contain every part asked about ----------------------------------------------
def test_a_part_past_a_fixed_cut_is_still_in_the_excerpt():
    # Electronics World 1960-07 p.82: the tubes sit at character 5,019, and a 4,000-character cut of the
    # page made the model answer, truthfully, that they were not there
    text = "Measuring meter resistance with a shunt. " + ("filler " * 3000) + "17 Tubes: 9001, 12A6, 12H6."
    got, missing = summarise.excerpt(text, ["12A6"])
    assert "12A6" in got and not missing
    assert "Measuring meter resistance" in got          # the head, which is what names the page
    assert "[...]" in got                               # and the gap is marked, not hidden


def test_a_part_is_found_however_the_page_spells_it():
    text = "Receivers for sale: BC-221 frequency meter, DM-34/BC.603 dynamotor."
    got, missing = summarise.excerpt(text, ["BC221", "BC603"])
    assert not missing and "BC-221" in got


def test_a_part_the_page_does_not_have_is_reported_rather_than_hidden():
    _, missing = summarise.excerpt("a page about something else entirely", ["ECC83"])
    assert missing == ["ECC83"]


def test_the_excerpt_stays_within_its_cap():
    text = " ".join(f"word{i} ECC83" for i in range(4000))
    got, _ = summarise.excerpt(text, ["ECC83"], cap=6000)
    assert len(got) <= 6000


# --- what comes back is checked against what was asked ----------------------------------------------
def test_an_answer_is_kept_only_for_the_parts_that_were_asked_about():
    answer = summarise.read_answer(json.dumps({
        "page": "Trainwreck Express guitar amplifier schematic",
        "parts": [{"part": "12AX7", "kind": "project", "line": "Preamp stage V1A"},
                  {"part": "EL34", "kind": "project", "line": "Power tube option for V4"},
                  {"part": "6V6", "kind": "project", "line": "invented, nobody asked"}]}),
        ["12AX7", "EL34"])
    assert set(answer["parts"]) == {"12AX7", "EL34"}
    assert answer["parts"]["12AX7"]["line"] == "Preamp stage V1A"
    assert answer["v"] == summarise.VERSION


def test_a_kind_this_project_does_not_use_becomes_none():
    answer = summarise.read_answer(
        '{"page": "p", "parts": [{"part": "ECC83", "kind": "schematic", "line": "somewhere"}]}', ["ECC83"])
    assert answer["parts"]["ECC83"]["kind"] == "none"


def test_a_part_left_unanswered_is_written_down():
    answer = summarise.read_answer(
        '{"page": "p", "parts": [{"part": "ECC83", "kind": "project", "line": "preamp"}]}',
        ["ECC83", "EL34"])
    assert answer["missing"] == ["EL34"]


def test_an_answer_about_none_of_the_parts_is_not_an_answer():
    # it raises, so `ask_local` leaves the page unanswered and the next run asks again
    with pytest.raises(ValueError):
        summarise.read_answer('{"page": "p", "parts": [{"part": "XX", "kind": "none", "line": "no"}]}',
                              ["ECC83"])
    with pytest.raises(Exception):
        summarise.read_answer("I am sorry, I cannot read this page", ["ECC83"])


# --- the cache key carries the version, which is how this stage is re-run ---------------------------
def test_bumping_the_version_asks_the_corpus_again():
    page = {"source": "esp", "key": "https://example.invalid/a.pdf", "page": 3}
    was = summarise.key_of(page)
    summarise.VERSION, old = "summarise-2", summarise.VERSION
    try:
        assert summarise.key_of(page) != was
    finally:
        summarise.VERSION = old


def test_the_prompt_names_the_document_the_parts_and_their_designators():
    text = summarise.prompt({"title": "Trainwreck express", "source": "el34world", "role": "schematic",
                             "page": 9, "excerpt": "V1A 12AX7 preamp",
                             "parts": [{"part": "12AX7", "times": 2, "near": "V1 V2"}]})
    assert "Trainwreck express" in text and "12AX7" in text and "beside V1 V2" in text
    assert "read 2x" in text
