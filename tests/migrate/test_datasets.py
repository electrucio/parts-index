"""Reading a part off a schematic sheet, and what must not be read off one."""
from __future__ import annotations

import csv

import pytest
import yaml

from parts_index.core.config import dataset_table, datasets_registry
from parts_index.migrate import datasets as D

KICAD6 = """(kicad_sch (version 20211123)
  (lib_symbols
    (symbol "Transistor_BJT:2N3055" (property "Value" "2N3055" (id 1)))
  )
  (symbol (lib_id "Transistor_BJT:2N3055") (property "Value" "BC237B" (id 1)))
  (symbol (lib_id "Device:R") (property "Value" "10k" (id 1)))
)"""
KICAD5 = 'L Device:R R1\nF 0 "R1" H 100 100 50\nF 1 "TL072CP" H 100 0 50\n'
EAGLE = '<part name="IC1" library="linear" deviceset="NE5532" value="NE5534"/>\n<part name="R1" value="4k7"/>'


def test_the_symbol_a_designer_picked_is_not_the_part():
    """A BC237B is routinely drawn with the library symbol for a 2N3055."""
    vals = D.placed_values(KICAD6)
    assert "BC237B" in vals
    assert "2N3055" not in vals          # it is only in lib_symbols, which is not a placement


@pytest.mark.parametrize("text,expected", [(KICAD5, "TL072CP"), (EAGLE, "NE5534")])
def test_the_other_two_formats_are_read_too(text, expected):
    assert expected in D.placed_values(text)


def test_eagle_falls_back_to_the_deviceset_only_when_there_is_no_value():
    assert "NE5532" not in D.placed_values(EAGLE)      # it has a value of its own
    assert "NE5532" in D.placed_values('<part name="IC1" deviceset="NE5532"/>')


@pytest.mark.parametrize("written,part", [
    ("TL072", "TL072"),
    ("TL072CP", "TL072"),          # package suffix
    # The part inside a phrase. BC547B resolves to itself, not to BC547: the grade letter is a
    # separate entry in the dictionary, because a B and a C grade are different parts to model.
    ("Q_NPN BC547B", "BC547B"),
    ("TL072_dual", "TL072"),
])
def test_a_written_value_is_resolved_to_the_catalogue_part(written, part):
    got = D.lookup(written)
    assert got == part, f"{written!r} -> {got!r}"


@pytest.mark.parametrize("junk", ["GND", "+5V", "10k", "PWR_FLAG", "MountingHole", "100nF", "TestPoint"])
def test_what_is_written_on_a_sheet_and_is_not_a_part_is_dropped(junk):
    """By count these dominate: one shard held 747 values that were parts and 17,506 that were not."""
    assert D.lookup(junk) is None


def test_the_unreliable_column_is_dropped_rather_than_published_with_a_warning(tmp_path, monkeypatch):
    root = tmp_path / "sch-datasets"
    (root / "component_stats" / "clean").mkdir(parents=True)
    (root / "component_stats" / "clean" / "parts.csv").write_text(
        "part,manufacturer,count,masala_spice\nTL072,TI,9,3\n", encoding="utf-8")
    monkeypatch.setattr(D, "dataset_table", lambda name: tmp_path / f"{name}.csv")
    got = D.part_stats(root)
    assert got["rows"] == 1
    with open(tmp_path / "part_stats.csv", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    assert "masala_spice" not in row and row["part"] == "TL072"


def test_the_registry_is_written_in_english_and_names_a_licence_for_each(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "datasets_registry", lambda: tmp_path / "registry.yaml")
    monkeypatch.setattr(D, "remotes", lambda root: {})
    D.registry(tmp_path)
    doc = yaml.safe_load((tmp_path / "registry.yaml").read_text(encoding="utf-8"))
    assert len(doc["datasets"]) == len(D.DATASETS)
    for e in doc["datasets"]:
        assert e["licence"] and e["source"], e["id"]
    assert doc["not_available"]


PUBLISHED = dataset_table("part_repos")


@pytest.mark.skipif(not PUBLISHED.is_file(), reason="datasets not distilled yet")
def test_the_table_publishes_a_link_and_nothing_copied_from_the_project():
    """The repository name is the tail of the link, and its blurb is third-party prose — one of them
    named a student. Part, how many sheets, and where to look."""
    with open(PUBLISHED, encoding="utf-8") as fh:
        fields = next(csv.reader(fh))
    assert fields == ["part", "sheets", "url"]


@pytest.mark.skipif(not PUBLISHED.is_file(), reason="datasets not distilled yet")
def test_every_part_in_the_published_table_is_one_the_index_knows():
    """A row for a part with no page would point nowhere."""
    from parts_index.core.parts.extractor import KNOWN
    known = {p for p, _ in KNOWN.values()}
    with open(PUBLISHED, encoding="utf-8") as fh:
        parts = {r["part"] for r in csv.DictReader(fh)}
    assert not (parts - known)


@pytest.mark.skipif(not datasets_registry().is_file(), reason="datasets not distilled yet")
def test_the_published_registry_matches_the_table_it_is_built_from():
    doc = yaml.safe_load(datasets_registry().read_text(encoding="utf-8"))
    assert {e["id"] for e in doc["datasets"]} == {d["id"] for d in D.DATASETS}
