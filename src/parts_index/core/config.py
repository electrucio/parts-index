"""Where everything is. This is the only module allowed to name a location.

No other module joins a path: it asks here. That keeps one rule checkable in one place —

    PUBLIC   lives in the repository and is committed: registries, ledgers, the exported index,
             model recipes, licence notes, verification results, the part dictionary, the website.
    PRIVATE  lives under the data root and is never committed: downloaded documents, OCR text,
             the sqlite index, vendor model files, datasheet PDFs, caches and the old code.

The data root is `$PIDX_DATA_ROOT`, else `private_uncommitted/` inside the checkout, which `.gitignore`
and `scripts/licence_guard.py` both refuse. Private accessors are wrapped in `require()` by their caller
so a contributor without the corpus gets an explanation instead of a stack trace.

    pidx paths        prints every location, resolved, marked public or private
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_DATA = REPO_ROOT / "data"


class PrivateDataMissing(RuntimeError):
    """Raised when work needs the private corpus and it is not here."""


def data_root() -> Path:
    env = os.environ.get("PIDX_DATA_ROOT")
    return Path(env).expanduser() if env else REPO_ROOT / "private_uncommitted"


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


def model_licence(source: str) -> Path:
    return models_dir() / "licences" / f"{source}.md"


def model_files(source: str) -> Path:
    """Model text we are allowed to host. Only for sources marked redistributable."""
    return models_dir() / "files" / source


def model_links() -> Path:
    return models_dir() / "links.csv"


def datasheets_table() -> Path:
    return PUBLIC_DATA / "datasheets" / "datasheets.csv"


def verification(kind: str, part: str) -> Path:
    """Measured results row by row against the datasheet."""
    return PUBLIC_DATA / "verification" / kind / f"{part}.json"


# --- public: the part dictionary and the repository itself ------------------------------------------
def known_parts() -> Path:
    return PUBLIC_DATA / "parts" / "known_parts.csv"


def rejected_tokens() -> Path:
    return PUBLIC_DATA / "parts" / "rejected_tokens.txt"


def datasets_registry() -> Path:
    return PUBLIC_DATA / "datasets" / "registry.yaml"


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
    """Build output of `pidx web build`; git-ignored, rebuilt from data/ alone."""
    return web_dir() / "public" / "data"


def tests_fixtures() -> Path:
    return REPO_ROOT / "tests" / "fixtures"


# --- private: the document corpus -------------------------------------------------------------------
def corpus() -> Path:
    return data_root() / "corpus"


def corpus_db() -> Path:
    """The full index: document text and local paths. Export from it by column allow-list, never wholesale."""
    return corpus() / "db" / "schematics.sqlite"


def corpus_db_uri(readonly: bool = True) -> str:
    """The only place this connection string is written."""
    return f"file:{corpus_db()}{'?mode=ro' if readonly else ''}"


def corpus_raw(source: str) -> Path:
    return corpus() / "raw" / source


def corpus_files_csv(source: str) -> Path:
    """Download manifest written by crawl and download."""
    return corpus_raw(source) / "files.csv"


def corpus_ocr(source: str) -> Path:
    """OCR with boxes, one gzip JSON-lines file per document."""
    return corpus() / "ocr_boxes" / source


def corpus_ocr_scans() -> Path:
    return corpus() / "ocr_scans"


def corpus_magazine_ocr(magazine: str | None = None) -> Path:
    d = corpus() / "magazines" / "ocr"
    return d / magazine if magazine else d


def corpus_magazine_ledger() -> Path:
    return corpus_magazine_ocr() / "sources.csv"


def corpus_elektor_ocr() -> Path:
    return corpus() / "elektor" / "ocr"


def corpus_books_ocr() -> Path:
    return corpus() / "books" / "ocr"


def corpus_pagesizes() -> Path:
    """Page sizes frozen before the PDFs were deleted; without them a link cannot carry a zoom."""
    return corpus() / "pagesizes.csv.gz"


def corpus_labelset() -> Path:
    return corpus() / "labelset"


# --- private: SPICE material ------------------------------------------------------------------------
def spice_root() -> Path:
    return data_root() / "spice"


def spice_source(source: str) -> Path:
    return spice_root() / "sources" / source


def spice_source_doc(source: str) -> Path:
    return spice_source(source) / "SOURCE.md"


def spice_source_manifest(source: str) -> Path:
    return spice_source(source) / "manifest.json"


def spice_model_dir(kind: str, part: str) -> Path:
    """Extracted vendor model text. Never published unless its source allows redistribution."""
    return spice_root() / "models" / kind / part


def spice_part_json(kind: str, part: str) -> Path:
    return spice_model_dir(kind, part) / "part.json"


def spice_index() -> Path:
    """Every definition found, with its parameters: a copy of the models. Never published."""
    return spice_root() / "index.jsonl"


def datasheet_pdfs() -> Path:
    return spice_root() / "datasheets"


def datasheet_manifest() -> Path:
    return datasheet_pdfs() / "manifest.json"


# --- private: everything else -----------------------------------------------------------------------
def books() -> Path:
    return data_root() / "books"


def elektor_pdfs() -> Path:
    return data_root() / "elektor_pdfs"


def sch_datasets() -> Path:
    return data_root() / "sch-datasets"


def staging(*parts: str) -> Path:
    """The old code, kept until each piece is ported."""
    return data_root().joinpath("staging", *parts)


def legacy() -> Path:
    return data_root() / "legacy"


def llm_cache() -> Path:
    return data_root() / "llm_cache"


def logs() -> Path:
    return data_root() / "logs"


def scratch() -> Path:
    return data_root() / "scratch"


def guard_extra_patterns() -> Path:
    return data_root() / "guard_extra_patterns.txt"


# --- the map ----------------------------------------------------------------------------------------
# name, visibility, sample arguments. `pidx paths` prints this; a test asserts nothing public resolves
# inside the data root and nothing private resolves inside the checkout's committed tree.
LOCATIONS: tuple[tuple[str, str, tuple], ...] = (
    ("schematics_registry", "public", ()),
    ("schematics_state", "public", ("esp",)),
    ("schematics_documents", "public", ("esp",)),
    ("schematics_pages", "public", ("esp",)),
    ("schematics_uses", "public", ("esp",)),
    ("schematics_parts", "public", ()),
    ("schematics_export_manifest", "public", ()),
    ("schematics_withdrawn", "public", ()),
    ("schematics_curated", "public", ("TL072",)),
    ("schematics_overrides", "public", ()),
    ("model_sources", "public", ("onsemi",)),
    ("model_state", "public", ("onsemi",)),
    ("model_part", "public", ("bjt", "2N3904")),
    ("model_licence", "public", ("onsemi",)),
    ("model_files", "public", ("germaniumbjts",)),
    ("model_links", "public", ()),
    ("datasheets_table", "public", ()),
    ("verification", "public", ("bjt", "2N3904")),
    ("known_parts", "public", ()),
    ("rejected_tokens", "public", ()),
    ("datasets_registry", "public", ()),
    ("components_dir", "public", ()),
    ("circuits_dir", "public", ()),
    ("docs_dir", "public", ()),
    ("status_md", "public", ()),
    ("web_dir", "public", ()),
    ("web_data", "public", ()),
    ("tests_fixtures", "public", ()),
    ("corpus", "private", ()),
    ("corpus_db", "private", ()),
    ("corpus_raw", "private", ("esp",)),
    ("corpus_files_csv", "private", ("esp",)),
    ("corpus_ocr", "private", ("esp",)),
    ("corpus_ocr_scans", "private", ()),
    ("corpus_magazine_ocr", "private", ()),
    ("corpus_magazine_ledger", "private", ()),
    ("corpus_elektor_ocr", "private", ()),
    ("corpus_books_ocr", "private", ()),
    ("corpus_pagesizes", "private", ()),
    ("corpus_labelset", "private", ()),
    ("spice_root", "private", ()),
    ("spice_source", "private", ("onsemi",)),
    ("spice_source_doc", "private", ("onsemi",)),
    ("spice_source_manifest", "private", ("onsemi",)),
    ("spice_model_dir", "private", ("bjt", "2N3904")),
    ("spice_part_json", "private", ("bjt", "2N3904")),
    ("spice_index", "private", ()),
    ("datasheet_pdfs", "private", ()),
    ("datasheet_manifest", "private", ()),
    ("books", "private", ()),
    ("elektor_pdfs", "private", ()),
    ("sch_datasets", "private", ()),
    ("staging", "private", ()),
    ("legacy", "private", ()),
    ("llm_cache", "private", ()),
    ("logs", "private", ()),
    ("scratch", "private", ()),
    ("guard_extra_patterns", "private", ()),
)


def describe() -> list[tuple[str, str, Path, bool]]:
    """(name, visibility, resolved path, exists) for every location, for `pidx paths`."""
    out = []
    for name, visibility, args in LOCATIONS:
        path = globals()[name](*args)
        out.append((name, visibility, path, path.exists()))
    return out
