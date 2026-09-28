"""Do the simulators agree? Compare batch results model by model.

    python3 docker/sim/bench/agree.py LIST.jsonl ngspice=DIR ltspice=DIR qspice=DIR [--tol 0.01]

For every quantity: in how many models all simulators gave a number, and in how many of those they agree
within --tol (relative to their mean). Then which models disagree most, with their source, since a
disagreement usually means one simulator reads the card differently (a dialect), not that it computes
differently.
"""

import argparse
import collections
import glob
import json

# Below these, a value is zero for this comparison: a model without junction capacitances gives 1e-35 F
# in one simulator and 1e-195 F in another, and that is agreement.
FLOORS = {"_F": 1e-16, "_s": 1e-12}


def load(d):
    out = {}
    for p in glob.glob(f"{d}/results-*.jsonl"):
        for line in open(p):
            r = json.loads(line)
            out[r["id"]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("runs", nargs="+", help="engine=dir")
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--worst", type=int, default=12)
    a = ap.parse_args()
    jobs = {json.loads(line)["id"]: json.loads(line) for line in open(a.list)}
    res = {e: load(d) for e, d in (x.split("=", 1) for x in a.runs)}
    engines = list(res)
    print("models measured without error:",
          ", ".join(f"{e} {sum(1 for r in res[e].values() if not r.get('error'))}/{len(jobs)}" for e in engines),
          f"— by all: {sum(1 for i in jobs if all(i in res[e] and not res[e][i].get('error') for e in engines))}")
    per_q = collections.defaultdict(lambda: [0, 0, 0])
    worst = []
    for i in jobs:
        ms = [res[e].get(i, {}).get("measurements") or {} for e in engines]
        for q in ms[0]:
            if q == "points" or q.startswith("_"):
                continue
            vals = [m.get(q) for m in ms]
            if not all(isinstance(v, (int, float)) for v in vals):
                continue
            floor = next((f for suffix, f in FLOORS.items() if q.endswith(suffix)), 0)
            if max(abs(v) for v in vals) <= floor:
                continue
            mean = sum(vals) / len(vals)
            if mean == 0:
                continue
            spread = (max(vals) - min(vals)) / abs(mean)
            per_q[q][0] += 1
            per_q[q][1] += spread <= a.tol
            per_q[q][2] += spread <= 5 * a.tol
            worst.append((spread, i, q, vals))
    print(f"\n{'quantity':24s} {'compared':>9s} {'within ' + format(a.tol, '.0%'):>10s} {'within ' + format(5 * a.tol, '.0%'):>10s}")
    for q, (n, ok, ok5) in per_q.items():
        print(f"{q:24s} {n:9d} {ok / n:10.1%} {ok5 / n:10.1%}")
    worst.sort(reverse=True)
    print(f"\nlargest disagreements ({' / '.join(engines)}):")
    seen = set()
    for spread, i, q, vals in worst:
        if i in seen:
            continue
        seen.add(i)
        j = jobs[i]
        print(f"  {spread:8.2%} {q:22s} {j['name']:18s} {j['source']:18s} " + " / ".join(f"{v:.4g}" for v in vals))
        if len(seen) >= a.worst:
            break


if __name__ == "__main__":
    main()
