"""Re-listing a source: what a brand page yields, what a dead one left behind, and append-only."""
import json
import re

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


INDEX = b"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://ti.example/lit/pdf/sitemap-other.xml</loc></sitemap>
</sitemapindex>"""
LITS = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ti.example/lit/pdf/sboa269</loc></url>
  <url><loc>https://ti.example/lit/pdf/tidu123</loc></url>
  <url><loc>https://ti.example/lit/pdf/spra456</loc></url>
  <url><loc>https://ti.example/lit/pdf/sszq789</loc></url>
</urlset>"""


@pytest.fixture(autouse=True)
def private_root(tmp_path, monkeypatch):
    """Every test in this file gets its own material root: the sitemap cache is written under it, and
    one of these tests spilled into the real tree before this existed."""
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))


class Site:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **kw):
        from parts_index.core.http import Response
        self.asked.append(url)
        return Response(200, url, "application/xml", self.pages[url])


SITEMAPS = {"https://ti.example/lit/sitemapindex.xml": INDEX,
            "https://ti.example/lit/pdf/sitemap-other.xml": LITS}


def test_a_sitemap_index_is_followed_to_the_sitemaps_it_points_at(monkeypatch):
    site = Site(SITEMAPS)
    monkeypatch.setattr(listing.http, "get", site.get)
    rows = [r for batch in listing.sitemap("ti", {"url": "https://ti.example/lit/sitemapindex.xml"})(delay=0)
            for r in batch]
    assert len(rows) == 4
    assert site.asked == list(SITEMAPS)          # the index, then the sitemap it named


def test_keep_says_which_families_hold_a_circuit(monkeypatch):
    """TI's literature sitemap names marketing bulletins and processor manuals too."""
    site = Site(SITEMAPS)
    monkeypatch.setattr(listing.http, "get", site.get)
    cfg = {"url": "https://ti.example/lit/sitemapindex.xml", "keep": r"/lit/pdf/(sboa|tidu)[0-9]"}
    rows = [r for batch in listing.sitemap("ti", cfg)(delay=0) for r in batch]

    assert [r["url"].rsplit("/", 1)[1] for r in rows] == ["sboa269", "tidu123"]
    assert rows[0]["title"] == "SBOA269"


def test_a_sitemap_block_is_a_lister(monkeypatch):
    monkeypatch.setattr(listing, "registry_entry", lambda source: {"sitemap": {"url": "https://ti.example/s.xml"}})
    assert callable(listing.lister_for("ti_appnotes"))


def test_a_sitemap_served_as_a_gzip_file_is_unpacked(monkeypatch):
    """vishay.com/sitemap.xml.gz arrives as the bytes it is, not as a content encoding."""
    import gzip as _gzip
    site = Site({"https://v.example/sitemap.xml.gz": _gzip.compress(LITS)})
    monkeypatch.setattr(listing.http, "get", site.get)
    rows = [r for batch in listing.sitemap("v", {"url": "https://v.example/sitemap.xml.gz"})(delay=0)
            for r in batch]
    assert len(rows) == 4


def test_a_sitemap_is_asked_for_once_however_often_the_pattern_changes(monkeypatch):
    """Renesas was walked three times in one morning — census, list, and again because `keep` changed.
    The third walk was 118 requests for files already on this disk, and then Cloudflare stopped us."""
    site = Site(SITEMAPS)
    monkeypatch.setattr(listing.http, "get", site.get)
    url = "https://ti.example/lit/sitemapindex.xml"

    wide = [r for b in listing.sitemap("ti", {"url": url})(delay=0) for r in b]
    asked_first = len(site.asked)
    narrow = [r for b in listing.sitemap("ti", {"url": url, "keep": r"sboa"})(delay=0) for r in b]

    assert len(wide) == 4 and len(narrow) == 1        # the pattern changed and the answer with it
    assert len(site.asked) == asked_first             # and not one more request was made


# --- the two new ways to find a design: GitHub's index, and a journal's ---------------------------------
TREE = {"tree": [{"type": "blob", "path": "hw/main.kicad_sch"},
                 {"type": "blob", "path": "hw/main.kicad_pcb"},
                 {"type": "blob", "path": "lib/symbols/house.kicad_sym"},
                 {"type": "blob", "path": "old/v1.sch"},
                 {"type": "tree", "path": "hw"}]}


class Hub:
    """The GitHub API, answering the three questions this asks it."""

    def __init__(self, code=None, repos=None, trees=None):
        self.code, self.repos, self.trees = code or {}, repos or {}, trees or {}
        self.asked = []

    def get(self, url, **kw):
        from parts_index.core.http import Response
        self.asked.append(url)
        if "/search/code" in url:
            part = url.split("q=")[1].split("%20")[0]
            items = [{"repository": {"full_name": n}} for n in self.code.get(part, [])]
            return Response(200, url, "application/json", json.dumps({"items": items}).encode())
        if "/search/repositories" in url:
            topic = url.split("topic%3A")[1].split("&")[0]
            page = int(url.split("page=")[1].split("&")[0])
            names = self.repos.get(topic, []) if page == 1 else []
            return Response(200, url, "application/json",
                            json.dumps({"items": [{"full_name": n} for n in names]}).encode())
        if "/git/trees/" in url:
            full = url.split("/repos/")[1].split("/git/")[0]
            return Response(200, url, "application/json",
                            json.dumps(self.trees.get(full, TREE)).encode())
        return Response(404, url, why="not in this fake")


