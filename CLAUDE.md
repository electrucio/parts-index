# parts-index — project rules

Open database for analog-audio electronics hobbyists: a static website (no backend) that answers, per
part number, "where is it used, where are its SPICE models and datasheets, and how good are the models".

## Map

The migration from the two old repositories is in progress; **(todo)** marks what is planned but not here
yet, so this list can be trusted as an inventory. `pidx --help` and `pidx paths` are always current.

- `src/parts_index/core/` shared code: `config` (every location in the project — see rule 4), `http`
  (the one polite client), `ledger` (what has been processed), `pagesio` (OCR page records), `adfilter`,
  `links` (the deep link, with `web/src/links.ts` as its other half and one golden fixture over both),
  `llm` (the two ways to ask a model — paid at OpenAI, or the local server — with one cache over both),
  and `parts/` (the part-number extractor, single source of truth; `catalogue` and `schemes`, what a part
  is — its family, the organisation behind it, how it relates to others, and what the letters of its name
  say under the standard that assigned them). **(todo)** `table`.
- `src/parts_index/schematics/` pillar 1: `download` (the sources whose URLs are already listed),
  `summarise` (one line per published use, saying what that part does on that page), `export` (the
  index into `data/`) and `titles`. **(todo)** crawl → ocr → index → linkcheck.
- `src/parts_index/models/` pillar 2: fetch, ingest, index, recover, reconcile (every definition file
  joined to the download it came from, so the ledgers count what the catalogue holds), match (which definitions are
  candidates for each wanted part, from `data/models/wanted.yaml` and the other lists), found (those
  grouped into distinct models, each with every copy of it) and promote (the public recipe per part:
  the curated judgement plus every model found). **(todo)** curate — pins, symbols, fixups, bench — and
  `datasheets/`.
- `src/parts_index/datasheets/` `register`: what a manufacturer's own catalogue says about each indexed
  part — category, production status, data sheet title and revision — facts and links only.
- `src/parts_index/web/` builds the site's data from `data/` alone: `build` and `parts` (one file
  per part, already joined and grouped, because a static site has nobody to ask). **(todo)** `src/parts_index/bench/`
  pillar 3: simulate models and score them against datasheet rows. QSPICE is the default engine, ngspice
  the open cross-check anyone can repeat, LTspice the compatibility check; the pinned images and a working
  prototype of the bench are in `docker/sim/` (see its README). `docker/vlm/` serves a vision-language model
  on one GPU, and `docker/datasheets/` is the experiment that reads data-sheet tables with it and holds
  every model of a part against its sheet (reference set, results and procedure in its README).
- `components/`, `circuits/` pillar 4: original LTspice components with `.asy` symbols, and reference
  circuits. The `.net` files reference model files that only exist in the private data root, so they do
  not run from a clean clone yet.
- `data/` the public dataset: registries, ledgers, the part dictionary and the parts worth having,
  the exported schematic index
  (documents, pages, uses, the line each use gets, and the parts those lines cast doubt on), the model
  recipes with their verification results, the LTspice symbols
  drawn for them, what was distilled from the research datasets, and the catalogue of what a part is
  (`data/parts/`: families, naming schemes, organisations, relations and the references they cite). **(todo)** the licence notes.
- `web/` the site (Vite + TypeScript + Preact): the parts browser and the coverage record. Its look
  is the previous project's site, carried over. `docs/` the roadmap, and `simulation-and-datasheets.md`:
  how models are simulated and data sheets read — decisions, findings, method. **(todo)** the maintainer runbook.
- `src/parts_index/datasets/` what is kept from the research datasets: `repos` reads how much
  attention each open-source project has, through the `gh` command's own login.
- `src/parts_index/migrate/` one-off steps carrying the old pipeline's state across; deleted when the
  last stage is ported.
- `private_material/` local, git-ignored, in transit: `ocr/` the page records with their map, `census/`
  the index pages the part census was read from, `downloads/` documents waiting to be read, and
  `staging/` the old code still to be ported. Port from there, never edit the old repositories.
  `private_web_spice_models/` is the other private tree, and it is permanent: the vendor model text and
  symbols the site serves in private mode. `core.config` names both and nothing else may.

## Hard rules

