"""Where everything is. This is the only module allowed to name a location.

No other module joins a path: it asks here. That keeps one rule checkable in one place —

    PUBLIC   lives in the repository and is committed: registries, ledgers, the exported index,
             model recipes, licence notes, verification results, the part dictionary, the website.
    BUILT    lives in the repository but is generated and git-ignored: the site's data files.
             Deleting it costs a rebuild, nothing more.
    PRIVATE  never committed, in two trees with different lifetimes:
             `private_web_spice_models/` is permanent — the vendor model text and symbols the site
             serves in private mode, which licences forbid publishing;
             `private_material/` is in transit — the OCR of everything scraped with the map over it,
             and what has not been ported or exported yet. It ends up holding only the OCR.

Both are `$PIDX_SPICE_MODELS` / `$PIDX_MATERIAL` if you keep them elsewhere. `.gitignore` and
`scripts/licence_guard.py` both refuse them. Private accessors are wrapped in `require()` by their caller
so a contributor without them gets an explanation instead of a stack trace.

    pidx paths        prints every location, resolved, marked public, built or private
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_DATA = REPO_ROOT / "data"


class PrivateDataMissing(RuntimeError):
    """Raised when work needs the private corpus and it is not here."""


def spice_models_root() -> Path:
    """Permanent: the vendor model text and symbols. Not publishable, not re-fetchable for the vendors
    that block us, and what the site shows in private mode."""
    env = os.environ.get("PIDX_SPICE_MODELS")
    return Path(env).expanduser() if env else REPO_ROOT / "private_web_spice_models"


def material_root() -> Path:
    """In transit: the OCR of everything scraped, its map, and what is not ported or exported yet."""
    env = os.environ.get("PIDX_MATERIAL")
    return Path(env).expanduser() if env else REPO_ROOT / "private_material"


def require(path: Path, why: str) -> Path:
    """Return `path`, or explain that this task needs the private data root."""
    if not path.exists():
        raise PrivateDataMissing(
            f"{why} needs {path}, which is not here. This step runs on the machine that holds the "
            f"corpus; set PIDX_DATA_ROOT if yours is elsewhere. Everything under data/ works without it."
        )
    return path


# --- public: the schematic index -------------------------------------------------------------------
def schematics_dir() -> Path:
    return PUBLIC_DATA / "schematics"


def schematics_registry() -> Path:
    """The source registry: add a site here to have it crawled."""
    return schematics_dir() / "sources.yaml"


def schematics_state(source: str) -> Path:
    """Processing ledger, one row per URL."""
    return schematics_dir() / "state" / f"{source}.csv"


def schematics_documents(source: str) -> Path:
    return schematics_dir() / "documents" / f"{source}.csv"


def schematics_pages(source: str) -> Path:
    return schematics_dir() / "pages" / f"{source}.csv"


def schematics_uses(source: str) -> Path:
    """Where each part was read: part, document, page, position."""
    return schematics_dir() / "uses" / f"{source}.csv"


def schematics_lines(source: str) -> Path:
    """One line per published use, saying what that part is doing on that page. Written by `summarise`
    through `export`, and kept beside the uses rather than inside them: a re-run of the model changes
    every line and nothing else, and a diff of that is worth reading."""
    return schematics_dir() / "lines" / f"{source}.csv"


def schematics_suspects() -> Path:
    """Parts whose published uses the model reads as something that is not a component at all — a record
    catalogue number, a resistor value, a designator, a piece of surplus equipment for sale. A by-product
    of summarising, and the shortlist for the next pass over the extractor (rule 4)."""
    return schematics_dir() / "suspects.csv"


def schematics_parts() -> Path:
    return schematics_dir() / "parts.csv"


def schematics_export_manifest() -> Path:
    return schematics_dir() / "export.json"


def schematics_withdrawn() -> Path:
    """Documents removed on request; the export gate consults it every time."""
    return schematics_dir() / "withdrawn.csv"


def schematics_curated(part: str | None = None) -> Path:
    """References added by hand, needing no corpus."""
    d = schematics_dir() / "curated"
    return d / f"{part}.yaml" if part else d


def schematics_overrides() -> Path:
    return schematics_dir() / "overrides.csv"


# --- public: SPICE models, datasheets, verification -------------------------------------------------
def models_dir() -> Path:
    return PUBLIC_DATA / "models"


def model_sources(source: str | None = None) -> Path:
    d = models_dir() / "sources"
    return d / f"{source}.yaml" if source else d


def model_state(source: str) -> Path:
    return models_dir() / "state" / f"{source}.csv"


def model_part(kind: str, part: str) -> Path:
    """The recipe for one part: candidates, where to get each, licence, verification."""
    return models_dir() / "parts" / kind / f"{part}.yaml"


def model_symbol(kind: str, part: str, name: str) -> Path:
    """An LTspice symbol we drew for one model: our own work, so it is published."""
    return models_dir() / "symbols" / kind / part / name


def model_licence(source: str) -> Path:
    return models_dir() / "licences" / f"{source}.md"


def model_files(source: str) -> Path:
    """Model text we are allowed to host. Only for sources marked redistributable."""
    return models_dir() / "files" / source


def model_changes() -> Path:
    """The fixups we apply to a model's text, named once with the reason for each."""
    return models_dir() / "changes.yaml"


