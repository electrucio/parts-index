"""The download stage: what it stores, what it refuses, and what it never asks for twice.

No network: `core.http.get` is replaced by a small server of canned answers that records every URL it
was asked for, which is how "polite" and "resumable" are asserted here.
"""
from __future__ import annotations

import json

import pytest

from parts_index.core import config
from parts_index.core.http import Response
from parts_index.core.ledger import Ledger
from parts_index.schematics import download as D

REGISTRY = """
audiocircuit: {kind: factory, title: AudioCircuit, home_url: 'https://ac.example/', status: active,
               list: {role: schematic}}
layouts: {kind: site, title: Layouts, home_url: 'https://lay.example/', status: active,
          list: {role: layout, figures: true, cdn: 'cdn\\.example$'}}
later: {kind: site, title: Not yet, home_url: 'https://soon.example/', status: proposed,
        list: {role: schematic}}
"""

PDF = b"%PDF-1.4\n" + b"x" * 4000
GIF = b"GIF89a" + b"x" * 4000
TINY_GIF = b"GIF89a" + b"x" * 50
PAGE = b"""<html><body>
  <a href="https://cdn.example/big/fuzz.png"><img src="https://cdn.example/small/fuzz.png"></a>
  <img src="https://cdn.example/img/site-logo.png">
  <img src="https://elsewhere.example/img/other.png">
  <img src="/local/schematic.gif">
</body></html>"""
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 9000


class Server:
    """Canned answers by URL, and the record of what was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.asked: list[str] = []

    def get(self, url, **kw):
        self.asked.append(url)
        answer = self.answers.get(url)
        if answer is None:
            return Response(404, url)
        return answer(url) if callable(answer) else answer


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A registry, a URL list per source, and a private root, all under tmp_path."""
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    (tmp_path / "material" / "source_lists").mkdir(parents=True)
    return data


def write_list(source: str, assets: list[dict]) -> None:
    with open(config.source_list(source), "w", encoding="utf-8") as f:
        for a in assets:
            f.write(json.dumps(a) + "\n")


def serve(monkeypatch, answers) -> Server:
    server = Server(answers)
    monkeypatch.setattr(D.http, "get", server.get)
    return server


def ledger(source: str) -> Ledger:
    return Ledger(config.schematics_state(source))


def test_a_listed_file_is_stored_under_the_name_the_ocr_tree_expects(site, monkeypatch):
    url = "https://ac.example/downloads/fender/Bandmaster-sch.pdf"
    write_list("audiocircuit", [{"url": url, "title": "Bandmaster", "kind": "schematic"}])
    serve(monkeypatch, {url: Response(200, url, "application/pdf", PDF)})

    D.run("audiocircuit", log=lambda *a: None)

    stored = config.downloads("audiocircuit") / "pdf" / D.safe_name(url, "pdf")
    assert stored.read_bytes() == PDF
    row = ledger("audiocircuit").get(url)
    assert (row["role"], row["type"], row["http"], row["bytes"]) == ("schematic", "pdf", "200", str(len(PDF)))
    assert row["sha256"] and row["download_at"] and not row["skip_reason"]
    assert row["url"] == ""                      # the key is the URL; the column stays empty, as everywhere


def test_the_second_run_asks_for_nothing(site, monkeypatch):
    url = "https://ac.example/a.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    serve(monkeypatch, {url: Response(200, url, "application/pdf", PDF)})
    D.run("audiocircuit", log=lambda *a: None)

    again = serve(monkeypatch, {url: Response(200, url, "application/pdf", PDF)})
    counts = D.run("audiocircuit", log=lambda *a: None)
    assert again.asked == [] and counts["already had"] == 1


def test_a_refusal_that_will_not_change_is_recorded_once(site, monkeypatch):
    url = "https://ac.example/gone.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    serve(monkeypatch, {url: Response(404, url)})
    D.run("audiocircuit", log=lambda *a: None)
    assert ledger("audiocircuit").get(url)["skip_reason"] == "http 404"

    again = serve(monkeypatch, {url: Response(404, url)})
    D.run("audiocircuit", log=lambda *a: None)
    assert again.asked == []                     # a 404 is asked once, not on every run


def test_a_transient_failure_is_left_for_the_next_run(site, monkeypatch):
    url = "https://ac.example/busy.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    serve(monkeypatch, {url: Response(503, url, why="gave up after 4 attempts (503)")})
    D.run("audiocircuit", log=lambda *a: None)
    assert ledger("audiocircuit").get(url) is None              # nothing stamped, nothing skipped

    again = serve(monkeypatch, {url: Response(200, url, "application/pdf", PDF)})
    D.run("audiocircuit", log=lambda *a: None)
    assert again.asked == [url] and ledger("audiocircuit").get(url)["type"] == "pdf"


