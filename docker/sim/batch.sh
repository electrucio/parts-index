#!/bin/sh
# Measure a list of bipolar models with one simulator, WORKERS containers side by side, and say what the
# whole run cost the machine.
#
#   sh docker/sim/batch.sh ENGINE WORKERS PACK LIST OUT [MODELS]
#     ENGINE   ngspice | ltspice | qspice          (the image parts-index-ENGINE)
#     WORKERS  containers at once; each takes every WORKERS-th model of the list
#     PACK     models per netlist (1 = one at a time)
#     LIST     the .jsonl from bench/sample_bjt.py
#     OUT      folder for results-*.jsonl, runs-*.jsonl, worker-*.json and run.json
#     MODELS   the folder the list's paths are relative to (default: private_web_spice_models)
#
# One container per worker, not one process per worker in a shared container: each gets its own Wine
# server and virtual screen, so nothing is shared between workers but the CPU. Each worker is limited to
# SIM_CPUS CPUs (default 1; 0 = no limit), so WORKERS x SIM_CPUS is what the run may take, and to 4 GB of
# memory (SIM_MEMORY): a model that makes a simulator run away fails alone instead of starving the machine.
# LTspice starts a solver thread per CPU of the host whatever its container allows; see the README.
set -eu
ENGINE=$1 WORKERS=$2 PACK=$3 LIST=$(realpath "$4") OUT=$5
MODELS=$(realpath "${6:-private_web_spice_models}")
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
OUT=$(realpath "$OUT")
cpu() { awk '/^cpu /{printf "%.0f %.0f\n", $2+$3+$4+$5+$6+$7+$8, $5+$6}' /proc/stat; }  # total, idle jiffies
set -- $(cpu); T0=$1 I0=$2
S0=$(date +%s.%N)
CPUS=${SIM_CPUS:-1}
LIMIT=""
[ "$CPUS" = 0 ] || LIMIT="--cpus $CPUS"
i=0
while [ $i -lt "$WORKERS" ]; do
    docker run --rm -d --name "sim-$ENGINE-$i" $LIMIT --memory "${SIM_MEMORY:-4g}" --tmpfs /tmp/batch \
        -v "$HERE/bench:/sim/bench:ro" -v "$MODELS:/models:ro" -v "$LIST:/jobs/list.jsonl:ro" \
        -v "$OUT:/out" "parts-index-$ENGINE" \
        python3 /sim/bench/batch.py --list /jobs/list.jsonl --models /models --out /out \
        --shard "$i/$WORKERS" --pack "$PACK" >/dev/null
    i=$((i + 1))
done
while docker ps --format '{{.Names}}' | grep -q "^sim-$ENGINE-"; do sleep 1; done
S1=$(date +%s.%N)
set -- $(cpu); T1=$1 I1=$2
python3 - "$OUT" "$ENGINE" "$WORKERS" "$PACK" "$S0" "$S1" "$T0" "$I0" "$T1" "$I1" "$(nproc)" "$CPUS" <<'EOF'
import json, sys, glob
out, engine, workers, pack, s0, s1, t0, i0, t1, i1, ncpu, cpus = sys.argv[1:]
w = [json.load(open(p)) for p in glob.glob(f"{out}/worker-*.json")]
wall = float(s1) - float(s0)
busy = 1 - (int(i1) - int(i0)) / max(1, int(t1) - int(t0))
models = sum(x["models"] for x in w)
ok = sum(x["ok"] for x in w)
run = {"engine": engine, "workers": int(workers), "cpus_per_worker": float(cpus), "pack": int(pack),
       "models": models, "ok": ok,
       "wall_s": round(wall, 1), "models_per_s": round(models / wall, 2),
       "worker_cpu_s": round(sum(x["container_cpu_s"] for x in w), 1),
       "cpu_s_per_model": round(sum(x["container_cpu_s"] for x in w) / max(1, models), 3),
       "worker_mem_peak_mb_max": round(max((x["container_mem_peak_mb"] or 0 for x in w), default=0), 1),
       "host_cpu_busy": round(busy, 3), "host_cpus": int(ncpu)}
json.dump(run, open(f"{out}/run.json", "w"))
print(json.dumps(run))
EOF
