"""Group each part's matches into distinct models, and say where every copy of each can be had.

    pidx models found

`pidx models match` lists every definition that could be a part's model; many of them are the same
model copied from one collection into the next. This reads each one with everything it references in
its own file, hashes the code — comments and whitespace removed, case folded — and groups identical
code into one model, attributed to the most original source that holds it (`SOURCE_RANK`), with the
others as its copies. For every model it records how to obtain it — the URL, the archive member, the
file's checksum, the line range of each definition — from the source's manifest. Two copies are the
same model when they differ only in the names of their own definitions, or, for a `.model`, only in
how its parameters are written out (`code_hash`).

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
from parts_index.models.index import embedded, model_text

# Most original first. Vendors > LTspice's own lib (mostly vendor models, curated by ADI) > authors
# who fitted models themselves > aggregations of other people's files. A source missing from the list
# ranks after all of them.
SOURCE_RANK = [
    "onsemi", "nexperia", "nxp", "ti", "infineon", "vishay", "rohm", "toshiba",
    "diodes-inc", "central-semi", "linear-systems", "interfet", "stmicro", "exicon",
    "microchip", "renesas", "nisshinbo", "sanken", "onsemi-ic", "adi", "nichia",
    "ltspice-native",
    # vendor libraries as another party distributed them: OrCAD's 1990s set on the Spice Model CD, and
    # the libraries Micro-Cap and QSPICE install
    "spice-model-cd", "microcap12", "qspice",
    "cordell", "reefman", "ayumi", "duncanamps", "koren", "suusi-tubes",
    "germaniumbjts", "hagtech", "andyc", "viva-analog", "cohen-helie", "dempwolf",
    "tedyapo-led-modeling", "z101-led-spice-model",
    "germanium-apm", "bordodynov", "bordodynov-qspice", "ltwiki", "kicad-spice-library", "spiceypedals",
    "gist-chanmix51", "electrucio",
]
RANK = {s: i for i, s in enumerate(SOURCE_RANK)}
# Path globs, relative to the model tree, whose definitions never become candidates: other simulators'
# syntax and superseded editions. Ayumi ships each model three times; win/ is the LTspice one.
EXCLUDE = ["sources/ayumi/extracted/simetrix/**", "sources/ayumi/extracted/linux/**",
           # edited during a delivery (a collection with AC127 added, another enlarged): published
           # nowhere, so no link can lead to them
           "sources/groupsio-ltspice/raw/standard_collections_RAW_no_curado/standard.with_AC127.bjt",
           "sources/groupsio-ltspice/raw/standard_collections_RAW_no_curado/standard_PB_enlarged.bjt",
           # Bordodynov's example schematics: the models in them are copies of his library, other
           # people's teaching models and test cards named whatever the exercise needed (N_50N, Test,
           # 2N3904P) — read for the benches and circuits around them, never as a part's model
           "sources/bordodynov/extracted/example/**"]
ARCHIVE_EXT = (".zip", ".7z", ".tgz", ".gz", ".rar", ".msi", ".tar")


def excluded(file: str) -> bool:
    return any(fnmatch.fnmatch(file, g) for g in EXCLUDE)


def registered(source: str) -> str:
    """The registry id of a source. The indexer names a folder with a manifest of its own after both,
    `vishay/semis`, which is the right key for its manifest and not a source of its own."""
    return source.split("/")[0]


def rank(source: str) -> int:
    return RANK.get(registered(source), 99)


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
        # sorted, because a set of strings iterates in a different order in every run, and the order
        # the dependencies are visited in is the order they are listed and hashed in
        for tok in sorted(set(re.findall(r"[A-Za-z0-9_.\-+$#]+", code))):
            t = tok.lower()
            if t != key and t in defs:
                visit(t)
        order.append(key)

    visit(name.lower())
    return [defs[k] for k in order]


SCALE = {"T": 1e12, "G": 1e9, "MEG": 1e6, "K": 1e3, "MIL": 25.4e-6, "M": 1e-3, "U": 1e-6, "N": 1e-9,
         "P": 1e-12, "F": 1e-15}
RX_NUMBER = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:E[+-]?\d+)?)(MEG|MIL|[TGKMUNPF])?[A-Z]*$")
RX_MODEL_HEAD = re.compile(r"^\.MODEL\s+\S+\s+(?:AKO:\s*\S+\s+)?([A-Z]+)\s*(.*)$", re.S)


def value(s: str) -> str:
    """A SPICE number in one spelling — 1.2N, 1.2E-9 and 0.0000000012 alike — or the text as it is."""
    m = RX_NUMBER.match(s)
    if not m:
        return s
    return repr(float(m.group(1)) * SCALE.get(m.group(2) or "", 1.0))


def code_lines(text: str) -> list[str]:
    """Code without comment lines, trailing comments, case, spacing or `+` line breaks."""
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        s = re.split(r";|\s\$\s", s)[0].strip()
        s = re.sub(r"\s+", " ", s).upper()
        if s.startswith("+") and lines:
            lines[-1] += " " + s[1:].strip()
        elif s:
            lines.append(s)
    return lines


def model_params(code: str) -> str | None:
    """A `.model` statement as its device type and parameters, in order, each value in one spelling.

    A parameter at zero is left out, and so is AF=1, because a library that rewrites a model — sorting
    its parameters, dropping the ones at their default — has not changed it: Bordodynov's MJ15001M is
    Motorola's 1997 Qmj15001 with CJS=0 PTF=0 KF=0 AF=1 dropped and the rest in alphabetical order.
    For almost every SPICE parameter zero is the default or means "infinite", which is its default.
    """
    m = RX_MODEL_HEAD.match(code)
    if not m:
        return None
    body = m.group(2).replace("(", " ").replace(")", " ").replace(",", " ")
    params = dict(re.findall(r"([A-Z_][A-Z0-9_]*)\s*=\s*(\S+)", body))
    kept = {k: value(v) for k, v in params.items()}
    kept = {k: v for k, v in kept.items() if v not in ("0.0", "-0.0") and not (k == "AF" and v == "1.0")}
    return m.group(1) + " " + " ".join(f"{k}={kept[k]}" for k in sorted(kept))


def code_hash(chain: list) -> str:
    """One model's identity: its code with every definition in it renamed by position, so a copy that
    only renamed the model (Q2N3904 for 2N3904, MJ15001M for Qmj15001) is still the same model, and each
    `.model` compared by its parameters rather than by how they were written out."""
    names = {nm.upper(): f"@{i}" for i, (_, nm, _) in enumerate(chain)}
    rename = re.compile(r"(?<![A-Z0-9_.\-+$#])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                        + r")(?![A-Z0-9_.\-+$#])") if names else None
    out = []
    for kind, _, body in chain:
        lines = code_lines(body)
        if rename:
            lines = [rename.sub(lambda m: names[m.group(1)], s) for s in lines]
        if kind == "model" and len(lines) == 1:
            out.append(model_params(lines[0]) or lines[0])
        else:
            out.extend(lines)
    return hashlib.sha1("\n".join(out).encode()).hexdigest()


class Files:
    """Each model file read once, however many parts ask about it."""

    def __init__(self, root: Path):
        self.root = root
        self.cache: dict[str, tuple] = {}

    def get(self, file: str) -> tuple:
        """(definitions, spans, sha256) of one file, named as the catalogue names it."""
        if file not in self.cache:
            raw = (self.root / file).read_bytes()
            text = model_text(raw, file)
            self.cache[file] = (blocks(text), spans(text), hashlib.sha256(raw).hexdigest())
        return self.cache[file]

    def at(self, file: str, line: int) -> tuple | None:
        """(kind, name, text) of the definition that starts at this line (1-based), or None.

        `get` keeps the last definition of a name, as a simulator reading the file would; a card chosen by
        its place — the index names every definition by file and line — may be an earlier one of the same
        name, and is read here from its own lines. The file is read again rather than kept: this is asked
        rarely, and keeping every file's text would double what a `found` run holds in memory."""
        text = model_text((self.root / file).read_bytes(), file)
        lines = text.splitlines()
        for kind, nm, a, b in _scan(text):
            if a == line:
                return kind, nm, "\n".join(lines[a - 1:b])
        return None


