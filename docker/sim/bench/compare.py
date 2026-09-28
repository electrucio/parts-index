"""Put one model's measurements from each simulator side by side.

    python3 docker/sim/bench/compare.py RUN_DIR      (RUN_DIR/<engine>/result.json, as bjt.py writes them)

Prints every quantity per simulator, the largest relative spread between simulators, and whether each
simulator gave the same numbers on every repeat (one digest per analysis).
"""

import json
import sys
from pathlib import Path


def main(run_dir):
    results = {p.parent.name: json.loads(p.read_text()) for p in sorted(Path(run_dir).glob("*/result.json"))}
    engines = list(results)
    keys = list(dict.fromkeys(k for r in results.values() for k in r["measurements"]))
    print(f"{'quantity':26s}" + "".join(f"{e:>15s}" for e in engines) + f"{'spread':>10s}")
    for k in keys:
        vals = [results[e]["measurements"].get(k) for e in engines]
        nums = [v for v in vals if isinstance(v, (int, float))]
        spread = ""
        if len(nums) > 1 and all(nums) and k != "points":
            spread = f"{(max(nums) - min(nums)) / abs(sum(nums) / len(nums)):.1e}"
        cells = "".join(f"{v:15.6g}" if isinstance(v, (int, float)) else f"{str(v):>15s}" for v in vals)
        print(f"{k:26s}{cells}{spread:>10s}")
    print()
    for e, r in results.items():
        runs = r["runs"]
        same = all(len({x["digest"] for x in runs if x["analysis"] == a}) == 1 for a in {x["analysis"] for x in runs})
        wall = sum(x["wall_s"] for x in runs) / max(1, len({x["repeat"] for x in runs}))
        print(f"{e:10s} {len(runs)} runs, {'identical' if same else 'DIFFERENT'} results on every repeat, "
              f"{wall:.2f} s of simulator per model")


if __name__ == "__main__":
    main(sys.argv[1])
