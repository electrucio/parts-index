"""Checking the pages a search found: what is published, what is dropped, and what waits."""
import json

from parts_index.core import http
from parts_index.datasheets import polarity as D

PAGES = {
    "https://a.example/bc109.html": (200, b"<html><b>BC109</b> NPN silicon planar transistor</html>"),
    "https://a.example/bd139.html": (200, b"<p>BD139 NPN and BD140 PNP medium power</p>"),
    "https://slow.example/ac127.html": (429, b""),
    "https://slow.example/oc72.html": (200, b"OC72 PNP germanium"),
    "https://gone.example/2n1132.html": (404, b""),
}


def test_a_page_is_published_only_when_it_says_it_and_a_slow_host_waits(tmp_path, monkeypatch):
    asked = []

    def get(url, **_):
        asked.append(url)
        status, body = PAGES[url]
        return http.Response(status, url, body=body, why="" if status == 200 else f"http {status}")

    monkeypatch.setattr(D.http, "get", get)
    monkeypatch.setattr(D, "datasheets_state", lambda _: tmp_path / "state.csv")
    monkeypatch.setattr(D, "datasheet_polarity", lambda: tmp_path / "polarity.csv")
    found = tmp_path / "found.jsonl"
    found.write_text("".join(json.dumps(c) + "\n" for c in [
        {"part": "BC109", "polarity": "NPN", "url": "https://a.example/bc109.html"},
        {"part": "BD139", "polarity": "NPN", "url": "https://a.example/bd139.html"},
        {"part": "AC127", "polarity": "NPN", "url": "https://slow.example/ac127.html"},
        {"part": "OC72", "polarity": "PNP", "url": "https://slow.example/oc72.html"},
        {"part": "2N1132", "polarity": "PNP", "url": "https://gone.example/2n1132.html"},
        {"part": "X1", "polarity": "", "url": "https://a.example/x1.html"},        # nothing claimed
    ]), encoding="utf-8")
    n = D.run([found], say=lambda _: None)
    assert n == {"says it": 1, "does not say it": 1, "come back later": 2, "page not read": 1}
    assert "https://slow.example/oc72.html" not in asked          # the host asked us to slow down
    published = (tmp_path / "polarity.csv").read_text(encoding="utf-8").splitlines()
    assert len(published) == 2 and published[1].startswith("BC109,NPN,https://a.example/bc109.html,")
    # A second run asks again only what waited: the slow host's two pages.
    asked.clear()
    D.run([found], say=lambda _: None)
    assert asked == ["https://slow.example/ac127.html"]
