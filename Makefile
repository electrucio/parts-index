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
.PHONY: vlm-image vlm-models vlm-serve vlm-stop sheets-pages sheets-extract sheets-evaluate sheets-crosscheck sim-vendor sim-qspice-capture sim-images sim-bjt sim-sample sim-batch datasheets-register datasheets-links datasheets-harvest datasheets-catalogue datasheets-databooks datasheets-rows datasheets-crops crops-publish web-deploy ocr-image help setup test test-web lint guard check status status-write paths toragi-report models-index models-missing models-recover models-verify models-reconcile models-match models-found models-promote models-cards models-claims datasets-repos schematics-summarise schematics-summarise-bg schematics-preview schematics-export backup migrate-datasets migrate-wanted migrate clean web web-data web-deps serve

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

models-reconcile:  ## (maintainer) which downloads the definitions came from; WRITE=1 records it [SOURCE='a b']
	$(RUN) pidx models reconcile $(foreach s,$(SOURCE),--source $(s)) $(if $(WRITE),--write,)

models-match:  ## (maintainer) find, for every wanted part, each definition that could be its model
	$(RUN) pidx models match

models-found:  ## (maintainer) group those matches into distinct models, with where each copy can be had
	$(RUN) pidx models found

models-promote:  ## (maintainer) write the public recipe for every curated part into data/models/parts/
	$(RUN) pidx models promote

models-cards:  ## (maintainer) what each recipe model's card lacks, into data/verification/ (after promote)
	$(RUN) pidx models cards

models-claims:  ## (maintainer) what each recipe model's author declares, into data/verification/ (after promote)
	$(RUN) pidx models claims

# --- simulators -------------------------------------------------------------------------------
# QSPICE (the default engine), ngspice (the open cross-check) and LTspice (the compatibility check), in
# images whose every input is pinned; see docker/sim/README.md.
# The vendor store holds the installers, which may not be redistributed: it is private, like the images.
SIM_VENDOR ?= private_material/simulators/vendor
SIM_RUNS ?= private_material/simulators/runs
SIM_MODELS ?= private_web_spice_models
SIM_BUILD = docker build --build-context vendor=$(SIM_VENDOR) --build-arg UID=$$(id -u) --build-arg GID=$$(id -g)
ENGINES ?= qspice ngspice ltspice

sim-vendor:  ## (maintainer) fetch the simulators' installers into the private store and check their sha256
	sh docker/sim/vendor.sh $(SIM_VENDOR)

sim-qspice-capture:  ## (maintainer, one-off) install QSPICE under Wine and pack it — this accepts Qorvo's licence
	$(SIM_BUILD) --target qspice-installer -t parts-index-qspice-installer docker/sim
	sh docker/sim/qspice_capture.sh $(SIM_VENDOR)

sim-images:  ## (maintainer) build the simulator images from the pinned inputs; [ENGINES='ngspice ltspice']
	for e in $(ENGINES); do $(SIM_BUILD) --target $$e -t parts-index-$$e docker/sim || exit 1; done

sim-bjt:  ## (maintainer) measure one bipolar model in each simulator; FILE=model.lib NAME=card [POL=pnp] [REPEAT=3]
	@test -n "$(FILE)" -a -n "$(NAME)" || { echo "give FILE=path/to/model.lib NAME=its .model name"; exit 1; }
	@mkdir -p $(SIM_RUNS)/$(NAME)/in && cp "$(FILE)" $(SIM_RUNS)/$(NAME)/in/model.lib
	for e in $(ENGINES); do docker run --rm -v "$(PWD)/$(SIM_RUNS)/$(NAME)":/w parts-index-$$e \
	  python3 /sim/bench/bjt.py --model-file /w/in/model.lib --model "$(NAME)" --polarity $(or $(POL),npn) \
	  --out /w/$$e --repeat $(or $(REPEAT),1) || exit 1; done
	python3 docker/sim/bench/compare.py $(SIM_RUNS)/$(NAME)

sim-sample:  ## (maintainer) list the distinct bipolar models in the index, N at random (0 = all); N=400
	python3 docker/sim/bench/sample_bjt.py private_material/index.jsonl $(SIM_RUNS)/bjt_$(or $(N),400).jsonl --n $(or $(N),400)

sim-batch:  ## (maintainer) measure a list of models; LIST=file [ENGINE=qspice] [WORKERS=40] [SIM_CPUS=1] [PACK=10] [OUT=dir]
	@test -n "$(LIST)" || { echo "give LIST=models.jsonl (make sim-sample writes one)"; exit 1; }
	SIM_CPUS=$(or $(SIM_CPUS),1) sh docker/sim/batch.sh $(or $(ENGINE),qspice) $(or $(WORKERS),$$(nproc)) $(or $(PACK),10) $(LIST) \
	  $(or $(OUT),$(SIM_RUNS)/batch-$(or $(ENGINE),qspice)-$$(date +%Y%m%d-%H%M%S)) $(SIM_MODELS)

