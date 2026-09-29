"""Simulate every recipe model of a part at the conditions of its data sheet's published rows.

    pidx bench run [--engine qspice] [--part 2N3904] [--workers 8]

A recipe whose data sheet (`datasheet.url`) is one of the published sheets (`pidx datasheets rows`) gets
its models measured at that sheet's rows. Every model whose card the bench reads — a Gummel-Poon
bipolar or a level-1 JFET `.model` (`pidx models cards`) — becomes a job: its card renamed DUT, with
each change made to it and why, and the rows the bench understands, at their own conditions. A row at a
temperature other than 25 °C is left out: the bench runs at 25 °C only.

The jobs run in the pinned simulator image (docker/sim/README.md), each shard in its own container, with
docker/sim/bench/spec.py. What comes back — each value and verdict, every netlist that was run, the
simulator's identity — is kept with the jobs in `config.bench_runs(<engine>)`, together with what it
takes to repeat the run: the image's id, the bench code's revision, the date and the command.
`pidx bench publish` publishes all of it but the cards.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import yaml

from parts_index.bench import record
from parts_index.core.config import (
    REPO_ROOT,
    bench_runs,
    datasheet_figures,
    datasheet_values,
    datasheet_values_index,
    model_part,
    require,
    sim_bench,
    spice_models_root,
    spice_recipe_locations,
)
from parts_index.datasheets.rows import TEMPERATURES, unit_factor
from parts_index.models import behaviours
from parts_index.models import cards as C
from parts_index.models import found as F
from parts_index.web.checks import read_for_another

# The rows docker/sim/bench/spec.py measures, by the kind of part.
BENCH_SYMS = {"bjt": {"hFE", "hfe", "vbe", "vcesat", "vbesat", "ft", "cob", "cib", "nf", "hie", "hre", "hoe",
                      "icex", "ibl", "td", "tr", "ts", "tf"},
              "jfet": {"idss", "vgsoff", "vgs", "gfs", "igss", "ciss", "crss", "en", "nf"}}
FAMILIES = {"bjt": "gummel-poon", "jfet": "jfet"}
POLARITY = {"NPN": "npn", "PNP": "pnp", "NJF": "n", "PJF": "p"}
CATALOGUE = re.compile(r"\b(?:" + "|".join(C.CATALOGUE) + r")\s*=\s*[^\s)]+", re.I)
# Each change made to a card before it is simulated, published with the result so it can be repeated.
CHANGES = {
    "renamed": "the .model renamed DUT, the name the bench's netlists use",
    "catalogue-fields": "LTspice's catalogue fields (mfg=, Vceo=, …) removed: ngspice refuses them, the others ignore them",
    "unit-a": "for ngspice, the A after a number removed (IKF=10A): ngspice reads it as atto",
}


def sheets_by_url() -> dict[str, dict]:
    with open(require(datasheet_values_index(), "the published sheets"), encoding="utf-8") as f:
        return {r["url"].lower(): r for r in csv.DictReader(f) if r["url"]}


def sheet_rows(doc: str, kind: str) -> tuple[list[dict], dict[int, str]]:
    """The rows of a sheet the bench can measure for this kind, in SI magnitudes, and why each other row
    is not measured."""
    jobs, why = [], {}
    with open(datasheet_values(doc), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            i, cond = int(r["row"]), json.loads(r["cond"])
            if r["sym"] not in BENCH_SYMS[kind]:
                why[i] = "no-bench"
                continue
            if any(k in cond for k in TEMPERATURES):
                why[i] = "temperature"
                continue
            fac = unit_factor(r["unit"]) or 1.0
            val = {c: abs(float(r[c])) * fac if r[c] != "" else None for c in ("min", "typ", "max")}
            jobs.append({"id": i, "sym": r["sym"], "cond": {k: abs(v) for k, v in cond.items()}, **val})
    return jobs, why


# The benches docker/sim/bench/curves.py has, by kind of part.
CURVE_BENCHES = {"bjt": {"bjt-hfe", "bjt-on-voltages", "bjt-tempco", "bjt-saturation", "bjt-capacitance",
                         "bjt-hparams", "bjt-nf-frequency", "bjt-nf-source"}}


def axis_factor(unit: str) -> float:
    """SI factor of a figure axis's unit: "mA" 1e-3, "kΩ" 1e3, "X 10-4" 1e-4, "mV/°C" 1e-3."""
    if unit.replace("°", "").strip() == "mV/C":
        return 1e-3
    return unit_factor(unit) or 1.0


def sheet_figures(doc: str, kind: str) -> list[dict]:
    """The sheet's graphs a bench can draw for this kind of part, their axis ranges in SI units."""
    p = datasheet_figures(doc)
    if not p.exists():
        return []
    out = []
    for f in json.loads(p.read_text(encoding="utf-8"))["figures"]:
        if f.get("kind") != "graph" or f.get("bench") not in CURVE_BENCHES.get(kind, ()):
            continue
        q, unit, scale, lo, hi = f["x"]
        fx = axis_factor(unit)
        out.append({"n": f["n"], "bench": f["bench"], "x": [lo * fx, hi * fx, scale], "fixed": f.get("fixed") or {},
                    "series": [{"label": se["label"], "cond": se.get("cond") or {}} for se in f["series"]],
                    "quantity": f["series"][0]["label"]})
    return out


def sheet_fixtures(doc: str) -> dict[str, dict]:
    """The test circuits the sheet draws, by the rows they are the fixture of (td, tr: Figure 1)."""
    p = datasheet_figures(doc)
    if not p.exists():
        return {}
    out = {}
    for f in json.loads(p.read_text(encoding="utf-8"))["figures"]:
        for sym in f.get("rows") or [] if f.get("fixture") else []:
            out[sym] = f["fixture"]
    return out


