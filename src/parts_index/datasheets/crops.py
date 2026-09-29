"""Crops of the data sheets, for the site to show beside what was read from them.

    pidx datasheets crops [--force]

For every published row (`pidx datasheets rows`) the box on its page it was read from, rendered from the
PDF at 200 dpi as WebP into `config.web_crops()/<doc>/r<row>.webp`. They are quotations (CLAUDE.md
rule 1): one row at a time, shown with the sheet's maker, title, page and link. They are made on the
maintainer's machine, where the PDFs are, and never committed; `make crops-publish` packs them into the
release asset the Pages workflow unpacks into the site.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter

from parts_index.core.config import (
    datasheet_store,
    datasheet_values,
    datasheet_values_index,
    require,
    web_crops,
)
from parts_index.datasheets.rows import manifest

DPI = 200
QUALITY = 82


def crop(page, box) -> bytes:
    """One box of a page as WebP."""
    import pymupdf
    from PIL import Image
    pix = page.get_pixmap(dpi=DPI, clip=pymupdf.Rect(*box))
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


def run(force: bool = False) -> Counter:
    import pymupdf
    c: Counter = Counter()
    by_sha = {f["sha256"]: path for path, f in manifest().items()}
    with open(require(datasheet_values_index(), "cropping the published rows"), encoding="utf-8") as f:
        sheets = list(csv.DictReader(f))
    for sh in sheets:
        path = by_sha.get(sh["sha256"])
        if not path or not (datasheet_store() / path).exists():
            c["no pdf"] += 1
            continue
        doc = pymupdf.open(datasheet_store() / path)
        out = web_crops() / sh["doc"]
        out.mkdir(parents=True, exist_ok=True)
        with open(datasheet_values(sh["doc"]), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r["box"]:
                    continue
                target = out / f"r{r['row']}.webp"
                if target.exists() and not force:
                    c["kept"] += 1
                    continue
                data = crop(doc[int(r["page"]) - 1], json.loads(r["box"]))
                target.write_bytes(data)
                c["made"] += 1
                c["bytes"] += len(data)
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true", help="make every crop again")
    a = ap.parse_args(argv)
    c = run(a.force)
    print(f"{c['made']:,} crops made ({c['bytes'] / 1e3:,.0f} kB), {c['kept']:,} kept; into {web_crops()}")
    if c["no pdf"]:
        print(f"{c['no pdf']} sheets have no PDF on this machine", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
