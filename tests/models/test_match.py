"""Which definitions in the catalogue count as candidates for a wanted part, and why."""
from __future__ import annotations

import json

from parts_index.models import match as M


def rec(name, source="acme", type="NPN", kind="model", parent=None, file=None):
    return {"source": source, "file": file or f"sources/{source}/raw/{name}.lib", "name": name, "kind": kind,
            "type": type, "pins": [], "encrypted": False, "mfg": None, "parent": parent}


def found(wanted, recs):
    return {p: [(c["name"], c["match"]) for c in v["candidates"]] for p, v in M.find(wanted, recs).items()}


def test_a_spice_prefix_before_a_digit_is_not_part_of_the_name():
    got = found({"bjt": [{"part": "2N3904"}]}, [rec("Q2N3904"), rec("2N3904")])
    assert got == {"2N3904": [("Q2N3904", "exact"), ("2N3904", "exact")]}


def test_a_tag_of_up_to_four_letters_is_a_suffix_and_a_digit_starts_another_part():
    got = found({"bjt": [{"part": "MJ15001"}]}, [rec("MJ15001M"), rec("MJ150012"), rec("MJ15001_ABCDE")])
    assert got == {"MJ15001": [("MJ15001M", "suffix")]}


def test_a_grade_letter_the_model_lacks_is_a_grade_match():
    got = found({"bjt": [{"part": "BC549C"}]}, [rec("BC549"), rec("BC54")])
    assert got == {"BC549C": [("BC549", "grade")]}


def test_a_model_of_the_wrong_device_type_is_dropped():
    got = found({"bjt": [{"part": "2N3904"}]}, [rec("2N3904", type="D"), rec("2N3904", type="SUBCKT", kind="subckt")])
    assert got == {"2N3904": [("2N3904", "exact")]}


def test_a_model_inside_another_subcircuit_is_not_a_candidate():
    got = found({"bjt": [{"part": "MJ15001"}]}, [rec("MJ15001", parent="MJ15001X")])
    assert got == {"MJ15001": []}


def test_an_ic_or_valve_is_only_ever_a_subcircuit():
    got = found({"tube": [{"part": "12AX7"}]}, [rec("12AX7", type="NPN"), rec("12AX7", type="SUBCKT", kind="subckt")])
    assert got == {"12AX7": [("12AX7", "exact")]}


def test_an_alias_is_searched_like_the_part_and_says_so():
    got = found({"tube": [{"part": "12AX7", "aliases": ["ECC83"]}]}, [rec("ECC83", type="SUBCKT", kind="subckt")])
    assert got == {"12AX7": [("ECC83", "alias:ECC83/exact")]}


def test_a_stand_in_is_used_only_when_the_part_has_nothing_of_its_own():
    wanted = {"bjt": [{"part": "BC183", "stand_in": ["BC547"]}]}
    assert found(wanted, [rec("BC547")]) == {"BC183": [("BC547", "stand-in:BC547/exact")]}
    assert found(wanted, [rec("BC547"), rec("BC183")]) == {"BC183": [("BC183", "exact")]}


def test_a_complement_named_only_as_a_field_becomes_a_part():
    got = M.find({"bjt": [{"part": "MJL3281A", "priority": 1, "complement": "MJL1302A"}]}, [rec("MJL1302A", type="PNP")])
    assert got["MJL1302A"]["priority"] == 1
    assert [c["name"] for c in got["MJL1302A"]["candidates"]] == ["MJL1302A"]


def test_components_we_draw_ourselves_are_not_matched():
    assert M.find({"non_native": [{"part": "potentiometer"}]}, [rec("POTENTIOMETER", type="SUBCKT", kind="subckt")]) == {}


def test_the_first_list_to_name_a_part_keeps_it():
    wanted = {"bjt": {"small": [{"part": "BC547B", "priority": 1}]}}
    M.merge(wanted, {"bjt": [{"part": "bc547b", "priority": 3}, {"part": "BC337", "priority": 2}]})
    assert wanted == {"bjt": {"small": [{"part": "BC547B", "priority": 1}],
                              "listed": [{"part": "BC337", "priority": 2}]}}


def test_generated_list_aliases_are_separated_by_spaces(tmp_path):
    p = tmp_path / "wanted.csv"
    p.write_text("part,kind,source,category,note,priority,aliases\n"
                 "6N3P,tube,databook,,,2,6S19P 6C19P\nX1,,shop,,,3,\n", encoding="utf-8")
    assert M.from_csv(p) == {"tube": [{"part": "6N3P", "priority": 2, "aliases": ["6S19P", "6C19P"]}]}


def test_parts_already_curated_are_looked_for_again(tmp_path):
    d = tmp_path / "bjt" / "MJ15001"
    d.mkdir(parents=True)
    (d / "part.json").write_text(json.dumps({"part": "MJ15001", "kind": "bjt", "group": "power_output",
                                             "priority": 3}), encoding="utf-8")
    assert M.from_curated(tmp_path) == {"bjt": {"power_output": [{"part": "MJ15001", "priority": 3}]}}


def test_definitions_that_cannot_match_anything_are_not_held(tmp_path):
    p = tmp_path / "index.jsonl"
    p.write_text("\n".join(json.dumps(dict(rec(n), params={"is": "1f"})) for n in ("Q2N3904", "BC547", "LM741"))
                 + "\n", encoding="utf-8")
    heads = M.names_wanted({"bjt": [{"part": "2N3904"}]})
    assert [r["name"] for r in M.load_definitions(p, heads)] == ["Q2N3904"]
    assert "params" not in M.load_definitions(p)[0]