def card_for(files: F.Files, file: str, name: str, engine: str) -> tuple[str, list[str]] | None:
    """The card as the bench is given it, and the changes made to it."""
    chain = F.closure(files.get(file)[0], name)
    if not chain or chain[-1][0] != "model":
        return None
    card = re.sub(r"^(\s*\.model\s+)(\S+)", lambda m: m[1] + "DUT", chain[-1][2], count=1, flags=re.I)
    changes = ["renamed"]
    stripped = CATALOGUE.sub("", card)
    if stripped != card:
        card, changes = stripped, changes + ["catalogue-fields"]
    if engine == "ngspice":
        fixed = C.AMPERE_UNIT.sub("", card)
        if fixed != card:
            card, changes = fixed, changes + ["unit-a"]
    return card, changes


def build_jobs(engine: str, only: str | None = None) -> tuple[list[dict], dict]:
    locations = json.loads(require(spice_recipe_locations(), "the recipes' models").read_text(encoding="utf-8"))
    sheets = sheets_by_url()
    files = F.Files(spice_models_root())
    jobs, meta = [], {}
    for key, models in sorted(locations.items()):
        kind, part = key.split("/", 1)
        grp = behaviours.group(kind)
        if grp not in BENCH_SYMS or (only and part != only):
            continue
        recipe = yaml.safe_load(model_part(kind, part).read_text(encoding="utf-8"))
        sheet = sheets.get(((recipe.get("datasheet") or {}).get("url") or "").lower())
        if not sheet or read_for_another(sheet, part):
            continue
        rows, why = sheet_rows(sheet["doc"], grp)
        fixtures = sheet_fixtures(sheet["doc"])
        figures = sheet_figures(sheet["doc"], grp)
        cards = record.load(kind, part).get("cards", {})
        meta[key] = {"doc": sheet["doc"], "not_measured": why, "rows": [r["id"] for r in rows]}
        for m in models:
            card_info = cards.get(m["hash"], {})
            if card_info.get("family") != FAMILIES[grp] or not m["file"].startswith("sources/"):
                continue
            got = card_for(files, m["file"], m["name"], engine)
            if not got:
                continue
            card, changes = got
            jobs.append({"part": key, "model_id": m["hash"], "kind": grp, "polarity": POLARITY[card_info["type"]],
                         "card": card, "model": "DUT", "changes": changes, "rows": rows, "fixtures": fixtures,
                         "figures": figures})
    return jobs, meta


def image_id(engine: str) -> str:
    out = subprocess.run(["docker", "image", "inspect", f"parts-index-{engine}", "--format", "{{.Id}}"],
                         capture_output=True, text=True)
    return out.stdout.strip()


def revision(path: Path) -> dict:
    """The commit the bench code was last changed in, and whether the working copy differs from it."""
    rel = str(path.relative_to(REPO_ROOT))
    commit = subprocess.run(["git", "log", "-1", "--format=%H", "--", rel], cwd=REPO_ROOT,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=REPO_ROOT,
                           capture_output=True, text=True).stdout.strip()
    return {"commit": commit, "clean": not dirty}


def shard(engine: str, jobs_file: Path, out_file: Path) -> subprocess.CompletedProcess:
    cmd = ["docker", "run", "--rm", "--cpus", "2", "--tmpfs", "/tmp/spec",
           "-v", f"{sim_bench()}:/sim/bench:ro", "-v", f"{jobs_file.parent}:/io", f"parts-index-{engine}",
           "python3", "/sim/bench/spec.py", f"/io/{jobs_file.name}", f"/io/{out_file.name}"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=7200)


def run(engine: str, only: str | None, workers: int) -> dict:
    jobs, meta = build_jobs(engine, only)
    out = bench_runs(engine)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*-*.json"):
        old.unlink()
    shards = [jobs[i::workers] for i in range(workers) if jobs[i::workers]]
    pairs = []
    for i, sh in enumerate(shards):
        jf = out / f"jobs-{i}.json"
        jf.write_text(json.dumps(sh), encoding="utf-8")
        pairs.append((jf, out / f"res-{i}.json"))
    with ThreadPoolExecutor(max(1, len(pairs))) as ex:
        procs = list(ex.map(lambda p: shard(engine, *p), pairs))
    failed = [p.stderr[-600:] for p in procs if p.returncode]
    results = [r for _, rf in pairs if rf.exists() for r in json.loads(rf.read_text(encoding="utf-8"))]
    changes = {(j["part"], j["model_id"]): j["changes"] for j in jobs}
    for r in results:
        r["changes"] = changes.get((r["part"], r["model_id"]), [])
    run_info = {"engine": engine, "on": date.today().isoformat(), "image": image_id(engine),
                "bench": revision(sim_bench()), "jobs": len(jobs), "results": len(results),
                "command": "docker run --rm --tmpfs /tmp/spec -v docker/sim/bench:/sim/bench:ro -v <jobs>:/io "
                           f"parts-index-{engine} python3 /sim/bench/spec.py /io/jobs.json /io/results.json"}
    (out / "results.json").write_text(json.dumps({"run": run_info, "meta": meta, "results": results}, indent=1),
                                      encoding="utf-8")
    if failed:
        print("\n".join(failed), file=sys.stderr)
    return run_info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", default="qspice", choices=("qspice", "ngspice", "ltspice"))
    ap.add_argument("--part", help="only one part")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    info = run(a.engine, a.part, a.workers)
    print(f"{info['results']:,} of {info['jobs']:,} models measured with {a.engine} ({info['image'][:19]}, "
          f"bench {info['bench']['commit'][:10]}{'' if info['bench']['clean'] else ' + uncommitted changes'})")
    return 0 if info["results"] == info["jobs"] else 1


if __name__ == "__main__":
    sys.exit(main())
