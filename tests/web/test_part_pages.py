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
    put(config.schematics_lines("esp"), ("doc", "page", "part", "kind", "line"),
        [["0", "1", "12AX7", "project", "First and second preamp stages V1 and V2 of the Bassman 5F6-A."]])

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
    recipes, _ = P.model_recipes()
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
    recipes, _ = P.model_recipes()
    rows, menu = P.search_index(idx, recipes)
    assert [r[0] for r in rows] == ["12AX7", "TL072"]
    assert dict((r[0], r[3]) for r in rows)["TL072"] == 1     # one model candidate
    at = {d["key"]: i for i, d in enumerate(menu)}
    assert dict((r[0], r[4]) for r in rows)["TL072"] & (1 << at["opamp"])   # from its recipe
    assert dict((r[0], r[4]) for r in rows)["12AX7"] & (1 << at["tube"])    # from the dictionary


def test_a_part_page_says_how_many_documents_and_how_many_copies_were_folded(data):
    page = P.part_payload("12AX7", P.index(), None)
    assert page["n"] == {"documents": 1, "shown": 1, "copies": 1}


def test_a_part_carries_the_open_source_projects_that_place_it(data, monkeypatch):
    """The third answer to "where is it used", and the only one pointing at a live board."""
    table = config.dataset_table("part_repos")
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("part,sheets,url\n"
                     "12AX7,3,https://github.com/a/one\n"
                     "12AX7,1,https://github.com/b/two\n", encoding="utf-8")
    page = P.part_payload("12AX7", P.index(), None)
    assert page["n"]["repos"] == 2
    # with no attention read yet, the one that places it on most sheets leads
    assert page["repos"][0][:2] == ["a/one", 3]


def test_the_index_says_what_kind_of_thing_each_source_is(data):
    """A factory sheet, a magazine page and a GitHub board are three different answers, so the page
    groups them apart — which it can only do if it knows which is which."""
    idx = P.index()
    assert idx["kinds"]["esp"] == "site"
    assert idx["kinds"]["el34world"] == "factory"


def test_a_page_link_is_stored_as_what_to_add_to_its_document(data):
    """All 94,170 of them are a suffix of the document's URL; writing them whole was three quarters of
    the URL text on a part's page, and that was the reason to cut documents that should not be cut."""
    page = P.part_payload("12AX7", P.index(), None)
    link = page["docs"][0]["p"][0][1]
    assert link.startswith("#page=")
    assert page["docs"][0]["u"] + link == \
        "https://esp.example/bassman.pdf#page=1&zoom=200,10,20&h=792"


def test_nothing_is_cut_from_a_part(data):
    """The 12AX7 is in 1,817 documents across 33 sources. Keeping the top two hundred meant 147 factory
    sheets crowding out Wireless World and Elektor, which is the part of the answer people want."""
    idx = P.index()
    for part in ("12AX7", "TL072"):
        page = P.part_payload(part, idx, None)
        assert page["n"]["shown"] == page["n"]["documents"]
        assert all("more" not in d for d in page["docs"])


def test_a_part_filed_under_two_kinds_is_reported_rather_than_hidden(data):
    """Five are, each curated once as silicon and once as germanium. Under the Pro-Electron convention
    the first letter settles it — B is silicon — but until the curation is merged, keeping one quietly
    is how the wrong one won: `bjt-ge` sorts after `bjt`."""
    other = config.model_part("bjt-ge", "TL072")
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("part: TL072\nkind: bjt-ge\nmodels: []\n", encoding="utf-8")
    recipes, clashes = P.model_recipes()
    assert clashes == ["TL072"]
    assert recipes["TL072"]["kind"] == "opamp"       # the one with more candidates, not the last read


def test_a_part_answers_to_every_device_it_could_be(data):
    """A JEDEC number cannot be told apart by its pattern: 2N3904 is a transistor, 2N5457 a JFET.
    Guessing one would hide the other, and the menu is a way of finding things."""
    at = {k: i for i, (k, _) in enumerate(P.DEVICES)}
    bits = P.device_bits("bjt/jfet/mosfet")
    for d in ("bjt", "jfet", "mosfet"):
        assert bits & (1 << at[d]), d
    assert not bits & (1 << at["tube"])


def test_every_kind_the_data_carries_is_mapped_or_deliberately_not(data):
    """An unmapped kind silently drops its parts out of every menu entry."""
    from parts_index.core.parts.extractor import FAMILIES
    for _family, kind, _rx, _strict in FAMILIES:
        assert kind in P.KIND_MAP, f"the extractor can produce {kind!r} and nothing maps it"


def test_the_menu_ships_whole_so_a_bit_always_means_the_same_device(data):
    """The bit a part carries is a position in this menu. Dropping the devices nothing answers to would
    renumber the rest and the filter would quietly select the wrong one; the site hides them instead."""
    idx = P.index()
    recipes, _ = P.model_recipes()
    rows, menu = P.search_index(idx, recipes)
    assert [d["key"] for d in menu] == [k for k, _ in P.DEVICES]
    at = {d["key"]: i for i, d in enumerate(menu)}
    assert dict((r[0], r[4]) for r in rows)["TL072"] & (1 << at["opamp"])