def test_robots_is_recorded_as_the_reason(site, monkeypatch):
    url = "https://ac.example/private/x.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    serve(monkeypatch, {url: Response(0, url, why="disallowed by robots.txt")})
    D.run("audiocircuit", log=lambda *a: None)
    assert ledger("audiocircuit").get(url)["skip_reason"] == "robots.txt"


def test_a_page_served_where_a_pdf_was_promised_is_not_stored(site, monkeypatch):
    url = "https://ac.example/soft404.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    serve(monkeypatch, {url: Response(200, url, "text/html", b"<html>not found</html>")})
    D.run("audiocircuit", log=lambda *a: None)
    assert ledger("audiocircuit").get(url)["skip_reason"] == "not the declared file type"
    assert not (config.downloads("audiocircuit") / "html").exists()


def test_a_layout_post_brings_its_drawing_from_the_blog_cdn(site, monkeypatch):
    post = "https://lay.example/2023/09/thorpy-dane.html"
    write_list("layouts", [{"url": post, "title": "Thorpy FX The Dane", "kind": "layout"}])
    server = serve(monkeypatch, {
        post: Response(200, post, "text/html", PAGE),
        "https://cdn.example/big/fuzz.png": Response(200, "https://cdn.example/big/fuzz.png", "image/png", PNG),
        "https://cdn.example/small/fuzz.png": Response(200, "https://cdn.example/small/fuzz.png", "image/png", TINY_GIF),
        "https://cdn.example/img/site-logo.png": Response(200, "https://cdn.example/img/site-logo.png", "image/png", PNG),
        "https://lay.example/local/schematic.gif": Response(200, "https://lay.example/local/schematic.gif", "image/gif", GIF),
    })
    D.run("layouts", log=lambda *a: None)

    led = ledger("layouts")
    assert led.get(post)["type"] == "html" and led.get(post)["role"] == "layout"
    assert led.get("https://cdn.example/big/fuzz.png")["type"] == "png"          # the full-size drawing
    assert led.get("https://lay.example/local/schematic.gif")["type"] == "gif"   # and the page's own image
    assert "https://elsewhere.example/img/other.png" not in server.asked         # another site's image is not ours
    assert "https://cdn.example/img/site-logo.png" not in server.asked           # furniture is never fetched
    assert led.get("https://cdn.example/small/fuzz.png")["skip_reason"] == "small image"


def test_a_source_that_is_not_active_is_refused(site, monkeypatch):
    write_list("later", [{"url": "https://soon.example/a.pdf", "kind": "schematic"}])
    serve(monkeypatch, {})
    with pytest.raises(SystemExit, match="set it to active"):
        D.run("later", log=lambda *a: None)


def test_dry_run_touches_nothing(site, monkeypatch):
    url = "https://ac.example/a.pdf"
    write_list("audiocircuit", [{"url": url, "kind": "schematic"}])
    server = serve(monkeypatch, {url: Response(200, url, "application/pdf", PDF)})
    counts = D.run("audiocircuit", dry=True, log=lambda *a: None)
    assert server.asked == [] and counts["would fetch"] == 1
    assert not config.schematics_state("audiocircuit").exists()


BLOG = b"""<html><body>
  <a href="https://cdn.example/img/b/x/s1008/Dane.png"><img src="https://cdn.example/img/b/x/s320/Dane.png"></a>
  <img src="https://cdn.example/img/b/x/w72-h72-p-k-no-nu/AnotherPost.png">
</body></html>"""


def test_a_preview_and_a_neighbour_s_thumbnail_are_not_the_drawing(site, monkeypatch):
    """Blogger serves the same file at several sizes and shows a strip of other posts' thumbnails.
    Only the full-size file of this post is worth a request."""
    post = "https://lay.example/2023/01/dane.html"
    write_list("layouts", [{"url": post, "kind": "layout"}])
    big = "https://cdn.example/img/b/x/s1008/Dane.png"
    server = serve(monkeypatch, {
        post: Response(200, post, "text/html", BLOG),
        big: Response(200, big, "image/png", PNG),
    })
    D.run("layouts", log=lambda *a: None)

    assert server.asked == [post, big]
    assert ledger("layouts").get(big)["type"] == "png"


def test_detaching_hands_the_work_over_and_does_none_of_it(site, monkeypatch):
    """The launcher lives in core.jobs; what matters here is what this stage hands it."""
    handed = {}
    monkeypatch.setattr(D, "detach", lambda module, args, name: handed.update(module=module, args=args, name=name) or 999)
    monkeypatch.setattr(D, "run", lambda *a, **k: pytest.fail("the parent must not download anything"))

    assert D.main(["--source", "tagboard", "--source", "dirtbox", "--detach"]) == 0
    assert handed["name"] == "download_tagboard-dirtbox"
    assert handed["module"] == D.MODULE
    assert "--detach" not in handed["args"]                  # or the child would detach again, forever
