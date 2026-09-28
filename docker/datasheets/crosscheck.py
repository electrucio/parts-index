"""Hold every SPICE model of a part against its data sheet: simulate each model at the conditions of each
row of the sheet's characteristics table, and count the rows it satisfies.

    uv run python docker/datasheets/crosscheck.py --golden docker/datasheets/golden.yaml \\
        --index private_material/index.jsonl --models private_web_spice_models \\
        --out private_material/datasheet_lab/crosscheck [--rows RUN_DIR] [--engine qspice] [--workers 8]

The rows come from golden.yaml (the hand-read reference) or, with --rows, from an extraction run — which
is the point: once extraction is trusted, a data sheet in, a verdict per model out. The models are every
distinct stand-alone .model card in the index whose name is one of the part's names below (an explicit
list: a wrong model is worse than none). The simulation is docker/sim/bench/spec.py, in the simulator
image, several containers at once.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))
from bench.batch import extract_card  # noqa: E402
from evaluate import COND, canon, clean, number, unit_factor  # noqa: E402

# The names a part's models go by in the index. Grades that the sheet covers count as the part.
NAMES = {
    "2N3904_onsemi": ("bjt", ["2N3904", "Q2N3904"]),
    "2N3906_onsemi": ("bjt", ["2N3906", "Q2N3906"]),
    "2N2222A_onsemi": ("bjt", ["2N2222A", "P2N2222A", "Q2N2222A", "PN2222A"]),
    "BC550_fairchild": ("bjt", ["BC550", "BC550B", "BC550C"]),
    "BC549C_nxp": ("bjt", ["BC549C", "QBC549C"]),
    "2SC2240_toshiba": ("bjt", ["2SC2240", "Q2SC2240", "2SC2240GR", "2SC2240BL"]),
    "2SA970_toshiba": ("bjt", ["2SA970", "Q2SA970", "2SA970GR", "2SA970BL"]),
    "2N5551_nxp": ("bjt", ["2N5551", "Q2N5551"]),
    "MJE340_onsemi": ("bjt", ["MJE340", "QMJE340"]),
    "BD139_onsemi": ("bjt", ["BD139", "QBD139", "BD139-16", "BD139-10"]),
    "2SK170_toshiba": ("jfet", ["2SK170", "J2SK170", "2SK170BL", "2SK170GR", "2SK170V"]),
    "2N5457_onsemi": ("jfet", ["2N5457", "J2N5457"]),
    "J201_interfet": ("jfet", ["J201", "JJ201"]),
    "BF862_nxp": ("jfet", ["BF862", "JBF862"]),
    "LSK170_linearsystems": ("jfet", ["LSK170", "LSK170A", "LSK170B", "LSK170C", "LSK170D"]),
}
SPEC_SYMS = {"bjt": {"hFE", "hfe", "vbe", "vcesat", "vbesat", "ft", "cob", "cib", "nf"},
             "jfet": {"idss", "vgsoff", "vgs", "gfs", "igss", "ciss", "crss", "en", "nf"}}


def named_conditions(text):
    """{NAME: |SI value|}; a frequency band ("f = 10 Hz to 15.7 kHz") is not a spot frequency and is
    left out, so the row is not measured rather than measured at the band's lower edge."""
    out = {}
    t = clean(text or "")
    band = re.search(r"f\s*=\s*[\d.]+\s*\w*\s*(to|~|-)\s*[\d.]+", t, re.I)
    for name, val, unit in COND.findall(t):
        if band and name.lower() == "f":
            continue
        n = re.sub(r"[()\[\]\s_]", "", name).upper()
        n = {"RS": "RG", "IGS": "IG"}.get(n, n)
        f = unit_factor(unit) or 1.0
        si = abs(float(val) * f)
        if si == 0 or n in ("TA", "TJ", "TC", "TAMB") and abs(float(val)) == 25:  # 25 C is the bench's own
            continue
        out.setdefault(n, si)
    return out


def rows_from_golden(d):
    rows = []
    for i, g in enumerate(d["rows"]):
        sym, cond, lo, typ, hi, unit = g[:6]
        f = unit_factor(unit) or 1.0
        rows.append({"id": i, "sym": canon(sym), "text": f"{sym} ({cond})", "cond": named_conditions(cond),
                     "min": None if lo is None else abs(lo) * f, "typ": None if typ is None else abs(typ) * f,
                     "max": None if hi is None else abs(hi) * f, "variant": g[6] if len(g) > 6 else None})
    return rows


def rows_from_run(d, run):
    rows = []
    for p in d["pages"]:
        f = Path(run) / f"{d['doc']}_p{p}.json"
        if not f.exists():
            continue
        for r in json.loads(f.read_text()).get("rows") or []:
            uf = unit_factor(r.get("unit")) or 1.0
            vals = {c: number(r.get(c)) for c in ("min", "typ", "max")}
            rows.append({"id": len(rows), "sym": canon(r.get("symbol"), r.get("parameter")),
                         "text": f"{r.get('symbol')} ({r.get('conditions')})",
                         "cond": named_conditions(r.get("conditions")),
                         **{c: None if v is None else abs(v) * uf for c, v in vals.items()},
                         "variant": r.get("variant")})
    return rows


