"""Walking a site: where it goes, what it takes, and what a resumed crawl costs."""
from __future__ import annotations

import shutil

import pytest

from parts_index.core import config
from parts_index.core.http import Response
from parts_index.core.ledger import Ledger
from parts_index.schematics import crawl as C
from parts_index.schematics import download as D

REGISTRY = """
tubecad: {kind: site, title: Tube CAD, home_url: 'https://tc.example/', status: active,
          crawl: {start: ['https://tc.example/'], allow: '^/(20\\d\\d|articles)', max: 0,
                  deny: '^/articles/index', cdn: 'cdn\\.example$'}}
"""

INDEX = b"""<html><head><title>Tube CAD</title></head><body>
  <a href="/2024/aikido.html">Aikido</a>
  <a href="/articles/list.html">Articles</a>
  <a href="/articles/index.html">Index of articles</a>
  <a href="/store/buy.html">Shop</a>
  <a href="/tag/valves/">Valves</a>
  <a href="https://other.example/elsewhere.html">Elsewhere</a>
  <a href="/2024/sheet.pdf">The sheet</a>
</body></html>"""

ARTICLE = b"""<html><head><title>Aikido</title></head><body>
  <img src="/img/schematic.gif" width="600">
  <img src="/img/site-logo.gif" width="600">
  <img src="/img/thumbnail.gif" width="80">
  <img src="https://cdn.example/img/board.png">
  <img src="https://elsewhere.example/img/other.png">
</body></html>"""

GIF = b"GIF89a" + b"x" * 4000
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 9000
PDF = b"%PDF-1.4\n" + b"x" * 4000


class Server:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def get(self, url, **kw):
        self.asked.append(url)
        answer = self.answers.get(url)
        return answer if answer is not None else Response(404, url)


ANSWERS = {
    "https://tc.example/": Response(200, "https://tc.example/", "text/html", INDEX),
    "https://tc.example/2024/aikido.html": Response(200, "https://tc.example/2024/aikido.html", "text/html", ARTICLE),
    "https://tc.example/articles/list.html": Response(200, "https://tc.example/articles/list.html", "text/html",
                                                      b"<html><title>List</title><body>nothing here</body></html>"),
    "https://tc.example/2024/sheet.pdf": Response(200, "https://tc.example/2024/sheet.pdf", "application/pdf", PDF),
    "https://tc.example/img/schematic.gif": Response(200, "https://tc.example/img/schematic.gif", "image/gif", GIF),
    "https://cdn.example/img/board.png": Response(200, "https://cdn.example/img/board.png", "image/png", PNG),
}


@pytest.fixture
def site(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    return data


def serve(monkeypatch, answers=ANSWERS) -> Server:
    server = Server(dict(answers))
    monkeypatch.setattr(D.http, "get", server.get)
    return server


def test_it_follows_the_site_and_nothing_else(site, monkeypatch):
    server = serve(monkeypatch)
    out = C.crawl("tubecad", log=lambda *a: None)

    assert "https://tc.example/2024/aikido.html" in server.asked      # allowed path
    assert "https://tc.example/articles/list.html" in server.asked
    assert "https://tc.example/articles/index.html" not in server.asked   # `deny` beats `allow`
    assert "https://tc.example/store/buy.html" not in server.asked        # outside `allow`
    assert "https://tc.example/tag/valves/" not in server.asked           # a listing, not a document
    assert "https://other.example/elsewhere.html" not in server.asked     # another site
    assert out["pages"] == 3


def test_it_takes_the_documents_a_page_shows(site, monkeypatch):
    serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)
    led = Ledger(config.schematics_state("tubecad"))

    assert led.get("https://tc.example/2024/sheet.pdf")["role"] == "linked"
    assert led.get("https://tc.example/img/schematic.gif")["type"] == "gif"
    assert led.get("https://cdn.example/img/board.png")["type"] == "png"   # the site's image host
    assert led.get("https://tc.example/img/site-logo.gif") is None         # furniture
    assert led.get("https://tc.example/img/thumbnail.gif") is None         # the page says it is 80 wide
    assert led.get("https://elsewhere.example/img/other.png") is None      # somebody else's image