1. **Links, not copies.** Never commit third-party documents, PDFs, scans, OCR text or manufacturer model
   text. Publish URL + sha256 + metadata. Model files go in `data/models/files/<source>/` only when the
   source licence is on the allow-list, together with its LICENSE file. **One exception, the
   maintainer's decision (2026-09-29): a data sheet may be quoted by small crops** — one table row or one
   graph — shown beside our transcription or simulation of it, with maker, document, revision, page and a
   link to the manufacturer's PDF; never whole pages or documents. Crops never enter git: they are made on
   the maintainer's machine and published as a release asset the site's build downloads, so deleting the
   asset withdraws them.
2. **Forbidding redistribution does not forbid indexing.** Every model is indexed and linked to its source.
   For non-redistributable sources publish measured results, not a dump of the `.model` parameters.
3. **Never bypass** a CAPTCHA, login, paywall, click-through licence or bot challenge. Respect
   robots.txt and per-host delays (use `core.http`). A blocked source is recorded as blocked, with the
   human-facing URL, because a link a person can follow is still worth publishing.
   **Tell a refusal of consent from a complaint about pace.** A site whose robots.txt permits this and
   whose CDN then answers 429 has not withdrawn permission — it has said we asked too fast, and a site
   that would allow this at some pace can be scraped legitimately. So that is a reason to come back
   slower, later, or from the maintainer's own browser at human pace; it is never a reason to give up,
   and never a reason to defeat the check. Patience, a longer delay, fewer wasted requests and asking
   the owner are all means. Disguise is not: not a borrowed user-agent, not another address, not
   solving the challenge. Such a source is `paused` with what was measured and a pace to try next;
   only a refusal that holds at any pace is `blocked`. **On a forum, index the attachments and never
   the conversation**, and among attachments only schematics or projects worked out to some degree — a
   thread page is read to find what it links to and is never itself a document. A SPICE model posted on
   one is still a model.
4. **Precision over recall.** A wrong link is worse than no link. When a part read is doubtful, drop it.
   Every extractor fix comes with a test case.
5. **Never reprocess what is done.** Every pipeline stage goes through `core.ledger`: an item is skipped
   when its stamp matches (input sha256, stage version). Reprocess by bumping the stage version, not by
   deleting state. New site or vendor = new registry entry, then run that source only.
6. **Nothing under `private_material/` or `private_web_spice_models/` is ever added to git**, and nothing
   public may depend on a local absolute path, a personal e-mail address or a secret — including inside a
   published URL, where ten exported links hid one for months. **Every location in the project is named in
   `core.config` and nowhere else** — no other module joins a path (`tests/core/test_config.py` fails if one
   does, and `pidx paths` prints the map). Credentials live outside the repository tree.
   `scripts/licence_guard.py` enforces the rest in the pre-commit hook and in CI.
7. **Move first, refactor later.** When porting from `private_material/staging/`, copy behaviour exactly
   and prove it with a golden test before cleaning up.
8. Everything public is in **English**.
9. Commit in small, reviewable steps. The maintainer approves each commit; do not push without being asked.

## Working here

**`make` is the front door**; run it with no target to list every step.

```
make setup      # install dependencies and enable the pre-commit guard, once per clone
make check      # guard + lint + tests, Python and web — what CI runs
make status     # what has been processed and what comes next, per source
make paths      # where everything is, and which side of the public/private line
make backup     # pack the private trees into one archive to carry off this machine
```

Each target is a thin wrapper around `pidx`, the command this package installs (`src/parts_index/cli.py`).
Use either; `make` exists so the steps are listed in one place. Python ≥ 3.11. `make` and `pidx --help`
list what exists today; the map above marks the rest **(todo)**. When you add a `pidx` command, add its
`make` target in the same commit.

## Where things stand

Read [STATUS.md](STATUS.md) first: one row per source with items downloaded, OCR'd, indexed and link-checked,
and the next action. It is generated from `data/schematics/sources.yaml` (the registry) and
`data/schematics/state/<source>.csv` (one ledger row per URL). To add a site, add a registry entry with
`status: proposed`; to reprocess, bump a stage version. Never edit ledgers by hand to force a rerun.
`make migrate` carries the old pipeline's state across: it rebuilds the ledgers and writes the OCR records
that pipeline never wrote to disk. It is one-off — `src/parts_index/migrate/` is deleted when the last
stage is ported.

## Without the private corpus you can still

add curated references for a part, report wrong links, propose sources, add model links and datasheet
rows, write components, fix the part extractor against fixtures, and work on the whole website. Crawling,
OCR, index builds, link verification, exports, paid VLM runs and LTspice/QSPICE runs happen on the
maintainer's machine.

## Estimating work

Express effort as "Claude sessions + waiting time", not person-days.
