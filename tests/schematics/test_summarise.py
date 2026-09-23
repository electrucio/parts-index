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
    page = {"source": "esp", "key": "https://example.invalid/a.pdf", "page": 3,
            "parts": [{"part": "ECC83"}]}
    was = summarise.key_of(page)
    summarise.VERSION, old = summarise.VERSION + "-changed", summarise.VERSION
    try:
        assert summarise.key_of(page) != was
    finally:
        summarise.VERSION = old


PAGE = {"title": "Trainwreck express", "key": "https://el34world.invalid/tw.pdf", "source": "el34world",
        "role": "schematic", "page": 9, "excerpt": "V1A 12AX7 preamp",
        "parts": [{"part": "12AX7", "times": 2, "near": "V1 V2"}]}


def test_the_prompt_names_the_document_the_parts_and_their_designators():
    text = summarise.prompt(PAGE)
    assert "Trainwreck express" in text and "12AX7" in text and "beside V1 V2" in text
    assert "read 2x" in text
    assert "https://el34world.invalid/tw.pdf" in text          # the URL often says more than the title


def test_the_prompt_says_what_the_source_is_rather_than_its_id():
    """`el34world` tells the model nothing about what it is reading."""
    plain = summarise.prompt(PAGE)
    named = summarise.prompt(PAGE, {"el34world": "EL34 World - factory"})
    assert "SOURCE: el34world" in plain
    assert "SOURCE: EL34 World - factory" in named


def test_the_prompt_says_whether_the_page_is_a_scan_or_a_file():
    """Telling the model a blog page is scrambled OCR is false, and it is how a sidebar came to be read
    as a circuit. Saying which it is was the single change that caught the most non-uses."""
    scanned = summarise.prompt(dict(PAGE, read_as="ocr"))
    typed = summarise.prompt(dict(PAGE, read_as="text"))
    assert "scan read by OCR" in scanned
    assert "not a scan" in typed and "born-digital" in typed
    assert "scan read by OCR" in summarise.prompt(PAGE)        # no answer: assume the harder case


def test_a_part_that_is_named_but_not_used_has_a_kind_of_its_own():
    answer = summarise.read_answer(
        '{"page": "p", "parts": ['
        '{"part": "LT1037", "kind": "mention", "line": "suggested in a comment to replace the TLE2141"},'
        '{"part": "BD315", "kind": "none", "line": "an H.M.V. record number in a list of records"}]}',
        ["LT1037", "BD315"])
    assert answer["parts"]["LT1037"]["kind"] == "mention"      # a real part, offered as an alternative
    assert answer["parts"]["BD315"]["kind"] == "none"          # not a component at all


def test_a_page_with_one_part_still_gets_room_for_a_whole_answer():
    # a 165-token cap cut a one-part answer in half, and a cut-off answer is asked again for ever
    assert summarise.room_for(1) >= 350
    assert summarise.room_for(24) > summarise.room_for(4)
    assert summarise.room_for(500) <= 2600


def test_the_registry_is_read_the_way_it_is_written(tmp_path, monkeypatch):
    # it is a flat mapping of id to entry, and reading it as if the entries hung under a `sources:` key
    # gave a run over the whole corpus that quietly did nothing
    registry = tmp_path / "sources.yaml"
    registry.write_text("esp: {kind: site, title: ESP}\nbooks: {kind: book, title: Books}\n",
                        encoding="utf-8")
    monkeypatch.setattr(summarise, "schematics_registry", lambda: registry)
    assert summarise.sources() == ["books", "esp"]


def test_a_page_whose_parts_have_changed_is_asked_again():
    """Rule 5 skips an item when its stamp matches the input, and the input is the page AND what was
    asked of it: a part the extractor learns to read tomorrow must not be skipped for ever."""
    page = {"source": "esp", "key": "https://example.invalid/a.pdf", "page": 3,
            "parts": [{"part": "ECC83"}, {"part": "EL34"}]}
    same_parts_other_order = dict(page, parts=[{"part": "EL34"}, {"part": "ECC83"}])
    one_more_part = dict(page, parts=page["parts"] + [{"part": "6V6"}])
    assert summarise.key_of(page) == summarise.key_of(same_parts_other_order)
    assert summarise.key_of(page) != summarise.key_of(one_more_part)