def model_links() -> Path:
    return models_dir() / "links.csv"


def model_wanted() -> Path:
    """The parts the model curation looks for, by kind, with the other names each one goes by and the
    parts declared to stand in for it. Written by hand; `wanted_parts` is the list generated from shops,
    databooks and documents."""
    return models_dir() / "wanted.yaml"


def datasheets_table() -> Path:
    """What each manufacturer's catalogue says about a part: category, status, data sheet title and link."""
    return PUBLIC_DATA / "datasheets" / "datasheets.csv"


def datasheet_links(source: str) -> Path:
    """Every data sheet one archive or catalogue links for each part: maker, link, size, language."""
    return PUBLIC_DATA / "datasheets" / "links" / f"{source}.csv"


def datasheet_documents(source: str) -> Path:
    """The data sheets a manufacturer publishes that were read: title, revision, pages, checksum."""
    return PUBLIC_DATA / "datasheets" / "documents" / f"{source}.csv"


def datasheet_covers(source: str) -> Path:
    """Which known parts each of those sheets documents, and whether that was seen on its first page."""
    return PUBLIC_DATA / "datasheets" / "covers" / f"{source}.csv"


def datasheet_pages(source: str) -> Path:
    """The pages of old databooks that head a known part: book, page, printed page number."""
    return PUBLIC_DATA / "datasheets" / "pages" / f"{source}.csv"


def datasheet_catalogue(source: str) -> Path:
    """What a manufacturer's own product list says about each indexed part it makes: category, status,
    and the data sheet it gives for it."""
    return PUBLIC_DATA / "datasheets" / "catalogue" / f"{source}.csv"


def datasheets_registry() -> Path:
    """The manufacturer catalogues the data-sheet register reads, and at what pace."""
    return PUBLIC_DATA / "datasheets" / "sources.yaml"


def datasheets_state(source: str) -> Path:
    """One ledger row per part asked of that catalogue."""
    return PUBLIC_DATA / "datasheets" / "state" / f"{source}.csv"


def verification(kind: str, part: str) -> Path:
    """Measured results row by row against the datasheet."""
    return PUBLIC_DATA / "verification" / kind / f"{part}.json"


# --- public: the part dictionary and the repository itself ------------------------------------------
def known_parts() -> Path:
    return PUBLIC_DATA / "parts" / "known_parts.csv"


def wanted_parts() -> Path:
    """Parts worth having that the index has nothing for yet, and who says so."""
    return PUBLIC_DATA / "parts" / "wanted.csv"


def rejected_tokens() -> Path:
    return PUBLIC_DATA / "parts" / "rejected_tokens.txt"


# --- public: what each part is — the catalogue beside the dictionary ---------------------------------
def part_families() -> Path:
    """The families a part can belong to, each with a definition, what choosing one comes down to, and
    the device kinds of the site that default to it."""
    return PUBLIC_DATA / "parts" / "families.yaml"


def documented_families() -> Path:
    """Parts whose family a manufacturer's own document states, with the reference that says so."""
    return PUBLIC_DATA / "parts" / "part_families.csv"


def part_relations() -> Path:
    """How parts relate — one sheet documents both, a maker offers one as the other's replacement, one
    product is sold under both names — each row citing the document that says so."""
    return PUBLIC_DATA / "parts" / "relations.csv"


def part_references() -> Path:
    """The books, datasheets, standards and histories the catalogue cites, as S01, S02… with how each
    link answered when it was last requested."""
    return PUBLIC_DATA / "parts" / "references.csv"


def naming_schemes(scheme: str | None = None) -> Path:
    """What the letters and digits of a part number mean, one file per numbering system (Pro Electron,
    JIS, JEDEC, the valve codes), transcribed from the standard or from the manufacturer that printed it."""
    d = PUBLIC_DATA / "parts" / "schemes"
    return d / f"{scheme}.yaml" if scheme else d


