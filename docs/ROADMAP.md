# Roadmap

What is known to be missing or improvable, so it is not rediscovered. Sources are **not** listed here:
every source lives in `data/schematics/sources.yaml` or `data/models/sources/`, and `STATUS.md` says where
each one stands. This file is for everything that is not a source.

## The missing middle of the pipeline

`download` and `crawl` are ported and `export` is ported; **`ocr` and `index` are not**, and they are the
two stages between them. Everything fetched since the migration is therefore sitting unread: audiocircuit
750 downloaded and 0 read, fendersupport 281 and 0, tagboard 2,562 and 0, and about 10,600 items over all
sources. Every download that runs makes that larger, and no extractor improvement — the census included —
can reach the site until the index is rebuilt, because `export` reads the database and nothing fills it.

Two decisions for the port, both already implied by what is here:

- **The OCR stage is driven by the ledger, not by a run being "finished".** `Ledger.pending("ocr")` already
  answers "what is downloaded and unread"; the command takes that and can be run again and again while a
  download is still going. Then the order of the two stops being something a person has to sequence.
- **It ships as a container.** The old pipeline ran OCR in containers built by hand on one machine. A
  Dockerfile with CUDA and PaddleOCR is what makes the heavy stage reproducible somewhere else, which is
  the difference between moving this work to another machine and rebuilding it there.

The five OCR scripts in `private_material/staging/` (`ocr.py`, `ocr_raw.py`, `ocr_turned.py`, `ocr_scans.py`,
`ocrio.py`, 408 lines between them) are one stage written five times; `build_index.py` is 456 lines and
already incremental on an extractor version, which is the same idea as the ledger's stage version. Port
behaviour first and prove it with a golden test, as rule 7 says: the OCR of a page that was read before
must come out the same.

## Quality of the schematic index

- **The same schematic appears several times.** The Bassman 5F6-A sheet is published by three different
  archives and is returned three times. Group results by the `sha256` already recorded in
  `data/schematics/state/<source>.csv`, and for copies that differ in bytes, by the similarity of the
  text read from them. Show one result with "also at …".
- **The advert filter decides per page, and it should decide per zone.** It currently drops a whole page
  when it looks like a mail-order price list, which loses good mentions on mixed pages — a part discussed
  in an article that happens to share the page with a distributor's advert. With the OCR boxes it can drop
  only the rows that carry a price. Measured on 150 hand-labelled pages: 97 % precision, 88 % recall.
  Keep the per-source counts in `export.json` so any change is measurable against today's baseline.
- **Poor document titles.** 659 documents from one archive are called "From Jeremiah" and 323 from another
  "Builders' gallery". For factory sheets the file name is almost always better than the page title.
- **Aliases belong to the part catalogue, not to the index.** The index records the name printed on the
  sheet, so GZ34 and 5AR4 are different entries; the equivalence lives with the parts and the search must
  apply it. Same for 12AX7 / ECC83.
- **Documents cut short.** Five documents over 600 pages are still truncated by the page cap. None of them
  carries audio schematics, but the cap should be raised or made per-source.

## The part extractor, seen from the design readers

Found on 2026-09-26 while reviewing `schematics/cad.py` against every name the dictionary and the census
know and against the 359 Toragi designs. The reader's side is fixed; what follows is the extractor's side,
left as it is because those files were mid-change in another session, and because each one deserves its
own test (rule 4). None is urgent; all are worth a look before the Japanese material is indexed in earnest.

- **The 1S series of JIS diodes is invisible.** 1S1588, 1S2076A, 1SS355: the census knows them, no family
  claims them, and the "declared in a design" path takes only names that start with a letter. Seventeen
  1S1588 out of the Toragi netlists reach the extractor as declared values and come out as nothing. A
  closed family `1S(S)?\d{3,4}[A-Z]?` beside the JIS transistor one would settle it, with 1S1588 as the
  test — and settle the OCR path too, where the same diodes appear in every Japanese schematic.
- **A grade suffix is captured as a part.** From `2SC1815GR` on a page the JIS pattern takes one letter and
  publishes `2SC1815G`, which is not a part; the ranks are GR, Y, O, BL. The design readers fold the grade
  before the extractor sees it (`cad.canonical`), so the CAD path is right and the OCR path is not. The
  fix belongs in `base_part` or the JIS family pattern: a rank of one or two letters after the digits,
  folded when what is left is known.