def test_what_was_walked_stays_known_after_its_files_are_deleted(site, monkeypatch):
    """A downloaded document is temporary — OCR reads it and it goes. What was scraped is not."""
    serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)

    shutil.rmtree(config.downloads("tubecad"))          # the retention rule, applied

    again = serve(monkeypatch)
    out = C.crawl("tubecad", log=lambda *a: None)
    assert again.asked == []                            # not one request to learn what we already knew
    assert out["pages"] == 0 and out["queued"] == 0


def test_a_budget_leaves_the_rest_of_the_queue_in_the_ledger(site, monkeypatch):
    server = serve(monkeypatch)
    out = C.crawl("tubecad", budget=1, log=lambda *a: None)
    assert out["fetched"] == 1 and out["queued"] >= 1
    assert "https://tc.example/2024/aikido.html" not in server.asked

    waiting = C.frontier(Ledger(config.schematics_state("tubecad")))
    assert "https://tc.example/2024/aikido.html" in waiting       # the queue outlives the process
    shutil.rmtree(config.downloads("tubecad"))

    next_run = serve(monkeypatch)
    C.crawl("tubecad", budget=0, log=lambda *a: None)
    assert "https://tc.example/" not in next_run.asked            # walked in the first run
    assert "https://tc.example/2024/aikido.html" in next_run.asked


def test_a_site_is_walked_again_only_when_asked(site, monkeypatch):
    """A site crawled to the end still publishes new articles; `--refresh` is how they are found."""
    serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)

    assert C.crawl("tubecad", log=lambda *a: None)["pages"] == 0      # done means done

    again = serve(monkeypatch)
    out = C.crawl("tubecad", refresh=True, log=lambda *a: None)
    assert out["pages"] == 3 and again.asked == []                    # re-read from the copies kept


def test_a_frameset_is_one_hop_further(site, monkeypatch):
    frames = b"""<html><frameset><frame src="/2024/inner.html"></frameset></html>"""
    inner = b"""<html><title>Inner</title><body><img src="/img/schematic.gif" width="600"></body></html>"""
    server = serve(monkeypatch, {
        "https://tc.example/": Response(200, "https://tc.example/", "text/html", frames),
        "https://tc.example/2024/inner.html": Response(200, "https://tc.example/2024/inner.html", "text/html", inner),
        "https://tc.example/img/schematic.gif": Response(200, "https://tc.example/img/schematic.gif", "image/gif", GIF),
    })
    C.crawl("tubecad", log=lambda *a: None)
    assert "https://tc.example/2024/inner.html" in server.asked
    assert Ledger(config.schematics_state("tubecad")).get("https://tc.example/img/schematic.gif")["type"] == "gif"


def test_a_page_that_never_says_html_is_still_a_page(site, monkeypatch):
    """Hand-written sites from the nineties open straight into <body>, and they are most of this corpus."""
    old = b"<body><a href='/2024/aikido.html'>Aikido</a></body>"
    server = serve(monkeypatch, dict(ANSWERS, **{"https://tc.example/": Response(200, "https://tc.example/", "text/plain", old)}))
    C.crawl("tubecad", log=lambda *a: None)
    assert "https://tc.example/2024/aikido.html" in server.asked


def test_a_queued_crawl_waits_for_every_job_it_was_told_to(site, monkeypatch):
    """The default is a day. A download of forty thousand files can outlast that, so it is a number."""
    waited = {}
    monkeypatch.setattr(C, "wait_for_all", lambda names, timeout: waited.update(names=names, timeout=timeout) or "")
    monkeypatch.setattr(C, "crawl", lambda *a, **k: {})

    C.main(["--source", "tubecad", "--after", "download_audiocircuit", "--after", "crawl_xdevs", "--wait-hours", "48"])
    assert waited == {"names": ["download_audiocircuit", "crawl_xdevs"], "timeout": 48 * 3600}


def test_a_page_every_page_links_to_is_queued_once(site, monkeypatch):
    """A site's front page is linked from all of it; the queue counted one entry per link."""
    hub = b"""<html><title>Hub</title><body>
        <a href="/2024/aikido.html">a</a><a href="/2024/aikido.html">again</a>
        <a href="/2024/aikido.html">and again</a></body></html>"""
    server = serve(monkeypatch, {
        "https://tc.example/": Response(200, "https://tc.example/", "text/html", hub),
        "https://tc.example/2024/aikido.html": Response(200, "https://tc.example/2024/aikido.html", "text/html", ARTICLE),
        "https://tc.example/img/schematic.gif": Response(200, "https://tc.example/img/schematic.gif", "image/gif", GIF),
        "https://cdn.example/img/board.png": Response(200, "https://cdn.example/img/board.png", "image/png", PNG),
    })
    out = C.crawl("tubecad", log=lambda *a: None)

    assert out["queued"] == 0                     # what is left, not what was ever appended
    assert server.asked.count("https://tc.example/2024/aikido.html") == 1


