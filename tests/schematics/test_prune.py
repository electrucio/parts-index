"""Making the past agree with the registry: what a narrowed scope drops, and what it must not."""
from __future__ import annotations

import pytest

from parts_index.core import config
from parts_index.core.ledger import Ledger
from parts_index.schematics import prune as P
from parts_index.schematics import verify as V

REGISTRY = """
radiomanual: {kind: reference, title: Radiomanual, home_url: 'https://rm.example/', status: active,
              crawl: {start: ['https://rm.example/'], allow: '^/schemi/', deny: '(?i)_(user|broch)[_.]'}}
xdevs: {kind: site, title: xDevs, home_url: 'https://xd.example/', status: active,
        crawl: {start: ['https://xd.example/'], allow: '^/article/', figures: false}}
tubecad: {kind: site, title: Tube CAD, home_url: 'https://tc.example/', status: active,
          crawl: {start: ['https://tc.example/'], allow: '^/20'}}
audiocircuit: {kind: factory, title: AudioCircuit, home_url: 'https://ac.example/', status: active,
               list: {role: schematic}}
"""


@pytest.fixture
def site(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    return data


def held(source: str, key: str, kind: str, role: str, size: int = 2000):
    """One row the ledger says was downloaded, with its file on disk."""
    led = Ledger(config.schematics_state(source))
    led.stamp(key, "download", role=role, type=kind, http=200, bytes=size, sha256="x" * 64)
    led.save()
    path = config.downloads(source) / kind / P.safe_name(key, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_a_deny_pattern_drops_what_it_would_refuse_today(site):
    manual = held("radiomanual", "https://rm.example/schemi/Y/FT-991_user_DE.pdf", "pdf", "linked")
    service = held("radiomanual", "https://rm.example/schemi/Y/FT-991_serv.pdf", "pdf", "linked")

    P.drop(P.look("radiomanual"), log=lambda *a: None)

    assert not manual.exists() and service.exists()
    led = Ledger(config.schematics_state("radiomanual"))
    assert led.get("https://rm.example/schemi/Y/FT-991_user_DE.pdf")["skip_reason"] == P.REASON
    assert led.get("https://rm.example/schemi/Y/FT-991_serv.pdf")["skip_reason"] == ""


def test_what_was_dropped_is_not_a_hole_and_is_never_fetched_again(site):
    """The ledger goes on saying the URL was fetched, so nothing asks for it; verify reads the reason."""
    held("radiomanual", "https://rm.example/schemi/Y/FT-991_user_DE.pdf", "pdf", "linked")
    P.drop(P.look("radiomanual"), log=lambda *a: None)

    report = V.look("radiomanual")
    assert report["counts"]["lost"] == 0 and report["broken"] == []

    # ... and the judgement is undone by the reason it was made under, not by hand in the file.
    led = Ledger(config.schematics_state("radiomanual"))
    assert V.clear(led, [P.REASON]) == 1
    assert V.look("radiomanual")["counts"]["lost"] == 1


def test_figures_off_drops_the_pictures_and_keeps_a_document_found_among_them(site):
    """92 of the URLs xdevs shows as images answer with a PDF, and a PDF is a document wherever it was
    found."""
    photo = held("xdevs", "https://xd.example/article/a/top.jpg", "jpeg", "figure")
    sheet = held("xdevs", "https://xd.example/article/a/looks-like.jpg", "pdf", "figure")
    linked = held("xdevs", "https://xd.example/article/a/manual.pdf", "pdf", "linked")

    P.drop(P.look("xdevs"), log=lambda *a: None)

    assert not photo.exists()
    assert sheet.exists() and linked.exists()


def test_the_pages_a_crawl_walked_are_kept(site):
    """A page is how a later run reads its links again without asking for them."""
    page = held("xdevs", "https://xd.example/article/a/", "html", "page")
    P.drop(P.look("xdevs"), log=lambda *a: None)
    assert page.exists()


def test_a_source_with_nothing_to_refuse_drops_nothing(site):
    held("tubecad", "https://tc.example/2024/a.png", "png", "figure")      # no deny, figures on
    held("audiocircuit", "https://ac.example/a.pdf", "pdf", "schematic")   # a list, not a crawl
    assert P.look("tubecad")["keys"] == []
    assert P.look("audiocircuit")["keys"] == []


def test_a_dry_run_deletes_nothing(site, capsys):
    url = "https://rm.example/schemi/Y/FT-991_user_DE.pdf"
    manual = held("radiomanual", url, "pdf", "linked", 1 << 20)
    P.main(["--source", "radiomanual", "--dry"])

    assert manual.exists()
    assert Ledger(config.schematics_state("radiomanual")).get(url)["skip_reason"] == ""
    assert "would drop 1 files" in capsys.readouterr().out
