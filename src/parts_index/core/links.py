"""The link a result points at, and where on the page to look.

On a scanned sheet of a 1959 amplifier, ctrl+F finds nothing: the text is a picture. So a result does not
just link to the document, it links to the page and asks the viewer to show the part:

    <pdf>#page=2&zoom=200,51,519&h=617

`zoom=scale,left,top` is the PDF Open Parameters way of asking for a position, and it is the only one
both major viewers honour — Chrome ignores `view=FitR` (measured 2026-09-20 with the Bassman 5F6-A sheet
in Chromium 153 and Firefox 155). The catch is that they disagree about `top`:

    Chrome / PDFium   measured DOWNWARDS from the top of the page, which is Adobe's specification
    Firefox / pdf.js  a PDF user-space y, measured UPWARDS from the bottom

They are mirror images, so **one URL cannot satisfy both**. The link is written Chrome's way and carries
the page height as `&h=`, a key neither viewer knows and both ignore (measured: the rendering is
byte-identical with and without it), so the page offering the link can flip it where it knows better:

    top_firefox = h - top_chrome

That flip happens in the browser, which is the only place that knows which viewer is about to open the
link. `web/src/links.ts` is the other half of this module, and `tests/fixtures/links_cases.json` is
checked by both, because two implementations of one URL must not drift apart.

The box comes from the OCR, in thousandths of the page, and the page size in PDF points says how big a
thousandth is. Without a size — an archive.org reader link, a bare image, a page read before sizes were
recorded — the plain page link is returned rather than a guess.
"""
from __future__ import annotations

import json

ZOOM = 200          # a part label is readable at 200 % and a good part of the sheet is still in view
MARGIN = 0.06       # start the view slightly left of and above the label, so it is not against the edge


def page_url(doc: dict, n: int, q: str = "") -> str:
    """The public link to page `n` of this document.

    Four shapes are in use: no template at all (the document is one page, or a link to a landing page),
    `#page=` for a PDF, archive.org's reader, which counts leaves from zero, and a `?q=` search for a
    book whose reader has no page anchor.
    """
    tpl = doc.get("page_url_tpl")
    if not tpl:
        return doc.get("public_url") or ""
    return tpl.format(url=doc.get("public_url") or "", n=n,
                      leaf=n - 1 + (doc.get("page_offset") or 0), q=q)


def part_url(doc: dict, n: int, boxes=None, q: str = "") -> str:
    """…and, where the viewer can be told, the first box the part was read in."""
    url = page_url(doc, n, q)
    if "#page=" not in url or not boxes:
        return url
    try:
        x0, y0 = (json.loads(boxes)[0] if isinstance(boxes, str) else boxes[0])[:2]
        w_pt, h_pt = doc["w_pt"], doc["h_pt"]
    except (KeyError, IndexError, TypeError, ValueError):
        return url
    if not w_pt or not h_pt:
        return url
    left = max(0.0, x0 / 1000 - MARGIN) * w_pt
    top = max(0.0, y0 / 1000 - MARGIN) * h_pt          # downwards from the top: Chrome's reading
    return f"{url}&zoom={ZOOM},{left:.0f},{top:.0f}&h={h_pt:.0f}"
