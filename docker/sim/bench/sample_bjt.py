"""Pick distinct bipolar .model cards from the model index, for a batch run.

    python3 docker/sim/bench/sample_bjt.py INDEX.jsonl OUT.jsonl [--n 400] [--seed 2026]

Only cards that stand alone — not the transistors inside an op-amp's or a regulator's subcircuit, which
are that subcircuit's business. Distinct = same polarity and same parameters (names lower-cased, values
as written); among copies the first in index order is kept. --n 0 keeps them all, which is the population
a full run would measure.
"""

import argparse
import json
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("index")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    seen = {}
    total = 0
    with open(a.index) as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") != "model" or r.get("type") not in ("NPN", "PNP") or r.get("encrypted"):
                continue
            if r.get("parent"):
                continue
            total += 1
            key = (r["type"], tuple(sorted((k.lower(), str(v).lower()) for k, v in r["params"].items())))
            seen.setdefault(key, r)
    rows = list(seen.values())
    print(f"{total} bipolar definitions, {len(rows)} distinct")
    random.Random(a.seed).shuffle(rows)
    if a.n:
        rows = rows[:a.n]
    with open(a.out, "w") as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({"id": i, "name": r["name"], "source": r["source"], "file": r["file"],
                                "line": r["line"], "polarity": r["type"].lower()}) + "\n")


if __name__ == "__main__":
    main()
