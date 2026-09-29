"""Publish what the bench measured, with everything it takes to measure it again.

    pidx bench publish

Reads the runs `pidx bench run` kept (`config.bench_runs(<engine>)`) and writes, into each part's record
(`data/verification/<kind>/<part>.json`, section `bench`):

- the sheet the rows come from, and for every row whether it was measured and, if not, why;
- per model, each row's value and verdict in every simulator run — QSPICE decides the page's colour,
  ngspice is kept beside it — and the changes made to its card before it was simulated;
- the netlists each simulator ran, which include the card (`model.lib`) and never contain it: our own
  work, published so that a reader who fetches the model from the link beside it can run them;
- for each simulator: its identity (ngspice's version, the sha256 of QSPICE64.exe), the image's id, the
  bench code's commit and whether it was clean, the date and the command.

A row printed for one grade of a part (LSK170A…) is judged only on a model named for that grade; on the
others its value is shown and not judged. Values are kept to four significant figures.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter

from parts_index.bench import record
from parts_index.bench.run import CHANGES
from parts_index.core.config import bench_runs, datasheet_values, spice_recipe_locations
from parts_index.core.ledger import today

VERSION = "bench-1"
ENGINES = ("qspice", "ngspice", "ltspice")
PRIMARY = "qspice"


def sig(x):
    return float(f"{x:.4g}") if isinstance(x, float) else x


def value(row: dict) -> list:
    """[value, verdict] of one measured row; a failed or impossible measurement has no value."""
    v, verdict = row["value"], row["verdict"]
    if isinstance(v, dict) or v is None:
        return [None, verdict]
    if verdict.startswith("x") and verdict.endswith(" of typ"):
        verdict = "typical"                    # the ratio is recomputed where it is shown
    return [sig(v), verdict]


def grades(doc: str, part: str) -> dict[int, str]:
    """Rows printed for one grade of the part (their variant names the part and a grade letter)."""
    with open(datasheet_values(doc), encoding="utf-8") as f:
        return {int(r["row"]): r["variant"] for r in csv.DictReader(f)
                if r["variant"] and r["variant"].upper().startswith(part.upper()) and r["variant"].upper() != part.upper()}


def load_runs() -> dict[str, dict]:
    out = {}
    for e in ENGINES:
        p = bench_runs(e) / "results.json"
        if p.exists():
            out[e] = json.loads(p.read_text(encoding="utf-8"))
    return out


def publish() -> Counter:
    c: Counter = Counter()
    runs = load_runs()
    if PRIMARY not in runs:
        raise SystemExit(f"no {PRIMARY} run: pidx bench run --engine {PRIMARY} first")
    names = {(key, m["hash"]): m["name"] for key, ms in
             json.loads(spice_recipe_locations().read_text(encoding="utf-8")).items() for m in ms}
    led = record.ledger()
    for key, meta in sorted(runs[PRIMARY]["meta"].items()):
        kind, part = key.split("/", 1)
        by_grade = grades(meta["doc"], part)
        models: dict[str, dict] = {}
        for e, run in runs.items():
            for r in run["results"]:
                if r["part"] != key:
                    continue
                m = models.setdefault(r["model_id"], {"values": {}, "changes": {}, "netlists": {}})
                name = names.get((key, r["model_id"]), "").upper()
                vals = {}
                for row in r["rows"]:
                    val = value(row)
                    g = by_grade.get(row["id"])
                    if g and val[0] is not None and not name.startswith(g.upper()):
                        val = [val[0], "grade"]          # another grade's limits: shown, not judged
                    vals[str(row["id"])] = val
                m["values"][e] = vals
                m["changes"][e] = r.get("changes", [])
                m["netlists"][e] = r.get("netlists", [])
        engines = {e: {**{k: run["run"][k] for k in ("on", "image", "bench", "command")},
                       "version": next((r.get("version") for r in run["results"] if r.get("version")), None)}
                   for e, run in runs.items()}
        rows = {str(i): "measured" for i in meta["rows"]}
        rows.update({str(i): why for i, why in meta["not_measured"].items()})
        section = {"sheet": meta["doc"], "primary": PRIMARY, "engines": engines, "rows": rows, "models": models,
                   "changes": {k: v for k, v in CHANGES.items()
                               if any(k in ch for m in models.values() for ch in m["changes"].values())}}
        dig = record.digest([engines, sorted(models)])
        c["written" if record.write_section(kind, part, "bench", section) else "unchanged"] += 1
        c["models"] += len(models)
        led.stamp(key, "bench", version=VERSION, when=today(), bench_in=dig)
    led.save()
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    c = publish()
    print(f"{c['written']} parts written, {c['unchanged']} unchanged: {c['models']} models measured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
