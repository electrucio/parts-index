"""Assembling the one OCR tree. Tiny in-memory index, never the real corpus."""
import csv
import gzip
import json
import sqlite3

import pytest

from parts_index.migrate import ocr_tree as m

SCHEMA = """
create table documents (doc_id integer primary key, source text, doc_key text, text_method text,
                        ocr_path text, local_path text, n_pages int, link_verified int, link_ok int, checked_at text);
create table pages (page_id integer primary key, doc_id int, page_no int, w_pt real, h_pt real);
create table page_text (page_id integer primary key, text text);
"""

MAGAZINE = "https://w.example/ww-1974.pdf"
BOXED = "https://sound.example/p1.pdf"
HTML = "https://sound.example/projects.htm"
ARTICLE = "https://archive.example/E_1998_01.pdf#e981014.pdf"


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.executemany("insert into documents values (?,?,?,?,?,?,?,?,?,?)", [
        # a magazine: its OCR path is recorded relative to magazines/
        (1, "wireless_world", MAGAZINE, "ocr", "ocr/wireless_world/ww-1974.pdf.jsonl.gz", None, 1, 0, None, None),
        # a page OCR'd with boxes: its file is found from the name of the file it was read from
        (2, "esp", BOXED, "ocr_boxes", None, "/private/raw/esp/pdf/ab_p1.pdf", 1, 0, None, None),
        # an HTML page: no OCR file ever existed, and one chunk of text is all there was
        (3, "esp", HTML, "text", None, "/private/raw/esp/html/cd.htm", 1, 1, 1, "2026-09-19"),
        # a born-digital article whose source is gone: the database is its last copy
        (4, "elektor", ARTICLE, "text", None, None, 2, 0, None, None),
    ])
    c.executemany("insert into pages values (?,?,?,?,?)", [
        (10, 1, 1, 612.0, 792.0), (11, 2, 1, None, None),
        (12, 3, 1, None, None), (13, 4, 1, 595.0, 842.0), (14, 4, 2, 595.0, 842.0),
    ])
    c.executemany("insert into page_text values (?,?)", [
        (10, "magazine text"), (11, "boxed page text"),
        (12, "A TL072 and a BC109 walk into a project page"),
        (13, "Elektor article page one, with an NE5534"),
        (14, "   "),                                   # a blank page is not written out
    ])
    yield c
    c.close()


@pytest.fixture()
def legacy(tmp_path):
    """A corpus holding the two documents the old pipeline did OCR."""
    root = tmp_path / "old"
    for rel, text in [("magazines/ocr/wireless_world/ww-1974.pdf.jsonl.gz", "from the magazine OCR"),
                      ("ocr_boxes/esp/ab_p1.pdf.jsonl.gz", "from the boxed OCR")]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(json.dumps({"page": 1, "how": "ocr", "blocks": [{"box": [1, 2, 3, 4], "text": text, "conf": 0.9}]}) + "\n")
    return root


def test_the_old_pipeline_kept_its_ocr_in_three_ways():
    assert m.legacy_file("ww", "ocr", "ocr/ww/x.pdf.jsonl.gz", None) == "magazines/ocr/ww/x.pdf.jsonl.gz"
    assert m.legacy_file("elektor", "ocr+text", "elektor/ocr/1975-02.jsonl.gz", None) == "elektor/ocr/1975-02.jsonl.gz"
    assert m.legacy_file("esp", "ocr_boxes", None, "/private/raw/esp/pdf/ab_p1.pdf") == "ocr_boxes/esp/ab_p1.pdf.jsonl.gz"
    assert m.legacy_file("esp", "text", None, "/private/raw/esp/html/cd.htm") is None


