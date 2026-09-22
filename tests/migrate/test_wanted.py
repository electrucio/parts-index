"""Which parts are worth listing although the index has nothing of its own for them, and who says so."""
from __future__ import annotations

import csv

import pytest

from parts_index.core import config
from parts_index.migrate import wanted as W

MUSIKDING = """
bjt-ge:
  - {part: EFT83, priority: 2, note: 'musikding.de: Transistoren / Germanium Transistoren / Selektiert;
      Selektierter, rauscharmer PNP Germaniumtransistor mit einem Verstärkungsfaktor im Bereich von 40 bis 50.'}
"""
DATABOOKS = """
bjt:
  - {part: KSC1520, priority: 2, aliases: [2SC1520],
     note: 'Samsung Transistor Data Book Vol. 1, small signal (1988): NPN; 98 magazine pages'}
"""
DOCS = """
opamp:
  - {part: OPA604, priority: 1,
     note: 'audio docs: 63 documents (groupdiy_threads); Precision audio op amp [Burr-Brown]'}
"""


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DATA", tmp_path / "data")
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "wanted_musikding.yaml").write_text(MUSIKDING, encoding="utf-8")
    (root / "wanted_databooks.yaml").write_text(DATABOOKS, encoding="utf-8")
    (root / "wanted_audio_docs.yaml").write_text(DOCS, encoding="utf-8")
    (root / "wanted_survey.yaml").write_text("regulator:\n  - {part: AMS1117-3.3, note: 'survey: 897'}\n",
                                             encoding="utf-8")
    return root


def read():
    with open(config.wanted_parts(), encoding="utf-8") as f:
        return {r["part"]: r for r in csv.DictReader(f)}


def test_the_facts_cross_and_the_shop_copy_does_not(catalog):
    W.promote(catalog)
    r = read()["EFT83"]
    assert r["source"] == "musikding.de"
    assert r["category"] == "Transistoren / Germanium Transistoren / Selektiert"
    assert r["note"] == "PNP, hFE 40–50"           # what it states outright
    assert "rauscharmer" not in str(r)             # their own writing stays theirs


def test_a_databook_entry_names_the_book_and_how_much_it_was_talked_about(catalog):
    r = read() if config.wanted_parts().exists() else None
    W.promote(catalog)
    r = read()["KSC1520"]
    assert r["source"] == "Samsung Transistor Data Book Vol. 1, small signal (1988)"
    assert r["note"] == "98 magazine pages mention it"
    assert r["aliases"] == "2SC1520"


def test_a_part_seen_in_documents_keeps_its_maker(catalog):
    W.promote(catalog)
    assert read()["OPA604"]["note"] == "made by Burr-Brown"


def test_the_survey_list_is_left_out(catalog):
    """423 of its entries are 3.3 V LDOs for microcontroller boards: real, popular, and off the focus
    this index keeps."""
    W.promote(catalog)
    assert "AMS1117-3.3" not in read()