def hash_at(files: Files, file: str, line: int) -> str | None:
    """The identity (`code_hash`) of the definition starting at one line of a file, with everything it
    references: how a result measured on a card chosen by its place is joined to a recipe's model."""
    block = files.at(file, line)
    if block is None:
        return None
    defs = dict(files.get(file)[0])
    defs[block[1].lower()] = block
    chain = closure(defs, block[1])
    return code_hash(chain) if chain else None


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
        declared = declared_origin(files, relf)
        if declared:
            prov.update(declared)
            return prov
        hit = next((f for f in files if f.get("path") == relf), None)
        if hit:
            # `page` is where a person reads it when there is no direct file URL (forum post, product page)
            prov.update(url=hit.get("url") or hit.get("page") or None, note=hit.get("note") or None)
            if hit.get("page_only"):        # the listing page that offers the file, not the file
                prov["url_is_source_page"] = True
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
        prov["url_is_source_page"] = bool(site)
        prov["note"] = ("file not listed in the manifest; the URL above is the source, not this file -- "
                        "see SOURCE.md" if site else "file not listed in the manifest; see SOURCE.md")
        return prov
    return prov


def declared_origin(files: list[dict], relf: str) -> dict | None:
    """Where a file came from when its manifest entry says which folder it went into.

    `unpacked_to`: the archive's root was unpacked into that folder, so the file's path below it is its
    member name — Micro-Cap's `LIBRARY/mpbjt.lib`, not the `mpbjt.lib` a guess from the folder name
    gives. `installed`: the file was copied out of an installed product that cannot be had any other
    way, so the honest answer is the product and the file's place in it, not the installer's URL.
    """
    for f in files:
        folder = (f.get("unpacked_to") or f.get("extracted_to")
                  or (f.get("installed") or {}).get("into") or "").strip("/")
        if not folder or not relf.startswith(folder + "/"):
            continue
        member = relf[len(folder) + 1:]
        inst = f.get("installed")
        out = {"fetched": f["fetched"]} if f.get("fetched") else {}
        if inst:
            return {**out, "url": None, "origin": inst.get("product", ""),
                    "installed_file": f"${inst.get('var', 'INSTALL_DIR')}/{member}"}
        return {**out, "url": f.get("url"), "member": member,
                "archive": {"path": f.get("path"), "url": f.get("url"), "sha256": f.get("sha256")}}
    return None


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
            defs, _, _ = files.get(c["file"])
            chain = closure(defs, c["name"])
            if not chain:
                continue
            h = code_hash(chain)
        except Exception:                      # unreadable file
            continue
        g = groups.setdefault(h, {"hash": h, "members": [], "best": None, "chain": None})
        g["members"].append(c)
        if g["best"] is None or rank(c["source"]) < rank(g["best"]["source"]):
            g["best"], g["chain"] = c, chain
    ordered = sorted(groups.values(), key=lambda g: (rank(g["best"]["source"]), -len(g["members"])))
    return ordered, len(groups)