def test_the_projects_are_ordered_by_stars_and_the_dead_ones_dropped(data):
    """287 projects place a TL072; what a reader wants is the five anybody has looked at."""
    config.dataset_table("part_repos").parent.mkdir(parents=True, exist_ok=True)
    config.dataset_table("part_repos").write_text(
        "part,sheets,url\n"
        "12AX7,1,https://github.com/a/small\n"
        "12AX7,9,https://github.com/b/big\n"
        "12AX7,1,https://github.com/c/gone\n", encoding="utf-8")
    config.dataset_table("repo_stats").write_text(
        "url,status,stars,forks,watchers,pushed,archived,moved_to,checked\n"
        "https://github.com/a/small,live,3,0,1,2026-01-01,0,,2026-09-22\n"
        "https://github.com/b/big,live,900,50,30,2026-01-01,0,https://github.com/b/renamed,2026-09-22\n"
        "https://github.com/c/gone,gone,,,,,,,2026-09-22\n", encoding="utf-8")
    page = P.part_payload("12AX7", P.index(), None)
    assert [r[0] for r in page["repos"]] == ["b/renamed", "a/small"]   # stars first, renamed followed
    assert page["repos"][0][2] == 900


def test_a_page_link_carries_the_line_saying_what_the_part_does_there(data):
    """"page 47" is a link and not yet an answer; the line beside it is what `summarise` wrote."""
    page = P.part_payload("12AX7", P.index(), None)
    p = page["docs"][0]["p"][0]
    assert p[4] == "First and second preamp stages V1 and V2 of the Bassman 5F6-A."
    assert p[5] == "project"


def test_a_page_not_summarised_yet_ends_at_the_count(data):
    """A clone without the model cache exports no lines, and the page must read exactly as before."""
    page = P.part_payload("TL072", P.index(), None)
    assert len(page["docs"][0]["p"][0]) == 4


