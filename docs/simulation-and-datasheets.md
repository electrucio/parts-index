# Simulating models and reading data sheets — decisions, findings and method

Pillar 3 asks of every SPICE model: **is it the part?** Answering takes two things — the model simulated
the way the part's data sheet measures the part, and the data sheet's numbers, structured and trustworthy
enough to be compared with automatically. This page gathers what the first round of work on both
(September 2026) decided, measured and learned, so that the next round starts from it. The procedures
and full results are in three READMEs:

- [docker/sim/README.md](../docker/sim/README.md) — the three simulators in pinned images, the bipolar
  bench, the batch runner, costs.
- [docker/vlm/README.md](../docker/vlm/README.md) — a vision-language model served on one GPU.
- [docker/datasheets/README.md](../docker/datasheets/README.md) — reading data-sheet tables with it, the
  reference set, and every model of a part held against its sheet.

Contents:

- [In short](#in-short)
- [Simulating](#simulating)
- [What differs between simulators, and what does not](#what-differs-between-simulators-and-what-does-not)
- [The model matters more than the simulator](#the-model-matters-more-than-the-simulator)
- [Cost, scale and GPUs](#cost-scale-and-gpus)
- [Data sheets: which sources to trust](#data-sheets-which-sources-to-trust)
- [Reading data sheets reliably](#reading-data-sheets-reliably)
- [Curves](#curves)
- [Next](#next)

## In short

- **Three simulators, run from the command line, in Docker images whose every input is pinned** — base
  image by digest, Debian packages by snapshot date, ngspice by source tarball, LTspice and QSPICE by the
  sha256 of files kept in a private store. Rebuilt from nothing, the images give bit-identical numbers.
- **QSPICE is the default engine; ngspice is the open cross-check; LTspice is the compatibility check.**
- **For the cards our library holds, the three simulators agree** to 4–10 digits in DC and AC and within
  1 % in transients. Where they disagree the cause has been dialect (how a card is read) or a named
  difference of implementation — never arithmetic.
- **Choosing another model of the same part changes results by whole factors**; choosing another
  simulator changes them by less than 1 %. A third of the cards filed under a part's name miss at least
  one limit of that part's data sheet; a few are plainly broken.
- **All 7,295 distinct stand-alone bipolar cards run in 99 s with QSPICE** on the 40-thread server
  (63 s ngspice, 872 s LTspice). Simulators cannot use GPUs; the GPUs are for reading data sheets.
- **Data sheets are read by a vision model, and never trusted on its word:** image plus a second look,
  every number checked against the PDF's text layer, a hand-read reference set to measure against.
  Qwen3.8-27B on one RTX 4090: 99.4 % of values right, no invented numbers, and the verdicts on 94 models
  identical to those from the hand-read rows.
- **Cross-reference sites are not a source of data-sheet values** (alltransistors.com checked: no test
  conditions, min/typ/max mixed, no source per value, several values wrong).
- **Curves are for people to compare by eye:** crop each graph, and say what to simulate to draw the same
  graph. The vision model finds and reads graphs well; the circuit must come from our own benches.

## Simulating

### Reproducible by construction

Everything a result depends on is pinned, and a result records what produced it (ngspice's version
string, the sha256 of `LTspice.exe` or `QSPICE64.exe`, wall time, CPU time, memory, a digest of the
numbers). The vendor files of LTspice and QSPICE may not be redistributed, so they live in the private
vendor store and the images built from them are never pushed: every machine builds its own from the
same files. Two vendor habits make the store copy the one that counts — Analog Devices replaces
`LTspice64.msi` at the same URL with every release, and QSPICE's installer always fetches the latest
build — so moving to a new release is a deliberate change of a sha256 file, and of every result
measured with the old one. The whole mechanism is in [docker/sim/README.md](../docker/sim/README.md).

### Which simulator for what

The maintainer chose **QSPICE as the default engine** (2026-09-28): it is the modern one, and it is
slower than ngspice, which is accepted. The other two stay, each for what QSPICE cannot give:

- **ngspice** is the **open cross-check**. The repository is public; nobody can rebuild the QSPICE image
  without accepting Qorvo's licence (which forbids giving the software to third parties), and no older
  QSPICE build can be downloaded, while anyone can repeat an ngspice number from source.
- **LTspice** is the **compatibility check**. It is what the people this project serves simulate with,
  and it refuses some broken cards that QSPICE and ngspice take without a word (Bordodynov's BFP180 ends
  in `KF=0AF=1)   )`).

Measuring more models is not by itself better: part of what a tolerant simulator measures is cards that
should have been refused. What to publish per model, eventually: which of the three run it, and whether
they agree.

### How a model is measured

The bench is the part of this that takes care; the lessons, each paid for once:

- **Measure as the data sheet measures.** Each quantity at the row's own conditions — hFE at (IC, VCE),
  VCE(sat) at (IC, IB), fT as |h21| × f at the sheet's frequency, Cob at VCB, NF at (IC, VCE, RG, f).
  `docker/sim/bench/spec.py` takes the rows and says inside / below / above, or the ratio to a typical.
- **Sweep, do not force.** Forcing collector currents, or fixed currents into many junctions at once,
  left ngspice with singular matrices and LTspice in minutes of gmin stepping. A DC sweep of a control
  voltage feeding the bases through `I = 10^V(x)` — ten points per decade of base current — starts each
  point from the last and converges in all three, for one model or for a pack of many.
- **Save only what is measured, and read waveforms as a stream.** One pack of ten models once left a
  text waveform that took the reader past 5 GB. With `.save` of the measured vectors and a line-by-line
  reader, the same pack peaks at 0.3 GB and takes half the time, with bit-identical results.
- **Pack models, start the simulator once.** Each model gets its own nodes in one netlist; packed and
  single runs give identical numbers. When a pack fails fast (one card a simulator refuses stops the
  whole netlist) it is halved down to the card at fault; when it runs out of time, its models are
  measured one by one, because halving would wait for the slow one at every level.
- **Clean the card for the dialect, not the model.** LTspice's catalogue fields (`mfg=`, `Vceo=`,
  `Icrating=`) are dropped; `10A` becomes `10` for ngspice alone (see below).
- **Distrust values no transistor has.** hFE above 10,000 or VBE outside 0.2–1.6 V is reported as
  *suspect*, not measured: QSPICE, driven by the bench's behavioural base source, settles on a wrong
  operating point for a card with RB ≈ 0 (Bordodynov's 2SC2240, `RB=1E-06`), while a plain current source
  gives the right answer in all three simulators.
- **LTspice needs handling.** It needs an X display even in batch mode (Xvfb), opens first-run windows
  that are answered at build time, and starts one solver thread per CPU of the host whatever its
  container is allowed — nothing in batch mode changes that — so how to share a machine between LTspice
  workers was measured (20 workers × 2 CPUs) rather than assumed.

## What differs between simulators, and what does not

**Feature tables mostly do not matter here.** Comparisons of the three simulators list MEXTRAM, HICUM,
Verilog-A, C++ devices, native GaN, self-heating, S-parameters. None of it changes a result unless a
card uses it, and our library hardly does. Counted among the index's top-level `.model` cards on
2026-09-28: 2 of 36,360 bipolar cards are VBIC (`level=9`), the rest Gummel-Poon; 1 of 10,444 JFET cards
is `level=2` (Parker–Skellern); none of 22,144 VDMOS cards uses `ksubthres` or `mtriode`; no card carries
thermal parameters (`RTH`, `CTH`). The same card read the same way gives the same numbers in all three —
measured on the 2N2222 and on 7,036 bipolar models.

**Where they do differ, measured** (the population run, plus eleven experiments on seven parts in all
three simulators; the experiments' script, cards and results are in `private_material/simulators/explore/`):

| difference | seen as | who is right |
|---|---|---|
| ngspice reads a unit after a number as a prefix: `IKF=10A` is 10 **atto**amperes | the odd one out in 523 of the 603 bipolar models where some value differs by more than 5 % | QSPICE and LTspice; the batch runner now removes the `A` for ngspice alone |
| ngspice clamps `NK` to 1; the others take the card's 4.8 | high-current hFE | — (a model-reading convention) |
| ngspice ignores LTspice's JFET extensions `isr`, `nr`, `alpha`, `vk` (with a warning) | gate current ~10× lower: IGSS at −30 V of a 2SK170 card 0.08 nA against 0.85–0.90 nA | QSPICE and LTspice (sheet: ≤ 1 nA) |
| ngspice and LTspice put gmin = 10⁻¹² S across junctions | below ~15 pA (at 15 V) what comes out is gmin, not the device: 2N5457 leakage 16 pA against QSPICE's 0.1 pA | none, without lowering gmin: **picoampere leakages are not trustworthy as simulated** |
| diode with `IKF`/`ISR` (Central's 1N4148) | ngspice VF 18 mV higher, IR 26 % lower; a plain card (onsemi's) is identical in all three | QSPICE and LTspice agree |
| diode reverse recovery | QSPICE's trr ~11 % longer (1.02 against 0.92 ns; 1.99 against 1.78 ns) | unknown; all well inside the sheet's ≤ 4 ns |
| VDMOS in weak inversion (IRF540N, 0.6 V below threshold) | QSPICE 6.6× the current of the other two | an implementation difference, as expected: VDMOS was LTspice's, and the others re-implemented it |
| noise output | QSPICE gives V²/Hz where the others give V/√Hz | a trap for automation, not a disagreement: 2SK170 en = 1.11 nV/√Hz in all three once converted |
| a badly posed circuit (a gate-charge test with no DC path) | QSPICE and ngspice solve it with gmin; LTspice finds no operating point | LTspice is the stricter |
| broken cards | BFP180's trailing `)   )`: LTspice refuses, the other two accept silently | LTspice |

Also measured and **identical** in all three: JFET transfer curves (IDSS, VGS(off), gm), VDMOS threshold,
capacitances and gate charge above threshold, temperature (2N2222 hFE 132 / 212 / 329 at −55 / 25 /
125 °C; ngspice even honours LTspice's JFET `Betatce` and `Vtotc`), and noise. The sub-threshold extension
that feature comparisons credit QSPICE with did not show on `level 1` JFET cards: all three cut off at the
same VGS.

**Models only one simulator opens** give no cross-check at all, whatever the numbers: QSPICE's own 1,265
native cards (103 GaN transistors at `level=2026` among them); about 1,100 subcircuits encrypted for
LTspice (1,021 of them Toshiba's), which are expected to have no QSPICE result (not yet tried); about
22,700 records encrypted for PSpice (Diodes Inc. 20,482, Toshiba 1,783, and onsemi, Infineon, TI, ROHM),
which probably none of the three opens (not yet checked); and 61 diode cards with LTspice-only parameters
(`Ron`, `Roff`, `Vfwd`).

**Still to measure:** subcircuits — op-amps, regulators, MOSFET macro-models — where the dialects part
most (PSpice's `VALUE`, `TABLE` and `LIMIT`; LTspice's own functions and `A` devices; Analog Devices'
models written for LTspice), and noise and temperature on many models rather than a few.

## The model matters more than the simulator

Holding each model against its part's data sheet (`docker/datasheets/crosscheck.py`; 15 bipolar and JFET
parts, 94 distinct cards, 147 rows at the sheets' own conditions): **64 of the 94 are inside every
limit.** The usual misses are fT and high-current hFE below the sheet, VBE(on) and VBE(sat) above it, and
IDSS and VGS(off) of JFETs. Some cards are not near misses but wrong:

- two 2N3904/2N3906 cards (a groups.io collection) with `KF=1E-9`: noise figure 44–46 dB where the sheet
  says ≤ 4–5 dB;
- an LSK170C card (Bordodynov) that never conducts (IDSS 1.8·10⁻¹⁴ A);
- J201 and 2N5457 cards from Micro-Cap netlists whose IDSS is several times the sheet's range (J201:
  4–26 mA against 0.2–1 mA).

In the exploration, two 1N4148 cards differ fivefold in capacitance (0.77 against 4.0 pF, onsemi's being
exactly the sheet's worst case), and the IRF540N card of LTspice's library has 3.5 times the sheet's
typical Crss. Two BC550C cards give noise figures of 0.2 and 0.6 dB, where the sheet says 1.2 typical —
models tend to be more optimistic than the typical device.

Two cautions when reading such comparisons: a *typical* value is one device, not a limit; and a bench's
fixture is sometimes simpler than the sheet's (the switching times here are).

## Cost, scale and GPUs

Measured on the 40-thread server (2 × Xeon Silver 4410T, 187 GB, shared), 2026-09-28:

| | QSPICE | ngspice | LTspice |
|---|---|---|---|
| CPU per bipolar model (three analyses) | 0.21 s | 0.12 s | 3.6 s |
| all 7,295 distinct stand-alone bipolar cards | **99 s** (40 × 1 CPU) | 63 s (40 × 1) | 872 s (20 × 2) |
| measured | 99.7 % | 98.5 % | 97.4 % |
| memory | < 0.5 GB per worker | < 0.5 GB | 0.5–1.6 GB |

At this size a run is bound by starting containers and by its slowest pack, not by the CPUs (80 QSPICE
workers: 95 s). Extrapolated, and so an order of magnitude only: the whole discrete library (23,911
distinct stand-alone cards) in 5–6 minutes with QSPICE; the subcircuits (137,668 distinct names), at ten
times a transistor's cost, about 5 hours with QSPICE — one night — and about 45 with LTspice.

**GPUs: none of the three simulators can use one.** ngspice has no GPU path (CUSPICE only ever evaluated
BSIM4 devices and is abandoned); LTspice and QSPICE are CPU programs. For thousands of small independent
circuits the parallelism that pays is one simulator per core. The GPUs serve the other half of pillar 3:
reading the data sheets the simulations are compared with.

## Data sheets: which sources to trust

**The manufacturer's data sheet, with its test conditions, is the reference; nothing else is.** A
simulated hFE can only be compared with an hFE at a stated IC and VCE, and the project's catalogue rule
applies: no fact without a source, and a language model is never the source.

**Cross-reference sites are not a source of values.** alltransistors.com was assessed on 2026-09-28. It
answers automated access with a Cloudflare challenge, so it was read only from two entries a person
pasted (2N2222A and 2SK170), compared with the manufacturers' sheets (onsemi, ST, Toshiba):

- each entry reduces the part to a fixed handful of numbers **without test conditions** (an hFE of 100 at
  no IC is meaningless: onsemi gives 50 at 0.1 mA, 75 at 1 mA, 100 at 10 mA, 100–300 at 150 mA, 30 at
  500 mA);
- it **mixes minimum, typical and maximum**, and manufacturers — its VCEO of 40 V is Philips' and
  Central's figure, where onsemi's metal-can sheet and ST's say 50 V — **without saying which sheet a
  number came from**;
- on the 2N2222A, 5 of 9 values match every sheet and the other 4 depend on the maker or lack conditions;
  on the 2SK170, 1 of 6 is right: PD 0.2 W against Toshiba's 400 mW, a "drain current" of 0.02 A that is
  the V grade's maximum IDSS, VGS(off) from 0.1 V against 0.2 V, an RDS(on) the sheet does not have —
  while what defines a 2SK170 (IDSS grades, |Yfs|, en, NF, Ciss, Crss) is missing.

Such a site is useful for finding substitutes and for reaching the original PDFs it links; for checking a
model it is not. Two entries are a small sample — ten to twenty would give a rate — but no rate would
supply the missing conditions.

## Reading data sheets reliably

### What the corpus looks like

Most data sheets are born digital: onsemi's, ST's, ROHM's, Fairchild's, NXP's and Burr-Brown's have text
on more than 99 % of their pages, so OCR adds nothing there and can only add digit errors. Scans are a
minority — old Toshiba sheets (35 % of pages without text), the archive.org databooks, magazine pages.
The hard part is not the characters but **the structure**: which number is the minimum, of which part,
under which conditions. Plain text loses the table. PyMuPDF's `find_tables()` rebuilds ruled tables
exactly (Toshiba's 2SK170), stacks the values of several parts in one cell (onsemi's 2N5457/2N5458), and
finds nothing in a table without rules (Infineon's IRF540N).

### The recipe

Measured on a reference set of 20 sheets (249 rows, 323 values; results in
[docker/datasheets/README.md](../docker/datasheets/README.md)):

1. **Show the model the page image, then ask for a second look.** Qwen3.8-27B (Q4_K_M, with its vision
   projector, on one RTX 4090 through llama.cpp) reads the rendered page at 150 dpi. The second turn asks
   only for the rows the first answer left out: omissions are silent, and this lifted recall from 97.6 %
   to 100 %. Result: 99.4 % of values right, 0.6 % wrong, 34 s per page (mean) with two pages in flight —
   some 200 table pages an hour.
2. **Use the text layer as a witness, never as an input.** Every number returned is looked up in the
   page's own text layer; one that is not there was invented or misread. Of 1,594 numbers returned, none
   was missing from its page. Given the text layer *as input*, the model copies its faults: a µ drawn
   from a symbol font is lost from onsemi's text layer, and "IC = 100 µAdc" came back as a noise test at
   100 A. Text-only reading was the worst method (5 % of values wrong; columns crossed in multi-part
   tables).
3. **Check what the page check cannot.** A right number in the wrong place passes the text-layer check.
   The observed case is subscripts — "VDG = 10 V" read as "VDS = 10 V" — so the condition quantities a
   symbol may have are few and can be listed (Crss: VDS or VDG; IG: VDG). Conditions are also checked for
   plausibility against the part (an IC of 100 A on a TO-92), and min ≤ typ ≤ max.
4. **Normalise deterministically:** symbols (hFE, VCE(sat), IDSS, VGS(off), |Yfs|…), units (`mAdc`,
   `µmhos`), conditions as structured data (`IC = 150 mAdc, VCE = 10 Vdc`), and the sheet's sign
   convention (PNP and P-channel sheets print negative values; some print magnitudes).
5. **Keep provenance per value:** URL and sha256 of the PDF, page, and the literal text. What can be
   published is the value with its link, never the document.
6. **Measure against a reference set, and grow it.** `docker/datasheets/golden.yaml` was read off the page
   images by Claude and checked without a person, against readers that fail differently: all 323 values
   and 604 condition numbers are on their pages; Qwen's four readings agree exactly on 213 rows and the
   other disagreements resolve in the reference's favour on the page image; signs agree; 300-dpi crops
   settled the condition names. No correction came out of it. A reader re-checking itself proves little,
   and a misreading every reader shares is still possible: a person's spot check is still due.
7. **Send what fails a check, plus a sample of what passes, to a person.**
8. **For scanned pages, read twice, independently** — OCR and the vision model — and send the
   disagreements to a person, since there is no text layer to be the witness.

**Runs are not bit-repeatable** with two requests in flight: llama.cpp batches them, and the same page can
come back slightly different even at temperature 0. One request at a time (`-np 1`) should be, at half the
throughput; not yet tried.

### Several sheets of one part (an idea, not yet tried)

Many parts have more than one data sheet: of the 7,790 parts the data-sheet sources name on a first page
or in a file name, 604 are named by two or more makers' sources and 86 by three or more (most often
Fairchild and onsemi: 265 parts; onsemi and ST: 122); 1,835 have two or more documents of any kind,
revisions and copies included. Of the reference set's 20 parts, 12 have sheets from other makers.

That redundancy can **find** reading errors; it cannot **correct** them by vote, because different makers'
sheets legitimately differ — the 2N2222A's VCEO is 40 V in Philips', Central's and onsemi's plastic
(P2N2222A) sheets, and 50 V in onsemi's metal-can sheet and ST's.
Each maker's sheet stays the source for its own figures. It helps at three strengths:

- **Copies of one document** — Fairchild's sheets reissued by onsemi, earlier revisions, archived copies:
  the tables should be identical, so any difference is a misreading or a real revision, and either way
  worth a look.
- **Registered parts** — JEDEC's 2N and 1N numbers, Pro Electron's BC and BD: every maker prints the
  registration's rows at the registration's conditions, mostly with its limits. Rows aligned by symbol
  and conditions expose what the text-layer check cannot: a subscript (VDG read as VDS where three other
  sheets say VDG), a lost µ (a test at 100 A where the others say 100 µA), a flipped sign, a row one
  reading left out.
- **One maker's part** (2SK170: Toshiba only) — no redundancy.

A reading that disagrees with the other sheets goes back to the model with a 300-dpi crop of that row and
a narrow question; if it still disagrees, the sheet really does, and it is kept as that maker's figure, or
sent to a person. Never copy a value from one sheet into another. The same alignment gives two more
things: the envelope of a part across makers, to judge a model whose maker is unknown, and each maker's
own sheet, to judge that maker's model. The experiment is cheap — read the other makers' sheets of the
12 reference parts and count what the cross-sheet check catches; the 2N3904's lost µ is one error it
should catch (Fairchild's and ROHM's sheets are in the store).

### From a sheet to a verdict

The point of the exercise: the rows the model read, with no hand-read reference involved, gave the same
verdict on each of the 94 models as the reference rows did — **909 of 909 row checks** (image with text:
927 of 927). What the model's reading lost was checks, not verdicts: 7 of 143 rows could not be paired
(omissions before the second look, the VDG read as VDS, a noise figure whose shared conditions it
dropped). A data sheet in, a verdict per model out, is within reach.

## Curves

The graphs in a data sheet — hFE against IC at three temperatures, capacitance against voltage, transfer
curves, noise against frequency — say more about a model than the table does, and they are where a
model's author fitted it. **The goal is not to digitise them.** It is, per graph: a crop of the graph,
and what to simulate to draw the same graph — so that a person compares the two by eye.

What is known so far (2026-09-28; nothing of it built yet):

- **Finding the graphs.** Asked for bounding boxes in pixels, Qwen3.8 misplaced them (240 px short on the
  right at 150 dpi). Asked in coordinates normalised to 0–1000 — the convention Qwen3-VL uses — it
  found onsemi's 2N2222A Figure 3 at [115, 850, 1128, 1238] px, against [124, 853, 1138, 1236] from the text layer's own tick labels and caption: within 10 px; it boxed the page's two circuit
  figures as well. A margin of a few percent and a render of the box from the PDF at 300 dpi gives a
  sharp crop. On a born-digital sheet the caption and tick labels are text and the curves are vector
  paths, so exact boxes — and, if ever needed, exact axis calibration (0.7 px rms on that figure) — can
  come from the PDF itself; the vision model is what works on scans too.
- **Reading the graph.** Given the crop, the model read everything printed correctly: both axes
  (quantity, unit, logarithmic, 0.1 mA to 1 A; hFE 10 to 1,000), all six series (TJ = −55, 25, 125 °C,
  each at VCE = 1 V solid and 10 V dashed), the caption. About 16 s per graph.
- **Choosing the circuit is not the model's job.** The same answer proposed a circuit with a voltage source
  and a current source on the same collector, and warned that SPICE sets ambient rather than junction
  temperature — wrong for a card without a thermal network, where `.temp` *is* the junction temperature.
  So the model reads, and our code decides: a table from (y quantity, x quantity) to a bench we have
  written and tested — hFE against IC → the bipolar bench's base-current sweep at fixed VCE, stepped over
  `.temp`; VCE(sat) against IC → the forced-β sweep; capacitance against reverse voltage → the AC
  capacitance measurement stepped over bias; ID against VGS; en against frequency — with the graph's
  series as the steps and its axes as the plot's.
- **What a person gets, per graph:** the crop, the recipe (axes, scales, series, conditions, the bench,
  the netlist), and the simulated graph drawn on the same axes and scales, side by side.

## Next

In rough order of value:

1. A person spot-checks `golden.yaml` — triangulated, not yet looked at by a human.
2. The curve pipeline above: locate, crop, read, map to a bench, draw; start with the 20 reference sheets.
3. Benches for diodes and MOSFETs in `spec.py` (VF, IR, CT, trr; VGS(th), RDS(on), Ciss/Coss/Crss, Qg) —
   the exploration has the circuits — then JFETs near cut-off, noise and temperature on many models.
4. The subscript check and the plausibility checks of the recipe, as code; and the cross-sheet check
   (above) measured on the reference parts' other sheets.
5. Grow the reference set to 50–100 sheets, older and scanned ones included; try other readers on it
   (a smaller Qwen for speed, Docling or MinerU for layout) and `-np 1` for repeatable runs.
6. Publish per model which simulators run it and whether they agree; try the encrypted models.
7. Port to `src/parts_index/datasheets/` (extraction) and `src/parts_index/bench/` (checks) once the recipe
   settles, with ledgers, so no page is read and no model simulated twice.

**Where things are.** Public: `docker/sim/`, `docker/vlm/`, `docker/datasheets/`, and the `sim-*`,
`vlm-*` and `sheets-*` targets in the `Makefile`. Private, never committed: the vendor store and every
run in `private_material/simulators/`; pages, extraction runs and cross-checks in
`private_material/datasheet_lab/`; the model weights outside the repository.
