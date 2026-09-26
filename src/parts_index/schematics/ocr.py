"""Read what has been downloaded and not read yet, page by page, with boxes.

    pidx schematics ocr --source audiocircuit [--limit N] [--gpu 0] [--shard 0/4] [--dry]

The stage between `download` and `index`, and the only one that wants a GPU. It takes its work from the
ledger — everything downloaded whose `ocr` stamp is missing or of an older version — so it can be run
again and again while a download is still going, and the two stages need no coordinating. Nothing is
read twice: rule 5 is the ledger's, and the stamp carries the version below.

Per page, not per document: a page with a text layer worth reading is read from it, with the boxes the
layer already gives; a page without one is rendered and passed to the OCR. That is why a born-digital
service manual with two scanned pages at the end does not lose them, and why a scanned sheet with a
typed cover does not lose the sheet.

Boxes are the point. These are big scanned drawings with no text layer, where ctrl+F finds nothing and
the eye finds nothing either, so a result has to be able to say *where* on the sheet the part is.

Ported from `ocr_raw.py` in the staging tree, behaviour first (rule 7): same page decision, same render
sizes, same record shape, same version stamp, so what was read before is not read again.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from pathlib import Path

from parts_index.core import pagesio
from parts_index.core.config import downloads, ocr_map, ocr_root, require, schematics_state
from parts_index.core.ledger import Ledger
from parts_index.schematics import cad
from parts_index.schematics.download import registry_entry, safe_name

OCR_VERSION = "ocr_boxes-1"          # what 45,443 documents already carry; bump it to have them read again
LONG = 4000                          # the long side in pixels a page is rendered at, within 150..300 dpi
MAX_PAGES = 600                      # 80 cut thirty service manuals short: their schematics are at the end
TEXT_WORDS = 50                      # a page with this many words in its text layer is read, not rendered
IMAGE_TYPES = {"gif", "png", "jpeg", "tiff"}
OCR_MODELS = "PP-OCRv5"              # see _reader(): v6 needs a newer paddle than the one that is here


def version_for(entry: dict) -> str:
    """The stamp a source's documents carry. A source read in another language than the default carries
    it in the stamp, so what was read in English is never taken for what was read in Japanese, and a
    change of language is a new version like any other (rule 5)."""
    lang = (entry.get("ocr") or {}).get("lang", "en")
    return OCR_VERSION if lang == "en" else f"{OCR_VERSION}-{lang}"


def _reader(gpu: int | None, lang: str = "en"):
    """The OCR itself, loaded only when a page actually needs it — a run with nothing to render must not
    ask for a GPU, and a machine without one must still be able to read born-digital documents."""
    if gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    import numpy as np
    from paddleocr import PaddleOCR

    # The model family is pinned. Left to itself PaddleOCR 3.x fetches PP-OCRv6, which a paddle 3.0
    # build refuses with "Type of attribute: strides is not right" on the first page it is given.
    # `lang` is the registry's: a Japanese magazine is read with PP-OCRv5's Japanese model, which reads the
    # Latin of a part number as well, where the English one turns every kana into a string of letters.
    engine = PaddleOCR(lang=lang, ocr_version=OCR_MODELS, use_doc_orientation_classify=False,
                       use_doc_unwarping=False, use_textline_orientation=False,
                       text_det_limit_side_len=LONG, text_det_limit_type="max")

    def read(img):
        blocks = []
        for res in engine.predict(img):
            for box, txt, score in zip(res["rec_polys"], res["rec_texts"], res["rec_scores"]):
                b = np.asarray(box)
                blocks.append({"box": [int(b[:, 0].min()), int(b[:, 1].min()), int(b[:, 0].max()), int(b[:, 1].max())],
                               "text": txt, "conf": round(float(score), 3)})
        return blocks

    return read


def _open(path: Path, kind: str):
    """A document as pages, whatever it arrived as. MuPDF reads PDFs and most images; the TIFFs it cannot
    decode come through Pillow, including the old JPEG-in-TIFF whose whole JPEG sits in tag 513."""
    import fitz

    try:
        doc = fitz.open(path)
        doc[0].get_pixmap(matrix=fitz.Matrix(0.05, 0.05))
        return doc
    except Exception:                                            # noqa: BLE001
        from PIL import Image

        try:
            im = Image.open(path).convert("L")
        except Exception:                                        # noqa: BLE001
            tif = Image.open(path)
            off, length = tif.tag_v2.get(513), tif.tag_v2.get(514)
            with open(path, "rb") as fh:
                fh.seek(off)
                im = Image.open(io.BytesIO(fh.read(length))).convert("L")
        doc = fitz.open()
        page = doc.new_page(width=im.width, height=im.height)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        page.insert_image(page.rect, stream=buf.getvalue())
        return doc


def _text_blocks(page, zoom):
    """The text layer as line blocks with their boxes, in the rendered page's own pixels."""
    lines: dict = {}
    for x0, y0, x1, y1, word, block, line, _ in page.get_text("words"):
        d = lines.setdefault((block, line), {"box": [x0, y0, x1, y1], "words": []})
        d["box"] = [min(d["box"][0], x0), min(d["box"][1], y0), max(d["box"][2], x1), max(d["box"][3], y1)]
        d["words"].append(word)
    return [{"box": [int(v * zoom) for v in d["box"]], "text": " ".join(d["words"]), "conf": 1.0}
            for d in lines.values()]