def located(root: Path, files: Files, c: dict) -> dict:
    """Where one copy came from, with the line range of each definition it is made of."""
    defs, sp, sha = files.get(c["file"])
    prov = provenance(root, c["file"], c["source"], sha)
    if embedded(c["file"]):
        # inside a QSPICE symbol's «library file» field: the checksum names the file, no line range does
        prov["embedded_in_symbol"] = True
    else:
        prov["lines"] = {nm: list(sp[nm.lower()]) for _, nm, _ in closure(defs, c["name"]) if nm.lower() in sp}
    return prov


def record(g: dict, root: Path, files: Files) -> dict:
    """One distinct model as the curation and the recipe need it: what it is, where the chosen copy came
    from, and where every other source holding the same code has it."""
    c, chain = g["best"], g["chain"]
    kind, name, body = chain[-1]
    return {"hash": g["hash"], "source": registered(c["source"]), "name": name, "def": kind,
            "type": model_type(kind, body), "pins": c["pins"], "match": c["match"],
            "deps": [nm for _, nm, _ in chain[:-1]], "provenance": located(root, files, c),
            "copies": [{"source": registered(m["source"]), "file": m["file"], "name": m["name"],
                        "provenance": located(root, files, m)}
                       for m in g["members"] if m is not c]}


def find(matches: dict, root: Path) -> dict:
    files = Files(root)
    out = {}
    for part, entry in matches.items():
        ordered, n = groups_for(entry, files)
        out[part] = {"kind": entry["kind"], "group": entry["group"], "priority": entry["priority"],
                     "distinct": n, "models": [record(g, root, files) for g in ordered]}
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