def part_makers() -> Path:
    """The organisations behind the parts: former names, headquarters with the date it was read, the
    prefixes they registered, and dated events such as acquisitions — each with its source."""
    return PUBLIC_DATA / "parts" / "makers.yaml"


def parts_census(source: str = "*") -> Path:
    """Which part numbers exist, according to a list whose job was to be complete about them.

    One file per source, as the schematic ledgers and document indexes are: together they passed the
    five megabytes a single file may have here, and a manufacturer's catalogue is the kind of thing
    that arrives twenty thousand rows at a time.
    """
    return PUBLIC_DATA / "parts" / "census" / f"{source}.csv"


def parts_benchmark() -> Path:
    """Labelled decisions on real pages: does this token, on this page, name a component. What every
    change to the extractor is measured against."""
    return PUBLIC_DATA / "parts" / "benchmark.csv"


def parts_verdicts() -> Path:
    """What each census name means *in this corpus*, judged once with the evidence, with the reason."""
    return PUBLIC_DATA / "parts" / "verdicts.csv"


def census_registry() -> Path:
    """The lists the census is read from: what each one covers, and on whose authority."""
    return PUBLIC_DATA / "parts" / "census_sources.yaml"


def census_state(source: str) -> Path:
    return PUBLIC_DATA / "parts" / "state" / f"{source}.csv"


def datasets_registry() -> Path:
    return PUBLIC_DATA / "datasets" / "registry.yaml"


def dataset_table(name: str) -> Path:
    """A result distilled from a research dataset: facts and links, never the dataset itself."""
    return PUBLIC_DATA / "datasets" / f"{name}.csv"


def components_dir(name: str | None = None) -> Path:
    return REPO_ROOT / "components" / name if name else REPO_ROOT / "components"


def circuits_dir(name: str | None = None) -> Path:
    return REPO_ROOT / "circuits" / name if name else REPO_ROOT / "circuits"


def docs_dir() -> Path:
    return REPO_ROOT / "docs"


def status_md() -> Path:
    return REPO_ROOT / "STATUS.md"


def web_dir() -> Path:
    return REPO_ROOT / "web"


def web_data() -> Path:
    """Build output of `pidx web build`: git-ignored, rebuilt from data/ alone."""
    return web_dir() / "public" / "data"


def web_dist() -> Path:
    """Build output of `make web`: the site itself, git-ignored."""
    return web_dir() / "dist"


def tests_fixtures() -> Path:
    return REPO_ROOT / "tests" / "fixtures"


# --- private: the OCR of everything scraped, and the indexes over it -------------------------------
def ocr_root() -> Path:
    """One tree, `<source>/<name>.jsonl.gz`, whatever produced the records."""
    return material_root() / "ocr"


def ocr_map() -> Path:
    """Which OCR file holds each document. Lives inside the tree, so copying it takes its index along."""
    return ocr_root() / "ocr_map.csv"


def summarise_preview() -> Path:
    """Every line the summarise pass has written so far, with the link the site would show beside it.
    A window into a run that takes days; the real export is `schematics_lines`, written when it ends."""
    return material_root() / "summarise_preview.csv"


def datasheets_cache(source: str) -> Path:
    """The head of each catalogue page the register read, compressed: third-party content, so it stays
    here, and a parser fix costs a re-read rather than another visit."""
    return material_root() / "datasheets_cache" / source


def datasheets_text(source: str) -> Path:
    """The text of every data sheet the harvest read, page by page, compressed: the manufacturer's, so it
    stays here, and a better reader costs no second download."""
    return material_root() / "datasheets_text" / source


def census_cache(source: str) -> Path:
    """The index pages a census source was read from. Third-party content, so it never leaves this tree;
    keeping it means a parser fix costs a re-read, not a re-crawl."""
    return material_root() / "census" / source


def linkchecks() -> Path:
    """Links checked by hand. Re-indexing regenerates every other judgement, but not these."""
    return ocr_root() / "linkchecks.csv"


def index_db() -> Path:
    """The full index: document text and local paths. Rebuildable from the OCR in about eight minutes,
    so it is in transit, not permanent. Export from it by column allow-list, never wholesale."""
    return material_root() / "index.sqlite"


def index_db_uri(readonly: bool = True) -> str:
    """The only place this connection string is written."""
    return f"file:{index_db()}{'?mode=ro' if readonly else ''}"


def page_sizes() -> Path:
    """Page geometry in points, frozen before the PDFs went. Without it a link cannot carry a zoom."""
    return material_root() / "pagesizes.csv.gz"


