"""The half of the index stage that creates rows: a read document becomes a document, its pages and
their text, and nothing else — the parts are `reindex`'s to compute."""
from __future__ import annotations

import csv
import sqlite3

import pytest

from parts_index.core import config, pagesio
from parts_index.core.ledger import Ledger
from parts_index.schematics import ingest as I
from parts_index.schematics.download import safe_name

REGISTRY = """
openhw_parts: {kind: site, title: Designs on GitHub, home_url: 'https://github.com/', status: active,
               list: {role: schematic}}
ti_appnotes: {kind: factory, title: TI application notes, home_url: 'https://www.ti.com/', status: active,
              list: {role: application_note}}
"""

RAW = "https://raw.githubusercontent.com/a/one/HEAD/hw/main.kicad_sch"
BLOB = "https://github.com/a/one/blob/HEAD/hw/main.kicad_sch"
TI = "https://www.ti.com/lit/pdf/sbaa001"


@pytest.fixture
def world(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    return tmp_path


def read_document(source: str, url: str, kind: str, pages: list[dict], listing: dict | None = None):
    """A document the stages before this one have finished with: ledger row, page file, map line."""
    led = Ledger(config.schematics_state(source))
    led.stamp(url, "download", role="schematic", type=kind, http=200, bytes=100, sha256="s" * 64)
    led.stamp(url, "ocr", version="ocr_boxes-1", n_pages=len(pages), text_method="text")
    led.save()
    name = safe_name(url, kind)
    folder = config.ocr_root() / source
    pagesio.write_pages(folder, name, pages)
    path = config.ocr_map()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["source", "doc_key", "text_method", "pages", "ocr_file", "origin"])
        w.writerow([source, url, "text", len(pages), f"{source}/{name}.jsonl.gz", "ocr"])
    if listing:
        import json
        lst = config.source_list(source)
        lst.parent.mkdir(parents=True, exist_ok=True)
        with open(lst, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, **listing}) + "\n")


CAD_PAGES = [{"page": 1, "w": 0, "h": 0, "how": "cad",
              "blocks": [{"text": "U1", "conf": 1.0, "field": "ref"},
                         {"text": "OPA1612", "conf": 1.0, "field": "value"}]}]


def test_a_read_document_becomes_rows_and_its_parts_are_left_to_reindex(world):
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES,
                  listing={"title": "a/one: main.kicad_sch", "page": BLOB, "repo": "a/one"})

    counts = I.run(["openhw_parts"], say=lambda *a: None)

    assert counts["documents"] == 1 and counts["pages"] == 1
    db = sqlite3.connect(config.index_db())
    doc = db.execute("SELECT source, doc_key, role, title, public_url, page_url_tpl, n_pages, text_method, "
                     "ocr_path, extractor_version FROM documents").fetchone()
    assert doc == ("openhw_parts", RAW, "schematic", "a/one: main.kicad_sch", BLOB, None, 1, "text",
                   f"openhw_parts/{safe_name(RAW, 'kicad_sch')}.jsonl.gz", None)
    assert db.execute("SELECT page_no, n_blocks FROM pages").fetchall() == [(1, 2)]
    assert db.execute("SELECT text FROM page_text").fetchone() == ("U1\nOPA1612",)
    assert db.execute("SELECT count(*) FROM page_parts").fetchone() == (0,)      # reindex's job, by version
    assert db.execute("SELECT rowid FROM fts WHERE fts MATCH 'OPA1612'").fetchall() == [(1,)]


def test_the_public_link_is_the_page_a_person_opens_and_the_raw_file_stays_the_key(world):
    """raw.githubusercontent.com serves a schematic as text; the blob page renders it."""
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES, listing={"page": BLOB})
    I.run(["openhw_parts"], say=lambda *a: None)
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT doc_key, public_url FROM documents").fetchone() == (RAW, BLOB)


def test_a_pdf_gets_the_page_template_and_a_factory_document_the_old_role(world):
    read_document("ti_appnotes", TI, "pdf", [{"page": 1, "w": 1, "h": 1, "how": "text",
                                              "blocks": [{"text": "ADS1299", "conf": 1.0, "box": [0, 0, 1, 1]}]}],
                  listing={"title": "SBAA001", "page": TI})
    I.run(["ti_appnotes"], say=lambda *a: None)
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT role, page_url_tpl, title FROM documents").fetchone() == \
        ("service_manual", "{url}#page={n}", "SBAA001")


def test_a_pdf_links_to_itself_even_when_the_listing_names_the_page_it_was_found_on(world):
    """audiocircuit's listing records the brand page a PDF was found on; `{url}#page={n}` on the brand
    page is no link at all. 20,416 uses pointed there before this test."""
    pdf = "https://audiocircuit.dk/downloads/akai/Akai-202DSS-tape-sm.pdf"
    read_document("ti_appnotes", pdf, "pdf", [{"page": 1, "w": 1, "h": 1, "how": "ocr",
                                               "blocks": [{"text": "2SC1815", "conf": 0.9, "box": [0, 0, 1, 1]}]}],
                  listing={"title": "Akai 202DSS", "page": "https://audiocircuit.dk/akai/"})
    I.run(["ti_appnotes"], say=lambda *a: None)
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT public_url FROM documents").fetchone() == (pdf,)


def test_a_second_run_adds_nothing_and_the_ledger_says_indexed(world):
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES, listing={"page": BLOB})
    I.run(["openhw_parts"], say=lambda *a: None)
    again = I.run(["openhw_parts"], say=lambda *a: None)

    assert again["documents"] == 0
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT count(*) FROM documents").fetchone() == (1,)
    led = Ledger(config.schematics_state("openhw_parts"))
    assert led.done(RAW, "index", I.VERSION)


