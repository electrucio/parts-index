"""Would the model's reading of the data sheets have judged the SPICE models the same as the hand-read one?

    python3 docker/datasheets/compare_verdicts.py REFERENCE/results-qspice.json EXTRACTED/results-qspice.json

Both files come from crosscheck.py: one with rows from golden.yaml, one with rows from an extraction run.
Rows are paired by quantity and test conditions; for every model of every part, each paired row's verdict
(inside / below / above / ratio to typical) is compared. Rows only one side has are counted apart: a row the
extraction missed is a check that would not have been made; a row only the extraction has is one the
reference did not transcribe (the reference holds the rows a bench can use, not every row).
"""

import json
import sys
from collections import Counter


def key(row):
    cond = {k: v for k, v in row["cond"].items() if not (k in ("TA", "TJ", "TC", "TAMB") and v == 25)}
    return (row["sym"], tuple(sorted((k, float(f"{v:.4g}")) for k, v in cond.items())))


def load(path):
    d = json.load(open(path))
    rows = {part: {key(r): r for r in m["rows"]} for part, m in d["meta"].items()}
    res = {(r["part"], r["model_id"]): {x["id"]: x for x in r["rows"]} for r in d["results"]}
    return rows, res


def main(ref_path, ext_path):
    ref_rows, ref_res = load(ref_path)
    ext_rows, ext_res = load(ext_path)
    c = Counter()
    diffs = []
    for part in ref_rows:
        rk, ek = ref_rows[part], ext_rows.get(part, {})
        c["rows_ref"] += len(rk)
        c["rows_paired"] += len(set(rk) & set(ek))
        c["rows_only_ref"] += len(set(rk) - set(ek))
        c["rows_only_ext"] += len(set(ek) - set(rk))
        for (p, mid), vals in ref_res.items():
            if p != part or (p, mid) not in ext_res:
                continue
            evals = ext_res[(p, mid)]
            for k in set(rk) & set(ek):
                a = vals[rk[k]["id"]]["verdict"]
                b = evals[ek[k]["id"]]["verdict"]
                same = a == b
                c["verdicts_same" if same else "verdicts_different"] += 1
                if not same:
                    diffs.append((part, mid.split(" [")[0], rk[k]["text"], a, b, ek[k]))
    print(json.dumps(c, indent=1))
    for part, mid, text, a, b, er in diffs[:30]:
        print(f"  {part:22s} {mid:12s} {text:48s} reference: {a:14s} extracted: {b:14s} "
              f"(extracted limits min={er['min']} typ={er['typ']} max={er['max']})")
    missing = [(part, rk_["text"]) for part in ref_rows for k, rk_ in ref_rows[part].items()
               if k not in ext_rows.get(part, {})]
    print("\nreference rows the extraction did not give (so no check):")
    for part, text in missing[:40]:
        print(f"  {part:22s} {text}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
