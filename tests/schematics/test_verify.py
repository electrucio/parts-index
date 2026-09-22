"""Telling a file that was deleted on purpose from one that was lost before anything read it."""
from __future__ import annotations

import hashlib

import pytest

from parts_index.core import config
from parts_index.core.http import Response
from parts_index.core.ledger import Ledger
from parts_index.schematics import download as D
from parts_index.schematics import verify as V

REGISTRY = """
esp: {kind: site, title: ESP, home_url: 'https://e.org/', status: active, list: {role: schematic}}
"""
PDF = b"%PDF-1.4\n" + b"x" * 4000


@pytest.fixture
def source(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    return data


def record(key, **values):
    led = Ledger(config.schematics_state("esp"))
    led.stamp(key, "download", type="pdf", role="schematic", http=200, bytes=len(PDF),
              sha256=hashlib.sha256(PDF).hexdigest())
    for field, value in values.items():
        led.row(key)[field] = value
    led.save()


def put(key, body=PDF, kind="pdf"):
    path = config.downloads("esp") / kind / D.safe_name(key, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_a_file_deleted_after_it_was_read_is_not_a_problem(source):
    record("https://e.org/read.pdf", ocr_at="2026-09-21", ocr_v="ocr_boxes-1")
    assert V.look("esp")["counts"] == {"held": 0, "released": 1, "lost": 0, "changed": 0, "unknown": 0}


def test_a_file_lost_before_anything_read_it_is_the_hole(source):
    record("https://e.org/never-read.pdf")
    report = V.look("esp")
    assert report["counts"]["lost"] == 1
    assert report["broken"] == ["https://e.org/never-read.pdf"]


def test_a_page_counts_as_read_once_the_index_has_it(source):
    """An HTML page needs no OCR, so what makes its file disposable is the index having read it."""
    led = Ledger(config.schematics_state("esp"))
    led.stamp("https://e.org/a.html", "download", type="html", role="project_page", http=200, bytes=10)
    led.save()
    assert V.look("esp")["counts"]["lost"] == 1        # nothing has read it yet

    led = Ledger(config.schematics_state("esp"))
    led.stamp("https://e.org/a.html", "index", version="parts-1")
    led.save()
    assert V.look("esp")["counts"]["released"] == 1


def test_a_file_that_is_here_is_held_and_its_checksum_is_only_read_when_asked(source):
    key = "https://e.org/here.pdf"
    record(key)
    put(key)
    assert V.look("esp")["counts"]["held"] == 1

    put(key, b"%PDF-1.4\nsomething else")
    assert V.look("esp")["counts"]["held"] == 1             # presence only, by default
    assert V.look("esp", deep=True)["counts"]["changed"] == 1


def test_repair_asks_only_for_the_holes_and_says_when_the_bytes_differ(source, monkeypatch):
    record("https://e.org/read.pdf", ocr_at="2026-09-21")       # released: must not be asked for
    record("https://e.org/lost.pdf")                            # the hole
    asked = []

    def server(url, **kw):
        asked.append(url)
        return Response(200, url, "application/pdf", PDF)

    monkeypatch.setattr(D.http, "get", server)
    out = V.repair(V.look("esp"), log=lambda *a: None)

    assert asked == ["https://e.org/lost.pdf"]
    assert out == {"recovered": 1, "differs": 0, "gone": 0}
    assert V.look("esp")["counts"] == {"held": 1, "released": 1, "lost": 0, "changed": 0, "unknown": 0}


def test_repair_reports_a_source_that_now_serves_something_else(source, monkeypatch):
    record("https://e.org/lost.pdf")
    monkeypatch.setattr(D.http, "get",
                        lambda url, **kw: Response(200, url, "application/pdf", b"%PDF-1.4\nnew edition"))
    out = V.repair(V.look("esp"), log=lambda *a: None)
    assert out["differs"] == 1

    row = Ledger(config.schematics_state("esp")).get("https://e.org/lost.pdf")
    assert row["ocr_at"] == "" and row["index_at"] == ""     # the input changed: later stages run again


def test_a_refusal_a_changed_rule_wrote_can_be_forgotten(source, monkeypatch):
    """A rule that was wrong leaves rows refused for a reason that no longer applies."""
    record("https://e.org/truncated.pdf")
    led = Ledger(config.schematics_state("esp"))
    led.skip("https://e.org/truncated.pdf", "small image")
    led.save()
    assert V.look("esp")["counts"]["lost"] == 0            # a refusal is not a hole

    report = V.look("esp", retry=["small image"])
    assert report["counts"]["lost"] == 1                   # asked about again, now that the rule has changed
    assert Ledger(config.schematics_state("esp")).get("https://e.org/truncated.pdf")["skip_reason"] == ""
