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


def download_manifest(source: str) -> Path:
    """What the crawler already has for a source, so it resumes instead of starting again."""
    return material_root() / "manifests" / f"{source}.csv"


def source_list(source: str) -> Path:
    """URLs gathered for a source that cannot be crawled; the input for downloading it."""
    return material_root() / "source_lists" / f"assets_{source}.jsonl"


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


def datasheets(kind: str | None = None) -> Path:
    """Vendor PDFs, kept until the simulation and datasheet-reading work is done."""
    d = material_root() / "datasheets"
    return d / kind if kind else d


def simulators() -> Path:
    """Installers and tools for the simulation stage, each with its URL and checksum recorded.
    Never published and never inside a docker image: the Dockerfile downloads them where it builds."""
    return material_root() / "simulators"


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
    ("web_data", "built", ()),
    ("web_dist", "built", ()),
    ("tests_fixtures", "public", ()),
    ("ocr_root", "private", ()),
    ("ocr_map", "private", ()),
    ("linkchecks", "private", ()),
    ("index_db", "private", ()),
    ("page_sizes", "private", ()),
    ("download_manifest", "private", ("esp",)),
    ("source_list", "private", ("diyaudio",)),
    ("spice_models_root", "private", ()),
    ("spice_source", "private", ("onsemi",)),
    ("spice_source_doc", "private", ("onsemi",)),
    ("spice_source_manifest", "private", ("onsemi",)),
    ("spice_curated", "private", ()),
    ("spice_model_dir", "private", ("bjt", "2N3904")),
    ("spice_part_json", "private", ("bjt", "2N3904")),
    ("spice_definitions", "private", ()),
    ("datasheets", "private", ()),
    ("simulators", "private", ()),
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
