"""Measure many bipolar models in one container: the unit of work for a large run.

    python3 /sim/bench/batch.py --list /jobs/models.jsonl --models /models --out /out \\
        --shard 3/40 --pack 20

Each line of the list names one model: {"id", "file" (relative to --models), "line" (1-based line of its
model card), "polarity" ("npn"|"pnp")}. The card is copied out of its file with its continuation lines and
renamed DUT<k>, so a name no simulator would parse, or one that clashes with another model packed beside
it, never matters. `--pack K` puts K models in each netlist: the simulator starts once per K models, which
is what makes a Windows simulator under Wine affordable in bulk. When a packed netlist fails fast as a
whole (one card a simulator refuses stops the whole netlist), it is split in halves and each half is
measured again, down to the one card at fault: the others keep their result and most of the packing's
saving. When it runs out of time, or a model fails on its own inside a pack that ran, the models at fault
are measured again one by one.

Workers share the list by claiming packs, not by taking fixed slices of it: each claims the next pack
nobody has (a file created in --out/claims, which only one creator can win), so a worker stuck on a slow
pack does not leave its share of the list waiting while the others sit idle. --shard i/n only names the
worker. Writes, in --out: results-<i>.jsonl (one line per model), runs-<i>.jsonl (one line per simulator
run: what it cost) and worker-<i>.json (the container's totals).
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import bjt, engines, raw  # noqa: E402

CARD_START = re.compile(r"^(\s*\.model\s+)(\S+)", re.I)
# LTspice's catalogue fields: they describe the part and do not enter the equations, and ngspice reads a
# bare word such as mfg=TFK as a parameter it cannot find. Taken out for every simulator alike.
# A good pack of 10 takes LTspice ~6 s on four CPUs; a card that sends a simulator into minutes of gmin
# stepping should cost this much once, not hold its whole pack.
RUN_TIMEOUT_S = (15, 2)  # seconds per run, plus per model in it
INFO_PARAMS = re.compile(r"\b(?:mfg|vceo|icrating)\s*=\s*[^\s)]+", re.I)


def extract_card(path, line):
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    i = line - 1
    if not CARD_START.match(lines[i]):
        raise ValueError(f"line {line} of {path} is not a .model card")
    card = [lines[i]]
    i += 1
    while i < len(lines) and (lines[i].lstrip().startswith("+") or not lines[i].strip()):
        if lines[i].strip():
            card.append(lines[i])
        i += 1
    return INFO_PARAMS.sub("", "\n".join(card))


# The cards are written for PSpice and LTspice, where a unit after a number is decoration: IKF=10A is ten
# amperes. ngspice reads the same "A" as atto (1e-18), and its compatibility modes do not change that, so
# for ngspice alone the unit is taken off. (What cannot be translated is left alone: ngspice also clamps
# NK/NKF to 1 where the others take the card's value.)
AMPERE_UNIT = re.compile(r"(?<=[\d.])A(?:MPS?)?(?=[\s),]|$)", re.I | re.M)


def for_engine(card, engine):
    return AMPERE_UNIT.sub("", card) if engine == "ngspice" else card


def rename(card, name):
    first, _, rest = card.partition("\n")
    first = CARD_START.sub(lambda m: m[1] + name, first, count=1)
    # "NAME NPN(" is legal; a name glued to its type ("NAMENPN(") is not something we produce.
    return first + ("\n" + rest if rest else "")


def run_pack(pack, workdir, engine, runs_out):
    """pack: [(job, card)]. Returns {job id: (measurements, error)}."""
    workdir.mkdir(parents=True, exist_ok=True)
    lib = workdir / "models.lib"
    lib.write_text("\n".join(rename(for_engine(card, engine), f"DUT{k}") for k, (_, card) in enumerate(pack))
                   + "\n")
    duts_base = [("models.lib", f"DUT{k}", 1 if job["polarity"] == "npn" else -1) for k, (job, _) in
                 enumerate(pack)]
    meas = {k: {} for k in range(len(pack))}
    timed_out = False
    err = {k: None for k in range(len(pack))}
    extra = {k: {} for k in range(len(pack))}
    for analysis in bjt.ANALYSES:
        duts = [(inc, name, s, {"ib_ft": extra[k].get("ib_ft")} if analysis == "ac" else None)
                for k, (inc, name, s) in enumerate(duts_base)]
        net = workdir / f"{analysis}.cir"
        net.write_text(bjt.netlist(analysis, engine, duts, title=f"batch pack of {len(pack)}"))
        cost = engines.run(net, engine, timeout=RUN_TIMEOUT_S[0] + RUN_TIMEOUT_S[1] * len(pack))
        cost.update(analysis=analysis, pack=len(pack), ids=[j["id"] for j, _ in pack])
        timed_out = timed_out or cost["timed_out"]
        plot = None
        if cost["raw"]:
            try:
                plot = bjt.pick_plot(raw.read(cost["raw"]), analysis)
            except Exception as exc:  # noqa: BLE001
                cost["error"] = f"read: {exc}"
        else:
            cost["error"] = "no waveform file"
        runs_out.write(json.dumps(cost) + "\n")
        runs_out.flush()
        for k in range(len(pack)):
            if plot is None:
                err[k] = err[k] or f"{analysis}: {cost['error']}"
                continue
            try:
                m = bjt.MEASURE[analysis](plot, duts_base[k][2], k)
                if "_ib_ft" in m:
                    extra[k]["ib_ft"] = m.pop("_ib_ft")
                meas[k].update(m)
            except Exception as exc:  # noqa: BLE001
                err[k] = err[k] or f"{analysis}: {type(exc).__name__}: {exc}"
        if cost["raw"]:
            Path(cost["raw"]).unlink(missing_ok=True)  # waveforms are large; the numbers are kept
    return {pack[k][0]["id"]: (meas[k], err[k]) for k in range(len(pack))}, timed_out


def measure(pack, workdir, engine, runs_out):
    got, timed_out = run_pack(pack, workdir, engine, runs_out)
    bad = [(job, card) for job, card in pack if got[job["id"]][1]]
    if len(pack) > 1 and bad:
        # A netlist that failed fast has a card the simulator refused: halve it to find the card. One that
        # ran out of time has a model the simulator cannot finish: halving would wait for it at every
        # level, so each model is measured alone and that one waits only once.
        if len(bad) == len(pack) and not timed_out:
            half = len(pack) // 2
            got.update(measure(pack[:half], workdir.with_name(workdir.name + "a"), engine, runs_out))
            got.update(measure(pack[half:], workdir.with_name(workdir.name + "b"), engine, runs_out))
        else:
            for job, card in bad:
                got.update(measure([(job, card)], workdir.with_name(f"{workdir.name}-{job['id']}"), engine,
                                   runs_out))
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", required=True)
    ap.add_argument("--models", required=True, help="root the list's file paths are relative to")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--pack", type=int, default=1)
    ap.add_argument("--engine", default=None)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    engine = a.engine or engines.engine_name()
    i = int(a.shard.split("/")[0])
    jobs = [json.loads(line) for line in Path(a.list).read_text().splitlines() if line.strip()]
    if a.limit:
        jobs = jobs[:a.limit]
    out = Path(a.out)
    claims = out / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    work = Path("/tmp/batch")
    t0 = time.perf_counter()
    cg0 = engines._cgroup_cpu_s()
    done = failed = 0
    mine = 0
    with open(out / f"results-{i}.jsonl", "w") as res_out, open(out / f"runs-{i}.jsonl", "w") as runs_out:
        for pi in range(0, (len(jobs) + a.pack - 1) // a.pack):
            try:
                os.close(os.open(claims / str(pi), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            except FileExistsError:
                continue
            mine += 1
            pack = []
            for job in jobs[pi * a.pack:(pi + 1) * a.pack]:
                try:
                    pack.append((job, extract_card(Path(a.models) / job["file"], job["line"])))
                except Exception as exc:  # noqa: BLE001
                    res_out.write(json.dumps({"id": job["id"], "engine": engine, "error": f"card: {exc}"}) + "\n")
                    failed += 1
            if not pack:
                continue
            got = measure(pack, work / f"p{pi}", engine, runs_out)
            for job, _ in pack:
                m, e = got[job["id"]]
                res_out.write(json.dumps({"id": job["id"], "engine": engine, "measurements": m, "error": e})
                              + "\n")
                done += e is None
                failed += e is not None
            res_out.flush()
    summary = {"engine": engine, "shard": a.shard, "pack": a.pack, "packs": mine, "models": done + failed, "ok": done,
               "failed": failed, "wall_s": round(time.perf_counter() - t0, 3),
               "container_cpu_s": round((engines._cgroup_cpu_s() or 0) - (cg0 or 0), 3),
               "container_mem_peak_mb": engines._cgroup_mem_peak_mb()}
    (out / f"worker-{i}.json").write_text(json.dumps(summary))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
