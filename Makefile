# Every step of the project, in one place. `make` on its own lists them.
#
# Most targets are thin wrappers around `pidx`, the project's command (installed by `make setup`).
# Targets marked "maintainer" need the private data root; everything else works from a clean clone.

UV := uv
RUN := $(UV) run --quiet

.DEFAULT_GOAL := help
.PHONY: help setup test test-web lint guard check status status-write paths models-index models-missing models-recover models-promote schematics-export backup migrate-datasets migrate clean web web-data web-deps serve

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

models-promote:  ## (maintainer) write the public recipe for every curated part into data/models/parts/
	$(RUN) pidx models promote

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

serve: web-data  ## bring the site up locally with live reload, at http://localhost:5173
	cd web && npm run dev

# --- maintainer only ----------------------------------------------------------------------------
migrate-datasets:  ## (maintainer, one-off) distil the research datasets; needs FROM=/path/to/sch-datasets
	@test -n "$(FROM)" || { echo "give the dataset tree: make migrate-datasets FROM=/path/to/sch-datasets"; exit 1; }
	$(RUN) --extra datasets python -m parts_index.migrate.datasets --from "$(FROM)"

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
