"""Writing the OCR records the old pipeline never wrote. Tiny in-memory index, never the real corpus."""
import gzip
import json
import sqlite3

import pytest

from parts_index.migrate import missing_ocr as m

SCHEMA = """
create table documents (doc_id integer primary key, source text, doc_key text, text_method text,
                        ocr_path text, local_path text, n_pages int, link_verified int, link_ok int, checked_at text);
create table pages (page_id integer primary key, doc_id int, page_no int, w_pt real, h_pt real);
create table page_text (page_id integer primary key, text text);
"""


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    docs = [
        # a magazine: its OCR path is relative to magazines/
        (1, "wireless_world", "https://w.example/ww-1974.pdf", "ocr", "ocr/wireless_world/ww-1974.pdf.jsonl.gz", None, 100, 0, None, None),
        # a site page OCR'd with boxes: found from the file it was read from
        (2, "esp", "https://sound.example/p1.pdf", "ocr_boxes", None, "/private/raw/esp/pdf/ab_p1.pdf", 3, 0, None, None),
        # an HTML page: no OCR file ever existed, and one chunk of text is all there was
        (3, "esp", "https://sound.example/projects.htm", "text", None, "/private/raw/esp/html/cd.htm", 1, 1, 1, "2026-09-19"),
        # a born-digital article whose source is gone: the database is its last copy
        (4, "elektor", "https://archive.example/E_1998_01.pdf#e981014.pdf", "text", None, None, 2, 0, None, None),
    ]
    c.executemany("insert into documents values (?,?,?,?,?,?,?,?,?,?)", docs)
    pages = [(10, 3, 1, None, None), (11, 4, 1, 595.0, 842.0), (12, 4, 2, 595.0, 842.0), (13, 1, 1, 612.0, 792.0)]
    c.executemany("insert into pages values (?,?,?,?,?)", pages)
    c.executemany("insert into page_text values (?,?)", [
        (10, "A TL072 and a BC109 walk into a project page"),
        (11, "Elektor article page one, with an NE5534"),
        (12, "   "),                                   # blank pages are not frozen
        (13, "magazine text that already has an OCR file"),
    ])
    yield c
    c.close()


def test_the_three_ocr_conventions(tmp_path):
    assert m.ocr_file("ww", "ocr", "ocr/ww/x.pdf.jsonl.gz", None) == "magazines/ocr/ww/x.pdf.jsonl.gz"
    assert m.ocr_file("elektor", "ocr+text", "elektor/ocr/1975-02.jsonl.gz", None) == "elektor/ocr/1975-02.jsonl.gz"
    assert m.ocr_file("esp", "ocr_boxes", None, "/private/raw/esp/pdf/ab_p1.pdf") == "ocr_boxes/esp/ab_p1.pdf.jsonl.gz"
    assert m.ocr_file("esp", "text", None, "/private/raw/esp/html/cd.htm") is None


def test_writes_only_what_has_no_ocr_file(db, tmp_path):
    counts = m.run(db, tmp_path, corpus_root=None)     # None: trust the convention, do not check disk
    assert counts["documents"] == 4
    assert counts["with_ocr"] == 2                              # the magazine and the boxed site page
    assert counts["written"] == 2                                # the HTML page and the Elektor article
    assert counts["written_pages"] == 2                          # the blank second page is skipped


def test_a_written_page_is_an_ordinary_ocr_record(db, tmp_path):
    from parts_index.core import pagesio
    from parts_index.core.parts import extractor

    m.run(db, tmp_path, corpus_root=None)
    path = tmp_path / m.written_name("esp", "https://sound.example/projects.htm")
    recs = pagesio.read_pages(path)
    assert len(recs) == 1 and recs[0]["how"] == "text"
    assert [h.part for h in extractor.extract_page(recs[0])] == ["TL072", "BC109"]


def test_page_geometry_survives_when_the_database_had_it(db, tmp_path):
    m.run(db, tmp_path, corpus_root=None)
    rec = json.loads(gzip.open(tmp_path / m.written_name(
        "elektor", "https://archive.example/E_1998_01.pdf#e981014.pdf"), "rt").readline())
    assert rec["w_pt"] == 595.0 and rec["h_pt"] == 842.0        # a zoom link still has something to aim at


def test_the_map_resolves_every_document(db, tmp_path):
    import csv
    m.run(db, tmp_path, corpus_root=None)
    rows = list(csv.DictReader(open(tmp_path / "ocr_map.csv", encoding="utf-8")))
    assert len(rows) == 4
    assert all(r["ocr_file"] and r["present"] == "1" for r in rows)
    assert not any("/private/" in line for line in (tmp_path / "ocr_map.csv").read_text().splitlines())


def test_hand_checked_links_are_kept(db, tmp_path):
    import csv
    counts = m.run(db, tmp_path, corpus_root=None)
    assert counts["linkchecks"] == 1
    row = next(iter(csv.DictReader(open(tmp_path / "linkchecks.csv", encoding="utf-8"))))
    assert row["doc_key"] == "https://sound.example/projects.htm" and row["checked_at"] == "2026-09-19"


def test_missing_ocr_file_on_disk_is_written_out_instead(db, tmp_path):
    empty = tmp_path / "nothing_on_disk"        # a corpus root that holds no OCR at all
    empty.mkdir()
    counts = m.run(db, tmp_path / "out", corpus_root=empty)
    assert counts["with_ocr"] == 0 and counts["ocr_missing"] == 2
    assert counts["written"] == 3        # the two text documents plus the magazine, which has text in the DB
