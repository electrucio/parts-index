"""Group each part's matches into distinct models, and say where every copy of each can be had.

    pidx models found

`pidx models match` lists every definition that could be a part's model; many of them are the same
model copied from one collection into the next. This reads each one with everything it references in
its own file, hashes the code — comments and whitespace removed, case folded — and groups identical
code into one model, attributed to the most original source that holds it (`SOURCE_RANK`), with the
others as its copies. For every model it records how to obtain it — the URL, the archive member, the
file's checksum, the line range of each definition — from the source's manifest.

Nothing is copied: this is the part of the old curation that decides *which* models a part has, without
the part that extracts them into files, infers their pins and runs them on a bench.

Ported from the old pipeline's `tools/curate.py` (candidates_for, code_hash) and `tools/extract.py`
(_scan, blocks, spans, closure, provenance).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from parts_index.core.config import require, spice_found, spice_matches, spice_models_root
from parts_index.models.index import decode

# Most original first. Vendors > LTspice's own lib (mostly vendor models, curated by ADI) > authors
# who fitted models themselves > aggregations of other people's files. A source missing from the list
# ranks after all of them.
SOURCE_RANK = [
    "onsemi", "nexperia", "nxp", "ti", "infineon", "vishay", "rohm", "toshiba",
    "diodes-inc", "central-semi", "linear-systems", "interfet", "stmicro", "exicon",
    "microchip", "renesas", "nisshinbo", "sanken", "onsemi-ic", "adi", "nichia",
    "ltspice-native",
    "cordell", "reefman", "ayumi", "duncanamps", "koren", "suusi-tubes",
    "germaniumbjts", "hagtech", "andyc", "viva-analog", "cohen-helie", "dempwolf",
    "tedyapo-led-modeling", "z101-led-spice-model",
    "germanium-apm", "bordodynov", "ltwiki", "kicad-spice-library", "spiceypedals",
    "gist-chanmix51", "electrucio",
]
RANK = {s: i for i, s in enumerate(SOURCE_RANK)}
# Path globs, relative to the model tree, whose definitions never become candidates: other simulators'
# syntax and superseded editions. Ayumi ships each model three times; win/ is the LTspice one.
EXCLUDE = ["sources/ayumi/extracted/simetrix/**", "sources/ayumi/extracted/linux/**"]
ARCHIVE_EXT = (".zip", ".7z", ".tgz", ".gz", ".rar", ".msi", ".tar")


def excluded(file: str) -> bool:
    return any(fnmatch.fnmatch(file, g) for g in EXCLUDE)


def rank(source: str) -> int:
    return RANK.get(source.split("/")[0], 99)


# --- reading definitions -----------------------------------------------------------------------------
def _scan(text: str):
    """Yield (kind, name, first_line, last_line) of top-level definitions (1-based)."""
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].lstrip()
        m = re.match(r"\.subckt\s+(\S+)", s, re.I)
        if m:
            depth, j = 1, i + 1
            while j < n and depth:
                t = lines[j].lstrip()
                if re.match(r"\.subckt\b", t, re.I):
                    depth += 1
                elif re.match(r"\.ends\b", t, re.I):
                    depth -= 1
                j += 1
            yield "subckt", m.group(1), i + 1, j
            i = j
            continue
        m = re.match(r"\.model\s+(\S+)", s, re.I)
        if m:
            j = i + 1
            while j < n and (lines[j].lstrip().startswith("+") or not lines[j].strip()
                             and j + 1 < n and lines[j + 1].lstrip().startswith("+")):
                j += 1
            yield "model", m.group(1), i + 1, j
            i = j
            continue
        i += 1


def blocks(text: str) -> dict:
    """Top-level definitions: {name_lower: (kind, name, raw_text)}; later ones win."""
    lines = text.splitlines()
    return {nm.lower(): (k, nm, "\n".join(lines[a - 1:b])) for k, nm, a, b in _scan(text)}


def spans(text: str) -> dict:
    """{name_lower: (first_line, last_line)} for the definitions blocks() returns."""
    return {nm.lower(): (a, b) for _, nm, a, b in _scan(text)}


def closure(defs: dict, name: str) -> list:
    """The definition of `name` and everything it references, deps first."""
    order, seen = [], set()

    def visit(key):
        if key in seen or key not in defs:
            return
        seen.add(key)
        _, nm, body = defs[key]
        # strip comments before looking for references
        code = "\n".join(line.split(";")[0] for line in body.splitlines()
                         if not line.lstrip().startswith("*"))
        for tok in set(re.findall(r"[A-Za-z0-9_.\-+$#]+", code)):
            t = tok.lower()
            if t != key and t in defs:
                visit(t)
        order.append(key)

    visit(name.lower())
    return [defs[k] for k in order]


def code_hash(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        s = re.split(r";|\s\$\s", s)[0]
        lines.append(re.sub(r"\s+", " ", s).upper())
    return hashlib.sha1("\n".join(lines).encode()).hexdigest()


class Files:
    """Each model file read once, however many parts ask about it."""

    def __init__(self, root: Path):
        self.root = root
        self.cache: dict[str, tuple] = {}

    def get(self, file: str) -> tuple:
        """(definitions, spans, sha256) of one file, named as the catalogue names it."""
        if file not in self.cache:
            raw = (self.root / file).read_bytes()
            text = decode(raw)
            self.cache[file] = (blocks(text), spans(text), hashlib.sha256(raw).hexdigest())
        return self.cache[file]


# --- where a file came from --------------------------------------------------------------------------
def provenance(root: Path, file: str, source: str, sha256: str) -> dict:
    """Where the file came from, as far as the source's manifest can tell."""
    prov = {"source": source, "file": file, "file_sha256": sha256}
    rel = Path(file).relative_to("sources")
    sdir = root / "sources" / rel.parts[0]
    mdirs = [sdir / rel.parts[1]] if len(rel.parts) > 2 else []
    mdirs.append(sdir)
    for mdir in mdirs:
        man_p = mdir / "manifest.json"
        if not man_p.exists():
            continue
        man = json.loads(man_p.read_text(encoding="utf-8"))
        prov["fetched"] = man.get("fetched")
        relf = str((root / file).relative_to(mdir))
        files = man.get("files", [])
        hit = next((f for f in files if f.get("path") == relf), None)
        if hit:
            # `page` is where a person reads it when there is no direct file URL (forum post, product page)
            prov.update(url=hit.get("url") or hit.get("page") or None, note=hit.get("note") or None)
            if hit.get("fetched"):          # files added by a later fetch carry their own date
                prov["fetched"] = hit["fetched"]
            return prov
        # unpacked from an archive: extracted/<archive-name>/<member>
        parts = Path(relf).parts
        if parts and parts[0] == "extracted" and len(parts) > 2:
            arch_dir, member = parts[1], str(Path(*parts[2:]))
            cands = [f for f in files if Path(f.get("path") or "").suffix.lower() in ARCHIVE_EXT
                     or (f.get("url") or "").lower().endswith(ARCHIVE_EXT)]
            best = None
            for f in cands:
                stem = Path(f.get("path") or f.get("url") or "").name
                for ext in ARCHIVE_EXT:
                    stem = stem[:-len(ext)] if stem.lower().endswith(ext) else stem
                if stem and (stem == arch_dir or stem in arch_dir or arch_dir in stem):
                    best = f
            prov["member"] = member
            prov["archive_dir"] = str(Path(*parts[:2]))
            if best:
                prov["archive"] = {"path": best.get("path"), "url": best.get("url"),
                                   "sha256": best.get("sha256")}
                prov["url"] = best.get("url") or best.get("page")
                if best.get("fetched"):
                    prov["fetched"] = best["fetched"]
            return prov
        # not listed one by one (the installer / archive was not kept): fall back to the source's own
        # link, so a reader is always told where the model comes from
        site = next((f.get("url") or f.get("page") for f in files if f.get("url") or f.get("page")), None)
        prov["url"] = site
        prov["note"] = ("file not listed in the manifest; the URL above is the source, not this file -- "
                        "see SOURCE.md" if site else "file not listed in the manifest; see SOURCE.md")
        return prov
    return prov