MHTML = b"""<html><head><title>74 TTL</title></head><body>
  <img src=3D"http://philips.example/images/clear.gif" width=3D"600">
  <a href=3D"http://tc.example/2024/quoted.html">A link that was escaped too</a>
  <img src="/img/schematic.gif" width="600">
</body></html>"""


def test_a_url_that_cannot_exist_is_never_asked_for(site, monkeypatch):
    """A page saved as MHTML and served as .htm keeps `src=3D"..."`, and the quote lands in the URL.

    Each one costs four attempts and, with the back-off between them, three minutes of the only turn its
    host gets: twelve of them on one sm0vpo page held that whole crawl still for an hour.
    """
    answers = dict(ANSWERS)
    answers["https://tc.example/2024/aikido.html"] = Response(
        200, "https://tc.example/2024/aikido.html", "text/html", MHTML)
    server = serve(monkeypatch, answers)
    C.crawl("tubecad", log=lambda *a: None)

    assert not [u for u in server.asked if '"' in u]
    assert "https://tc.example/img/schematic.gif" in server.asked     # the sound links on the page still count


def test_an_impossible_url_already_in_the_queue_is_dropped_not_asked_for(site, monkeypatch):
    """The guard stops new ones; the frontier of an older run still holds twenty-four of them."""
    led = Ledger(config.schematics_state("tubecad"))
    led.row('https://tc.example/2024/3D"http:/philips.example/clear.gif"')["role"] = "page"
    led.save()

    server = serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)

    assert not [u for u in server.asked if '"' in u]
    again = Ledger(config.schematics_state("tubecad"))
    assert again.get('https://tc.example/2024/3D"http:/philips.example/clear.gif"')["skip_reason"] == "malformed url"
    assert C.frontier(again) == []          # and it never comes back to the queue


def test_one_page_spelled_two_ways_is_walked_once_and_both_rows_say_so(site, monkeypatch):
    """qrp-labs links itself over http and answers over https: 297 pages looked owed for ever."""
    led = Ledger(config.schematics_state("tubecad"))
    led.row("https://tc.example/2024/aikido.html")["crawl_at"] = "2026-09-20"   # walked by an earlier run
    led.row("http://tc.example/2024/aikido.html")["role"] = "page"              # its other spelling, not walked
    led.save()

    server = serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)

    assert not [u for u in server.asked if u.endswith("/2024/aikido.html")]     # one page, already walked
    again = Ledger(config.schematics_state("tubecad"))
    assert again.get("http://tc.example/2024/aikido.html")["crawl_at"]          # and now both rows say so
    assert C.frontier(again) == []


TRAP = b"""<html><title>News</title><body>
  <a href="www.tubecad.com/news/">News</a>
  <a href="/2024/aikido.html">Aikido</a>
</body></html>"""


def test_a_link_written_without_its_scheme_does_not_become_a_circle(site, monkeypatch):
    """muzique.com writes some links as `www.muzique.com/news/`, and joining one buries a hostname in
    the path. The page that comes back carries the same link, a segment deeper, for ever: 3,937 of its
    6,340 rows were that one circle."""
    answers = dict(ANSWERS)
    answers["https://tc.example/"] = Response(200, "https://tc.example/", "text/html", TRAP)
    server = serve(monkeypatch, answers)
    C.crawl("tubecad", log=lambda *a: None)

    assert not [u for u in server.asked if "tc.example/www.tubecad.com" in u]
    assert "https://tc.example/2024/aikido.html" in server.asked       # the sound link on the page still counts


def test_a_path_that_repeats_itself_is_read_as_a_circle():
    assert C.unusable("https://x.example/news/a/news/b/news/") == "the path goes round in a circle"
    assert C.unusable("https://x.example/news/a/news/b/") == ""            # twice is a site, not a trap
    assert C.unusable("https://x.example/files/setup.com") == ""           # a file may be called that
    assert C.unusable("https://x.example/www.other.com/files/") == "link written without its scheme"