def test_a_title_the_listing_did_not_give_comes_from_the_url(world):
    """`titles.from_url` is the old pipeline's, pinned by its own tests, and it strips one extension;
    `.kicad_sch` is two. Every CAD listing gives a title, so this fallback is for crawled documents."""
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES)
    I.run(["openhw_parts"], say=lambda *a: None)
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT title FROM documents").fetchone() == ("Main.kicad sch",)


def test_a_dry_run_counts_and_writes_nothing(world):
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES)
    counts = I.run(["openhw_parts"], dry=True, say=lambda *a: None)
    assert counts["documents"] == 1
    db = sqlite3.connect(config.index_db())
    assert db.execute("SELECT count(*) FROM documents").fetchone() == (0,)


def test_stamping_the_ledger_keeps_what_another_stage_wrote_meanwhile(world):
    """The downloader is still fetching audiocircuit while the 20,416 documents already read are
    indexed. Each stage saves its whole copy of the ledger; this one must not save the copy it read."""
    read_document("openhw_parts", RAW, "kicad_sch", CAD_PAGES, listing={"page": BLOB})
    other = "https://raw.githubusercontent.com/b/two/HEAD/x.kicad_sch"

    def someone_else_downloads(*a, **k):
        led = Ledger(config.schematics_state("openhw_parts"))
        led.stamp(other, "download", role="schematic", type="kicad_sch", http=200, bytes=1, sha256="t" * 64)
        led.save()
        return I._real_put(*a, **k)

    I._real_put = I.put
    try:
        import unittest.mock as m
        with m.patch.object(I, "put", someone_else_downloads):
            I.run(["openhw_parts"], say=lambda *a: None)
    finally:
        del I._real_put

    led = Ledger(config.schematics_state("openhw_parts"))
    assert led.done(RAW, "index", I.VERSION), "our stamp is there"
    assert led.rows[other]["download_at"], "and so is what the downloader wrote while we worked"


def test_a_page_size_comes_from_the_record_then_the_file_then_a_declared_dpi(tmp_path):
    """The file is temporary by rule, so the size has to come from somewhere that stays."""
    rec = [{"page": 1, "w": 2550, "h": 3300, "w_pt": 612.0, "h_pt": 792.0, "blocks": []}]
    assert I.sizes_for(rec, None, None) == [(612.0, 792.0)]
    px = [{"page": 1, "w": 2550, "h": 3300, "blocks": []}]
    assert I.sizes_for(px, tmp_path / "gone.pdf", 300) == [(612.0, 792.0)]     # Letter at 300 dpi
    assert I.sizes_for(px, tmp_path / "gone.pdf", None) == []                   # no guess without a DPI


def test_sizes_are_filled_in_afterwards_for_pages_indexed_without_them(world):
    """481,319 pages of audiocircuit were indexed after their files were released, with no size and no
    zoom link. The registry says that OCR ran at 300 dpi, and that is enough to recover them."""
    pdf = "https://audiocircuit.dk/downloads/akai/Akai-202DSS-tape-sm.pdf"
    (world / "data" / "schematics" / "sources.yaml").write_text(
        REGISTRY + "audiocircuit: {kind: factory, title: AudioCircuit, home_url: 'https://audiocircuit.dk/',"
        " status: active, list: {role: schematic}, ocr: {dpi: 300}}\n", encoding="utf-8")
    read_document("audiocircuit", pdf, "pdf", [{"page": 1, "w": 2480, "h": 3508, "how": "ocr",
                                                "blocks": [{"text": "2SC1815", "conf": 0.9, "box": [0, 0, 1, 1]}]}])
    I.run(["audiocircuit"], say=lambda *a: None)
    db = sqlite3.connect(config.index_db())
    db.execute("UPDATE pages SET w_pt = NULL, h_pt = NULL")     # as the first ingest left them
    db.commit()
    db.close()

    counts = I.backfill_sizes(["audiocircuit"], say=lambda *a: None)

    db = sqlite3.connect(config.index_db())
    assert counts["pages"] == 1
    assert db.execute("SELECT w_pt, h_pt FROM pages").fetchone() == (595.2, 841.9)     # A4


def test_a_delivered_file_is_published_under_its_public_url_not_its_key():
    """adi_eval keys a file delivery:CN/CN0183.pdf and the registry gives it analog.com's URL; 72 pages went
    out under the key. A delivered file with no public URL is not indexed at all."""
    row = {"key": "delivery:CN/CN0183.pdf", "type": "pdf", "role": "application_note",
           "url": "https://www.analog.com/media/en/reference-design-documentation/reference-designs/CN0183.pdf"}
    doc = I.document_row("adi_eval", {"kind": "delivery"}, row, {"pages": "5"}, {})
    assert doc["public_url"] == row["url"] and doc["doc_key"] == row["key"]      # the key finds its OCR file
    doc = I.document_row("adi_eval", {"kind": "delivery"}, dict(row, url=""), {"pages": "5"}, {})
    assert doc["public_url"] == ""


def test_a_pdf_inside_an_archive_is_linked_as_the_archive_without_a_page():
    row = {"key": "delivery:x/TR0712US.zip!TR0712US/p.pdf", "type": "pdf", "role": "schematic",
           "url": "https://toragi.cqpub.co.jp/Portals/0/download/2007/TR0712US.zip"}
    doc = I.document_row("toragi_zips", {"kind": "delivery"}, row, {"pages": "3"}, {})
    assert doc["public_url"].endswith(".zip") and doc["page_url_tpl"] is None
    row = {"key": "https://e.example/a.pdf", "type": "pdf", "role": "schematic"}
    assert I.document_row("s", {}, row, {"pages": "3"}, {})["page_url_tpl"] == "{url}#page={n}"
