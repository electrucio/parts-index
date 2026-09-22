# Coverage

How much of what a person will look up can this answer, and how do we know. Candidate sources are not
listed here — they go into `data/schematics/sources.yaml` with `status: proposed`, which is what that
registry is for. This file is the method.

## Two different failures, which look the same from outside

Looking up a part and getting nothing has two causes, and they need opposite work:

1. **The index read the part and threw it away.** `6V6` was in zero documents while `6V6GT` was in 484;
   `7805` was in zero while `LM7805` was in 155. Measured over 458 documents: 10,580 distinct parts
   recognised, 4,692 of them never reaching the confidence the publishing gate asks for — 19,694 of
   61,977 references discarded. This is an extractor problem and code fixes it. The census
   (`data/parts/census.csv`) is that fix.
2. **No document here contains the part.** `2SC3334`, `KSA1220`, `THF51S`, `C3M0280090D`. No code change
   finds these. Either a source that has them is added, or the answer comes from somewhere other than a
   schematic.

Telling them apart takes a second; `pidx parts explain <part>` exists so it does not take an argument.

## An answer does not have to be a schematic

Chasing part numbers off random forum schematics is unbounded — there are millions of type numbers and
no corpus will hold them all. But "no schematic uses it" is not the same as "nothing to say about it",
and this project already holds four separate things that can answer:

| what it knows | where it is | size today |
|---|---|---|
| schematics that use the part | `data/schematics/uses/` | 156,318 document-part postings |
| the list that says the part exists, and its data sheet | `data/parts/census.csv` | 11,724 valve types |
| a SPICE model and the vendor page it came from | `data/models/`, the definition index | 171,983 distinct definition names over 75 vendors |
| open-source projects that use it | `data/datasets/part_repos.csv` | 2,337 parts in 15,039 repositories |

`C3M0280090D` is the example worth keeping in mind: a SiC MOSFET that no schematic here uses, whose
model this project already holds in 122 variants. A blank answer for it is a plumbing failure, not a
coverage one. **Answer with what is held, and say which of the four it came from.**

## Measure it, do not sample it by hand

Coverage is a number, not an impression, and hand-probing a few schematics measures whatever segment
those schematics came from. The benchmark is a list of part numbers taken from real schematics in the
domains below, kept in `data/parts/benchmark.csv` with the domain each came from, and the score is the
share the index can say something useful about — split by which of the four answers served it. It is
re-run when a source lands, so every addition is measurable, the way `export.json` makes an index
change measurable.

## Domains, and how far out to go

Scope widened on 2026-09-22 from "instrument and studio" to general audio and analogue electronics.
That still needs an edge, or the benchmark has no denominator:

- **A. Audio.** Instrument amplification, effects, studio and hi-fi, valve and solid-state. The core;
  everything else is judged against it.
- **B. Analogue building blocks.** Op-amps, regulators, references, discretes, optocouplers, converters
  — the vocabulary A is written in, and the same vocabulary as the SPICE pillar.
- **C. Test and instrumentation.** Oscilloscopes, generators, meters. Classic discrete analogue design,
  well archived, and it shares B's vocabulary almost entirely.
- **D. Power.** SMPS, SiC and GaN. Where the EEVblog end of the hobby lives. It shares little vocabulary
  with A, and it is where the corpus would grow fastest for the least benefit to audio. Answer it from
  the model and census sides — which already cover it — before spending crawl and OCR on it.

## What makes a source worth adding

In the order the questions actually settle it:

1. Does every file have a public URL a person can open? No URL, no entry (rule: links, not copies).
2. Does robots.txt allow it, with no CAPTCHA, login or click-through? A blocked source is recorded as
   blocked, with its human-facing URL, because a link is still worth publishing.
3. Does it carry schematics, or only prose about them?
4. Does it bring vocabulary A and B do not already have? Measured against the benchmark, not guessed.
5. What does it cost in download and OCR hours, and does the advert filter hold on it? The filter was
   validated on magazines (97 % precision, 88 % recall on 150 labelled pages); new material of a new
   shape needs its own labelled sample before its pages are trusted.
