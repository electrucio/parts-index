"""What reaches `data/` from the index, and what is refused.

Runs against `tests/fixtures/mini_corpus.sql`, so it needs none of the maintainer's 3.9 GB database.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from parts_index.core import config
from parts_index.schematics import export as E

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mini_corpus.sql"
REGISTRY = """
esp: {kind: site, title: Elliott Sound Products, home_url: 'https://e.org/', status: active}
books: {kind: book, title: Books, home_url: 'https://archive.org/', status: active}
wireless_world: {kind: magazine, title: Wireless World, home_url: 'https://e.org/', status: active}
"""


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A public data root and a database built from the fixture."""
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    db_path = tmp_path / "index.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(FIXTURE.read_text(encoding="utf-8"))
    con.commit()
    con.close()
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setattr(E, "index_db", lambda: db_path)
    monkeypatch.setattr(E, "index_db_uri", lambda **k: f"file:{db_path}?mode=ro")
    return data / "schematics"


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_only_a_link_we_can_stand_behind_is_published(corpus):
    E.export()
    keys = {r["key"] for s in ("esp", "books") for r in read(corpus / "documents" / f"{s}.csv")}
    assert "https://e.org/amp.pdf" in keys                      # we hold its checksum
    assert "https://archive.org/details/radio-handbook" in keys  # a person checked the link
    assert "https://e.org/reader/tubes" in keys                  # the link is a search, not a location
    assert "https://e.org/unchecked.html" not in keys            # none of the three


def test_a_price_list_is_not_a_use(corpus):
    """A part number on a mail-order page means somebody sold it, not that it was used in anything."""
    E.export()
    pages = {int(r["page"]) for r in read(corpus / "pages" / "wireless_world.csv")}
    assert 81 not in pages and 47 in pages


def test_a_doubtful_reading_is_dropped_and_its_page_survives(corpus):
    E.export()
    uses = read(corpus / "uses" / "wireless_world.csv")
    assert {u["part"] for u in uses} == {"12AX7"}      # the medium-confidence 2N3O55 is gone


def test_the_viewer_is_told_where_to_look_when_it_can_be(corpus):
    E.export()
    by_page = {int(r["page"]): r["url"] for r in read(corpus / "pages" / "esp.csv")}
    assert by_page[2] == "https://e.org/amp.pdf#page=2&zoom=200,55,523&h=792"
    books = {int(r["page"]): r["url"] for r in read(corpus / "pages" / "books.csv")}
    # no page size recorded, so the plain page link; and archive.org counts leaves from zero
    assert books[5] == "https://archive.org/details/radio-handbook/page/n16/mode/2up"


def test_a_title_written_for_a_browser_tab_is_cleaned_up(corpus):
    E.export()
    by_key = {r["key"]: r["title"] for r in read(corpus / "documents" / "esp.csv")}
    assert by_key["https://e.org/amp.pdf"] == "60W Amplifier"      # site name stripped off both ends
    assert by_key["https://e.org/fig/amp-psu.gif"] == "60W Amplifier"   # a figure borrows its parent's


def test_a_figure_keeps_its_own_row_and_points_at_its_parent(corpus):
    E.export()
    docs = {r["key"]: r for r in read(corpus / "documents" / "esp.csv")}
    fig = docs["https://e.org/fig/amp-psu.gif"]
    assert fig["role"] == "figure"
    assert fig["parent"] == docs["https://e.org/amp.pdf"]["id"]


def test_only_designators_survive_in_near_and_at_most_four(corpus):
    """"page 47" is not much; "R3 and IC1 on page 47" is a result. Anything else on the line is noise."""
    E.export()
    doc = next(r["id"] for r in read(corpus / "documents" / "esp.csv")
               if r["key"] == "https://e.org/amp.pdf")
    use = next(r for r in read(corpus / "uses" / "esp.csv")
               if r["part"] == "12AX7" and r["doc"] == doc)
    assert use["near"] == "V1 R3 C12 Q4"          # 'xx' is not a designator; R9 is the fifth


def test_a_withdrawn_document_is_dropped_and_keeps_its_id(corpus):
    E.export()
    docs = read(corpus / "documents" / "esp.csv")
    gone = next(r for r in docs if r["key"] == "https://e.org/gone.pdf")
    taken = gone["id"]

    (corpus / "withdrawn.csv").write_text(
        "key,why,when\nhttps://e.org/gone.pdf,taken down by the site,2026-09-21\n", encoding="utf-8")
    E.export()
    after = read(corpus / "documents" / "esp.csv")
    assert all(r["key"] != "https://e.org/gone.pdf" for r in after)
    assert all(r["id"] != taken for r in after), "an id in use elsewhere must not be handed on"


def test_an_id_survives_a_re_export(corpus):
    """People link to these pages, so a re-export must not renumber them."""
    E.export()
    before = {r["key"]: r["id"] for r in read(corpus / "documents" / "esp.csv")}
    E.export()
    assert {r["key"]: r["id"] for r in read(corpus / "documents" / "esp.csv")} == before


def test_parts_and_the_manifest_agree_with_the_rows(corpus):
    E.export()
    parts = {r["part"]: r for r in read(corpus / "parts.csv")}
    assert parts["12AX7"]["sources"] == "books esp wireless_world"
    assert int(parts["12AX7"]["uses"]) == 4
    manifest = json.loads((corpus / "export.json").read_text(encoding="utf-8"))
    assert manifest["version"] == E.VERSION
    assert manifest["totals"]["uses"] == sum(s["uses"] for s in manifest["sources"].values())
    assert manifest["sources"]["esp"]["title"] == "Elliott Sound Products"


def test_exporting_one_source_leaves_the_others_alone(corpus):
    E.export()
    before = (corpus / "uses" / "books.csv").read_text(encoding="utf-8")
    E.export(["esp"])
    assert (corpus / "uses" / "books.csv").read_text(encoding="utf-8") == before
