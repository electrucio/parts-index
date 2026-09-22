"""Walking a site: where it goes, what it takes, and what a resumed crawl costs."""
from __future__ import annotations

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


def test_a_resumed_crawl_pays_only_for_what_it_no_longer_has(site, monkeypatch):
    serve(monkeypatch)
    C.crawl("tubecad", log=lambda *a: None)

    again = serve(monkeypatch)
    out = C.crawl("tubecad", log=lambda *a: None)
    assert again.asked == []                     # every page is read from the copy kept on disk
    assert out["pages"] == 3 and out["fetched"] == 0

    # the same crawl after the page files are lost, which is what the old pipeline left behind
    for f in (config.downloads("tubecad") / "html").iterdir():
        f.unlink()
    third = serve(monkeypatch)
    out = C.crawl("tubecad", log=lambda *a: None)
    assert out["fetched"] == 3 and sorted(third.asked) == sorted(
        ["https://tc.example/", "https://tc.example/2024/aikido.html", "https://tc.example/articles/list.html"])


def test_a_budget_stops_the_run_and_the_next_one_carries_on(site, monkeypatch):
    server = serve(monkeypatch)
    out = C.crawl("tubecad", budget=1, log=lambda *a: None)
    assert out["fetched"] == 1 and out["queued"] >= 1
    assert "https://tc.example/2024/aikido.html" not in server.asked

    C.crawl("tubecad", budget=0, log=lambda *a: None)
    assert "https://tc.example/2024/aikido.html" in server.asked


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
