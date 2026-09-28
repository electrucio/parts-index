"""Score extracted data-sheet rows against the hand-read reference (golden.yaml).

    uv run python docker/datasheets/evaluate.py --golden docker/datasheets/golden.yaml \\
        --pdfs private_material/datasheets/vendor  RUN_DIR [RUN_DIR ...]

For every reference row: was it found (same quantity, overlapping test conditions, same grade), are its
min/typ/max right (value and column, compared in SI after reading the units), and are its conditions
complete. For every number the model returned: does it appear in the page's text layer — a number that
does not was invented or misread, whatever the reference says.
"""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf
import yaml

PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
BASES = ["V/rtHz", "ohm", "mhos", "Hz", "A", "V", "F", "S", "s", "C", "W", "dB", "%"]


def clean(s):
    s = str(s)
    for a, b in (("−", "-"), ("–", "-"), ("—", "-"), ("µ", "u"), ("μ", "u"), ("Ω", "ohm"), ("√Hz", "rtHz"),
                 ("√ Hz", "rtHz"), ("Hz1/2", "rtHz"), ("°", ""), (" ", " ")):
        s = s.replace(a, b)
    return s


def unit_factor(unit):
    """SI factor of a printed unit: 'mAdc' -> 1e-3, 'kohm' -> 1e3, 'umhos' -> 1e-6, '' -> 1."""
    u = clean(unit or "").strip().replace(" ", "")
    u = re.sub(r"dc$", "", u)
    if u in ("", "-", "dB", "%", "X10-4"):
        return 1.0
    for base in BASES:
        if u.endswith(base):
            pre = u[: -len(base)]
            if pre in PREFIX:
                return PREFIX[pre]
    if u in PREFIX:
        return PREFIX[u]
    return None


def number(s):
    if s is None:
        return None
    t = clean(s).replace(" ", "").replace(",", "")
    m = re.search(r"[-+]?\d+(\.\d+)?(e[-+]?\d+)?", t, re.I)
    return float(m[0]) if m else None


COND = re.compile(r"([A-Za-z][A-Za-z0-9_()\[\]/]*)\s*[=≥≤<>]\s*([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z/%]*)")


def cond_name(name):
    n = re.sub(r"[()\[\]\s_]", "", name).upper()  # V_DS, V(DS), VDS: one name
    return {"RS": "RG", "IE": "IE", "TAMB": "TA", "TJ": "TA", "TC": "TA"}.get(n, n)


def conditions(text, named=False):
    """Test conditions as a set of rounded |SI value| (or (name, value) pairs); zeros and 25 C dropped."""
    out = set()
    t = clean(text or "")
    for name, val, unit in COND.findall(t):
        v = float(val)
        f = unit_factor(unit)
        if f is None:
            f = 1.0
        si = abs(v * f)
        if si == 0 or (unit.upper().startswith("C") and abs(v) == 25) or name.lower().startswith("t") and abs(v) == 25:
            continue
        out.add((cond_name(name), float(f"{si:.4g}")) if named else float(f"{si:.4g}"))
    return out


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
}


def canon(symbol, parameter=""):
    s = clean(symbol or "")
    s = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†]+", "", s)  # footnote marks printed as superscripts
    s = re.sub(r"\(note\)|\(\d\)|note\s*\d", "", s, flags=re.I)
    s = re.sub(r"[\s|()\[\]_]", "", s)
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


def row_values(r, unit):
    f = unit_factor(unit)
    out = {}
    for col in ("min", "typ", "max"):
        v = number(r.get(col)) if isinstance(r, dict) else r[col]
        out[col] = None if v is None else abs(v) * (f if f else 1.0)
    return out


def same(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=2e-3, abs_tol=1e-18)


def text_tokens(pdf, pages):
    doc = pymupdf.open(pdf)
    toks = set()
    for p in pages:
        t = clean(doc[p - 1].get_text())
        for m in re.finditer(r"[-+]?\d+(?:\.\d+)?", t.replace(",", "")):
            toks.add(float(m[0]))
            toks.add(abs(float(m[0])))
    return toks


