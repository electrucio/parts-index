"""The reading stage: what it takes from the ledger, how shards divide it, and the page decision."""
import csv

import pytest

from parts_index.core.ledger import Ledger
from parts_index.schematics import ocr


class FakePage:
    """Only what the text-layer path asks of a page: its words, each with a box, a block and a line."""

    def __init__(self, words):
        self._words = words

    def get_text(self, what):
        return self._words


def test_a_text_layer_becomes_line_blocks_in_the_rendered_pages_pixels():
    words = [(10, 20, 30, 28, "IC1", 0, 0, 0), (35, 20, 60, 28, "TL072", 0, 0, 1),
             (10, 40, 25, 48, "R1", 0, 1, 0)]
    blocks = ocr._text_blocks(FakePage(words), zoom=2.0)
    assert [b["text"] for b in blocks] == ["IC1 TL072", "R1"]        # one block per line, words joined
    assert blocks[0]["box"] == [20, 40, 120, 56]                     # the line's bounding box, times the zoom
    assert all(b["conf"] == 1.0 for b in blocks)                     # a text layer is not a guess


def test_a_page_with_no_text_layer_and_no_ocr_says_so_instead_of_writing_an_empty_page(tmp_path):
    """The failure that matters: a scanned sheet read without an OCR loaded would otherwise be stored as a
    page with nothing on it, and the ledger would call it done."""
    pytest.importorskip("fitz")
    import fitz

    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "scan.pdf"
    doc.save(path)
    with pytest.raises(RuntimeError, match="no text layer"):
        ocr.read_document(path, "pdf", read_image=None)


def _ledger_with(tmp_path, n):
    led = Ledger(tmp_path / "state" / "src.csv")
    for i in range(n):
        led.stamp(f"https://example.org/{i}.pdf", "download", sha256=f"{i:040d}", type="pdf", http=200)
    led.save()
    return led


def test_shards_divide_the_work_once_each(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "registry_entry", lambda source: {})
    monkeypatch.setattr(ocr, "schematics_state", lambda source: tmp_path / "state" / "src.csv")
    _ledger_with(tmp_path, 10)
    halves = [ocr.run("src", shard=f"{k}/2", dry=True)["to read"] for k in (0, 1)]
    assert halves == [5, 5]
    assert ocr.run("src", dry=True)["to read"] == 10


def test_a_document_already_read_is_not_offered_again(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "registry_entry", lambda source: {})
    monkeypatch.setattr(ocr, "schematics_state", lambda source: tmp_path / "state" / "src.csv")
    led = _ledger_with(tmp_path, 3)
    led.stamp("https://example.org/1.pdf", "ocr", version=ocr.OCR_VERSION, n_pages=4, text_method="ocr_boxes")
    led.save()
    assert ocr.run("src", dry=True)["to read"] == 2


def test_the_map_is_appended_to_never_rewritten(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "ocr_map", lambda: tmp_path / "ocr_map.csv")
    ocr._note_in_map("src", "https://example.org/a.pdf", "ocr_boxes", 12, "aaa_a.pdf")
    ocr._note_in_map("src", "https://example.org/b.pdf", "text", 3, "bbb_b.pdf")
    rows = list(csv.DictReader(open(tmp_path / "ocr_map.csv", encoding="utf-8")))
    assert [r["doc_key"] for r in rows] == ["https://example.org/a.pdf", "https://example.org/b.pdf"]
    assert rows[0]["ocr_file"] == "src/aaa_a.pdf.jsonl.gz" and rows[1]["pages"] == "3"


def test_a_published_key_never_carries_a_path_out_of_a_disk():
    """Ten exported Elektor keys were `<url>#/data/<account>/audio-index/elektor/ia_pdfs/<file>`. The
    fragment identifies the document and is published with it, so it keeps its last two segments only."""
    from parts_index.schematics.export import publishable_key

    # split so this file does not itself carry the shape the guard refuses
    leaked = "https://archive.org/download/x/e991018.pdf#" + "/data" + "/someone/audio-index/elektor/ia_pdfs/e991018.pdf"
    assert publishable_key(leaked) == "https://archive.org/download/x/e991018.pdf#ia_pdfs/e991018.pdf"
    kept = "https://archive.org/download/x/e991026.pdf#Elektor 1999/e991026.pdf"
    assert publishable_key(kept) == kept                      # a relative fragment is the document's name
    assert publishable_key("https://example.org/a.pdf") == "https://example.org/a.pdf"