def downloads(source: str) -> Path:
    """What the download stage fetched for a source, `<type>/<sha1(url)[:10]>_<name>`. In transit by the
    retention rule — download, extract, verify, delete — so only the OCR of it is kept."""
    return material_root() / "downloads" / source


def download_manifest(source: str) -> Path:
    """What the crawler already has for a source, so it resumes instead of starting again."""
    return material_root() / "manifests" / f"{source}.csv"


def source_list(source: str) -> Path:
    """URLs gathered for a source that cannot be crawled; the input for downloading it."""
    return material_root() / "source_lists" / f"assets_{source}.jsonl"


def toragi_index() -> Path:
    """CQ出版社's own index of every トランジスタ技術 article, as the publisher gives it away: TRDBWin25.zip
    with TR.txt inside (CP932, one comma-separated row per article since 1964). Fetched by hand from
    https://toragi.cqpub.co.jp/database/ and kept private, since it is their database and not ours."""
    return material_root() / "indexes" / "toragi" / "TRDBWin25.zip"


def toragi_reports() -> Path:
    """Coverage of トランジスタ技術 by year and by issue, written by `pidx schematics toragi`."""
    return scratch() / "toragi"


def listing_cache(source: str) -> Path:
    """The index pages a list was gathered from. Kept for the same reason the census keeps its own: a
    changed `keep` pattern should cost a re-read, not another walk of somebody's sitemap."""
    return material_root() / "source_lists" / "cache" / source


# --- private: the SPICE models the site serves in private mode --------------------------------------
def spice_source(source: str) -> Path:
    return spice_models_root() / "sources" / source


def spice_source_doc(source: str) -> Path:
    """Licence analysis and how it was fetched; promoted to data/models/licences/ once translated."""
    return spice_source(source) / "SOURCE.md"


def spice_source_manifest(source: str) -> Path:
    return spice_source(source) / "manifest.json"


def spice_curated() -> Path:
    """Where the curation lives: one directory per part, holding its candidates and `part.json`."""
    return spice_models_root() / "models"


def spice_model_dir(kind: str, part: str) -> Path:
    """Curated model text for one part. Published only where its source allows redistribution."""
    return spice_curated() / kind / part


def spice_part_json(kind: str, part: str) -> Path:
    return spice_model_dir(kind, part) / "part.json"


# --- private: in transit ----------------------------------------------------------------------------
def spice_definitions() -> Path:
    """Every definition found, with its parameters: a copy of the models. Never published, and
    regenerated from the sources, so it is in transit."""
    return material_root() / "index.jsonl"


def spice_matches() -> Path:
    """Every definition whose name matches a wanted part, per part: read from the definitions above,
    so it is in transit too."""
    return material_root() / "model_matches.json"


def spice_found() -> Path:
    """Those matches grouped into distinct models, each with every copy of it and where each can be had."""
    return material_root() / "model_found.json"


def datasheets(kind: str | None = None) -> Path:
    """Vendor PDFs, kept until the simulation and datasheet-reading work is done."""
    d = material_root() / "datasheets"
    return d / kind if kind else d


def simulators() -> Path:
    """The simulation stage's private side: the vendor store below, and the runs (docker/sim/README.md)."""
    return material_root() / "simulators"


def simulator_vendor() -> Path:
    """What the simulator images are built from, each checked against docker/sim/sha256/: ngspice's
    tarball, LTspice's MSI and the captured QSPICE program folder. Never published, and the images built
    from them are never pushed. The last two cannot be fetched again — their makers serve only the
    current release — so this is backed up with the essentials."""
    return simulators() / "vendor"


# --- private: the rest, all of it temporary ---------------------------------------------------------
def staging(*parts: str) -> Path:
    """The old code, kept until each piece is ported."""
    return material_root().joinpath("staging", *parts)


def legacy() -> Path:
    return material_root() / "legacy"


def llm_cache() -> Path:
    return material_root() / "llm_cache"


def logs() -> Path:
    return material_root() / "logs"


def scratch() -> Path:
    return material_root() / "scratch"


def backups() -> Path:
    """Where a backup archive is written before it is carried off this machine."""
    return material_root() / "backups"


def guard_extra_patterns() -> Path:
    return material_root() / "guard_extra_patterns.txt"


