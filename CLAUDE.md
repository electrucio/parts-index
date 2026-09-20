# parts-index — project rules

Open database for analog-audio electronics hobbyists: a static website (no backend) that answers, per
part number, "where is it used, where are its SPICE models and datasheets, and how good are the models".

## Map

- `src/parts_index/core/` shared code: config, polite HTTP, manifests, OCR page IO, processing ledger,
  LLM client, and `parts/` (the part-number extractor, single source of truth).
- `src/parts_index/schematics/` pillar 1: crawl → download → OCR → index → link-check → export.
- `src/parts_index/models/`, `datasheets/` pillar 2: fetch, index, curate and link SPICE models and datasheets.
- `src/parts_index/bench/` pillar 3: simulate models (ngspice is the reference engine) and score them against datasheet rows.
- `components/`, `circuits/` pillar 4: original LTspice components with `.asy` symbols, and reference circuits.
- `data/` the public dataset. `web/` the site. `docs/` conventions and the maintainer runbook.
- `private_uncommitted/` local, git-ignored data root. `staging/` inside it holds the old code still to be ported.

## Hard rules

1. **Links, not copies.** Never commit third-party documents, PDFs, scans, OCR text or manufacturer model
   text. Publish URL + sha256 + metadata. Model files go in `data/models/files/<source>/` only when the
   source licence is on the allow-list, together with its LICENSE file.
2. **Forbidding redistribution does not forbid indexing.** Every model is indexed and linked to its source.
   For non-redistributable sources publish measured results, not a dump of the `.model` parameters.
3. **Never bypass** a CAPTCHA, login, paywall or click-through licence. Respect robots.txt and per-host
   delays (use `core.http`). User forums are out of scope. A blocked source is recorded as blocked, with
   the human-facing URL.
4. **Precision over recall.** A wrong link is worse than no link. When a part read is doubtful, drop it.
   Every extractor fix comes with a test case.
5. **Never reprocess what is done.** Every pipeline stage goes through `core.ledger`: an item is skipped
   when its stamp matches (input sha256, stage version). Reprocess by bumping the stage version, not by
   deleting state. New site or vendor = new registry entry, then run that source only.
6. **Nothing under `private_uncommitted/` is ever added to git**, and nothing public may depend on a local
   absolute path, a personal e-mail address or a secret. Paths come from `core.config`; credentials live
   outside the repository tree. `scripts/licence_guard.py` enforces this in the pre-commit hook and in CI.
7. **Move first, refactor later.** When porting from `private_uncommitted/staging/`, copy behaviour exactly
   and prove it with a golden test before cleaning up.
8. Everything public is in **English**.
9. Commit in small, reviewable steps. The maintainer approves each commit; do not push without being asked.

## Working here

```
git config core.hooksPath .githooks     # once per clone
python3 scripts/licence_guard.py --all  # what CI runs
uv sync && uv run pytest                # or: PYTHONPATH=src python3 -m pytest
uv run pidx status                      # what is processed and what comes next; --write refreshes STATUS.md
```

Python ≥ 3.11. The web app and the remaining `pidx` commands arrive with the corresponding commits; this file
is updated as each lands.

## Where things stand

Read [STATUS.md](STATUS.md) first: one row per source with items downloaded, OCR'd, indexed and link-checked,
and the next action. It is generated from `data/schematics/sources.yaml` (the registry) and
`data/schematics/state/<source>.csv` (one ledger row per URL). To add a site, add a registry entry with
`status: proposed`; to reprocess, bump a stage version. Never edit ledgers by hand to force a rerun.
`python -m parts_index.schematics.seed` rebuilds the ledgers from the pre-monorepo pipeline outputs (maintainer
only; used until the pipeline stages are ported and write the ledgers themselves).

## Without the private corpus you can still

add curated references for a part, report wrong links, propose sources, add model links and datasheet
rows, write components, fix the part extractor against fixtures, and work on the whole website. Crawling,
OCR, index builds, link verification, exports, paid VLM runs and LTspice/QSPICE runs happen on the
maintainer's machine.

## Estimating work

Express effort as "Claude sessions + waiting time", not person-days.