- **A net label passes for a part.** `IN3`, `OUT1`: designators by shape, taken as parts by the bare
  reader when the page has enough of them around. Three of them came off one Toragi netlist. Labels of
  the form IN/OUT plus a digit are never parts and could be dropped by name.
- **The census lists ratings as parts.** `100N`, `4U7`, `10`, `1000H` are census entries, read off lists
  that had to be complete. `cad.recognised` refuses a census name shaped like a rating unless it is also
  shaped like a valve (6V6 is both); the extractor's own census gate may want the same rule, or the census
  a cleaning pass, since a `100N` in OCR text is a capacitor a thousand times before it is a part once.
- **PSpice model names are in the census as parts.** `Q2N3904`, `QBFG425W`, `QC1815A` came in with the
  SPICE-definition lists, letter and all, so `norm("Q2N3904")` is "known". The readers strip the letter
  and prefer the reading that says most (`cad.model_name`); a page of OCR'd netlist would still publish
  the model name. Either the census marks these as models, or the extractor learns the same stripping.

What the readers now guarantee, and the test that holds them to it: nothing the dictionary or the census
vouches for is dropped by a shape rule (`test_nothing_the_dictionary_or_the_census_knows_is_dropped_by_a_filter`
runs the whole vocabulary). The rules that once dropped 1N4148 as a nanofarad, 2SC1815 as an SC-18 case
and ISO7721 as an SO-77 are the reason it exists; a new filter that swallows a real part fails it.

## What a part is

The catalogue under `data/parts/` (families, naming schemes, organisations, relations, references) and the
data-sheet register under `data/datasheets/` began on 2026-09-27. Everything in them cites a source; what
follows is what they do not cover yet, roughly in order of what a reader would notice.

- **The drafts need a reading.** The 69 rows of `part_families.csv` and the 30 of `relations.csv` are
  marked `draft` and the site says "not yet reviewed" beside each. Reviewing one is opening its reference
  and checking the row says what it says; then `status: reviewed`.