# --- the map ----------------------------------------------------------------------------------------
# name, visibility, sample arguments. `pidx paths` prints this, and tests/core/test_config.py asserts
# that each kind keeps to its side: public is committed and never git-ignored, built is in the checkout
# but always ignored, private lives under the data root.
LOCATIONS: tuple[tuple[str, str, tuple], ...] = (
    ("schematics_registry", "public", ()),
    ("schematics_state", "public", ("esp",)),
    ("schematics_documents", "public", ("esp",)),
    ("schematics_pages", "public", ("esp",)),
    ("schematics_uses", "public", ("esp",)),
    ("schematics_lines", "public", ("esp",)),
    ("schematics_suspects", "public", ()),
    ("schematics_parts", "public", ()),
    ("schematics_export_manifest", "public", ()),
    ("schematics_withdrawn", "public", ()),
    ("schematics_curated", "public", ("TL072",)),
    ("schematics_overrides", "public", ()),
    ("model_sources", "public", ("onsemi",)),
    ("model_state", "public", ("onsemi",)),
    ("model_part", "public", ("bjt", "2N3904")),
    ("model_symbol", "public", ("bjt", "2N3904", "2N3904_acme.asy")),
    ("model_changes", "public", ()),
    ("model_licence", "public", ("onsemi",)),
    ("model_files", "public", ("germaniumbjts",)),
    ("model_links", "public", ()),
    ("model_wanted", "public", ()),
    ("datasheets_table", "public", ()),
    ("datasheets_registry", "public", ()),
    ("datasheet_links", "public", ("frank_pocnet",)),
    ("datasheet_documents", "public", ("onsemi_docs",)),
    ("datasheet_covers", "public", ("onsemi_docs",)),
    ("datasheet_catalogue", "public", ("diotec_products",)),
    ("datasheet_pages", "public", ("archive_databooks",)),
    ("datasheets_state", "public", ("ti_products",)),
    ("verification", "public", ("bjt", "2N3904")),
    ("known_parts", "public", ()),
    ("wanted_parts", "public", ()),
    ("rejected_tokens", "public", ()),
    ("part_families", "public", ()),
    ("documented_families", "public", ()),
    ("part_relations", "public", ()),
    ("part_references", "public", ()),
    ("naming_schemes", "public", ("pro-electron",)),
    ("part_makers", "public", ()),
    ("parts_census", "public", ()),
    ("parts_benchmark", "public", ()),
    ("parts_verdicts", "public", ()),
    ("census_registry", "public", ()),
    ("census_state", "public", ("frank_pocnet",)),
    ("datasets_registry", "public", ()),
    ("dataset_table", "public", ("part_repos",)),
    ("components_dir", "public", ()),
    ("circuits_dir", "public", ()),
    ("docs_dir", "public", ()),
    ("status_md", "public", ()),
    ("web_dir", "public", ()),
    ("web_data", "built", ()),
    ("web_dist", "built", ()),
    ("tests_fixtures", "public", ()),
    ("ocr_root", "private", ()),
    ("ocr_map", "private", ()),
    ("linkchecks", "private", ()),
    ("summarise_preview", "private", ()),
    ("census_cache", "private", ("frank_pocnet",)),
    ("datasheets_cache", "private", ("ti_products",)),
    ("datasheets_text", "private", ("onsemi_docs",)),
    ("index_db", "private", ()),
    ("page_sizes", "private", ()),
    ("downloads", "private", ("esp",)),
    ("download_manifest", "private", ("esp",)),
    ("source_list", "private", ("diyaudio",)),
    ("toragi_index", "private", ()),
    ("toragi_reports", "private", ()),
    ("spice_models_root", "private", ()),
    ("spice_source", "private", ("onsemi",)),
    ("spice_source_doc", "private", ("onsemi",)),
    ("spice_source_manifest", "private", ("onsemi",)),
    ("spice_curated", "private", ()),
    ("spice_model_dir", "private", ("bjt", "2N3904")),
    ("spice_part_json", "private", ("bjt", "2N3904")),
    ("spice_definitions", "private", ()),
    ("spice_matches", "private", ()),
    ("spice_found", "private", ()),
    ("datasheets", "private", ()),
    ("simulators", "private", ()),
    ("simulator_vendor", "private", ()),
    ("staging", "private", ()),
    ("legacy", "private", ()),
    ("llm_cache", "private", ()),
    ("logs", "private", ()),
    ("scratch", "private", ()),
    ("backups", "private", ()),
    ("guard_extra_patterns", "private", ()),
)


def describe() -> list[tuple[str, str, Path, bool]]:
    """(name, visibility, resolved path, exists) for every location, for `pidx paths`."""
    out = []
    for name, visibility, args in LOCATIONS:
        path = globals()[name](*args)
        out.append((name, visibility, path, path.exists()))
    return out