def test_a_source_read_in_japanese_carries_its_language_in_the_stamp(monkeypatch, tmp_path):
    """Read in English is not read in Japanese: a document stamped with the default is read again when its
    source asks for another language, and one read in that language is not."""
    assert ocr.version_for({}) == ocr.OCR_VERSION
    assert ocr.version_for({"ocr": {"lang": "japan"}}) == f"{ocr.OCR_VERSION}-japan"
    monkeypatch.setattr(ocr, "registry_entry", lambda source: {"ocr": {"lang": "japan"}})
    monkeypatch.setattr(ocr, "schematics_state", lambda source: tmp_path / "state" / "src.csv")
    led = _ledger_with(tmp_path, 3)
    led.stamp("https://example.org/0.pdf", "ocr", version=ocr.OCR_VERSION, n_pages=1, text_method="ocr_boxes")
    led.stamp("https://example.org/1.pdf", "ocr", version=f"{ocr.OCR_VERSION}-japan", n_pages=1, text_method="ocr_boxes")
    led.save()
    assert ocr.run("src", dry=True)["to read"] == 2


def test_a_design_is_read_again_when_its_reader_changes_and_a_scan_is_not(monkeypatch, tmp_path):
    from parts_index.schematics import cad
    monkeypatch.setattr(ocr, "registry_entry", lambda source: {})
    monkeypatch.setattr(ocr, "schematics_state", lambda source: tmp_path / "state" / "src.csv")
    led = _ledger_with(tmp_path, 2)
    led.stamp("https://example.org/2.asc", "download", sha256="2" * 40, type="ltspice_asc", http=200)
    led.stamp("https://example.org/0.pdf", "ocr", version=ocr.OCR_VERSION, n_pages=1, text_method="ocr_boxes")
    led.stamp("https://example.org/2.asc", "ocr", version=ocr.OCR_VERSION, n_pages=1, text_method="text")
    led.save()
    assert ocr.run("src", dry=True)["to read"] == 2               # 1.pdf, never read; 2.asc, read by an older reader
    led.stamp("https://example.org/2.asc", "ocr", version=f"{ocr.OCR_VERSION}-cad{cad.VERSION}", n_pages=1,
              text_method="text")
    led.save()
    assert ocr.run("src", dry=True)["to read"] == 1


def test_a_design_already_on_disk_is_written_again_when_its_reader_changed(monkeypatch, tmp_path):
    """The page file of a scan says it was read; the page file of a design says an older reader read it."""
    from parts_index.core import pagesio
    from parts_index.schematics import cad
    monkeypatch.setattr(ocr, "registry_entry", lambda source: {})
    monkeypatch.setattr(ocr, "schematics_state", lambda source: tmp_path / "state" / "src.csv")
    monkeypatch.setattr(ocr, "ocr_root", lambda: tmp_path / "ocr")
    monkeypatch.setattr(ocr, "ocr_map", lambda: tmp_path / "ocr_map.csv")
    monkeypatch.setattr(ocr, "downloads", lambda source: tmp_path / "downloads")
    url = "https://example.org/amp.asc"
    led = Ledger(tmp_path / "state" / "src.csv")
    led.stamp(url, "download", sha256="a" * 40, type="ltspice_asc", http=200)
    led.stamp(url, "ocr", version=ocr.OCR_VERSION, n_pages=1, text_method="text")
    led.save()
    name = ocr.safe_name(url, "ltspice_asc")
    (tmp_path / "downloads" / "ltspice_asc").mkdir(parents=True)
    (tmp_path / "downloads" / "ltspice_asc" / name).write_text(
        "Version 4\nSHEET 1 1 1\nSYMBOL npn 0 0 R0\nSYMATTR InstName Q1\nSYMATTR Value 2SC1815\n", encoding="utf-8")
    pagesio.write_pages(tmp_path / "ocr" / "src", name, [{"page": 1, "w": 0, "h": 0, "how": "cad", "blocks": []}])
    counts = ocr.run("src")
    assert counts["read"] == 1 and counts["already there"] == 0
    row = Ledger(tmp_path / "state" / "src.csv").get(url)
    assert row["ocr_v"] == f"{ocr.OCR_VERSION}-cad{cad.VERSION}"
    texts = [b["text"] for p in pagesio.read_pages(pagesio.out_path(tmp_path / "ocr" / "src", name)) for b in p["blocks"]]
    assert "2SC1815" in texts