def models_for(index, names, kind, limit):
    want = {n.upper() for n in names}
    types = {"bjt": ("NPN", "PNP"), "jfet": ("NJF", "PJF")}[kind]
    seen, out = set(), []
    with open(index) as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") != "model" or r.get("parent") or r.get("encrypted") or r["type"] not in types:
                continue
            if r["name"].upper() not in want:
                continue
            key = (r["type"], tuple(sorted((k.lower(), str(v).lower()) for k, v in r["params"].items())))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= limit:
                break
    return out


def run_shard(image, bench, models_root, jobs_file, out_file):
    cmd = ["docker", "run", "--rm", "--cpus", "2", "--tmpfs", "/tmp/spec",
           "-v", f"{bench}:/sim/bench:ro", "-v", f"{jobs_file.parent}:/io", image,
           "python3", "/sim/bench/spec.py", f"/io/{jobs_file.name}", f"/io/{out_file.name}"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=7200)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default=None, help="an extraction run folder instead of golden.yaml")
    ap.add_argument("--engine", default="qspice")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=12, help="models per part")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    golden = yaml.safe_load(open(a.golden))
    jobs, meta = [], {}
    for d in golden["docs"]:
        if d["doc"] not in NAMES:
            continue
        kind, names = NAMES[d["doc"]]
        rows = rows_from_run(d, a.rows) if a.rows else rows_from_golden(d)
        rows = [r for r in rows if r["sym"] in SPEC_SYMS[kind]]
        meta[d["doc"]] = {"part": d["part"], "rows": rows}
        for m in models_for(a.index, names, kind, a.limit):
            try:
                card = extract_card(Path(a.models) / m["file"], m["line"])
            except Exception:  # noqa: BLE001
                continue
            card = re.sub(r"^(\s*\.model\s+)(\S+)", lambda mm: mm[1] + "DUT", card, count=1, flags=re.I)
            pol = {"NPN": "npn", "PNP": "pnp", "NJF": "n", "PJF": "p"}[m["type"]]
            mid = f"{m['name']} [{m['source']}] {m['file']}:{m['line']}"
            jobs.append({"part": d["doc"], "model_id": mid, "kind": kind, "polarity": pol, "card": card,
                         "model": "DUT", "rows": [{k: r[k] for k in ("id", "sym", "cond", "min", "typ", "max")}
                                                   for r in rows]})
    shards = [jobs[i::a.workers] for i in range(a.workers)]
    bench = (Path(__file__).resolve().parents[1] / "sim" / "bench")
    files = []
    for i, sh in enumerate(shards):
        jf = out / f"jobs-{a.engine}-{i}.json"
        jf.write_text(json.dumps(sh))
        files.append((jf, out / f"res-{a.engine}-{i}.json"))
    with ThreadPoolExecutor(a.workers) as ex:
        procs = list(ex.map(lambda p: run_shard(f"parts-index-{a.engine}", bench, a.models, *p), files))
    for p in procs:
        if p.returncode:
            print(p.stderr[-800:], file=sys.stderr)
    results = [r for _, rf in files if rf.exists() for r in json.loads(rf.read_text())]
    (out / f"results-{a.engine}.json").write_text(json.dumps({"meta": meta, "results": results}, indent=1,
                                                              default=str))
    # summary: per part, each model's count of rows inside the sheet's limits
    by_part = defaultdict(list)
    for r in results:
        by_part[r["part"]].append(r)
    for doc, rs in by_part.items():
        rows = meta[doc]["rows"]
        judged = [r for r in rows if r["min"] is not None or r["max"] is not None]
        print(f"\n## {meta[doc]['part']} ({doc}): {len(rs)} models, {len(judged)} rows with limits, "
              f"{len(rows) - len(judged)} typical-only")
        scored = []
        for r in rs:
            v = {x["id"]: x for x in r["rows"]}
            name = r["model_id"].split(" [")[0].upper()
            mine = []
            groups = defaultdict(list)
            for j in judged:
                if j.get("variant"):
                    groups[(j["sym"], json.dumps(j["cond"], sort_keys=True))].append(j)
                else:
                    mine.append(j)
            for rows_g in groups.values():
                own = [j for j in rows_g if name.endswith(str(j["variant"]).upper()[-1:])]
                if own:
                    mine += own
                else:  # a model of no stated grade: judged against the grade whose range holds it, if any
                    ok = [j for j in rows_g if v[j["id"]]["verdict"] == "inside"]
                    mine.append(ok[0] if ok else rows_g[0])
            inside = sum(v[j["id"]]["verdict"] == "inside" for j in mine)
            measured = sum(v[j["id"]]["verdict"] in ("inside", "below", "above") for j in mine)
            suspect = sum(v[j["id"]]["verdict"] == "suspect" for j in mine)
            scored.append((inside, measured, r["model_id"], v, mine, suspect))
        scored.sort(key=lambda t: (-t[0], t[1]))
        for inside, measured, mid, v, mine, suspect in scored:
            fails = [f"{j['text']}: {v[j['id']]['verdict']} ({v[j['id']]['value']:.4g})"
                     for j in mine if v[j["id"]]["verdict"] in ("below", "above")
                     and isinstance(v[j["id"]]["value"], float)]
            note = f"  ({suspect} suspect)" if suspect else ""
            print(f"  {inside:2d}/{measured:2d} inside  {mid}{note}")
            for fl in fails[:4]:
                print(f"         ✗ {fl}")


if __name__ == "__main__":
    main()
