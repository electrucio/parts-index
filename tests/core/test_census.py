"""The census: what a list of type numbers is read as, and what the extractor is allowed to do with it."""
import csv

from parts_index.core.parts import census

# Frank's index as it really is: entries are links to the data sheet PDF whose file name is the type
# number, several brands per type, and the letter's continuation pages at the foot.
PAGE = """<html><body>
  <table>
    <tr><td><a href="sheets/084/6/6V6.pdf">6V6.pdf</a><td><a href="sheets/093/6/6V6.pdf">6V6.pdf</a>
    <tr><td><a href="sheets/011/6/6V6GT.pdf">6V6GT.pdf</a>
    <tr><td><a href="sheets/026/6/6336A.pdf">6336A.pdf</a>
    <tr><td><a href="sheets/049/5/5687.pdf">5687.pdf</a>
    <tr><td><a href="sheets/074/6/6-22AM.pdf">6-22AM.pdf</a>
    <tr><td><a href="images/RCA/6/6336A_RCA_HM.jpg">picture</a>
  </table>
  <table><tr><td><a href="sheets61.html">642(501-1000)</a><td><a href="sheetsA.html">A</a></table>
</body></html>"""
URL = "https://frank.pocnet.net/sheets6.html"


def test_an_entry_is_the_type_number_and_the_page_that_vouches_for_it():
    got = census._frank_entries(URL, PAGE)
    assert {e.part for e in got} == {"6V6", "6V6GT", "6336A", "5687", "6-22AM"}     # the .jpg is not a type
    assert all(e.kind == "tube" for e in got)
    assert [e.url for e in got if e.part == "6336A"] == ["https://frank.pocnet.net/sheets/026/6/6336A.pdf"]


def test_the_same_type_from_two_brands_is_one_part_with_one_link():
    rows = {}
    for e in census._frank_entries(URL, PAGE):
        rows.setdefault(e.part.upper(), e)
    assert rows["6V6"].url.endswith("/084/6/6V6.pdf")           # the first page to vouch for it


def test_a_letter_page_leads_to_its_continuation_pages():
    assert census._frank_more(URL, PAGE) == [
        "https://frank.pocnet.net/sheets61.html", "https://frank.pocnet.net/sheetsA.html"]


def test_load_is_empty_and_harmless_without_a_census(monkeypatch, tmp_path):
    monkeypatch.setattr(census, "parts_census", lambda: tmp_path / "nothing.csv")
    assert census.load() == {} and census.load_rows() == []


def test_load_keys_a_part_the_way_the_extractor_spells_it(monkeypatch, tmp_path):
    f = tmp_path / "census.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=census.FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerow({"part": "6-22AM", "kind": "tube", "source": "frank_pocnet", "url": "https://x/6-22AM.pdf"})
        w.writerow({"part": "6V6", "kind": "tube", "source": "frank_pocnet", "url": "https://x/6V6.pdf"})
    monkeypatch.setattr(census, "parts_census", lambda: f)
    loaded = census.load()
    assert loaded["6V6"] == ("6V6", "tube")
    assert loaded["622AM"] == ("6-22AM", "tube")                # norm() drops the punctuation


def test_every_row_carries_the_page_that_vouches_for_it():
    """A census row is a fact and its evidence. Without a public link it is neither something a reader
    can check nor something the site can offer, so it is not a row."""
    rows = census.load_rows()
    if not rows:
        return                                              # no census built here
    assert not [r for r in rows if not r["url"].startswith("http")]


def test_a_model_library_says_npn_or_pnp_when_its_libraries_agree(monkeypatch, tmp_path):
    """2N4403 is PNP in three libraries and NPN in one, which is outvoted; 2N1132 is split and says
    nothing; a sub-circuit says nothing about what is inside it."""
    import json
    f = tmp_path / "index.jsonl"
    defs = [("2N4403", "PNP", s) for s in ("onsemi", "bordodynov", "ltwiki")] + [("2N4403", "NPN", "groupsio")]
    defs += [("2N1132", "PNP", "a"), ("2N1132", "NPN", "b"), ("Q2N5457", "NJF", "a"), ("IRF540", "SUBCKT", "a")]
    f.write_text("".join(json.dumps({"name": n, "type": t, "source": s, "parent": None, "file": "x/y.lib"}) + "\n"
                         for n, t, s in defs), encoding="utf-8")
    monkeypatch.setattr(census, "spice_definitions", lambda: f)
    monkeypatch.setattr(census, "_model_file_urls", lambda: {})
    monkeypatch.setattr(census, "_source_homes", lambda: {s: f"https://{s}.example/" for _, _, s in defs})
    got = {e.part: e.polarity for e in census.spice_definitions_entries({})}
    assert got["2N4403"] == "PNP"
    assert got["2N1132"] == ""
    assert got["2N5457"] == "N-channel"                         # LTspice's Q prefix taken off
    assert got.get("IRF540", "") == ""