def read_document(path: Path, kind: str, read_image=None) -> list[dict]:
    """-> one page record per page, in the shape core.pagesio documents."""
    if kind in cad.KINDS:
        return cad.read(path, kind)       # a design, not a picture: its fields are read, nothing is OCR'd
    import fitz
    import numpy as np

    fitz.TOOLS.mupdf_display_errors(False)
    doc = _open(path, kind)
    pages = []
    for pno in range(min(doc.page_count, MAX_PAGES)):
        page = doc[pno]
        long_pt = max(page.rect.width, page.rect.height)
        if kind == "pdf":
            zoom = min(max(LONG / long_pt, 150 / 72), 300 / 72)
        else:
            zoom = 2.0 if long_pt < 1200 else min(1.0, LONG / long_pt)
        words = page.get_text("words") if kind == "pdf" else []
        if len(words) >= TEXT_WORDS:
            blocks, how = _text_blocks(page, zoom), "text"
            w_px, h_px = int(page.rect.width * zoom), int(page.rect.height * zoom)
        else:
            if read_image is None:
                raise RuntimeError(f"page {pno + 1} of {path.name} has no text layer and no OCR is loaded")
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
            img = np.stack([np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)] * 3, axis=-1)
            blocks, how, w_px, h_px = read_image(img), "ocr", pix.w, pix.h
        blocks.sort(key=lambda b: (round(b["box"][1] / 12), b["box"][0]))
        pages.append({"page": pno + 1, "w": w_px, "h": h_px, "how": how, "blocks": blocks})
    return pages


def _note_in_map(source: str, url: str, method: str, n_pages: int, name: str) -> None:
    """Append to the map that says which file holds which document. Appending, not rewriting: shards run
    beside one another, and a row already there is a document already read."""
    path = ocr_map()
    header = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if header:
            w.writerow(["source", "doc_key", "text_method", "pages", "ocr_file", "origin"])
        w.writerow([source, url, method, n_pages, f"{source}/{name}.jsonl.gz", "ocr"])


def run(source: str, *, limit: int = 0, gpu: int | None = None, shard: str = "0/1", dry: bool = False) -> dict:
    entry = registry_entry(source)                              # refuses a source that is not registered
    version, lang = version_for(entry), (entry.get("ocr") or {}).get("lang", "en")
    led = Ledger(schematics_state(source))
    k, n = (int(x) for x in shard.split("/"))

    def version_of(row: dict) -> str:
        # A design is read by cad.py and not by the OCR, so it carries that reader's version: when the
        # reader changes what it keeps, every design is read again and no scan is.
        return f"{version}-cad{cad.VERSION}" if row.get("type") in cad.KINDS else version

    # A design is stamped `text`, which to the ledger means "no OCR pass", and that is right for a page
    # with a text layer and wrong for a design, whose reader can change: it is asked about by version.
    pending = [key for key, row in led.rows.items()
               if row["download_at"] and not row["skip_reason"]
               and (row.get("type") in cad.KINDS or led._applies(row, "ocr"))
               and not led.done(key, "ocr", version_of(row))]
    todo = [key for i, key in enumerate(sorted(pending)) if i % n == k]
    if limit:
        todo = todo[:limit]
    folder = ocr_root() / source
    counts = {"to read": len(todo), "read": 0, "already there": 0, "file gone": 0, "failed": 0, "pages": 0}
    if dry or not todo:
        return counts

    read_image, pages_rendered = None, 0
    for url in todo:
        row = led.row(url)
        kind = row.get("type") or "pdf"
        name = safe_name(url, kind)
        # A page file already written is a page already read — for a scan. A design's pages are its
        # reader's output, and the ledger has just said that reader has changed, so they are written again.
        if kind not in cad.KINDS and pagesio.is_done(folder, name):
            counts["already there"] += 1
            continue
        path = downloads(source) / kind / name
        if not path.exists():
            counts["file gone"] += 1                             # `pidx schematics verify --repair` fetches these back
            continue
        t0 = time.time()
        try:
            if read_image is None and kind not in ("html", *cad.KINDS):
                read_image = _reader(gpu, lang)                  # loaded once, on the first document
            pages = read_document(path, kind, read_image)
        except Exception as e:                                   # noqa: BLE001  a broken file must not stop the batch
            counts["failed"] += 1
            print(f"  ERROR {name}: {str(e)[:120]}", file=sys.stderr, flush=True)
            continue
        pagesio.write_pages(folder, name, pages)
        how = "ocr_boxes" if any(p["how"] == "ocr" for p in pages) else "text"
        _note_in_map(source, url, how, len(pages), name)
        led.stamp(url, "ocr", version=version_of(row), n_pages=len(pages), text_method=how)
        counts["read"] += 1
        counts["pages"] += len(pages)
        pages_rendered += sum(1 for p in pages if p["how"] == "ocr")
        if counts["read"] % 25 == 0:
            led.save()
        print(f"  {name[:60]}: {len(pages)} pages ({sum(1 for p in pages if p['how'] == 'ocr')} by OCR)"
              f" in {time.time() - t0:.0f}s", flush=True)
    led.save()
    counts["rendered pages"] = pages_rendered
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics ocr", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", required=True, help="a source with documents downloaded (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many documents")
    ap.add_argument("--gpu", type=int, default=None, help="which GPU to give the OCR")
    ap.add_argument("--shard", default="0/1", help="k/n: read only every nth document, for running several at once")
    ap.add_argument("--dry", action="store_true", help="say how much there is to read and read nothing")
    a = ap.parse_args(argv)
    require(ocr_root().parent, "reading downloaded documents")
    for source in a.source:
        counts = run(source, limit=a.limit, gpu=a.gpu, shard=a.shard, dry=a.dry)
        print(f"{source}: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
