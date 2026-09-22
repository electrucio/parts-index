"""What one part's page carries, and what it leaves out."""
from __future__ import annotations

import csv

import pytest

from parts_index.core import config
from parts_index.web import parts as P

SOURCES = ["esp", "el34world"]


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A tiny exported index: one sheet published twice, and one part with a model."""
    root = tmp_path / "data"
    monkeypatch.setattr(config, "PUBLIC_DATA", root)
    (root / "schematics").mkdir(parents=True)

    def put(path, fields, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(fields)
            w.writerows(rows)

    put(config.schematics_documents("esp"),
        ("id", "key", "title", "url", "parent", "role", "year", "month", "pages", "sha"),
        [["0", "k1", "Bassman 5F6-A", "https://esp.example/bassman.pdf", "", "schematic", "1959", "", "1", "deadbeef"],
         ["1", "k2", "Opamp Bypassing", "https://esp.example/p00.htm", "", "project_page", "", "", "1", "cafe"]])
    put(config.schematics_pages("esp"), ("doc", "page", "url", "schematic", "parts"),
        [["0", "1", "https://esp.example/bassman.pdf#page=1&zoom=200,10,20&h=792", "1", "9"],
         ["1", "1", "https://esp.example/p00.htm", "0", "2"]])
    put(config.schematics_uses("esp"), ("part", "doc", "page", "times", "near"),
        [["12AX7", "0", "1", "2", "V1 V2"], ["TL072", "1", "1", "1", "IC1"]])

    (root / "schematics" / "sources.yaml").write_text(
        "esp: {kind: site, title: ESP, home_url: 'https://e.org/', status: active}\n"
        "el34world: {kind: factory, title: El34World, home_url: 'https://el34.example/', status: active}\n",
        encoding="utf-8")
    put(config.schematics_documents("el34world"),
        ("id", "key", "title", "url", "parent", "role", "year", "month", "pages", "sha"),
        [["0", "k3", "Fender Bassman", "https://el34.example/bassman.pdf", "", "schematic", "1959", "", "1", "deadbeef"]])
    put(config.schematics_pages("el34world"), ("doc", "page", "url", "schematic", "parts"),
        [["0", "1", "https://el34.example/bassman.pdf#page=1", "1", "9"]])
    put(config.schematics_uses("el34world"), ("part", "doc", "page", "times", "near"),
        [["12AX7", "0", "1", "1", ""]])

    put(config.schematics_parts(), ("part", "documents", "pages", "uses", "sources"),
        [["12AX7", "2", "2", "2", "el34world esp"], ["TL072", "1", "1", "1", "esp"]])

    recipe = config.model_part("opamp", "TL072")
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text(
        "part: TL072\nkind: opamp\npreferred: ti\npreferred_why: best agreement\n"
        "models:\n"
        "- source: ti\n  name: TL072\n  def: subckt\n  verbatim: true\n  symbol: TL072_ti.asy\n"
        "  get: {url: 'https://ti.example/tl072.lib', sha256: aa, lines: {TL072: [1, 9]}}\n"
        "  verification: {score: 1.0, pass: 6, marginal: 0, fail: 0}\n",
        encoding="utf-8")
    return root


def test_one_sheet_published_twice_is_one_result_that_names_the_other(data):
    idx = P.index()
    page = P.part_payload("12AX7", idx, None)
    assert len(page["docs"]) == 1
    assert page["docs"][0]["also"] == ["el34world"]
    assert page["n"]["copies"] == 1


def test_a_page_link_travels_with_its_deep_link(data):
    idx = P.index()
    page = P.part_payload("12AX7", idx, None)
    assert page["docs"][0]["p"][0][1].endswith("&zoom=200,10,20&h=792")


def test_the_recipe_is_trimmed_to_what_the_page_shows_and_carries_no_model_text(data):
    idx = P.index()
    recipes = P.model_recipes()
    page = P.part_payload("TL072", idx, recipes["TL072"])
    m = page["models"]["models"][0]
    assert m["source"] == "ti" and m["symbol"] == "TL072_ti.asy"
    assert m["get"]["url"] == "https://ti.example/tl072.lib"
    assert "lines" not in m["get"] and "sha256" not in m["get"]   # the page does not need them
    assert m["score"] == 1.0 and m["rows"] == [6, 0, 0]


def test_the_source_names_are_not_repeated_in_every_part_file(data):
    """They are the same in all of them; repeating them cost 90 MB across 15,558 files."""
    page = P.part_payload("12AX7", P.index(), None)
    assert "sources" not in page


def test_the_search_index_holds_every_part_from_either_side(data):
    idx = P.index()
    rows = P.search_index(idx, P.model_recipes())
    assert [r[0] for r in rows] == ["12AX7", "TL072"]
    assert dict((r[0], r[3]) for r in rows)["TL072"] == 1     # one model candidate


def test_a_part_in_everything_is_capped_and_says_so(data, monkeypatch):
    monkeypatch.setattr(P, "CAP", 1)
    page = P.part_payload("12AX7", P.index(), None)
    assert page["n"]["shown"] == 1 and page["n"]["documents"] == 1


def test_a_part_carries_the_open_source_projects_that_place_it(data, monkeypatch):
    """The third answer to "where is it used", and the only one pointing at a live board."""
    table = config.dataset_table("part_repos")
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("part,sheets,url\n"
                     "12AX7,3,https://github.com/a/one\n"
                     "12AX7,1,https://github.com/b/two\n", encoding="utf-8")
    page = P.part_payload("12AX7", P.index(), None)
    assert page["n"]["repos"] == 2
    assert page["repos"][0] == ["a/one", 3]        # the one that places it most, first


def test_the_index_says_what_kind_of_thing_each_source_is(data):
    """A factory sheet, a magazine page and a GitHub board are three different answers, so the page
    groups them apart — which it can only do if it knows which is which."""
    idx = P.index()
    assert idx["kinds"]["esp"] == "site"
    assert idx["kinds"]["el34world"] == "factory"
