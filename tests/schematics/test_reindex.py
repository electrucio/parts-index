"""Reading the corpus again: what one page becomes, and where on the page a part was found."""
from parts_index.core.parts import extractor as parts
from parts_index.schematics import reindex


def page(texts, boxes=None, w=1000, h=1000):
    boxes = boxes or [[0, 0, 10, 10]] * len(texts)
    return {"w": w, "h": h, "page": 1,
            "blocks": [{"box": b, "text": t, "conf": 0.99} for t, b in zip(texts, boxes)]}


def test_one_row_per_part_per_page_carrying_how_it_was_read():
    p = page("V1 V2 12AX7 12AX7 6V6 R1 C1".split())
    _, summ = reindex.page_record(p)
    assert summ["12AX7"]["n"] == 2 and summ["12AX7"]["n_label"] == 2      # twice, both as a short label
    assert summ["12AX7"]["kind"] == "tube" and summ["12AX7"]["conf"] == "high"
    assert summ["6V6"]["base"] == "6V6"


def test_a_repaired_read_says_so():
    _, summ = reindex.page_record(page(["IN4148", "R1", "C1"]))
    assert summ["1N4148"]["read_by"] == "ocr_fix"                          # the leading I was a 1


def test_a_part_carries_where_it_is_and_what_is_printed_beside_it():
    texts = ["2N3904", "Q3", "R7", "12AX7"]
    boxes = [[400, 500, 460, 520], [402, 530, 430, 548], [900, 100, 930, 118], [10, 10, 60, 28]]
    _, summ = reindex.page_record(page(texts, boxes, w=1000, h=1000))
    box, near = summ["2N3904"]["boxes"][0], summ["2N3904"]["near"]
    assert box == [400, 500, 460, 520]                                     # thousandths of a 1000x1000 page
    assert near == ["Q3"]                                                  # R7, across the page, is not beside it


def test_the_advert_score_is_recomputed_because_it_depends_on_what_was_read():
    feats, _ = reindex.page_record(page("V1 V2 12AX7 6V6 R1 C1 R2 C2".split()))
    assert feats["is_ad"] == 0 and feats["n_desig"] >= 4
    assert set(feats) >= {"n_blocks", "n_parts", "ad_score", "has_schematic", "seq_run", "priced_rows"}


def test_summarise_keeps_the_highest_confidence_seen():
    Hit = parts.Hit
    hits = [(Hit("X1", "X1", "X1", "fam", "bjt", "medium", False, 0), False),
            (Hit("X1", "X1", "X1", "fam", "bjt", "high", False, 1), True)]
    d = reindex.summarise(hits)["X1"]
    assert d["conf"] == "high" and d["n"] == 2 and d["n_label"] == 1