def test_the_one_json_mistake_this_model_makes_is_repaired():
    """A trailing comma before a closing brace, in about one answer in fifty — thousands of pages over
    the corpus, and no reason to spend the call again."""
    answer = summarise.read_answer(
        '{"page": "a parts list", "parts": [\n'
        '{"part": "TL072", "kind": "reference", "line": "op-amps IC1 and IC2 in the parts list",},\n'
        '{"part": "1N914", "kind": "reference", "line": "diodes D2 and D4 in the parts list",},\n'
        ']}', ["TL072", "1N914"])
    assert set(answer["parts"]) == {"TL072", "1N914"}


def test_nothing_else_is_guessed_at():
    """Only that one repair: an answer broken some other way is asked again, not patched."""
    with pytest.raises(Exception):
        summarise.read_answer('{"page": "p", "parts": [{"part": "TL072" "kind": "reference"}]}', ["TL072"])


# --- an article runs over several pages and only the first names it ---------------------------------
def test_the_pages_of_one_document_are_asked_in_order_and_documents_are_independent():
    pages = [{"source": "pe", "key": "a", "page": 27}, {"source": "pe", "key": "a", "page": 24},
             {"source": "pe", "key": "b", "page": 3}]
    chains = summarise.chains_of(pages)
    assert sorted(len(c) for c in chains) == [1, 2]
    two = next(c for c in chains if len(c) == 2)
    assert [p["page"] for p in two] == [24, 27]


def test_a_continuation_page_is_told_what_the_page_before_it_was():
    """Practical Electronics 1971-04: the Aurora runs from page 24 to 28 and only page 24 names it."""
    earlier = [({"page": 24}, {"page": "P.E. Aurora light and colour control system"})]
    got = summarise.carried({"page": 25}, earlier)
    assert "p.24: P.E. Aurora" in got and "plainly the same article" in got


def test_a_page_far_from_the_last_one_inherits_nothing():
    """The queue holds only pages with a published use, so the previous one can be forty pages back."""
    earlier = [({"page": 24}, {"page": "P.E. Aurora light and colour control system"})]
    assert summarise.carried({"page": 24 + summarise.CARRY_GAP}, earlier)
    assert summarise.carried({"page": 24 + summarise.CARRY_GAP + 1}, earlier) == ""
    assert summarise.carried({"page": 20}, earlier) == ""          # and never backwards


def test_only_the_pages_next_door_are_carried():
    """The distance rule is the whole of it: at most CARRY_GAP pages can be within CARRY_GAP."""
    earlier = [({"page": n}, {"page": f"page {n}"}) for n in range(1, 8)]
    got = summarise.carried({"page": 8}, earlier)
    assert got.count("  p.") == summarise.CARRY_GAP
    assert "p.7" in got and "p.6" in got and "p.5" not in got


# --- a web page's first words are its menu, not its standfirst --------------------------------------
def test_the_furniture_of_a_web_page_is_marked_as_furniture():
    text = "Home About Tags ESP8266 Raspberry " + " ".join(f"w{i}" for i in range(60)) + " TL072 input buffer"
    web, _ = summarise.excerpt(text, ["TL072"], head=5, around=4, web=True)
    assert web.startswith("[top of the web page")
    assert "[end of the page furniture" in web
    scan, _ = summarise.excerpt(text, ["TL072"], head=5, around=4, web=False)
    assert "[top of the web page" not in scan and "[end of the page furniture" not in scan


def test_the_prompt_carries_the_earlier_pages_when_there_are_any():
    assert "EARLIER PAGES" not in summarise.prompt(PAGE)
    assert "EARLIER PAGES" in summarise.prompt(PAGE, None, "EARLIER PAGES OF THIS DOCUMENT\n\n")


def test_a_line_longer_than_a_line_is_cut():
    long = "x " * 300
    answer = summarise.read_answer(
        json.dumps({"page": long, "parts": [{"part": "TL072", "kind": "project", "line": long}]}), ["TL072"])
    assert len(answer["parts"]["TL072"]["line"]) <= summarise.LINE_CHARS
    assert len(answer["page"]) <= summarise.LINE_CHARS


def test_a_cache_key_is_read_whatever_version_wrote_it():
    """The key gained a field when the asked parts went into it, and the cache keeps its own history."""
    new = summarise.parse_key("summarise-3|esp|https://e.org/a.pdf|7|9e7da777")
    old = summarise.parse_key("summarise-1|esp|https://e.org/a.pdf|7")
    assert new == ("summarise-3", "esp", "https://e.org/a.pdf", 7)
    assert old == ("summarise-1", "esp", "https://e.org/a.pdf", 7)
