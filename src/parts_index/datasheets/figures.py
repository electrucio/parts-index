"""A data sheet's figures: where each is on its page, and what it plots.

    pidx datasheets figures

For each sheet of the figure reference (`config.datasheet_figure_reference()`), every figure is found on
its page and published with what the reference says it plots — axes, scales, series, conditions, the
bench that draws the same graph for a model — into `config.datasheet_figures(doc)`. `pidx datasheets
crops` cuts each figure out of the PDF by that box, for the site to show beside the simulated one.

On a born-digital page a figure is its caption ("Figure 3. Capacitance", in the text layer) and the vector
drawing above it: the grid, the curves and the tick labels. The drawing is taken from the caption up to the
previous caption in the same column, so two figures side by side, or one above the other, are not merged.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

import yaml

from parts_index.bench import record
from parts_index.core.config import (
    datasheet_figure_reference,
    datasheet_figures,
    datasheet_store,
    require,
)
from parts_index.datasheets.rows import reference

VERSION = "figures-1"


def column(page_width: float, cx: float) -> tuple[float, float]:
    """The horizontal span of the column a caption centred at cx heads: a half page, or the whole width
    for a figure centred on the page."""
    if abs(cx - page_width / 2) < page_width * 0.12:
        return 0.0, page_width
    return (0.0, page_width / 2) if cx < page_width / 2 else (page_width / 2, page_width)


GAP = 24.0          # points of white space that end a figure going up from its caption


def union(boxes) -> list[float]:
    """The box around boxes given as (x0, y0, x1, y1). Written out because a grid line has no width or no
    height, and PyMuPDF's union skips empty rectangles — which dropped the top of a chart made of lines."""
    boxes = list(boxes)
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def caption(page, n: int) -> list[float] | None:
    """The box of figure n's caption: the text block holding "Figure n."."""
    hits = page.search_for(f"Figure {n}.")
    if not hits:
        return None
    cap = [hits[0].x0, hits[0].y0, hits[0].x1, hits[0].y1]
    for b in page.get_text("blocks"):
        if b[0] < cap[2] and b[2] > cap[0] and b[1] < cap[3] and b[3] > cap[1]:
            cap = union([cap, b[:4]])
    return cap


def inside_column(page, lo: float, hi: float) -> list[tuple]:
    """The words of the lines that lie within the column: a heading printed across two figures belongs
    to neither, and cut at the column's edge it would read as nonsense."""
    lines: dict[tuple, list] = {}
    for w in page.get_text("words"):
        lines.setdefault((w[5], w[6]), []).append(w)
    out = []
    for ws in lines.values():
        if min(w[0] for w in ws) >= lo - 2 and max(w[2] for w in ws) <= hi + 2:
            out += [tuple(w[:4]) for w in ws]
    return out


def locate(page, n: int) -> list[float] | None:
    """The box (PDF points) of figure n on the page: caption, drawing and the labels around it.

    The drawing is gathered upwards from the caption, one piece at a time, while the next piece starts
    within GAP of what is already taken: a table or another figure above is separated by white space. The
    search stops at the previous caption whose width overlaps this figure's column."""
    cap = caption(page, n)
    if cap is None:
        return None
    lo, hi = column(page.rect.width, (cap[0] + cap[2]) / 2)
    above = 36.0
    for m in range(1, 60):
        other = caption(page, m) if m != n else None
        if other and other[3] < cap[1] and other[0] < hi and other[2] > lo:
            above = max(above, other[3] + 2)
    # drawings and words alike: a note between a circuit and its caption ("* Total shunt capacitance…")
    # must not read as the white space that ends the figure
    words = inside_column(page, lo, hi)
    shapes = [(r.x0, r.y0, r.x1, r.y1) for r in (d["rect"] for d in page.get_drawings())]
    shapes += words
    pieces = sorted((r for r in shapes if r[3] <= cap[1] + 1 and r[1] >= above
                     and lo - 1 <= (r[0] + r[2]) / 2 <= hi + 1 and r[2] - r[0] < hi - lo + 2), key=lambda r: -r[3])
    taken, top = [], cap[1]
    grew = True
    while grew:
        grew = False
        for r in pieces:
            if r not in taken and r[3] >= top - GAP:
                taken.append(r)
                top = min(top, r[1])
                grew = True
    if not taken:
        return None
    box = union(taken)
    # the tick labels and axis titles around the drawing, a rotated y-axis title included
    words = [w for w in words if w[0] >= max(lo, box[0] - 75) and w[2] <= min(hi, box[2] + 20)
             and w[1] >= box[1] - 12 and w[3] <= cap[1] + 1]
    box = union([box, cap, *words])
    return [round(v, 1) for v in (box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3)]


def figure_reference() -> dict[str, list[dict]]:
    doc = yaml.safe_load(require(datasheet_figure_reference(), "the figure reference").read_text(encoding="utf-8"))
    return {d["doc"]: d["figures"] for d in doc["docs"]}


def publish() -> Counter:
    import pymupdf
    c: Counter = Counter()
    led = record.ledger()
    pdfs = {d["doc"]: d["pdf"] for d in reference()}
    for doc, figs in figure_reference().items():
        pdf = datasheet_store() / pdfs[doc]
        dig = record.digest([figs, pdf.stat().st_size if pdf.exists() else 0])
        if led.fresh(f"sheet:{doc}", "figures", VERSION, dig):
            c["fresh"] += 1
            continue
        d = pymupdf.open(pdf) if pdf.exists() else None
        out = []
        for f in figs:
            box = locate(d[f["page"] - 1], f["n"]) if d is not None else None
            out.append({**f, "box": box})
            c["figures"] += 1
            c["located"] += box is not None
        p = datasheet_figures(doc)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"doc": doc, "read_by": "reference", "read_on": "2026-09-29", "figures": out},
                                indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        led.stamp(f"sheet:{doc}", "figures", version=VERSION, figures_in=dig)
        c["sheets"] += 1
    led.save()
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    c = publish()
    print(f"{c['sheets']} sheets written ({c['fresh']} already done): {c['figures']} figures, {c['located']} located")
    return 0


if __name__ == "__main__":
    sys.exit(main())