- **Manufacturer prefixes.** LM, NE, CA, MC, TL, NJM, uPC: the part page says nothing about them yet,
  because none of the sources read states which company registered which prefix, and a prefix is a habit,
  not a registration (TI sells National's LM parts, and several companies made NE5532s). The evidence is
  already in the repository: the 508 recipes with a datasheet say who published each part's sheet, and
  the register adds TI's. A prefix page could say "the sheets linked here for LM parts come from National
  Semiconductor and, since 2011, from TI" and be true.
- **Integrated-circuit numbering.** Pro Electron numbered ICs on its own plan (TDA, TBA, SAA); JEDEC's
  7400 and 4000 series have their own logic. Neither is read yet.
- **The register's other catalogues.** Renesas (840 indexed parts; its robots.txt allows this by name),
  then onsemi, Nexperia and ST, each needing its own reader. Only facts leave a page.
- **Pictures of the letters.** A drawing of a TO-92 with its pins, as inventable.eu does for the BC548, is
  a thing a family page could carry — drawn here, never copied.
- **Longer family pages.** The twelve to twenty families a reader of audio circuits meets most (dual
  triode, JFET, OTA, BBD, VCA, op-amp input stages) deserve a page of their own words, with a schematic
  from this index as the example.

## Links

- **Nothing re-checks links.** Some will rot, and at least one archive.org item is a private upload that
  could be withdrawn. A polite periodic HEAD should set `link_ok` and the date, and the site must say
  "link unavailable, last seen on …" rather than sending the reader to a 404. A dead link is hidden, never
  replaced by a local copy.
- **Deep links disagree between viewers.** `#page=N&zoom=…` is honoured by Chrome and Firefox, but they
  measure the vertical position from opposite edges, so one URL cannot satisfy both. The page number and
  the position map have to answer on their own; the zoom is a bonus. Safari is untested.

## SPICE models

- **Every source is `licence: unreviewed`, so no model file can be offered for download.** Reviewing the
  licence of each source is human work, and it is what stands between the current "here is where to get it"
  and "here it is". Start with the sources already believed to be permissive.
- **970 parts have never been looked up** at a vendor that might have a model, and 840 are recorded as not
  available. Both counts are in `STATUS.md`.
- **The ledger attributes a definition to the file it was downloaded as, so unpacked models are counted
  against their archive — and when the archive is not kept, against nothing.** `STATUS.md` totals 626,794
  definitions while the catalogue holds 847,884; the 221,090 difference is files with no ledger row of
  their own: members unpacked from an archive, and models transcribed out of a datasheet. It shows up as
  sources that appear to hold almost nothing — toshiba reports 5 and holds 9,878. `stamp_ledgers` should
  credit an unpacked member to the archive's row, the same join `recovery_targets` already makes.
- **Nothing routinely checks that the downloaded tree still holds what was downloaded.** `models index
  --missing` compares the tree against `index.jsonl`, which is rebuilt from that same tree, so a file lost
  between two runs disappears from both and the check reports nothing. The durable record is elsewhere and
  is already written: the manifests hold a sha256 per file and the ledgers a committed `n_defs` per URL.
  A `pidx models verify` reading those two would have caught the 59,407 definitions pruned by mistake on
  the day it happened, instead of after the archives had been deleted. It found one stale record when run
  by hand, so it is worth having as a step with its own `make` target.
- **2,029 parts have a model in the catalogue and no published recipe**, and between them they appear in
  25,764 documents. The curation reached 1,712 parts; the catalogue holds definitions for far more.
  Since 2026-09-27 `pidx models match` + `found` + `promote` publish every model the catalogue holds for
  each *wanted* part, judged or not — 1,954 recipes — so a wanted part never waits for the curation
  again. What is left is the parts the site shows and no list wants: the most looked-up in the whole
  index are among them — ECC83 (908 documents, 7 sources hold a model), 6L6 (725, 6), BC547 (702, 3),
  2N2222 (631, 7), GZ34 (420, 3). The next step is to match the site's own part names too, exact names
  only. Two different causes, both fixable:
    - **A variant was curated and the bare number was not.** `2N2222A` has a recipe, `2N2222` does not,
      although five sources hold a definition called exactly `2N2222`. Same for `12AX7A` against
      `12AX7`, which *is* curated — so the A variant is the orphan there.
    - **The alias problem below.** ECC83 is a 12AX7 and GZ34 is a 5AR4; the index records the name
      printed on the sheet, and the curation filed the model under the other one.
- **Five parts are filed under two kinds at once**: BC109, BC177, BCY70, BCY71 and BUX48, each curated
  once as silicon and once as germanium, with different candidates in each. Under the Pro-Electron
  convention the first letter settles it — A is germanium, B is silicon — so the germanium copy is the
  wrong one in all five. `pidx web build` prints them and keeps whichever has more candidates rather
  than resolving it in silence; the curation still has to be merged. The dictionary had the same error
  in six entries and is corrected; `test_no_transistor_filed_as_germanium_is_named_silicon` keeps it so.
  BX120, also filed as germanium, is not a semiconductor at all on the pages that print it (a transformer,
  a fragment of a model number) and is left for the dictionary's next review.
- Some vendors publish only encrypted models, readable by one simulator and no other. They are recorded as
  `encrypted_only`; the link is still worth publishing.

## Sources deliberately not pursued

Kept here so the decision is not revisited by accident:

- **User forums** as schematic sources: noise, and how the index would be built is arguable. Captures
  already made are kept but never indexed. A SPICE model posted on a forum is still a model, and those
  sources are registered normally.
- **Digital and microcontroller sites** (tutorial networks, maker blogs, big educational archives): out of
  the analog-audio focus, and large enough to dominate the index. Several are named in the project's
  history; none is registered.
- **Anything behind a CAPTCHA, a login or a click-through licence.** One large factory archive is excluded
  for exactly this reason: its catalogue is indexed by others, but every file needs a CAPTCHA.
- **Very large service-manual archives** that would need tens of gigabytes downloaded before anything can
  be linked. Worth revisiting once the link-only path is proven.
- Magazines outside the audio and general-electronics selection: hi-fi review, music industry, broadcast,
  DX listening, television trade and computing titles.
