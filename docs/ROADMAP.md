# Roadmap

What is known to be missing or improvable, so it is not rediscovered. Sources are **not** listed here:
every source lives in `data/schematics/sources.yaml` or `data/models/sources/`, and `STATUS.md` says where
each one stands. This file is for everything that is not a source.

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
  25,764 documents. The curation reached 1,712 parts; the catalogue holds definitions for far more. The
  worst of it is the most looked-up parts in the whole index: ECC83 (908 documents, 7 sources hold a
  model), 6L6 (725, 6), BC547 (702, 3), 2N2222 (631, 7), GZ34 (420, 3). Two different causes, both
  fixable:
    - **A variant was curated and the bare number was not.** `2N2222A` has a recipe, `2N2222` does not,
      although five sources hold a definition called exactly `2N2222`. Same for `12AX7A` against
      `12AX7`, which *is* curated — so the A variant is the orphan there.
    - **The alias problem below.** ECC83 is a 12AX7 and GZ34 is a 5AR4; the index records the name
      printed on the sheet, and the curation filed the model under the other one.
- **Five parts are filed under two kinds at once**: BC109, BC177, BCY70, BCY71 and BUX48, each curated
  once as silicon and once as germanium, with different candidates in each. Under the Pro-Electron
  convention the first letter settles it — A is germanium, B is silicon — so the germanium copy is the
  wrong one in all five. `pidx web build` prints them and keeps whichever has more candidates rather
  than resolving it in silence; the curation still has to be merged. The dictionary has the same error
  in seven entries, which is what puts BC109 in the "Germanium" filter on the site.
- Some vendors publish only encrypted models, readable by one simulator and no other. They are recorded as
  `encrypted_only`; the link is still worth publishing.
- **Several parts filed as germanium are silicon.** Under the Pro-Electron naming convention the first
  letter says which: A is germanium, B is silicon. So BC114, BC148, BC153 and BC169 are silicon, as are
  MJ3001, MJ2501, MJ481 and BDY20 (the last being an equivalent of the 2N3055). This belongs in the part
  dictionary rather than in a note, so that searching for germanium stops returning them.

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
