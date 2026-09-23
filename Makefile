# Every step of the project, in one place. `make` on its own lists them.
#
# Most targets are thin wrappers around `pidx`, the project's command (installed by `make setup`).
# Targets marked "maintainer" need the private data root; everything else works from a clean clone.

UV := uv
RUN := $(UV) run --quiet

# Where `make serve` puts the site. Every interface, so it can be opened from another machine.
WEB_HOST ?= 0.0.0.0
WEB_PORT ?= 8026

.DEFAULT_GOAL := help
.PHONY: help setup test test-web lint guard check status status-write paths models-index models-missing models-recover models-verify models-promote datasets-repos schematics-summarise schematics-summarise-bg schematics-preview schematics-export backup migrate-datasets migrate-wanted migrate clean web web-data web-deps serve

help:  ## show this list
	@echo "parts-index — make <target>"
	@echo
	@grep -hE '^[a-z][a-zA-Z0-9_-]*:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Targets marked (maintainer) need the private data root; the rest work from a clean clone."

# --- setting up ---------------------------------------------------------------------------------
setup:  ## install dependencies and enable the pre-commit guard
	$(UV) sync
	git config core.hooksPath .githooks
	@echo "ready — try 'make status'"

# --- checking your work -------------------------------------------------------------------------
test:  ## run the test suite
	$(RUN) pytest -q

test-web:  ## run the website's tests (the other half of the link builder)
	@test -d web/node_modules || { echo "skipping: run 'make web-deps' first"; exit 0; }
	cd web && npx vitest run

lint:  ## check code style
	$(RUN) ruff check src scripts tests

guard:  ## refuse anything that must not be published (what CI runs)
	python3 scripts/licence_guard.py --all

check: guard lint test test-web  ## guard + lint + tests, in that order

# --- looking at the project ---------------------------------------------------------------------
status:  ## what has been processed and what comes next, per source
	$(RUN) pidx status

status-write:  ## regenerate STATUS.md from the ledgers
	$(RUN) pidx status --write

paths:  ## where everything is, and which side of the public/private line
	$(RUN) pidx paths

# --- SPICE models ------------------------------------------------------------------------------
models-index:  ## (maintainer) find every definition in the model sources, and stamp the ledgers
	$(RUN) pidx models index --stats

models-missing:  ## (maintainer) what the catalogue recorded that the sources no longer hold
	$(RUN) pidx models index --missing

models-recover:  ## (maintainer) fetch those files again, checking each against the checksum we had
	$(RUN) pidx models recover

models-verify:  ## (maintainer) check the tree still holds every model file, byte for byte
	$(RUN) pidx models verify

models-promote:  ## (maintainer) write the public recipe for every curated part into data/models/parts/
	$(RUN) pidx models promote

datasets-repos:  ## (maintainer) read stars, forks and watchers for every open-source project (needs `gh`)
	$(RUN) pidx datasets repos

schematics-download:  ## (maintainer) fetch sources whose URLs are already listed; SOURCE='a b' [LIMIT=n]
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-download SOURCE=audiocircuit"; exit 1; }
	$(RUN) pidx schematics download $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT),)

schematics-download-bg:  ## (maintainer) the same, detached under a lock with a log — for the long ones
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-download-bg SOURCE='tagboard dirtbox'"; exit 1; }
	$(RUN) pidx schematics download $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT),) --detach

schematics-list:  ## (maintainer) gather a source's file URLs again from the site's listing; SOURCE='a b' [DRY=1]
	uv run pidx schematics list $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(DRY),--dry)

explain:  ## why a part gives nothing — the extractor, or no document that has it; PART='6V6 TTC004B'
	uv run pidx parts explain $(PART)

parts-benchmark:  ## score today's extractor against the labelled pages; BUILD=1 labels more (spends money)
	uv run pidx parts benchmark $(if $(BUILD),--build) $(if $(PER_SOURCE),--per-source $(PER_SOURCE)) $(if $(BUDGET),--budget $(BUDGET))

parts-judge:  ## decide which census names mean a component here; COLLECT=1 then ASK=1 (ASK spends money)
	uv run pidx parts judge $(if $(COLLECT),--collect) $(if $(ASK),--ask) $(if $(BUDGET),--budget $(BUDGET))

parts-census:  ## (maintainer) read the lists that say which part numbers exist; [SOURCE='a b'] [READ=1]
	uv run pidx parts census $(foreach s,$(SOURCE),--source $(s)) $(if $(READ),--read)

schematics-crawl:  ## (maintainer) walk a site and take what it shows; SOURCE='a b' [MAX=n]
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-crawl SOURCE=tubecad"; exit 1; }
	$(RUN) pidx schematics crawl $(foreach s,$(SOURCE),--source $(s)) $(if $(MAX),--max $(MAX),)

