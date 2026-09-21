"""Distil the research datasets into the few facts worth keeping, so the 19 GB can go.

    pidx migrate datasets --from /path/to/sch-datasets

Thirteen public datasets of schematic images were surveyed. None of them is a source for the index —
they are textbook figures, hand-drawn exercises and cropped symbols — but two things in them are: which
open-source projects use which part, and a catalogue of real part references with their manufacturer.
Both are facts and links about public repositories, so both can be published.

Three files come out, and then the datasets themselves are no longer needed:

  `part_repos.csv`  one row per (part, GitHub repository), read out of the Open Schematics dump. It is
                    the third answer to "where is this part used", beside schematics and magazines, and
                    the only dataset that points back at an original project rather than a figure.
                    Part, sheet count and link, and nothing else: the repository name is already the tail
                    of the link, and the project's own blurb is third-party prose that belongs at the
                    link rather than here — one of them named a student, which is not ours to republish.
  `part_stats.csv`  real part references with manufacturer, description and per-dataset counts.
  `registry.yaml`   one entry per dataset: what it holds, its licence, and whether its ground truth can
                    be trusted. Written here rather than copied, because the survey it comes from is in
                    Spanish and everything public is in English.

Reading the dump needs `pyarrow`, which is an optional dependency for exactly this reason: it is wanted
once, and `src/parts_index/migrate/` goes away when the last stage is ported.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

from parts_index.core.config import dataset_table, datasets_registry
from parts_index.core.parts.extractor import KNOWN, norm

# Only the value of a PLACED component counts. The symbol a designer picked says nothing about the part:
# a BC237B is often drawn with the library symbol "Transistor_BJT:2N3055", a 1N5817 with "Diode:1N4148".
# So the embedded (lib_symbols ...) block of a KiCad 6 sheet is skipped, and Eagle's deviceset is used
# only when the part carries no value of its own.
KICAD6_FIRST = re.compile(r"\(symbol\s*\(lib_id ")
KICAD6_VAL = re.compile(r'\(property "Value" "([^"]{2,40})"')
KICAD5_VAL = re.compile(r'^F 1 "([^"]{2,40})"', re.M)
EAGLE_PART = re.compile(r"<part\b[^>]*>")
# TL072CP -> TL072, LM358DR2G -> LM358: package and reel suffixes a vendor adds to an order code.
SUFFIX_CUTS = (r"(?<=\d)[A-Z]{1,3}$", r"(?<=\d)[A-Z]{1,3}\d?[A-Z]{0,4}$")
# The survey judged this column unreliable — its models are LLM-generated and five of five checked were
# wrong — so it is dropped rather than published with a warning nobody reads.
STATS_DROP = {"masala_spice"}

# What each dataset is, in English, from the survey. Ground truth that says what is *connected* is rare;
# most of these say only where each symbol sits on the page, which is a different and lesser thing.
DATASETS = [
    dict(id="open_schematics", name="Open Schematics", images=33_320,
         source="Hugging Face `Joseferrera24/open-schematics`",
         licence="CC-BY-4.0 for the dataset; each source project keeps its own (GPL, CERN-OHL, MIT…)",
         transcription="complete EDA source", netlist="yes, derivable",
         ground_truth="exact by construction",
         note="the only one that points back at an original project rather than a figure"),
    dict(id="masala_chai", name="Masala-CHAI", images=6_371,
         source="Google Drive; the link had been removed from the README and was recovered from its history",
         licence="not declared; images cropped from ten textbooks, so third-party copyright",
         transcription="SPICE plus caption", netlist="yes", ground_truth="poor",
         note="netlists are LLM-generated; five of five checked by hand were wrong"),
    dict(id="cghd", name="CGHD — Circuit Graph Handwritten Dataset", images=4_181,
         source="Hugging Face `lowercaseonly/cghd`; Zenodo 14042961 answered 403",
         licence="CC-BY-SA-3.0 per its README, while the Hugging Face card says CC-BY-3.0",
         transcription="symbol, junction and text boxes, with rotation and OCR",
         netlist="12 .asc files", ground_truth="high, hand-made",
         note="perception ground truth: where each symbol is, not what is joined to what"),
    dict(id="ci2n", name="Image2Net / CI2N", images=2_269,
         source="https://github.com/LAD021/ci2n_datasets",
         licence="Apache-2.0 for the repository; images from papers, books and the web, so third-party copyright",
         transcription="device boxes, crossings, orientation", netlist="122 verified",
         ground_truth="high, hand-made",
         note="its 122 golden netlists are the only hand-verified connectivity in any of these"),
    dict(id="amsnet_v1", name="AMSNet 1.0", images=734,
         source="https://github.com/AMS-Net/ams-net.github.io",
         licence="GPL-3.0 for the repository; figures from textbooks, so third-party copyright",
         transcription="SPICE plus component and node boxes", netlist="yes",
         ground_truth="medium-high, automatic", note="component values are generic"),
    dict(id="digitize_hcd", name="Digitize-HCD", images=1_277,
         source="Mendeley Data `rngcz5wtv8` v2", licence="CC-BY-4.0",
         transcription="component boxes, text with its string, ports in crops", netlist="no",
         ground_truth="high, hand-made", note="perception ground truth only"),
    dict(id="sesyd", name="SESYD, synthetic electrical diagrams", images=1_000,
         source="http://mathieu.delalandre.free.fr/projects/sesyd/symbols/diagrams.html",
         licence="none stated; the site asks that the paper be cited (Delalandre et al., 2010)",
         transcription="symbol boxes and full vector geometry", netlist="no, but the geometry is exact",
         ground_truth="exact, synthetic", note="generated, so it says nothing about real drawings"),
    dict(id="aitee", name="AITEE", images=828,
         source="https://github.com/CKnievel/aitee-dataset", licence="Apache-2.0",
         transcription="YOLO boxes, 11 classes", netlist="no", ground_truth="high",
         note="a trivial domain"),
    dict(id="juhccr", name="JUHCCR-v1", images=56_017,
         source="Kaggle `ayush02102001/circuit-component-analysis`",
         licence="CC-BY-NC-ND-4.0 for the paper",
         transcription="one class per folder", netlist="no", ground_truth="isolated components",
         note="crops of single components, no circuit"),
    dict(id="circuit_recognizer", name="Hand-drawn Circuit Recognizer", images=306,
         source="https://github.com/mahmut-aksakalli/circuit_recognizer", licence="not recorded",
         transcription="one class per folder", netlist="no", ground_truth="isolated components",
         note="crops of single components, no circuit"),
    dict(id="circuitnet", name="CircuitNet (aaanthonyyy)", images=2_991,
         source="https://github.com/aaanthonyyy/CircuitNet", licence="not recorded",
         transcription="class and orientation per folder", netlist="no",
         ground_truth="isolated components", note="crops of single components, no circuit"),
]
NOT_AVAILABLE = [
    ("circuitpile_9k", "CircuitPile-9k / CircuitHub9K", "the repository was withdrawn"),
    ("amsnet_v2", "AMSnet 2.0", "announced but never published"),
    ("dcd", "DCD — Digital Circuit Diagram", "no source could be located"),
]


def placed_values(text: str) -> set[str]:
    """Every value written on a component that was actually placed on this sheet."""
    vals: set[str] = set()
    m = KICAD6_FIRST.search(text)
    if m:
        vals |= set(KICAD6_VAL.findall(text[m.start():]))
    vals |= set(KICAD5_VAL.findall(text))
    for tag in EAGLE_PART.findall(text):
        v = re.search(r'\bvalue="([^"]{2,40})"', tag) or re.search(r'\bdeviceset="([^"]{2,40})"', tag)
        if v:
            vals.add(v.group(1))
    return vals


def lookup(value: str) -> str | None:
    """The catalogue part this written value refers to, if any.

    A value on a sheet is whatever the designer typed: an order code, a part with its package, or a
    phrase with the part inside it. Each of those is tried in turn, and anything still unknown is
    dropped — a wrong part here would put a project on the wrong page.
    """
    k = norm(value)
    if k in KNOWN:
        return KNOWN[k][0]
    for cut in SUFFIX_CUTS:
        b = re.sub(cut, "", k)
        if b != k and b in KNOWN:
            return KNOWN[b][0]
    for piece in re.split(r"[\s_/,;()]+", value.upper()):        # "Q_NPN BC547B", "TL072_dual"
        k = norm(piece)
        if k in KNOWN:
            return KNOWN[k][0]
    return None


def scan(path: str) -> list[tuple[str, str, int, str]]:
    """One shard of the dump: (part, repository, sheets, description)."""
    import pyarrow.parquet as pq

    out: Counter = Counter()
    for batch in pq.ParquetFile(path).iter_batches(batch_size=200, columns=["name", "schematic"]):
        for r in batch.to_pylist():
            parts = {p for p in (lookup(v) for v in placed_values(r.get("schematic") or "")) if p}
            for p in parts:
                out[(p, r["name"])] += 1
    return [(p, repo, n) for (p, repo), n in out.items()]


def part_repos(root: Path, workers: int = 20) -> dict:
    shards = sorted(str(p) for p in (root / "01_open_schematics").rglob("*.parquet"))
    if not shards:
        return {"shards": 0, "rows": 0, "parts": 0, "repos": 0}
    agg: Counter = Counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, rows in enumerate(ex.map(scan, shards), 1):
            for p, repo, n in rows:
                agg[(p, repo)] += n
            if i % 20 == 0:
                print(f"  {i}/{len(shards)} shards …", flush=True)
    out = dataset_table("part_repos")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["part", "sheets", "url"])
        for (p, repo), n in sorted(agg.items()):
            w.writerow([p, n, f"https://github.com/{repo}"])
    return {"shards": len(shards), "rows": len(agg),
            "parts": len({p for p, _ in agg}), "repos": len({r for _, r in agg})}


def part_stats(root: Path) -> dict:
    src = root / "component_stats" / "clean" / "parts.csv"
    if not src.exists():
        return {"rows": 0}
    with open(src, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {"rows": 0}
    fields = [f for f in rows[0] if f not in STATS_DROP]
    out = dataset_table("part_stats")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return {"rows": len(rows), "dropped_columns": sorted(STATS_DROP)}


def remotes(root: Path) -> dict[str, str]:
    """Where each cloned dataset came from, asked of the clone itself."""
    import subprocess
    out = {}
    for d in sorted(p for p in root.iterdir() if (p / ".git").exists()):
        r = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            out[d.name] = r.stdout.strip()
    return out


def registry(root: Path) -> dict:
    found = remotes(root)
    by_id = {k.split("_", 1)[-1].replace("_gdrive", ""): v for k, v in found.items()}
    entries = []
    for d in DATASETS:
        e = dict(d)
        for key, url in by_id.items():
            if key in e["id"] or e["id"] in key:
                e["clone"] = url          # the remote of the clone that was actually on disk
                break
        entries.append(e)
    doc = {
        "note": ("Public research datasets of schematic images, surveyed and then deleted. None is a "
                 "source for this index — they are textbook figures, hand-drawn exercises and cropped "
                 "symbols — and several carry non-commercial or no-derivatives terms, or hold figures "
                 "cropped from copyrighted textbooks, which would keep them out regardless. What is "
                 "kept is what may be kept: the facts and links distilled into `part_repos.csv` and "
                 "`part_stats.csv`, and this list, so the survey is not repeated."),
        "datasets": entries,
        "not_available": [{"id": i, "name": n, "why": w} for i, n, w in NOT_AVAILABLE],
    }
    datasets_registry().parent.mkdir(parents=True, exist_ok=True)
    datasets_registry().write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    return {"datasets": len(entries), "with_repo": sum(1 for e in entries if e.get("clone")),
            "not_available": len(NOT_AVAILABLE)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="root", required=True, help="the sch-datasets tree")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--skip-repos", action="store_true", help="only the stats and the registry")
    a = ap.parse_args(argv)

    root = Path(a.root)
    if not root.is_dir():
        print(f"{root} is not here", file=sys.stderr)
        return 1

    r = registry(root)
    print(f"registry: {r['datasets']} datasets ({r['with_repo']} with a repository recorded), "
          f"{r['not_available']} that were never available -> {datasets_registry()}")
    s = part_stats(root)
    print(f"part_stats: {s['rows']:,} part references -> {dataset_table('part_stats')}"
          + (f" (dropped {', '.join(s['dropped_columns'])}: judged unreliable)" if s.get("rows") else ""))
    if a.skip_repos:
        return 0
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("reading the Open Schematics dump needs pyarrow: uv sync --extra datasets",
              file=sys.stderr)
        return 1
    p = part_repos(root, a.workers)
    print(f"part_repos: {p['rows']:,} (part, repository) pairs — {p['parts']:,} parts in "
          f"{p['repos']:,} repositories, from {p['shards']} shards -> {dataset_table('part_repos')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