def test_one_scheme_whatever_the_origin():
    assert m.canonical("ww", "magazines/ocr/ww/x.pdf.jsonl.gz", "k") == "ww/x.pdf.jsonl.gz"
    assert m.canonical("elektor", "elektor/ocr/1975-02.jsonl.gz", "k") == "elektor/1975-02.jsonl.gz"
    assert m.canonical("esp", None, HTML).startswith("esp/") and m.canonical("esp", None, HTML).endswith(".jsonl.gz")


def test_gathers_what_exists_and_writes_what_does_not(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    counts = m.run(db, out, corpus_root=legacy)

    assert counts["documents"] == 4
    assert counts["copied"] == 2                       # the magazine and the boxed page
    assert counts["written"] == 2                      # the HTML page and the article
    assert counts["written_pages"] == 2                # the article's blank second page is skipped
    assert counts["no_pages"] == 0 and counts["collisions"] == 0
    assert (out / "wireless_world/ww-1974.pdf.jsonl.gz").is_file()
    assert (out / "esp/ab_p1.pdf.jsonl.gz").is_file()


def test_a_gathered_file_keeps_its_contents(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    m.run(db, out, corpus_root=legacy)
    rec = json.loads(gzip.open(out / "esp/ab_p1.pdf.jsonl.gz", "rt").readline())
    assert rec["how"] == "ocr" and rec["blocks"][0]["text"] == "from the boxed OCR"


def test_a_written_page_is_an_ordinary_ocr_record(db, legacy, tmp_path):
    from parts_index.core import pagesio
    from parts_index.core.parts import extractor

    out = tmp_path / "ocr"
    m.run(db, out, corpus_root=legacy)
    recs = pagesio.read_pages(out / m.canonical("esp", None, HTML))
    assert len(recs) == 1 and recs[0]["how"] == "text"
    assert [h.part for h in extractor.extract_page(recs[0])] == ["TL072", "BC109"]


def test_page_geometry_survives_when_the_database_had_it(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    m.run(db, out, corpus_root=legacy)
    rec = json.loads(gzip.open(out / m.canonical("elektor", None, ARTICLE), "rt").readline())
    assert rec["w_pt"] == 595.0 and rec["h_pt"] == 842.0      # a zoom link still has something to aim at


def test_the_map_resolves_every_document_and_names_no_local_path(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    m.run(db, out, corpus_root=legacy)
    rows = list(csv.DictReader(open(out / "ocr_map.csv", encoding="utf-8")))
    assert len(rows) == 4
    assert all(r["ocr_file"] and r["origin"] in ("copied", "written") for r in rows)
    assert all((out / r["ocr_file"]).is_file() for r in rows)
    assert "/private/" not in (out / "ocr_map.csv").read_text()


def test_without_a_corpus_everything_comes_from_the_database(db, tmp_path):
    counts = m.run(db, tmp_path / "ocr", corpus_root=None)
    assert counts["copied"] == 0 and counts["written"] == 4


def test_a_document_with_no_pages_points_at_nothing(db, tmp_path):
    db.execute("delete from page_text where page_id = 11")
    db.execute("delete from pages where page_id = 11")
    counts = m.run(db, tmp_path / "ocr", corpus_root=None)
    assert counts["no_pages"] == 1
    rows = {r["doc_key"]: r for r in csv.DictReader(open(tmp_path / "ocr/ocr_map.csv", encoding="utf-8"))}
    assert rows[BOXED]["ocr_file"] == "" and rows[BOXED]["origin"] == ""


def test_running_twice_gathers_nothing_new(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    m.run(db, out, corpus_root=legacy)
    again = m.run(db, out, corpus_root=legacy)
    assert again["copied"] == 0 and again["written"] == 0      # already there: left alone


def test_hand_checked_links_are_kept(db, legacy, tmp_path):
    out = tmp_path / "ocr"
    counts = m.run(db, out, corpus_root=legacy)
    assert counts["linkchecks"] == 1
    row = next(iter(csv.DictReader(open(out / "linkchecks.csv", encoding="utf-8"))))
    assert row["doc_key"] == HTML and row["checked_at"] == "2026-09-19"
