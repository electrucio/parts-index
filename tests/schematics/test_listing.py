"""Re-listing a source: what a brand page yields, and the promise that it only ever appends."""
import json

from parts_index.schematics import listing

PAGE = """<html><head><title>Akai Audio Schematics &amp; Service Manuals</title></head><body>
  <a href="https://audiocircuit.dk/downloads/akai/Akai-202DSS-tape-sm.pdf">Akai-202DSS-tape-sm.pdf</a>
  <a href="/downloads/akai/Akai-AAR41-rec-sm.pdf">Akai-AAR41-rec-sm.pdf</a>
  <a href="https://audiocircuit.dk/akai/?eeListID=1&ee=1&eePage=1">2</a>
</body></html>"""


def test_a_brand_page_names_its_brand_and_its_files():
    assert listing._brand(PAGE, "https://audiocircuit.dk/akai/") == "Akai Audio"
    assert listing._title_of("https://audiocircuit.dk/downloads/akai/Akai-202DSS-tape-sm.pdf") == "Akai 202DSS tape sm"


def test_a_page_without_a_title_falls_back_to_its_url():
    assert listing._brand("<html></html>", "https://audiocircuit.dk/tascam/") == "Tascam"


def test_listing_only_ever_appends(monkeypatch, tmp_path):
    path = tmp_path / "assets_x.jsonl"
    path.write_text(json.dumps({"url": "https://x/a.pdf", "title": "kept"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(listing, "source_list", lambda source: path)
    rows = [{"url": "https://x/a.pdf", "title": "would overwrite"}, {"url": "https://x/b.pdf", "title": "new"}]
    assert listing.append_new("x", rows) == 1
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [r["title"] for r in lines] == ["kept", "new"]           # the row already listed is untouched
    assert listing.append_new("x", rows) == 0                       # and a second run adds nothing


def test_a_dry_run_writes_nothing(monkeypatch, tmp_path):
    path = tmp_path / "assets_x.jsonl"
    monkeypatch.setattr(listing, "source_list", lambda source: path)
    assert listing.append_new("x", [{"url": "https://x/a.pdf"}], dry=True) == 1
    assert not path.exists()
