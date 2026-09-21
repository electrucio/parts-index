"""The Python half of the link builder, checked against the fixture the TypeScript half also reads."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parts_index.core import links

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "links_cases.json")
                     .read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]


def test_the_two_implementations_agree_on_their_constants():
    assert links.ZOOM == FIXTURE["zoom"]
    assert links.MARGIN == FIXTURE["margin"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case):
    got = links.part_url(case["doc"], case["page"], case.get("boxes"), case.get("q", ""))
    assert got == case["expect"]


def test_page_url_ignores_the_box_that_part_url_would_use():
    """They are two questions: which page, and where on it."""
    doc = {"public_url": "https://e.org/a.pdf", "page_url_tpl": "{url}#page={n}", "w_pt": 612, "h_pt": 792}
    assert links.page_url(doc, 2) == "https://e.org/a.pdf#page=2"
    assert "zoom" in links.part_url(doc, 2, [[150, 720, 210, 745]])


def test_a_document_with_neither_url_nor_template_gives_an_empty_string_not_a_crash():
    assert links.part_url({}, 1) == ""
