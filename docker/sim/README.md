# docker/sim — ngspice, LTspice and QSPICE, pinned, from the command line

Three SPICE simulators in Docker images whose every input is pinned, a bench that measures a bipolar
transistor model the way its data sheet is measured, and a batch runner that does it for thousands of
models on every core of a machine.

**QSPICE is the default engine** (the maintainer's choice, 2026-09-28: the modern one, slower accepted).
The other two stay, each for what QSPICE cannot give: **ngspice** is the open cross-check — the
repository is public, and nobody can rebuild the QSPICE image without accepting Qorvo's licence, while
anyone can repeat an ngspice number — and **LTspice** is the compatibility check, because it is what the
people this project serves simulate with, and because QSPICE accepts some broken cards without a word
(see the BFP180 below).

This is the first working piece of pillar 3 (`src/parts_index/bench/`, still **(todo)**): the code here
is a prototype, stdlib-only so that it runs unchanged inside every image.

- [What is pinned](#what-is-pinned)
- [Building the images](#building-the-images)
- [Measuring one model](#measuring-one-model)
- [The bipolar bench](#the-bipolar-bench)
- [Measuring many models](#measuring-many-models)
- [What it costs](#what-it-costs)
- [How each simulator is driven, and what it took](#how-each-simulator-is-driven-and-what-it-took)

## What is pinned

| input | version | pinned by | from |
|---|---|---|---|
| base image | Debian 13 (trixie) slim | digest, `ARG DEBIAN` in the Dockerfile | Docker Hub |
| every Debian package (Wine 10.0, Xvfb, Python 3.13, compilers…) | as of `SNAPSHOT=20260926T000000Z` | snapshot.debian.org at that instant | Debian |
| ngspice | 47 | sha256 of the release tarball, built from source in the image | sourceforge.net/projects/ngspice |
| LTspice | 26.1.1 | sha256 of `LTspice64.msi` | ltspice.analog.com/software/LTspice64.msi |
| QSPICE | build "Sep 13 2026 09:34:10" | sha256 of an archive of the installed program folder | getqspice.com (`InstallQSPICE.exe`) |

The sha256 files are in `sha256/`. The vendor files themselves live in the **private vendor store**
(`private_material/simulators/vendor/`, `SIM_VENDOR` in the Makefile): LTspice and QSPICE may not be
redistributed, so they never enter the repository, and the images built from them are never pushed to a
registry — every machine builds its own from the same files. The build context is `docker/sim/` alone;
the store is passed as a named context (`--build-context vendor=…`).

Analog Devices replaces `LTspice64.msi` at the same URL with every release, and QSPICE's installer always
fetches the latest build. So the store copy is the one that counts: `make sim-vendor` reports a download
that no longer matches its pinned sha256 and never uses it. Moving to a new release is a deliberate change
of the sha256 file — and of every result measured with the old one.

## Building the images

```sh
make sim-vendor            # fetch the installers into the private store, check the sha256 of each
make sim-qspice-capture    # once: install QSPICE under Wine and pack it (accepts Qorvo's licence, see below)
make sim-images            # parts-index-ngspice, parts-index-ltspice, parts-index-qspice
```

From nothing (`--no-cache`), on the 40-thread server: ngspice 2.5 min (most of it compiling), LTspice
2.2 min and QSPICE 1.5 min (most of each is installing Wine from the snapshot). Images: ngspice 0.13 GB,
LTspice and QSPICE 3.7 GB each, of which 2 GB is the Wine base they share.

**Reproducibility, checked:** all three images were rebuilt from nothing — no cache, and with the
containers' internal paths moved — and the 2N2222 below measured again: every number in every simulator
came out bit-identical to the run on the images before, with the same `LTspice.exe` and `QSPICE64.exe`
sha256. Within one image, repeats are bit-identical too.

The containers run as a user with the host's uid/gid (build args), so the files they write are yours.

## Measuring one model

```sh
make sim-bjt FILE=path/to/2N2222.LIB NAME=2N2222 REPEAT=3
```

runs the bench in each simulator and prints the measurements side by side, the spread between
simulators, and whether every repeat gave identical numbers. By hand, in one image:

```sh
docker run --rm -v "$PWD/run":/w parts-index-ltspice \
  python3 /sim/bench/bjt.py --model-file /w/2N2222.LIB --model 2N2222 --out /w/ltspice --repeat 3
docker run --rm -v "$PWD/run":/w parts-index-qspice simrun /w/any.cir   # any netlist: files + cost as JSON
```

`--out` receives the three netlists, each simulator's waveform file and log, and `result.json`: the
measurements, the simulator's identity (ngspice's version string; the sha256 of `LTspice.exe` or
`QSPICE64.exe`), and per run its wall time, CPU time, peak memory and a digest of the numbers it produced.

The result for Central Semiconductor's 2N2222 model (`2N2222.LIB`, 2014), with REPEAT=3:

| quantity (data-sheet condition) | QSPICE (default) | ngspice 47 | LTspice 26.1.1 | spread |
|---|---|---|---|---|
| hFE, IC = 0.1 mA, VCE = 10 V | 102.936 | 102.936 | 102.936 | 1e-7 |
| hFE, IC = 10 mA, VCE = 10 V | 211.642 | 211.644 | 211.642 | 1e-5 |
| hFE, IC = 150 mA, VCE = 10 V | 161.685 | 161.700 | 161.685 | 9e-5 |
| hFE, IC = 500 mA, VCE = 10 V | 92.674 | 92.685 | 92.674 | 1e-4 |
| VCE(sat), 150 mA / 15 mA | 0.09221 V | 0.09221 V | 0.09221 V | 1e-5 |
| VBE(sat), 500 mA / 50 mA | 1.0382 V | 1.0382 V | 1.0382 V | 1e-5 |
| fT (\|h21\| × 100 MHz), 20 mA, 20 V | 366.5 MHz | 366.5 MHz | 366.5 MHz | 3e-6 |
| Cob, VCB = 10 V, 1 MHz | 4.290 pF | 4.290 pF | 4.290 pF | 3e-10 |
| Cib, VEB = 0.5 V, 1 MHz | 20.63 pF | 20.63 pF | 20.63 pF | 3e-10 |
| ts, 150 mA, IB1 = IB2 = 15 mA | 156.2 ns | 155.8 ns | 155.8 ns | 3e-3 |
| tf | 9.55 ns | 9.48 ns | 9.48 ns | 7e-3 |

Every simulator gave bit-identical numbers on each of its three repeats. DC and AC agree to 4–10
significant digits (the ngspice DC difference is the solver tolerance, `reltol=1e-4`); the transient
times differ by under 1 % because each simulator picks its own time steps.

Against a data sheet: Central publishes its 2N2222A model with the same parameters as its 2N2222, so the
limits of onsemi's 2N2222A data sheet ([2n2222a-d.pdf](https://www.onsemi.com/download/data-sheet/pdf/2n2222a-d.pdf),
"Electrical characteristics", T = 25 °C) apply:

| quantity | limit (onsemi) | model (ngspice) | |
|---|---|---|---|
| hFE at 0.1 / 1 / 10 / 150 / 500 mA, 10 V | ≥ 50 / 75–325 / ≥ 100 / 100–300 / ≥ 30 | 102.9 / 171.5 / 211.6 / 161.7 / 92.7 | inside |
| VCE(sat) at 150 / 500 mA, IC/IB = 10 | ≤ 0.3 / 1.0 V | 0.092 / 0.209 V | inside |
| VBE(sat) at 150 / 500 mA | 0.6–1.2 / ≤ 2.0 V | 0.892 / 1.038 V | inside |
| \|hfe\| at 20 mA, 20 V, 100 MHz | ≥ 2.5 | 3.67 | inside |
| Cibo (VEB = 0.5 V) / Cobo (VCB = 10 V) | ≤ 25 / 8 pF | 20.6 / 4.29 pF | inside |
| ton / toff (MIL-PRF-19500/255 fixture) | ≤ 35 / 300 ns | td+tr 13.9 / ts+tf 165 ns | inside, but a simpler fixture |

## The bipolar bench

`bench/bjt.py` writes three netlists — LTspice runs one analysis per netlist, so one each:

- **dc** — a DC sweep of `V(x)` from −8 to −1 in steps of 0.1, with behavioural sources
  `I = 10^V(x)` feeding the bases: 10 points per decade of base current, 10 nA to 100 mA. One transistor
  per VCE (1, 10 and 20 V, collector held by a voltage source) gives IC(IB) and VBE(IB), and hFE at each
  data-sheet IC is read by interpolating in log IC. One more transistor has its collector fed 10 × its base
  current along the same sweep, for VCE(sat) and VBE(sat) at IC/IB = 10; a diode to 30 V catches the
  collector of a transistor too weak to take it, which is then reported as not saturated.
  Why a sweep: forcing the collector current, or feeding fixed currents into many junctions at once, left
  ngspice with a singular matrix and LTspice in minutes of gmin stepping; a sweep starts each point from
  the last one, so it converges in all three, and packs of many models converge as easily as one.
- **ac** — fT: the transistor biased at IC = 20 mA, VCE = 20 V (the base current comes from the dc run),
  an AC current into the base, the collector held by a voltage source: |h21| at 100 MHz × 100 MHz, as the
  data sheet does it, and where |h21| crosses 1. Cob (VCB = 10 V, emitter open) and Cib (VEB = 0.5 V,
  collector open) from the imaginary part of the source current at 1 MHz.
- **tran** — a 200 Ω load from 30 V (IC ≈ 150 mA), the base driven through 1 kΩ by an edge to +15.8 V and
  back to −14.2 V (IB1 = IB2 ≈ 15 mA): td, tr, ts, tf between the 10 % and 90 % points. A simplification of
  the data sheet's switching fixture (MIL-PRF-19500/255), not a copy of it.

Every analysis has `.options reltol=1e-4` and `.temp 25`; LTspice also gets `plotwinsize=0` (no
waveform compression) and `numdgt=15` (doubles in the waveform file). Each netlist `.save`s only the
vectors its measurements read (two to eight per model instead of every node and device current), and all
three simulators are asked for text waveform files, which `bench/raw.py` reads line by line into arrays
of doubles: ngspice's `.raw`, LTspice's UTF-16 `.raw` and QSPICE's `.qraw` share one layout. Both matter
in bulk: before them, one pack of ten models whose transient QSPICE resolved in very fine steps left a
text file that took the reader past 5 GB, and the container was killed; with them, the same pack peaks at
0.3 GB and takes half the time, with bit-identical results.

Each netlist may hold several models, each with its own nodes (`netlist(analysis, engine, duts)`): the
batch runner uses this to start a simulator once for many models. Packed and single runs give identical
numbers.

## Measuring many models

```sh
make sim-sample N=0                                     # every distinct bipolar card in the model index
make sim-batch LIST=private_material/simulators/runs/bjt_0.jsonl              # QSPICE, one worker per CPU
make sim-batch LIST=… ENGINE=ltspice WORKERS=20 SIM_CPUS=2                   # LTspice, as measured below
```

`bench/sample_bjt.py` lists the distinct `.model` cards of type NPN/PNP in the index that stand alone
(not the transistors inside an op-amp's subcircuit; distinct = same polarity and parameters): 7,295 of
the 36,360 such definitions. `batch.sh` starts WORKERS containers, each held to SIM_CPUS CPUs (default 1)
and 4 GB (SIM_MEMORY). Inside each, `bench/batch.py` claims the next pack of PACK models nobody has taken
(a file created with O_EXCL in the output folder, so a worker stuck on a slow pack holds up nobody),
copies each card out of its file, renames it `DUT<k>`, drops LTspice's catalogue fields (`mfg=`, `Vceo=`,
`Icrating=` — ngspice reads `mfg=TFK` as a parameter it cannot find), and measures the pack. A run is
stopped after 15 s + 2 s per model in it. When a whole netlist fails fast — one card a simulator refuses
stops all of it — the pack is split in halves and each is measured again, down to the card at fault, so
the others keep their result and most of the packing's saving. When it runs out of time, the models are
measured again one by one instead: halving would wait for the slow model at every level. It writes `results-<i>.jsonl` (one line per
model), `runs-<i>.jsonl` (one per simulator run, with its cost), `worker-<i>.json`, and `run.json` for the
whole run (wall time, models per second, CPU seconds per model, the busiest worker's memory, how busy the
host's CPUs were). `bench/agree.py` then compares the simulators model by model.

## What it costs

Measured on the maintainer's server — 2 × Xeon Silver 4410T, 20 cores / 40 threads at up to 2.7 GHz,
187 GB of memory, shared with other people's services — on 2026-09-28, with the bench above, packs of 10.

**What one model costs** (one worker, 400 distinct stand-alone bipolar cards drawn at random):

| simulator | wall time | CPU per model | measured | simulator process | worker (container) peak |
|---|---|---|---|---|---|
| QSPICE (1 CPU) | 200 s | 0.40 s | 398 / 400 | ≤ 0.1 GB | 0.3 GB |
| ngspice (1 CPU) | 62 s | 0.14 s | 392 / 400 | ≤ 0.06 GB | 0.15 GB |
| LTspice (4 CPUs) | 756 s | 3.2 s | 388 / 400 | 0.15 GB | 0.5–1.6 GB |

Inside a good pack a model costs QSPICE 0.04 s (dc) + 0.05 s (ac) + 0.15 s (tran) of wall time, ngspice
0.01 + 0.002 + 0.05 s. LTspice's CPU time is mostly its solver threads waiting for each other; how to
share the machine between LTspice workers was measured on the same 400:

| LTspice workers × CPUs each | 1 × 4 | 10 × 4 | 20 × 2 | 40 × 1 | 40 × no limit |
|---|---|---|---|---|---|
| wall time | 756 s | 107 s | 97 s | 118 s | 93 s |
| CPU per model | 3.2 s | 3.1 s | 3.3 s | 4.0 s | 5.2 s |

20 × 2 is within 5 % of the fastest for two thirds of the CPU, so that is what the full run used.

**The whole population** — every distinct stand-alone bipolar card in the index, 7,295 of them:

| simulator | workers × CPUs | wall time | models / s | CPU per model | measured | host CPU busy |
|---|---|---|---|---|---|---|
| QSPICE | 40 × 1 | **99 s** | 74 | 0.21 s | 7,273 (99.7 %) | 43 % |
| ngspice | 40 × 1 | **63 s** | 115 | 0.12 s | 7,188 (98.5 %) | 38 % |
| LTspice | 20 × 2 | **872 s** | 8.4 | 3.6 s | 7,105 (97.4 %) | 78 % |

80 QSPICE workers took 95 s: at this size the run is bounded by starting the containers and by its
slowest pack, not by the CPUs. Memory is never the limit — under 0.5 GB per worker for QSPICE and
ngspice, under 20 GB for forty — and the results take 9 MB per simulator per full run (the waveforms are
deleted once measured). Images: 0.13 GB for ngspice, 3.7 GB for each Wine image (the 2 GB Wine base is
shared between them); the vendor store is 0.24 GB.

**Do the simulators agree?** On the 7,036 models all three measured, the DC quantities agree within 1 %
in 97–100 % of models, fT and the capacitances in 96–98 %, the switching times in 91–97 % (98 % within
5 %). In the 603 models where some value differs by more than 5 %, the odd one out is ngspice in 523,
QSPICE in 92 and LTspice in 17: QSPICE reads the cards the way LTspice does, which is what the default
engine should do. The reasons found so far are dialect, not arithmetic: ngspice reads `IKF=10A` as
10 attoamperes (the "a" prefix; in PSpice and LTspice the unit is decoration) — now translated for
ngspice alone — and clamps `NK` to 1 where the others take the card's 4.8. A broken card shows up too:
Bordodynov's BFP180 ends in `KF=0AF=1)   )`; LTspice refuses it, QSPICE and ngspice take it silently.

**Everything, estimated.** Only the bipolar bench exists. The index holds 23,911 distinct stand-alone
discrete models — 7,295 bipolar, 11,678 diodes, 3,658 MOSFETs (1,534 NMOS, 299 PMOS, 1,825 VDMOS), 1,280
JFETs. If the benches still to write for diodes, MOSFETs and JFETs cost what the bipolar one does, the
whole discrete library takes about **5–6 minutes with QSPICE**, 3–4 with ngspice and 45–50 with LTspice on
this machine. Subcircuits are the bulk: 337,864 definitions under 137,668 distinct names (op-amps,
regulators, MOSFET macro-models), each kind needing its own bench, with circuits several times larger:
at ten times a transistor's cost that is about 5 hours with QSPICE — one night — and about 45 with
LTspice. Those two figures are orders of magnitude, not measurements.

**And the GPUs?** None of the three simulators can use them (see below). What makes this fast is one
simulator per core, packing models into netlists, and saving only what is measured.

## How each simulator is driven, and what it took

**ngspice** — `ngspice -b -r out.raw deck.cir` with `SPICE_ASCIIRAWFILE=1`. Built from the release
tarball with XSPICE, CIDER and OpenMP. Its OpenMP only parallelises BSIM device evaluation, so one run
uses one core. It rejects LTspice's catalogue fields in model cards (`mfg=…`), hence the clean-up above,
and reads a unit after a number as a prefix (`10A` is ten attoamperes to it), so for ngspice alone the
batch runner takes the "A" off. Its compatibility modes (`set ngbehavior=ltps`) change neither.

**LTspice** — `wine64 LTspice.exe -b -ascii deck.cir`, run from the deck's folder. Three things stood in
the way, each solved at build time so no container meets them:
1. The MSI's installer hangs under Wine in a custom action that reports the installation home
   (`AI_IaLogPkgStarted`, InstallerAnalytics.dll). The MSI is unpacked with `msiextract` instead; LTspice
   is a program folder and needs nothing from the registry.
2. The first launches open windows, even in batch mode, and wait: whether to send usage data, whether to
   keep the keyboard shortcuts, and "Installing library files". `ltspice/LTspice.ini` answers the first
   (`CaptureAnalytics=false`), and `ltspice/firstrun.sh` runs LTspice under Xvfb at build time, answering
   what is left with its default, until a batch run finishes with no window; it fails the build rather
   than answer a question about usage data.
3. It needs an X display even with `-b` (without one it exits with status 9 and writes nothing), so every
   container starts an Xvfb once, with one persistent Wine server.
It starts one solver thread per CPU of the host — 40 here, whatever its container is allowed — and in
batch mode nothing changes that: `.options nthreads=1` is a syntax error in 26.1.1, the Control Panel's
"Max threads" is not remembered between runs, and Wine's `WINE_CPU_TOPOLOGY` does not move it. The
threads wait for each other by spinning, so an LTspice confined to one CPU by affinity (`taskset`,
`--cpuset-cpus`) never finishes a transient, and one held to one CPU by quota (`--cpus 1`) takes ~5 s
for what takes ~1.5 s with four. How to share a machine between LTspice workers is therefore measured
([What it costs](#what-it-costs)) rather than assumed.

**QSPICE** — `wine QSPICE64.exe deck.cir -ascii -r deck.qraw` (usage found in the binary:
`deck.cir [ -r deck.qraw ] [ -o deck.out ] [ -binary ] [ -ascii ]`). `QSPICE64.exe` and `QSPICE80.exe`
are **32-bit** programs — the number is the floating-point width, 80 being the x87 extended type — so the
Wine base carries both 32- and 64-bit Wine. Its installer is a downloader with a licence window, so it
cannot run inside a build: `qspice_capture.sh` runs it once in the `qspice-installer` stage, answers its
windows with xdotool (DirectX 12 warnings, install as administrator, download, the licence, install),
screenshots the licence it accepts, and packs `C:\Program Files\QSPICE` (1,427 files, nothing outside it
but shortcuts) with sorted names, fixed times and owners, so a second capture of the same build gives
the same sha256 — checked: the scripted capture, run from nothing, reproduced the hand-made one exactly.
A capture never overwrites the pinned archive: a different build is kept beside it, for the maintainer to
adopt deliberately. **The licence**, "Software License Agreement for QSPICE Software", forbids giving the
software to third parties; the maintainer accepted it on 2026-09-20 for this build. Run the capture only
if you accept it yourself.

**GPUs** — none of the three can use one. ngspice has no GPU path (the old CUDA fork, CUSPICE, only ever
evaluated BSIM4 devices and is abandoned), and LTspice and QSPICE are CPU programs. On this kind of work —
thousands of small, independent circuits — the parallelism that pays is one simulator per core. The GPUs
belong to the other half of pillar 3: reading the data sheets' tables and curves that the measurements
are compared with.
