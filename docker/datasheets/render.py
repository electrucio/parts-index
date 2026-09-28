"""Render the pages golden.yaml lists to PNG, at the resolution the model reads them (150 dpi).

    uv run python docker/datasheets/render.py --golden docker/datasheets/golden.yaml \\
        --pdfs private_material/datasheets/vendor --out private_material/datasheet_lab/pages
"""

import argparse
from pathlib import Path

import pymupdf
import yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in yaml.safe_load(open(a.golden))["docs"]:
        doc = pymupdf.open(Path(a.pdfs) / d["pdf"])
        for p in d["pages"]:
            dest = out / f"{d['doc']}_p{p}.png"
            if not dest.exists():
                doc[p - 1].get_pixmap(dpi=a.dpi).save(dest)
                n += 1
    print(f"{n} pages rendered into {out}")


if __name__ == "__main__":
    main()
