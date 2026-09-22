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
