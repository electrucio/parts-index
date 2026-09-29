"""A figure is its caption and the drawing above it, bounded by white space and by the caption above."""
import pytest

from parts_index.datasheets import figures as FG

pymupdf = pytest.importorskip("pymupdf")


def page_with_two_rows_of_figures():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 60), "Ordering information: 2N3904 TO-92 bulk", fontsize=9)   # a table above
    for (x, y, n) in ((60, 120, 1), (330, 120, 2), (60, 420, 3)):
        page.draw_rect(pymupdf.Rect(x + 20, y, x + 230, y + 200))                       # a chart's frame
        for k in range(1, 6):
            page.draw_line((x + 20, y + 40 * k), (x + 230, y + 40 * k))                   # grid lines: no height
        page.insert_text((x + 2, y + 100), "0.5", fontsize=7)                              # a tick label, left
        page.insert_text((x + 60, y + 230), f"Figure {n}. Something", fontsize=9)
    return page


def test_each_figure_is_its_own_chart_and_caption_and_nothing_beside_or_above_it():
    page = page_with_two_rows_of_figures()
    one, two, three = (FG.locate(page, n) for n in (1, 2, 3))
    assert one[0] < 62 and one[1] < 121 and one[2] < 300 and one[3] > 340      # tick label, top line, caption
    assert one[1] > 70                                                          # not the table above
    assert two[0] > 300                                                         # not its left neighbour
    assert three[1] > 355                                                       # not figure 1 above it


def test_a_grid_line_counts_although_it_has_no_height():
    assert FG.union([(0, 10, 100, 10), (0, 50, 100, 60)]) == [0, 10, 100, 60]