def evaluate(golden, pdfs, run):
    run = Path(run)
    res = Counter()
    per_doc = {}
    secs, tokens = [], Counter()
    for d in golden["docs"]:
        ext = []
        for p in d["pages"]:
            f = run / f"{d['doc']}_p{p}.json"
            if not f.exists():
                continue
            rec = json.loads(f.read_text())
            if rec.get("seconds"):
                secs.append(rec["seconds"])
            for k, v in (rec.get("usage") or {}).items():
                if isinstance(v, int):
                    tokens[k] += v
            res["pages"] += 1
            res["parse_errors"] += bool(rec.get("parse_error") or rec.get("error"))
            for r in rec.get("rows") or []:
                if isinstance(r, dict):
                    ext.append(r)
        toks = text_tokens(Path(pdfs) / d["pdf"], d["pages"])
        # every number the model gave, checked against the page
        for r in ext:
            for col in ("min", "typ", "max"):
                v = number(r.get(col))
                if v is None:
                    continue
                res["values_out"] += 1
                if v not in toks and abs(v) not in toks:
                    res["values_not_on_page"] += 1
        # every reference row, looked for among the model's
        cand = defaultdict(list)
        for r in ext:
            cand[canon(r.get("symbol"), r.get("parameter"))].append(r)
        doc_ok = doc_n = 0
        for g in d["rows"]:
            sym, cond, gmin, gtyp, gmax, unit = g[:6]
            variant = g[6] if len(g) > 6 else None
            gv = {c: (None if v is None else abs(v) * (unit_factor(unit) or 1.0))
                  for c, v in zip(("min", "typ", "max"), (gmin, gtyp, gmax))}
            gc = conditions(cond)
            res["ref_rows"] += 1
            res["ref_values"] += sum(v is not None for v in gv.values())
            best, best_score = None, -1.0
            for r in cand.get(canon(sym), []):
                if variant and variant.startswith(("NF(", "NF (")) is False and variant:
                    rv = str(r.get("variant") or "") + " " + str(r.get("symbol") or "")
                    if variant[-1] not in rv and variant not in rv:
                        continue
                rc = conditions(r.get("conditions"))
                overlap = len(gc & rc) / len(gc) if gc else 1.0
                ev = row_values(r, r.get("unit"))
                agree = sum(same(gv[c], ev[c]) for c in gv if gv[c] is not None)
                score = overlap + 0.01 * agree
                if variant and variant.startswith("NF("):
                    score += 0.5 * (variant.replace("NF", "") in str(r.get("symbol")))
                if score > best_score:
                    best, best_score = r, score
            if best is None or (gc and best_score < 0.5):
                res["rows_missing"] += 1
                doc_n += 1
                continue
            res["rows_found"] += 1
            res["rows_conditions_complete"] += conditions(cond, True) <= conditions(best.get("conditions"), True)
            ev = row_values(best, best.get("unit"))
            row_ok = True
            for c in ("min", "typ", "max"):
                if gv[c] is None:
                    if ev[c] is not None:
                        res["values_extra"] += 1
                        row_ok = False
                    continue
                if same(gv[c], ev[c]):
                    res["values_right"] += 1
                else:
                    res["values_wrong"] += 1
                    row_ok = False
            res["rows_exact"] += row_ok
            doc_ok += row_ok
            doc_n += 1
        per_doc[d["doc"]] = (doc_ok, doc_n)
    res["seconds_per_page"] = round(sum(secs) / len(secs), 1) if secs else None
    return res, per_doc, tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--per-doc", action="store_true")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    golden = yaml.safe_load(open(a.golden))
    table = {}
    for run in a.runs:
        res, per_doc, tokens = evaluate(golden, a.pdfs, run)
        table[Path(run).name] = (res, per_doc, tokens)
    names = list(table)
    def pct(x, y):
        return f"{100 * x / y:5.1f} %" if y else "   —"
    lines = [("pages read", lambda r: str(r["pages"])),
             ("answers that were not JSON", lambda r: str(r["parse_errors"])),
             ("seconds per page", lambda r: str(r["seconds_per_page"])),
             ("reference rows found", lambda r: pct(r["rows_found"], r["ref_rows"])),
             ("  ... with all their conditions", lambda r: pct(r["rows_conditions_complete"], r["ref_rows"])),
             ("  ... exactly right (all columns)", lambda r: pct(r["rows_exact"], r["ref_rows"])),
             ("reference values right", lambda r: pct(r["values_right"], r["ref_values"])),
             ("reference values wrong", lambda r: pct(r["values_wrong"], r["ref_values"])),
             ("values put in an empty column", lambda r: str(r["values_extra"])),
             ("numbers returned", lambda r: str(r["values_out"])),
             ("  ... not on the page at all", lambda r: pct(r["values_not_on_page"], r["values_out"]))]
    print(f"{'':36s}" + "".join(f"{n:>22s}" for n in names))
    for label, fn in lines:
        print(f"{label:36s}" + "".join(f"{fn(table[n][0]):>22s}" for n in names))
    if a.per_doc:
        print()
        docs = list(next(iter(table.values()))[1])
        for doc in docs:
            print(f"{doc:36s}" + "".join(f"{'%d/%d' % table[n][1].get(doc, (0, 0)):>22s}" for n in names))


if __name__ == "__main__":
    main()
