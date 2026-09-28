# docker/datasheets — reading data-sheet tables with a vision-language model, and holding SPICE models against them

An experiment, and the procedure to repeat and extend it. The question: can a model running on our own
GPU turn a manufacturer's data sheet into rows we can trust — symbol, test conditions, min/typ/max, unit —
well enough to check every SPICE model of a part against that part's sheet automatically?

The rule it works under is the project's: **the data sheet is the source; a model only arranges it.**
Every number the model returns is looked up in the page's own text layer; a number that is not there was
invented or misread, whatever else is true.

- [The pipeline](#the-pipeline)
- [Running it](#running-it)
- [The reference set](#the-reference-set)
- [Results: extraction](#results-extraction)
- [Results: SPICE models against their sheets](#results-spice-models-against-their-sheets)
- [What we learned](#what-we-learned)
- [Next](#next)

## The pipeline

```
 PDF ──render 150 dpi──► page PNG ─┐
  │                                ├─► Qwen3.8-27B (docker/vlm, lola GPU 1) ─► rows as JSON
  └──text layer + find_tables ─────┘                                              │
                                                                                  ▼
  golden.yaml (hand-read reference) ─────► evaluate.py: found? right column? right value? on the page?
                                                                                  │
  model index ─► every distinct card of the part ─► docker/sim/bench/spec.py (QSPICE, ngspice)
                                                     simulated at each row's own test conditions
                                                                                  ▼
                                               crosscheck.py: inside / below / above the sheet's limits
```

- `render.py` — the pages of the reference set, as PNG at 150 dpi.
- `extract.py` — one prompt, three ways of showing the page: `text` (the PDF's text layer plus the tables
  PyMuPDF's `find_tables()` rebuilds from the drawing, as Markdown), `image` (the rendered page), and
  `image+text` (both). `--second-look` sends a second turn asking only for the rows the first answer left
  out. Output: one JSON per page with the rows, the raw answer, tokens and seconds.
- `evaluate.py` — scores a run against `golden.yaml` (below) and checks every returned number against the
  text layer.
- `crosscheck.py` + `../sim/bench/spec.py` — for each part: every distinct stand-alone `.model` card in the
  index under the part's names (an explicit list, precision over recall), simulated at the exact conditions
  of each row the bench understands, and judged against the row's limits. The rows can come from the
  reference (`golden.yaml`) or from an extraction run (`--rows RUN`), which is the point: sheet in,
  verdict per model out.

## Running it

```sh
make vlm-image                                   # docker/vlm/README.md
make vlm-models VLM_MODELS=/path/to/models       # 17 GB, sha256-checked
make vlm-serve  VLM_MODELS=/path/to/models       # GPU 1 by default (VLM_GPU=…)
make sheets-pages
make sheets-extract METHOD=image                 # also: text, image+text; NAME=run-name
make sheets-evaluate RUNS='private_material/datasheet_lab/runs/image private_material/datasheet_lab/runs/text'
make sheets-crosscheck ENGINE=qspice             # rows from golden.yaml
make sheets-crosscheck ENGINE=qspice ROWS=private_material/datasheet_lab/runs/image   # rows from the model
make vlm-stop
```

Everything it writes — pages, runs, cross-check results — goes to `private_material/datasheet_lab/`
(`DATASHEET_LAB`), never into the repository: the pages are third-party documents. The PDFs themselves are
read from the private data-sheet store (`DATASHEET_PDFS`, with its `manifest.json` giving each file's URL).

## The reference set

`golden.yaml`: 20 data sheets chosen to be awkward in different ways — onsemi, NXP/Philips, Toshiba,
Fairchild, Vishay, Infineon, InterFET, Linear Systems; 2000 to 2026; tables with and without rules; several
parts per table (2N3903/2N3904, 2N5457/2N5458, BC546…550, 1N91x/1N4x48, 2N7000/2N7002); grades (LSK170
A–D); PNP sheets printing negative values; typos in the sheets themselves (BC550's "f = 30~15000 MHz",
2SK170's two NF rows both at 1 kHz). 22 pages, **249 rows, 323 values**, read off the page images by Claude
on 2026-09-28.

**How the reference was checked** (the same day, without a person — a reader re-checking itself proves
little, so the check is against readers that fail differently):

1. *The text layer as a mechanical witness:* all 323 values and all 604 numbers in the conditions are on
   their page. Nothing was mistyped or invented; what remains possible is a right number in the wrong
   row, column or sign.
2. *Qwen's four readings as a second, independent reader:* 213 of the 249 rows agree exactly with all
   four. Of the other 36, most are Qwen's omissions or a single dissenting run (usually text-only, which
   loses the µ of symbol fonts) with the other three agreeing with the reference; two rows had two runs
   agreeing on another reading (BC550's VBE(on) at 10 mA and its band noise figure), and the page image
   shows the reference is right (the runs had merged the 2 mA row's values, and the two NF rows).
3. *Signs:* 604 value pairs compared with sign — no disagreement.
4. *Condition names:* where two or more runs named a condition differently (2SK170 Crss, LSK170 IG —
   VDG against VDS; 1N4148's pulse condition), a 300-dpi crop of the row settled it: the reference was
   right each time.

No correction to the reference came out of it; two gaps in the evaluator did (a symbol printed with
another kind of bar, and Vishay's "VDS" for a breakdown voltage), and are fixed. What this cannot rule
out is a misreading every reader shares; a person's spot check is still worth having.

## Results: extraction

Qwen3.8-27B (Q4_K_M) on lola's GPU 1, two requests at a time, temperature 0, no thinking; 22 pages:

| | image | text | image + text | **image + second look** |
|---|---|---|---|---|
| reference rows found | 97.6 % | 94.8 % | 98.0 % | **100 %** |
| ... with all their conditions | 95.6 % | 90.8 % | 94.8 % | **98.0 %** |
| ... exactly right (every column) | 96.8 % | 89.6 % | 98.0 % | **99.2 %** |
| reference values right | 97.2 % | 89.8 % | 98.5 % | **99.4 %** |
| reference values wrong | 0.6 % | 5.0 % | 0.0 % | 0.6 % |
| values put in an empty column | 2 | 6 | 0 | 2 |
| numbers not on the page at all | **0** | **0** | **0** | **0** |
| seconds per page (median) | 26 | 28 | 24 | 34 (mean) |

Per page: 2,200–4,200 prompt tokens (a 150-dpi page is ≈ 2,000 image tokens), ≈ 1,000 generated, at
≈ 42 tokens/s per request with two in flight; 19.4 GB of GPU memory. At that pace one GPU reads ≈ 250
table pages an hour — the ≈ 9,300 data sheets already downloaded, at two table pages each, would take
about three days.

What the numbers say, and what they hide:

- **The model did not invent a single number** in 1,594 returned — every one is on the page. Its errors
  are of placement, omission and reading, not fabrication.
- **Omissions are silent.** On 2N5551's page the image run returned 8 rows and stopped; the six it left
  out (VBEsat, Cc, Ce, fT…) came back when asked a second time ("which rows are missing from your
  answer?"). The second look costs one short turn and lifted recall from 97.6 % to 100 %.
- **Subscripts are the weak point.** "VDG = 10 V" read as "VDS = 10 V" (2SK170's Crss, LSK170's IG) — the
  number is right, the quantity it applies to is not, and no check against the page catches it, because
  "10" is there. The reference catches it; nothing else does yet.
- **The text layer is a witness, not an input.** Given the text layer, the model copies its faults: in
  onsemi's 2N3904 sheet the µ of "IC = 100 µAdc" is a symbol-font glyph that the text layer drops, and the
  image+text run returned "IC = 100 Adc" — a noise-figure test at 100 A. The image alone reads it right.
  Text-only is the worst on values (5 % wrong): without the picture, columns and parts in multi-part
  tables get crossed (1N914: 3 of 8 rows).
- **Runs are not bit-repeatable.** With two requests in flight llama.cpp batches them, and the same page
  can come back slightly different: the second-look run's first pass is the same request as the image
  run's, and 3 of the 22 answers differ in some detail. Temperature 0 is not enough; `-np 1` should be,
  at half the throughput (not yet tried).

The recipe this suggests: **image + second look**, then every number checked against the text layer, then
a plausibility check of the conditions against the part (an IC of 100 A on a TO-92), and the rows that
fail any check — plus a sample of those that pass — to a person.

## Results: SPICE models against their sheets

`crosscheck.py` took, for the 15 bipolar and JFET parts of the reference, every distinct stand-alone card
in the index under the part's names (up to 12 per part: **94 models**), and simulated each at the
conditions of each row `spec.py` understands — hFE, VBE, VCE(sat), VBE(sat), fT, h_fe, Cob, Cib, NF;
IDSS, VGS(off), VGS, gfs, IGSS, Ciss, Crss, en, NF — 147 rows, of which 117 carry limits.

**With the reference rows** (QSPICE): **64 of the 94 models are inside every limit.** The usual misses are
fT (below), hFE at high current (below), VBE(on)/VBE(sat) (above) for bipolars; IDSS and VGS(off) for
JFETs. Some are not near misses but broken or mislabelled cards the check exposes on its own:

| model (source) | row | model | sheet |
|---|---|---|---|
| 2N3904, 2N3906 (groups.io collection) | NF at 100 µA, 1 kHz, 1 kΩ | 46, 44 dB | ≤ 5, ≤ 4 dB — both cards have `KF=1E-9` |
| LSK170C (Bordodynov) | IDSS | 1.8e-14 A | 10–20 mA — the card never conducts |
| LSK170C (QSPICE's own library) | IDSS | 9.1 mA | 10–20 mA for grade C |
| 2N5457 (Micro-Cap, a pedal netlist) | IDSS | 12 mA | 1–5 mA |
| J201 (Micro-Cap, two cards) | VGS(off), IDSS | −2.3…−3.9 V, 4–26 mA | −0.3…−1.5 V, 0.2–1 mA |

**QSPICE and ngspice agree** on 999 of 1,006 row verdicts. The 7 that differ all come from one card
(Bordodynov's 2SC2240, `RB=1E-06`): with the bench's behavioural base drive QSPICE settles on a wrong
operating point (hFE ≈ 1.3 million) where a plain current source gives 416 in all three simulators. `spec.py`
now reports such values as *suspect* instead of measuring them.

**With the rows the model read** (the image run, no reference involved), the same 94 models got the same
verdict on **every one of the 909 row checks** both runs made (image + text: 927 of 927). What the model's
reading lost were checks, not verdicts: 7 of the 143 distinct rows could not be paired — the 2N5551 omissions
(before the second look), the 2SK170 Crss whose VDG became VDS, and a band noise figure whose shared
conditions it dropped.

## What we learned

- A 27B vision-language model on one consumer GPU transcribes characteristics tables well enough to drive
  model checks: 99.4 % of values right with a second look, and no invented numbers. The failure modes are
  specific and checkable: omissions (ask again), subscripts (VDG/VDS — needs a check of its own), lost
  glyphs in the text layer (do not feed it the text layer).
- The check a SPICE model most needs is not "does it simulate" but "is it the part": a third of the cards
  under a part's name miss at least one of its data-sheet limits, and a few are plainly broken.
- The reference set is what makes any of this measurable. It is small (20 sheets); it is the thing to
  grow, and to have a person confirm.

## Next

1. A person spot-checks `golden.yaml` — it has been triangulated (above), not looked at by a human.
2. Grow the reference to 50–100 sheets, older and scanned ones included (Toshiba's, the archive.org
   databooks), where there is no text layer to check numbers against.
3. A subscript check: the condition quantities a row can have are few per symbol (Crss: VDS or VDG;
   IG: VDG), so a mismatch between symbol and conditions can be flagged.
4. Plausibility of conditions against the part's ratings (IC ≤ IC(max), …).
5. Benches for diodes and MOSFETs in `spec.py` (VF, IR, CT, trr; VGS(th), RDS(on), Ciss/Coss/Crss, Qg) —
   the exploration in `private_material/simulators/explore/` has the circuits.
6. Try other readers on the same reference (Qwen3-VL-8B for speed, Docling/MinerU for layout) and `-np 1`
   for repeatable runs.
7. Port to `src/parts_index/datasheets/` (extraction) and `src/parts_index/bench/` (checks) once the recipe
   settles, with ledgers, so no page is read twice.