def test_a_part_number_is_a_question_about_which_designs_use_it(monkeypatch):
    """The direction that fights the bias: not "what did people publish" but "who uses OPA1612"."""
    hub = Hub(code={"OPA1612": ["a/one", "b/two"]})
    monkeypatch.setattr(listing.http, "get", hub.get)

    assert listing._by_part("s", "OPA1612", ["kicad_sch"], 0) == ["a/one", "b/two"]
    assert "extension%3Akicad_sch" in hub.asked[0]


def test_a_search_is_asked_once_however_often_a_run_is_restarted(monkeypatch):
    """6,889 part numbers at one search every fifteen seconds is a day and a half. It will be
    interrupted, and the next run must not pay for the first one's questions again."""
    hub = Hub(code={"LT3045": ["c/three"]})
    monkeypatch.setattr(listing.http, "get", hub.get)

    first = listing._by_part("s", "LT3045", ["kicad_sch"], 0)
    again = listing._by_part("s", "LT3045", ["kicad_sch"], 0)

    assert first == again == ["c/three"]
    assert len(hub.asked) == 1


def test_only_the_parts_still_in_production_are_asked_about(monkeypatch, tmp_path):
    census = tmp_path / "ti.csv"
    census.write_text("part,kind,source,url\nOPA1612,opamp,ti,u\nTL072,opamp,ti,u\n"
                      "ECC83,tube,ti,u\nLT3045,regulator,ti,u\n", encoding="utf-8")
    monkeypatch.setattr(listing, "parts_census", lambda name: census)

    assert listing._seed_parts({"from": ["ti"]}) == ["OPA1612", "LT3045"]
    assert listing._seed_parts({"from": ["ti"], "max": 1}) == ["OPA1612"]
    assert listing._seed_parts({"from": ["ti"], "modern": False}) == ["OPA1612", "TL072", "ECC83", "LT3045"]
    assert listing._seed_parts({"also": ["opa1656"]}) == ["OPA1656"]


def test_a_repository_is_read_out_of_prose_and_never_twice(monkeypatch):
    """A paper writes the URL in a sentence and a list writes it one per line; both are the same name.
    And a repository found under two topics, or by two part numbers, is one tree call."""
    hub = Hub(code={"OPA1612": ["a/one"], "LT3045": ["a/one", "b/two"]}, repos={"eurorack": ["a/one"]})
    monkeypatch.setattr(listing.http, "get", hub.get)
    cfg = {"topics": ["eurorack"], "parts": {"also": ["OPA1612", "LT3045"], "ext": ["kicad_sch"]}}

    rows = [r for batch in listing.github("s", cfg)(delay=0) for r in batch]

    assert sorted({r["repo"] for r in rows}) == ["a/one", "b/two"]
    assert len([u for u in hub.asked if "/git/trees/" in u]) == 2        # not three, and not four


def test_only_the_schematic_sources_of_a_repository_are_taken(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(listing.http, "get", hub.get)
    rows = listing._tree_rows("s", "a/one", {}, 0, listing.GH_EXT, None)

    assert [r["url"].rsplit("/", 1)[1] for r in rows] == ["main.kicad_sch", "v1.sch"]
    assert rows[0]["page"] == "https://github.com/a/one/blob/HEAD/hw/main.kicad_sch"
    assert listing._tree_rows("s", "a/one", {}, 0, listing.GH_EXT, re.compile(r"^old/")) == rows[:1]


PAPER = {"hitCount": 1, "nextCursorMark": "",
         "resultList": {"result": [{"pmcid": "PMC1", "doi": "10.1016/j.ohx.2026.e00800",
                                    "title": "A demultiplexing PCB for EEG"}]}}
FULLTEXT = """<article><p>The board uses an ADS1299 and the design files are at
  https://github.com/eneriz-daniel/eeg-emulator/blob/master/eeg_acquisition/design_files/eeg_acq.kicad_sch
  with the archive at https://doi.org/10.5281/zenodo.17488266.</p></article>"""


class Journal(Hub):
    """Europe PMC's search and full text, and the GitHub API the papers point at."""

    def get(self, url, **kw):
        from parts_index.core.http import Response
        if "/search?query=" in url:
            self.asked.append(url)
            return Response(200, url, "application/json", json.dumps(PAPER).encode())
        if url.endswith("/fullTextXML"):
            self.asked.append(url)
            return Response(200, url, "application/xml", FULLTEXT.encode())
        return super().get(url, **kw)


def test_a_paper_gives_the_design_files_it_links_and_keeps_its_citation(monkeypatch):
    """HardwareX will not publish a paper whose design files are not open, and the paper says where they
    are. Elsevier does not serve us the PDF, so the file is the row and the paper is the link a reader of
    this index should be given."""
    journal = Journal()
    monkeypatch.setattr(listing.http, "get", journal.get)

    rows = [r for b in listing.europepmc("hardwarex", {"query": 'JOURNAL:"HardwareX"'})(delay=0) for r in b]

    assert [r["url"].rsplit("/", 1)[1] for r in rows] == ["main.kicad_sch", "v1.sch"]
    assert rows[0]["repo"] == "eneriz-daniel/eeg-emulator"
    assert rows[0]["paper"] == "https://doi.org/10.1016/j.ohx.2026.e00800"
    assert "A demultiplexing PCB" in rows[0]["title_hint"]


def test_a_europepmc_block_is_a_lister(monkeypatch):
    monkeypatch.setattr(listing, "registry_entry", lambda source: {"europepmc": {"query": "x"}})
    assert callable(listing.lister_for("hardwarex"))