schematics-crawl-bg:  ## (maintainer) the same, detached under a lock with a log; AFTER=<job> to queue it
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-crawl-bg SOURCE=tubecad"; exit 1; }
	$(RUN) pidx schematics crawl $(foreach s,$(SOURCE),--source $(s)) $(if $(MAX),--max $(MAX),) \
	  $(if $(AFTER),--after $(AFTER),) --detach

schematics-ocr:  ## (maintainer) read what is downloaded and not read yet; SOURCE='a b' [GPU=0] [SHARD=0/2] [DRY=1]
	uv run pidx schematics ocr $(foreach s,$(SOURCE),--source $(s)) $(if $(GPU),--gpu $(GPU)) $(if $(SHARD),--shard $(SHARD)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(DRY),--dry)

schematics-ocr-docker:  ## (maintainer) the same inside the CUDA image, one shard per GPU; SOURCE='a b' GPU=0 SHARD=0/2
	docker run --rm --gpus '"device=$(GPU)"' -v "$(PWD)":/repo parts-index-ocr \
	  schematics ocr $(foreach s,$(SOURCE),--source $(s)) --gpu 0 $(if $(SHARD),--shard $(SHARD))

schematics-verify:  ## (maintainer) find documents lost before anything read them; REPAIR=1 fetches them back
	$(RUN) pidx schematics verify $(if $(SOURCE),$(foreach s,$(SOURCE),--source $(s)),) $(if $(REPAIR),--repair,)

schematics-reindex:  ## (maintainer) read the corpus again with the current extractor; [SOURCE='a b'] [WORKERS=n]
	uv run pidx schematics reindex $(foreach s,$(SOURCE),--source $(s)) $(if $(WORKERS),--workers $(WORKERS)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(DRY),--dry)

schematics-summarise:  ## (maintainer) one line per published use, from the model next door; SOURCE='a b' [LIMIT=n] [DRY=1]
	$(RUN) pidx schematics summarise $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT),) $(if $(DRY),--dry)

schematics-summarise-bg:  ## (maintainer) the same, detached under a lock with a log - this one runs for days
	$(RUN) pidx schematics summarise $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT),) --detach

schematics-preview:  ## (maintainer) what the summarise pass has written so far, with its links
	$(RUN) pidx schematics summarise --preview

schematics-export:  ## (maintainer) write the schematic index into data/, where the site is built from
	$(RUN) pidx schematics export

backup:  ## (maintainer) pack the private trees into one archive to carry off this machine
	$(RUN) pidx backup

# --- the website -------------------------------------------------------------------------------
web-deps:  ## install the website's dependencies (once)
	cd web && npm install --no-fund --no-audit

web-data:  ## write the site's data from data/ — reads nothing private
	$(RUN) pidx web build

web: web-data  ## build the site into web/dist
	cd web && npm run build

serve: web-data  ## bring the site up with live reload, at http://0.0.0.0:8026/parts-index/
	@echo "  http://$(WEB_HOST):$(WEB_PORT)/parts-index/"
	cd web && PIDX_WEB_HOST=$(WEB_HOST) PIDX_WEB_PORT=$(WEB_PORT) npm run dev

# --- maintainer only ----------------------------------------------------------------------------
migrate-datasets:  ## (maintainer, one-off) distil the research datasets; needs FROM=/path/to/sch-datasets
	@test -n "$(FROM)" || { echo "give the dataset tree: make migrate-datasets FROM=/path/to/sch-datasets"; exit 1; }
	$(RUN) --extra datasets python -m parts_index.migrate.datasets --from "$(FROM)"

migrate-wanted:  ## (maintainer, one-off) publish the parts worth having; needs FROM=<catalog dir>
	@test -n "$(FROM)" || { echo "give the catalog directory: make migrate-wanted FROM=<dir>"; exit 1; }
	$(RUN) python -m parts_index.migrate.wanted --from "$(FROM)"

migrate:  ## (maintainer, one-off) carry the old pipeline's state across — see src/parts_index/migrate/
	$(RUN) python -m parts_index.migrate.model_ledgers
	$(RUN) python -m parts_index.migrate.ocr_tree
	$(MAKE) status-write

clean:  ## remove caches and build output (never touches the private data root)
	rm -rf .pytest_cache .ruff_cache web/dist web/public/data
	find src tests scripts -name __pycache__ -type d -prune -exec rm -rf {} +

# Arriving as the pipelines are ported — see the plan:
#   crawl / download / ocr / index / linkcheck   pillar 1, per source
#   export                                       the private index -> data/
#   fetch / promote                              pillar 2, SPICE models
#   serve-private                                the site with the model text inlined, never deployed
