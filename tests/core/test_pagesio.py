from parts_index.core import pagesio

PAGES = [{"page": 1, "w": 100, "h": 50, "how": "ocr", "blocks": [{"box": [1, 2, 30, 12], "text": "BC109 µA741", "conf": 0.97}]},
         {"page": 2, "w": 100, "h": 50, "how": "text", "blocks": []}]


def test_round_trip_and_done_marker(tmp_path):
    assert not pagesio.is_done(tmp_path, "doc.pdf") and pagesio.existing(tmp_path, "doc.pdf") is None
    path = pagesio.write_pages(tmp_path / "src", "doc.pdf", PAGES)
    assert path.name == "doc.pdf.jsonl.gz" and pagesio.is_done(tmp_path / "src", "doc.pdf")
    assert pagesio.read_pages(path) == PAGES
    assert not list((tmp_path / "src").glob("*.tmp"))


def test_reads_uncompressed_files_from_early_runs(tmp_path):
    import json
    p = tmp_path / "old.pdf.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in PAGES) + "\n\n", encoding="utf-8")
    assert pagesio.existing(tmp_path, "old.pdf") == p and pagesio.read_pages(p) == PAGES
    assert not pagesio.is_done(tmp_path, "old.pdf")            # no marker: treated as unfinished