def model_type(kind: str, body: str) -> str:
    if kind != "model":
        return "SUBCKT"
    m = re.match(r"\.model\s+\S+\s+(?:ako:\s*\S+\s+)?([A-Za-z]+)", body.lstrip(), re.I)
    return m.group(1).upper() if m else ""


# --- grouping ----------------------------------------------------------------------------------------
def groups_for(entry: dict, files: Files) -> tuple[list[dict], int]:
    """The distinct models among one part's candidates, most original first, and how many there are."""
    cands = [c for c in entry["candidates"] if not c["encrypted"] and not excluded(c["file"])]
    strong = [c for c in cands if not c["match"].endswith("grade")]
    if strong:
        cands = strong
    groups: dict[str, dict] = {}
    for c in cands:
        try:
            defs, sp, sha = files.get(c["file"])
            chain = closure(defs, c["name"])
            if not chain:
                continue
            h = code_hash("\n".join(b for _, _, b in chain))
        except Exception:                      # unreadable file
            continue
        g = groups.setdefault(h, {"hash": h, "members": [], "best": None, "chain": None})
        g["members"].append(c)
        if g["best"] is None or rank(c["source"]) < rank(g["best"]["source"]):
            g["best"], g["chain"], g["spans"], g["sha"] = c, chain, sp, sha
    ordered = sorted(groups.values(), key=lambda g: (rank(g["best"]["source"]), -len(g["members"])))
    return ordered, len(groups)


def record(g: dict, root: Path) -> dict:
    """One distinct model as the curation and the recipe need it: what it is, where the chosen copy came
    from, and every other source holding the same code."""
    c, chain = g["best"], g["chain"]
    kind, name, body = chain[-1]
    prov = provenance(root, c["file"], c["source"], g["sha"])
    prov["lines"] = {nm: list(g["spans"][nm.lower()]) for _, nm, _ in chain if nm.lower() in g["spans"]}
    return {"hash": g["hash"], "source": c["source"], "name": name, "def": kind,
            "type": model_type(kind, body), "pins": c["pins"], "match": c["match"],
            "deps": [nm for _, nm, _ in chain[:-1]], "provenance": prov,
            "copies": [{"source": m["source"], "file": m["file"], "name": m["name"]}
                       for m in g["members"] if m is not c]}


def find(matches: dict, root: Path) -> dict:
    files = Files(root)
    out = {}
    for part, entry in matches.items():
        ordered, n = groups_for(entry, files)
        out[part] = {"kind": entry["kind"], "group": entry["group"], "priority": entry["priority"],
                     "distinct": n, "models": [record(g, root) for g in ordered]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    matches = json.loads(require(spice_matches(), "grouping the matches").read_text(encoding="utf-8"))
    found = find(matches, spice_models_root())
    out = spice_found()
    out.write_text(json.dumps(found, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    models = [m for v in found.values() for m in v["models"]]
    print(f"{sum(1 for v in found.values() if v['models']):,} parts, {len(models):,} distinct models "
          f"({sum(len(m['copies']) for m in models):,} further copies of them) -> {out.name}")
    by_source = Counter(m["source"] for m in models)
    print("attributed to: " + ", ".join(f"{s} {n:,}" for s, n in by_source.most_common(12)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