def test_a_document_that_only_mentions_the_part_sorts_after_one_that_uses_it(data):
    """Two schematics of the same weight, and the one that sorts first by title only sells the part:
    the one whose every summarised page is a mention, an advert or not a component at all goes after
    the one that uses it. A page not summarised yet is not moved either way."""
    with open(config.schematics_uses("esp"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(
            [["TL072", "0", "1", "9", ""], ["TL072", "2", "1", "9", ""]])
    with open(config.schematics_documents("esp"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerow(
            ["2", "k9", "A Sale", "https://esp.example/sale.pdf", "", "schematic", "", "", "1", "beef"])
    with open(config.schematics_pages("esp"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerow(
            ["2", "1", "https://esp.example/sale.pdf#page=1", "1", "9"])
    with open(config.schematics_lines("esp"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(
            [["0", "1", "TL072", "project", "Tone stack buffer IC1 of the Bassman 5F6-A."],
             ["2", "1", "TL072", "advert", "Offered at a price in a mail-order list."]])
    page = P.part_payload("TL072", P.index(), None)
    assert [d["t"] for d in page["docs"]] == ["Bassman 5F6-A", "A Sale", "Opamp Bypassing"]


def test_a_part_says_the_oldest_dated_document_that_prints_it(data):
    idx = P.index()
    page = P.part_payload("12AX7", idx, None)
    year, title, si, url = page["about"]["first"]
    assert year == 1959 and title in ("Bassman 5F6-A", "Fender Bassman")    # both copies are from 1959
    assert url.endswith("bassman.pdf")


def test_what_no_source_says_is_left_out_rather_than_guessed(data):
    # The fixture has no naming schemes, no families and no catalogue: the page gets the first appearance,
    # which the index itself vouches for, and nothing else.
    idx = P.index()
    assert set(P.part_payload("TL072", idx, None).get("about", {})) <= {"first"}


def test_a_variant_borrows_its_types_sheets_and_a_bare_number_its_makers_names():
    from parts_index.web.parts import kin_names
    assert kin_names("NJM4558D") == [("package", "NJM4558")]
    assert kin_names("BC547BTA") == [("packing", "BC547B"), ("grade", "BC547")]
    assert kin_names("2SC1815GR") == [("grade", "2SC1815")]
    assert ("maker's name", "L7812") in kin_names("7812") and ("maker's name", "SN74HC04") in kin_names("74HC04")
    # another part, not a package of one: less current, a better grade, another rating, another voltage
    for other in ("LM317L", "LM358A", "6L6GC", "TIP31C"):
        assert kin_names(other) == []


def test_japanese_packages_and_unbuffered_4000_names_find_their_type():
    from parts_index.web.parts import kin_names
    assert kin_names("NJM4556AL") == [("package", "NJM4556A")]
    assert kin_names("NE5534AN") == [("package", "NE5534A")]
    assert ("maker's name", "CD4011B") in kin_names("CD4011")
    assert kin_names("LM317L") == []            # L is a package only on the Japanese makers' names


def test_a_jrc_name_is_sold_as_njm():
    from parts_index.web.parts import kin_names
    assert ("maker's name", "NJM4558") in kin_names("JRC4558D")


def test_a_bare_valve_is_filed_by_its_envelope():
    from parts_index.web.parts import kin_names
    assert ("envelope", "5Y3GT") in kin_names("5Y3") and ("envelope", "12B4A") in kin_names("12B4")


def test_a_sheet_running_over_pages_is_linked_at_its_first(tmp_path, monkeypatch):
    from parts_index.web import parts as wp
    d = tmp_path / "pages"
    d.mkdir()
    (d / "books.csv").write_text(
        "part,book,leaf,printed,maker,title,year,checked,kind,link\n"
        "LT1028,bk,10,8,,Linear Databook,1990,,sheet,\nLT1028,bk,11,9,,Linear Databook,1990,,sheet,\n"
        "LT1028,bk,12,10,,Linear Databook,1990,,sheet,\nLT1028,bk,40,38,,Linear Databook,1990,,sheet,\n")
    monkeypatch.setattr(wp, "datasheet_pages", lambda source: d / f"{source}.csv")
    got = wp.databook_pages()["LT1028"]
    assert [r[0].rsplit("/", 1)[-1] for r in got] == ["n9", "n39"]


def test_a_forum_is_indexed_but_not_shown_and_a_repository_is_whatever_found_it(data):
    """diyAudio's attachments and Toragi's zips stay out of the site until it is decided they belong;
    a GitHub sheet is shown even when a journal found it, because the page lists it as a project."""
    reg = data / "schematics" / "sources.yaml"
    reg.write_text(reg.read_text(encoding="utf-8")
                   + "diyaudio: {kind: forum, title: diyAudio, home_url: 'https://d.example/', status: active}\n"
                   + "hardwarex: {kind: journal, title: HardwareX, home_url: 'https://h.example/', status: active}\n",
                   encoding="utf-8")
    for src, url in (("diyaudio", "https://d.example/att/1.pdf"),
                     ("hardwarex", "https://github.com/a/board/blob/HEAD/b.kicad_sch")):
        with open(config.schematics_documents(src), "w", encoding="utf-8") as f:
            f.write(f"id,key,title,url,parent,role,year,month,pages,sha\n0,k,T,{url},,schematic,2001,,1,{src}\n")
        with open(config.schematics_pages(src), "w", encoding="utf-8") as f:
            f.write(f"doc,page,url,schematic,parts\n0,1,{url},1,1\n")
        with open(config.schematics_uses(src), "w", encoding="utf-8") as f:
            f.write("part,doc,page,times,near\nTL072,0,1,1,U1\n")
    idx = P.index()
    page = P.part_payload("TL072", idx, None)
    assert sorted(idx["sources"][d["s"]] for d in page["docs"]) == ["esp", "hardwarex"]
    rows, _ = P.search_index(idx, {})
    assert dict((r[0], r[1]) for r in rows)["TL072"] == 2       # the forum's document is not counted


def test_databook_pages_are_listed_apart_from_the_makers_sheets(data):
    idx = P.index()
    idx["databook"] = {"TL072": [["https://archive.org/details/bk/page/n9", "", "", "Linear Databook p. 8",
                                  "archive_databooks", "a page of a databook (1990)"]]}
    idx["books"] = {"archive_databooks"}
    idx["sheets"] = {"TL072": [["https://ti.example/tl072.pdf", "ti", "", "", "ti_datasheets", ""]]}
    about = P.part_payload("TL072", idx, None)["about"]
    assert [r[0] for r in about["sheets"]] == ["https://ti.example/tl072.pdf"]
    assert [r[4] for r in about["books"]] == ["archive_databooks"]


def test_a_repository_among_the_documents_carries_its_stars(data):
    """The page lists every repository in one list by stars, whichever way it was found."""
    idx = P.index()
    idx["repo_stats"] = {"a/board": {"stars": "7", "forks": "1", "watchers": "2", "status": "live"}}
    idx["uses"]["TL072"] = [(idx["sources"].index("esp"), {"doc": "9", "page": "1", "times": "1", "near": ""})]
    idx["documents"]["esp"]["9"] = {"title": "a/board: b.kicad_sch", "url": "https://github.com/a/board/blob/HEAD/b.kicad_sch"}
    assert P.part_payload("TL072", idx, None)["stars"] == {"a/board": [7, 1, 2]}


def test_an_issue_is_dated_to_the_month_when_its_row_says_so():
    assert P.issue_date({"year": "1985", "month": "8"}) == "1985-08"
    assert P.issue_date({"year": "1985", "month": ""}) == "1985"
    assert P.issue_date({"year": "", "month": "08"}) == ""