# --- data sheets (experiments) -------------------------------------------------------------------
# A vision-language model on one GPU reads the characteristics tables of manufacturer data sheets; the
# rows are scored against a hand-read reference and used to hold SPICE models against the sheet. See
# docker/datasheets/README.md. VLM_MODELS: the folder with the weights (outside the repository).
DATASHEET_PDFS ?= private_material/datasheets/vendor
DATASHEET_LAB ?= private_material/datasheet_lab
GOLDEN ?= docker/datasheets/golden.yaml
VLM_PORT ?= 8090
VLM_GPU ?= 1

vlm-image:  ## (maintainer) build llama.cpp's server for CUDA 12.2 (lola's driver) — docker/vlm/README.md
	docker build -t parts-index-vlm docker/vlm

vlm-models:  ## (maintainer) fetch Qwen3.8-27B + its vision projector, sha256-checked; VLM_MODELS=dir
	@test -n "$(VLM_MODELS)" || { echo "give VLM_MODELS=/path/to/models"; exit 1; }
	sh docker/vlm/fetch_qwen38_vl.sh $(VLM_MODELS)

vlm-serve:  ## (maintainer) serve the model on VLM_GPU=1 at 127.0.0.1:$(VLM_PORT); VLM_MODELS=dir
	@test -n "$(VLM_MODELS)" || { echo "give VLM_MODELS=/path/to/models"; exit 1; }
	docker rm -f vlm-qwen >/dev/null 2>&1 || true
	docker run -d --name vlm-qwen --gpus '"device=$(VLM_GPU)"' -p 127.0.0.1:$(VLM_PORT):8090 \
	  -v $(VLM_MODELS):/models:ro parts-index-vlm -m /models/Qwen3.8-27B-UD-Q4_K_M.gguf \
	  --mmproj /models/mmproj-F16.gguf -ngl 99 -fa on -c 32768 -np 2 --jinja --host 0.0.0.0 --port 8090

vlm-stop:  ## (maintainer) stop the model server and free its GPU
	docker rm -f vlm-qwen

sheets-pages:  ## (maintainer) render the reference pages to PNG (150 dpi)
	$(RUN) python docker/datasheets/render.py --golden $(GOLDEN) --pdfs $(DATASHEET_PDFS) --out $(DATASHEET_LAB)/pages

sheets-extract:  ## (maintainer) have the model read the reference pages; METHOD=image|text|image+text [NAME=run]
	$(RUN) python docker/datasheets/extract.py --method $(or $(METHOD),image) --server http://127.0.0.1:$(VLM_PORT) \
	  --golden $(GOLDEN) --pdfs $(DATASHEET_PDFS) --pages $(DATASHEET_LAB)/pages \
	  --out $(DATASHEET_LAB)/runs/$(or $(NAME),$(or $(METHOD),image))

sheets-evaluate:  ## (maintainer) score extraction runs against the reference; RUNS='dir dir'
	$(RUN) python docker/datasheets/evaluate.py --golden $(GOLDEN) --pdfs $(DATASHEET_PDFS) --per-doc $(RUNS)

sheets-crosscheck:  ## (maintainer) every model of each reference part against its sheet; [ENGINE=qspice] [ROWS=run]
	$(RUN) python docker/datasheets/crosscheck.py --golden $(GOLDEN) --index private_material/index.jsonl \
	  --models $(SIM_MODELS) --out $(DATASHEET_LAB)/crosscheck-$(or $(ENGINE),qspice) --engine $(or $(ENGINE),qspice) \
	  $(if $(ROWS),--rows $(ROWS))

# --- research datasets -------------------------------------------------------------------------
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

datasheets-register:  ## (maintainer) what each maker's catalogue says about the indexed parts; [SOURCE=ti_products] [LIMIT=N] [REREAD=1]
	uv run pidx datasheets register $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(REREAD),--reread)

datasheets-links:  ## (maintainer) every data sheet an archive lists for each part, from its cached index; [SOURCE=frank_pocnet]
	uv run pidx datasheets links $(foreach s,$(SOURCE),--source $(s))

datasheets-harvest:  ## (maintainer) read the data sheets a maker's sitemap lists, to learn which parts each covers; [SOURCE=onsemi_docs] [LIMIT=N] [LIST=1]
	uv run --extra ocr pidx datasheets harvest $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(LIST),--list-only)

datasheets-catalogue:  ## (maintainer) read a maker's whole product list: each known part, its status and its sheet; [SOURCE=diotec_products] [REFRESH=1]
	uv run pidx datasheets catalogue $(foreach s,$(SOURCE),--source $(s)) $(if $(REFRESH),--refresh)

datasheets-databooks:  ## (maintainer) the pages of old databooks on archive.org that head a known part; [LIMIT=N] [LIST=1] [REREAD=1]
	uv run pidx datasheets databooks $(if $(LIMIT),--limit $(LIMIT)) $(if $(LIST),--list-only) $(if $(REREAD),--reread)

