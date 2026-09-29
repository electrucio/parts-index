"""A data sheet's characteristics rows, published beside the models they are held against.

    pidx datasheets rows

Each row as the sheet prints it — symbol, test conditions, min, typ, max, unit — with the page it is on
and the box on that page it was read from, so that the crop the site shows beside it (CLAUDE.md rule 1)
lets a reader check the transcription against the PDF. The rows of the reference set are published
first (`config.datasheet_reference()`: 20 sheets read by hand and checked against the text layer and
four independent readings); rows read by the vision model will follow, each sheet saying who read it.

The reading of units and conditions is ported from docker/datasheets/ (evaluate.py, crosscheck.py) and
kept identical, but for one fix: a temperature keeps its sign. The prototype took the absolute value of
every condition, so "TA = −55 °C" became 55 — harmless while the bench only ran at 25 °C, wrong the day
it does not.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

from parts_index.bench import record
from parts_index.core.config import (
    datasheet_reference,
    datasheet_store,
    datasheet_values,
    datasheet_values_index,
    require,
)

VERSION = "rows-1"
READ = {  # who read a sheet's rows, how and when: the provenance line the page shows above them
    "reference": ("read by hand (Claude) off 150-dpi page images; every number checked against the PDF's "
                  "text layer; disagreements with four machine readings settled on 300-dpi crops", "2026-09-28"),
}

# --- units and symbols, as docker/datasheets/evaluate.py reads them ------------------------------------
PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
BASES = ["V/rtHz", "ohm", "mhos", "Hz", "A", "V", "F", "S", "s", "C", "W", "dB", "%"]
SYN = {
    "vbrceo": "vbrceo", "vceosus": "vbrceo", "vbrcbo": "vbrcbo", "vbrebo": "vbrebo",
    "vcesat": "vcesat", "vbesat": "vbesat", "vbeon": "vbe", "vbe": "vbe", "ft": "ft",
    "cobo": "cob", "cob": "cob", "cc": "cob", "cibo": "cib", "cib": "cib", "ce": "cib",
    "nf": "nf", "f": "nf", "en": "en", "icbo": "icbo", "iebo": "iebo",
    "vbrgss": "vbrgss", "bvgss": "vbrgss", "vbrgds": "vbrgds", "igss": "igss", "idss": "idss",
    "vgsoff": "vgsoff", "vgs": "vgs", "yfs": "gfs", "gfs": "gfs", "yos": "gos", "gos": "gos",
    "ciss": "ciss", "crss": "crss", "coss": "coss", "ig": "ig", "vf": "vf", "ir": "ir", "vbr": "vbr",
    "cd": "cd", "ct": "cd", "ctot": "cd", "trr": "trr", "vbrdss": "vbrdss", "bvdss": "vbrdss",
    "rdson": "rdson", "vgsth": "vgsth", "qg": "qg", "qgs": "qgs", "qgd": "qgd", "vsd": "vsd",
    "rg": "rg", "igssf": "igssf", "igssr": "igssr", "vdson": "vdson", "idon": "idon",
    "td": "td", "tr": "tr", "ts": "ts", "tf": "tf",
    "hie": "hie", "hre": "hre", "hoe": "hoe", "ibl": "ibl", "icex": "icex",
}
COND = re.compile(r"([A-Za-z][A-Za-z0-9_()\[\]/]*)\s*[=≥≤<>]\s*([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z/%]*)")
TEMPERATURES = ("TA", "TJ", "TC", "TAMB")


def clean(s) -> str:
    s = str(s)
    for a, b in (("−", "-"), ("–", "-"), ("—", "-"), ("µ", "u"), ("μ", "u"), ("Ω", "ohm"), ("√Hz", "rtHz"),
                 ("√ Hz", "rtHz"), ("Hz1/2", "rtHz"), ("°", ""), (" ", " ")):
        s = s.replace(a, b)
    return s


def unit_factor(unit) -> float | None:
    """SI factor of a printed unit: 'mAdc' -> 1e-3, 'kohm' -> 1e3, 'umhos' -> 1e-6, '' -> 1."""
    u = clean(unit or "").strip().replace(" ", "")
    u = re.sub(r"dc$", "", u)
    if u in ("", "-", "dB", "%"):
        return 1.0
    if u.upper() in ("X10-4", "×10-4"):
        return 1e-4                                     # hre, printed in units of 10^-4
    for base in BASES:
        if u.endswith(base):
            pre = u[: -len(base)]
            if pre in PREFIX:
                return PREFIX[pre]
    if u in PREFIX:
        return PREFIX[u]
    return None


def canon(symbol, parameter="") -> str:
    """The quantity a row measures, in the bench's names: 'V(BR)CEO' -> 'vbrceo', 'Cobo' -> 'cob'."""
    s = clean(symbol or "")
    s = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†]+", "", s)  # footnote marks printed as superscripts
    s = re.sub(r"\(note\)|\(\d\)|note\s*\d", "", s, flags=re.I)
    s = re.sub(r"[\s|()\[\]_⎪∣]", "", s)  # |Yfs| is printed with several kinds of bar
    p = (parameter or "").lower()
    if re.fullmatch(r"h[FfEe]{2}\d*", s):
        return "hFE" if s[1] == "F" else "hfe"
    k = s.lower()
    k = re.sub(r"\d+$", "", k) if k.startswith(("nf", "hfe")) else k
    if "noise figure" in p:
        return "nf"
    if "breakdown" in p or "sustaining" in p:
        if k in ("vds", "vbrdss", "bvdss"):
            return "vbrdss"
        if k in ("vr", "vbr", "vbrr"):
            return "vbr"
    return SYN.get(k, k)


