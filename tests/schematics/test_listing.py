"""Re-listing a source: what a brand page yields, what a dead one left behind, and append-only."""
import json

import pytest

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


class Archive:
    """The CDX index, answering as it does: a count first, then a page of rows at a time."""

    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **kw):
        from parts_index.core.http import Response
        self.asked.append(url)
        if "showNumPages" in url:
            return Response(200, url, "text/plain", f"{len(self.pages)}\n".encode())
        page = int(url.rsplit("page=", 1)[1])
        body = "".join(f"{u} {stamp} {size}\n" for u, stamp, size in self.pages[page])
        return Response(200, url, "text/plain", body.encode())


CAPTURES = [
    [("http://kallhovde.com:80/pioneer/sx-1980.pdf", "20100806165154", "485637")],
    [("http://kallhovde.com:80/advent/100a.pdf", "20100806165155", "338448")],
]


def test_a_dead_site_is_listed_from_what_the_archive_kept(monkeypatch):
    archive = Archive(CAPTURES)
    monkeypatch.setattr(listing.http, "get", archive.get)
    lister = listing.wayback("kallhovde", {"domain": "kallhovde.com", "kind": "service_manual"})

    rows = [r for batch in lister(delay=0) for r in batch]

    assert [r["url"] for r in rows] == [
        "https://web.archive.org/web/20100806165154id_/http://kallhovde.com:80/pioneer/sx-1980.pdf",
        "https://web.archive.org/web/20100806165155id_/http://kallhovde.com:80/advent/100a.pdf"]
    assert rows[0]["title"] == "sx 1980" and rows[0]["kind"] == "service_manual"
    assert rows[0]["page"] == "http://kallhovde.com:80/pioneer/sx-1980.pdf"      # where it lived when alive
    assert rows[0]["archived"] == "20100806165154"


def test_the_archive_is_asked_only_for_good_captures_of_documents(monkeypatch):
    archive = Archive(CAPTURES)
    monkeypatch.setattr(listing.http, "get", archive.get)
    list(listing.wayback("kallhovde", {"domain": "kallhovde.com"})(delay=0))

    query = archive.asked[0]
    assert "collapse=urlkey" in query           # one row per URL, not one per visit
    assert "filter=statuscode:200" in query
    assert "filter=mimetype:(application/pdf)" in query


def test_a_limit_stops_after_that_many_pages_of_the_index(monkeypatch):
    archive = Archive(CAPTURES)
    monkeypatch.setattr(listing.http, "get", archive.get)
    rows = [r for batch in listing.wayback("kallhovde", {"domain": "kallhovde.com"})(delay=0, limit=1)
            for r in batch]
    assert len(rows) == 1


def test_a_source_with_no_lister_and_no_archive_says_so(monkeypatch):
    monkeypatch.setattr(listing, "registry_entry", lambda source: {"kind": "site"})
    with pytest.raises(SystemExit, match="wayback"):
        listing.lister_for("tubecad")


def test_a_wayback_block_is_a_lister(monkeypatch):
    monkeypatch.setattr(listing, "registry_entry",
                        lambda source: {"wayback": {"domain": "kallhovde.com"}})
    assert callable(listing.lister_for("kallhovde"))
