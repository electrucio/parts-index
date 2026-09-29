"""The promise of the ledger: a second run does nothing, a version bump redoes one stage only."""
from parts_index.core.ledger import Ledger

URL = "https://example.org/schematics/fuzz.pdf"


def make(tmp_path):
    return Ledger(tmp_path / "state" / "example.csv")


def test_second_run_has_nothing_to_do(tmp_path):
    led = make(tmp_path)
    assert not led.done(URL, "download")
    led.stamp(URL, "download", sha256="aa", http=200, type="pdf", bytes=10)
    led.stamp(URL, "ocr", version="ocr-1", n_pages=3, text_method="ocr_boxes")
    led.stamp(URL, "index", version="parts-1")
    led.save()

    again = make(tmp_path)
    assert again.done(URL, "download") and again.done(URL, "ocr", "ocr-1") and again.done(URL, "index", "parts-1")
    assert again.pending("ocr", "ocr-1") == [] and again.pending("index", "parts-1") == []


def test_version_bump_redoes_only_that_stage(tmp_path):
    led = make(tmp_path)
    led.stamp(URL, "download", sha256="aa")
    led.stamp(URL, "ocr", version="ocr-1")
    led.stamp(URL, "index", version="parts-1")
    assert led.pending("index", "parts-2") == [URL]
    assert led.pending("ocr", "ocr-1") == []
    assert led.done(URL, "download")


def test_changed_input_flows_through_again(tmp_path):
    led = make(tmp_path)
    led.stamp(URL, "download", sha256="aa")
    led.stamp(URL, "ocr", version="ocr-1")
    led.stamp(URL, "index", version="parts-1")
    led.stamp(URL, "download", sha256="bb")                 # the site replaced the file
    assert not led.done(URL, "ocr", "ocr-1") and not led.done(URL, "index", "parts-1")
    led.stamp(URL, "download", sha256="bb")                 # same file again: nothing is cleared
    led.stamp(URL, "ocr", version="ocr-1")
    led.stamp(URL, "download", sha256="bb")
    assert led.done(URL, "ocr", "ocr-1")


def test_stage_order_and_text_documents(tmp_path):
    led = make(tmp_path)
    led.row(URL)
    assert led.pending("download") == [URL] and led.pending("ocr", "ocr-1") == []   # not downloaded yet
    page = "https://example.org/projects/fuzz.html"
    led.stamp(page, "download", sha256="cc", text_method="text")
    assert led.pending("index", "parts-1") == [page]          # born-digital text skips OCR
    assert led.pending("ocr", "ocr-1") == []
    html = "https://example.org/projects/"
    led.stamp(html, "download", sha256="dd", type="html")
    assert html not in led.pending("ocr", "ocr-1") and html in led.pending("index", "parts-1")


def test_skip_is_never_retried(tmp_path):
    led = make(tmp_path)
    led.skip(URL, "404", http=404)
    assert led.done(URL, "download") and led.pending("download") == []
    assert led.summary() == {"items": 1, "skipped": 1, "download": 0, "ocr": 0, "index": 0, "linkcheck": 0}


def test_file_is_sorted_and_stable(tmp_path):
    led = make(tmp_path)
    for u in ("https://b.example/2", "https://a.example/1"):
        led.stamp(u, "download", sha256="x")
    led.save()
    first = led.path.read_text()
    assert first.splitlines()[1].startswith("https://a.example/1")
    again = make(tmp_path)
    again.dirty = True
    again.save()
    assert again.path.read_text() == first
    assert not list(led.path.parent.glob("*.tmp"))


def test_a_verification_stage_is_redone_when_what_it_read_changed(tmp_path):
    """A part's cards stage reads the recipe's model files: a new file means new work, same version or not."""
    from parts_index.core.ledger import VERIFY_FIELDS, VERIFY_STAGES, VERIFY_VERSIONED
    def open_():
        return Ledger(tmp_path / "state.csv", stages=VERIFY_STAGES, fields=VERIFY_FIELDS,
                      versioned=VERIFY_VERSIONED)
    led = open_()
    assert not led.fresh("bjt/2N3904", "cards", "cards-1", "d1")
    led.stamp("bjt/2N3904", "cards", version="cards-1", cards_in="d1")
    led.save()
    again = open_()
    assert again.fresh("bjt/2N3904", "cards", "cards-1", "d1")
    assert not again.fresh("bjt/2N3904", "cards", "cards-1", "d2")      # an input changed
    assert not again.fresh("bjt/2N3904", "cards", "cards-2", "d1")      # the stage changed
    assert not again.fresh("bjt/2N3904", "claims", "claims-1", "d1")    # another stage, not yet run