datasheets-rows:  ## (maintainer) publish the reference sheets' rows, each located on its page, into data/datasheets/values/
	$(RUN) pidx datasheets rows

datasheets-crops:  ## (maintainer) crop each published row from its PDF into web/public/data/crops (never committed)
	$(RUN) pidx datasheets crops

crops-publish:  ## (maintainer) upload the crops as the release asset the Pages workflow unpacks (CLAUDE.md rule 1)
	@test -d web/public/data/crops || { echo "no crops: make datasheets-crops first"; exit 1; }
	tar -cf "$${TMPDIR:-/tmp}/crops.tar" -C web/public/data crops
	gh release view datasheet-crops >/dev/null 2>&1 || gh release create datasheet-crops --title "Data-sheet crops" \
	  --notes "Crops of data sheets quoted on the site beside their transcription (CLAUDE.md rule 1). Deleting this asset withdraws them."
	gh release upload datasheet-crops "$${TMPDIR:-/tmp}/crops.tar" --clobber

toragi-report:  ## (maintainer) トランジスタ技術: coverage by year and by issue, from the lists and ledgers
	$(RUN) pidx schematics toragi

schematics-crawl:  ## (maintainer) walk a site and take what it shows; SOURCE='a b' [MAX=n]
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-crawl SOURCE=tubecad"; exit 1; }
	$(RUN) pidx schematics crawl $(foreach s,$(SOURCE),--source $(s)) $(if $(MAX),--max $(MAX),)

schematics-crawl-bg:  ## (maintainer) the same, detached under a lock with a log; AFTER=<job> to queue it
	@test -n "$(SOURCE)" || { echo "give the source: make schematics-crawl-bg SOURCE=tubecad"; exit 1; }
	$(RUN) pidx schematics crawl $(foreach s,$(SOURCE),--source $(s)) $(if $(MAX),--max $(MAX),) \
	  $(if $(AFTER),--after $(AFTER),) --detach

schematics-ocr:  ## (maintainer) read what is downloaded and not read yet; SOURCE='a b' [GPU=0] [SHARD=0/2] [DRY=1]
	uv run pidx schematics ocr $(foreach s,$(SOURCE),--source $(s)) $(if $(GPU),--gpu $(GPU)) $(if $(SHARD),--shard $(SHARD)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(DRY),--dry)

# The CUDA the image is built for has to be one this machine's driver runs; see docker/ocr.Dockerfile.
PADDLE_TAG ?= 3.2.2-gpu-cuda12.6-cudnn9.5

ocr-image:  ## (maintainer) build the OCR image; PADDLE_TAG=3.2.2-gpu-cuda11.8-cudnn8.9 for a driver older than CUDA 12.6
	docker build --build-arg PADDLE_TAG=$(PADDLE_TAG) -f docker/ocr.Dockerfile -t parts-index-ocr .

schematics-ocr-docker:  ## (maintainer) the same inside the CUDA image, one shard per GPU; SOURCE='a b' GPU=0 SHARD=0/2
	docker run --rm --gpus '"device=$(GPU)"' --user $$(id -u):$$(id -g) -e HOME=/repo/private_material/cache_ocr_home \
	  -v "$(PWD)":/repo parts-index-ocr \
	  schematics ocr $(foreach s,$(SOURCE),--source $(s)) --gpu 0 $(if $(SHARD),--shard $(SHARD))

schematics-verify:  ## (maintainer) find documents lost before anything read them; REPAIR=1 fetches them back
	$(RUN) pidx schematics verify $(if $(SOURCE),$(foreach s,$(SOURCE),--source $(s)),) $(if $(REPAIR),--repair,)

schematics-prune:  ## (maintainer) drop what a source's rules no longer want; [SOURCE='a b'] [DRY=1]
	$(RUN) pidx schematics prune $(foreach s,$(SOURCE),--source $(s)) $(if $(DRY),--dry,)

schematics-release:  ## (maintainer) delete downloaded files whose text is already read; [SOURCE='a b'] [DRY=1]
	$(RUN) pidx schematics release $(foreach s,$(SOURCE),--source $(s)) $(if $(DRY),--dry,)

schematics-ingest:  ## (maintainer) put what has been read into the index database; [SOURCE='a b'] [LIMIT=n] [DRY=1]
	$(RUN) pidx schematics ingest $(foreach s,$(SOURCE),--source $(s)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(DRY),--dry)

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

web-deploy:  ## (maintainer) publish the site: run the Pages workflow on GitHub from what is pushed, and watch it
	@git fetch --quiet origin main && test "$$(git rev-parse origin/main)" = "$$(git rev-parse main)" \
	  || { echo "main is not pushed: the workflow builds what GitHub has. git push first."; exit 1; }
	gh workflow run pages.yml && sleep 5 && gh run watch $$(gh run list --workflow=pages.yml --limit 1 --json databaseId --jq '.[0].databaseId')
	@echo "  https://electrucio.github.io/parts-index/"

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