def conditions(text) -> dict[str, float]:
    """{NAME: SI value} of a row's test conditions, as docker/datasheets/crosscheck.py's
    `named_conditions` reads them — magnitudes, a frequency band left out rather than read as its lower
    edge, zeros and 25 °C (the bench's own) dropped — except that a temperature keeps its sign."""
    out: dict[str, float] = {}
    t = clean(text or "")
    band = re.search(r"f\s*=\s*[\d.]+\s*\w*\s*(to|~|-)\s*[\d.]+", t, re.I)
    for name, val, unit in COND.findall(t):
        if band and name.lower() == "f":
            continue
        n = re.sub(r"[()\[\]\s_]", "", name).upper()
        n = {"RS": "RG", "IGS": "IG"}.get(n, n)
        f = unit_factor(unit) or 1.0
        v = float(val) * f
        if v == 0 or n in TEMPERATURES and float(val) == 25:
            continue
        out.setdefault(n, v if n in TEMPERATURES else abs(v))
    return out


# --- where on the page a row is ------------------------------------------------------------------------
def tokens(values) -> set[float]:
    out = set()
    for v in values:
        if v is None or v == "":
            continue
        for m in re.finditer(r"\d+(?:\.\d+)?", clean(v)):
            out.add(round(float(m[0]), 6))
    return out


def lines_of(page) -> list[tuple[float, float, list]]:
    """The page's words gathered into visual lines: (top, bottom, words), top to bottom."""
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    out: list[list] = []
    for w in words:
        mid = (w[1] + w[3]) / 2
        if out and abs(mid - out[-1][3]) <= 2.5:
            out[-1][2].append(w)
            out[-1][0], out[-1][1] = min(out[-1][0], w[1]), max(out[-1][1], w[3])
        else:
            out.append([w[1], w[3], [w], mid])
    return [(a, b, ws) for a, b, ws, _ in out]


def locate(page, row: list, part: str = "", after: float = 0.0) -> tuple[list[float], float] | None:
    """The box (PDF points) of the one to three consecutive visual lines that best hold this row: its
    values count double, its condition numbers, its symbol and the part's own name (in a table of several
    parts) half as much. A row printed over several lines — conditions on one, each part's value on its own
    — is found whole. Rows run down the page, so a window above the previous row's scores a little less.
    None when nothing on the page answers for it (a scan)."""
    sym, cond, lo, typ, hi = row[:5]
    want_vals = tokens([lo, typ, hi])
    want_cond = tokens([cond]) - {25.0}
    head = re.sub(r"[^A-Za-z]", "", clean(sym))[:3].lower()
    lines = lines_of(page)
    best, score = None, 0.0
    for i in range(len(lines)):
        for n in (1, 2, 3):
            win = lines[i:i + n]
            if len(win) < n or win[-1][1] - win[0][0] > 40:
                break
            ws = [w for _, _, x in win for w in x]
            got = tokens([w[4] for w in ws])
            s = 2 * len(want_vals & got) + len(want_cond & got)
            s += 1 if head and any(re.sub(r"[^A-Za-z]", "", w[4]).lower().startswith(head) for w in ws) else 0
            s += 0.5 if part and any(w[4].upper() == part.upper() for w in ws) else 0
            s -= 0.6 * (n - 1) + (0.5 if win[0][0] < after - 1 else 0)
            if s > score:
                best, score = (win[0][0], win[-1][1], ws), s
    if best is None or score < 2:
        return None
    top, bottom, ws = best
    box = [min(w[0] for w in ws) - 3, top - 2, max(w[2] for w in ws) + 3, bottom + 2]
    return [round(x, 1) for x in box], score


# --- publishing ------------------------------------------------------------------------------------------
FIELDS = ("row", "page", "symbol", "parameter", "conditions", "min", "typ", "max", "unit", "variant", "sym",
          "cond", "box")
INDEX_FIELDS = ("doc", "part", "also", "url", "sha256", "maker", "title", "pages", "read_by", "read_on",
                "checked_by")


def reference() -> list[dict]:
    return yaml.safe_load(require(datasheet_reference(), "publishing the reference rows").read_text(encoding="utf-8"))["docs"]


def manifest() -> dict[str, dict]:
    m = json.loads(require(datasheet_store() / "manifest.json", "the data sheets' links").read_text(encoding="utf-8"))
    return {Path(f["path"]).relative_to("datasheets").as_posix(): f for f in m["files"]}


def csv_text(fields, rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def sheet_rows(d: dict, pdf: Path | None) -> list[dict]:
    """A reference sheet's rows as published, each located on its page when the PDF is at hand."""
    import pymupdf
    doc = pymupdf.open(pdf) if pdf and pdf.exists() else None
    out = []
    last = (d["pages"][0], 0.0)                 # the page and top of the previous row found
    for i, r in enumerate(d["rows"]):
        page, box = d["pages"][0], None
        if doc is not None:
            cands = [(p, locate(doc[p - 1], r, d["part"], last[1] if p == last[0] else 0.0)) for p in d["pages"]]
            cands = [(p, x) for p, x in cands if x]
            if cands:
                page, (box, _) = max(cands, key=lambda c: (c[1][1], -c[0]))
                last = (page, box[1])
        out.append({"row": i, "page": page, "symbol": r[0], "parameter": r[7] if len(r) > 7 else "",
                    "conditions": r[1], "min": "" if r[2] is None else r[2], "typ": "" if r[3] is None else r[3],
                    "max": "" if r[4] is None else r[4], "unit": r[5], "variant": r[6] if len(r) > 6 and r[6] else "",
                    "sym": canon(r[0], r[7] if len(r) > 7 else ""),
                    "cond": json.dumps(conditions(r[1]), sort_keys=True), "box": json.dumps(box) if box else ""})
    return out


def publish() -> Counter:
    c: Counter = Counter()
    led = record.ledger()
    man = manifest()
    index = []
    for d in reference():
        m = man.get(d["pdf"], {})
        pdf = datasheet_store() / d["pdf"]
        key = f"sheet:{d['doc']}"
        index.append({"doc": d["doc"], "part": d["part"], "also": " ".join(d.get("also_in_doc") or []),
                      "url": m.get("url", ""), "sha256": m.get("sha256", ""), "maker": m.get("maker", ""),
                      "title": m.get("doc", ""), "pages": " ".join(map(str, d["pages"])),
                      "read_by": "reference", "read_on": READ["reference"][1], "checked_by": ""})
        dig = record.digest([d, m.get("sha256", "")])
        if led.fresh(key, "rows", VERSION, dig):
            c["fresh"] += 1
            continue
        rows = sheet_rows(d, pdf)
        c["rows"] += len(rows)
        c["located"] += sum(1 for r in rows if r["box"])
        path = datasheet_values(d["doc"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(csv_text(FIELDS, rows), encoding="utf-8")
        led.stamp(key, "rows", version=VERSION, rows_in=dig)
        c["sheets"] += 1
    datasheet_values_index().write_text(csv_text(INDEX_FIELDS, index), encoding="utf-8")
    led.save()
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    c = publish()
    print(f"{c['sheets']} sheets written ({c['fresh']} already done): {c['rows']} rows, "
          f"{c['located']} located on their page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
