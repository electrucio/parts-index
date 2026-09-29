"""Find every `.model` and `.subckt` in the model sources, and record what each file yielded.

    pidx models index            rebuild the catalogue and stamp the ledgers
    pidx models index --missing  what a previous catalogue had that the tree no longer holds

Vendors use any extension they like — `.lib`, `.301`, `.dio`, `.mos`, `.bjt`, `.prm`, none at all — so the
scanner filters by what is certainly **not** a model rather than by what might be one. That asymmetry is
deliberate and was learned the hard way: an allow-list of extensions silently dropped 59,407 definitions.

One JSON record per definition goes to the catalogue, and each source's ledger gets the number of
definitions its files produced, so `pidx status` can say which downloads turned out to hold nothing.

The catalogue is private: three quarters of its records carry the model's own parameters, which is the
model itself. What becomes public is the recipe — where to get the file, and what we measured from it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from parts_index.core.config import (
    model_sources,
    model_state,
    require,
    spice_definitions,
    spice_models_root,
    spice_source_manifest,
)
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger

VERSION = "index_models-1"

SKIP_DIRS = {".git", "__MACOSX", "node_modules"}
MAX_BYTES = 40_000_000

# Parameters worth keeping in the catalogue; the rest stay in the file.
KEEP_PARAMS = {"mfg", "vceo", "icrating", "vds", "ron", "qg", "vbv", "bv", "ibv", "iave", "vpk", "ipk",
               "type", "is", "bf", "vto", "beta", "n", "rs", "cjo", "vj", "tt", "eg", "vaf", "ikf", "rb",
               "kp", "lambda", "level", "vt0", "rd"}

# What no vendor ever ships a model in.
NOT_MODELS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".zip", ".7z", ".gz", ".tgz",
              ".rar", ".exe", ".msi", ".dll", ".asy", ".html", ".htm", ".css", ".js", ".json", ".md",
              ".py", ".plt", ".raw", ".log", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ico", ".ttf",
              ".wav", ".mp3", ".xml", ".kicad_mod", ".kicad_sch", ".kicad_pcb", ".kicad_sym", ".olb",
              ".opj"}

RX_MODEL = re.compile(r"^\.model\s+(\S+)\s+(?:ako:\s*\S+\s+)?([A-Za-z_]+)\s*(.*)$", re.I)
RX_SUBCKT = re.compile(r"^\.subckt\s+(\S+)\s*(.*)$", re.I)
RX_ENDS = re.compile(r"^\.ends\b", re.I)
RX_PARAM = re.compile(r"([A-Za-z_][\w.]*)\s*=\s*(\{[^}]*\}|\"[^\"]*\"|[^\s,()]+)")


def decode(blob: bytes) -> str:
    if blob[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(blob) > 20 and blob[:200].count(b"\x00") > 40):
        enc = "utf-16-be" if blob[:2] == b"\xfe\xff" else "utf-16-le"
        return blob.decode(enc, "replace").lstrip("﻿")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


# A QSPICE symbol (.qsym) carries its model inside it: a «library file: |…» field whose text is the
# netlist, with each line break written as `\n`. A field without the `|` names a file instead.
RX_QSYM_MODEL = re.compile(r"«library file: \|(.*?)»", re.S)


def model_text(blob: bytes, name: str) -> str:
    """The SPICE text a file holds: the file itself, or for a QSPICE symbol the netlists embedded in it.

    A symbol's netlists are joined one after another, so the line numbers counted in the result are
    not lines of the file; `embedded()` says which files that is true of.
    """
    if not embedded(name):
        return decode(blob)
    text = blob.decode("latin-1")
    return "\n".join(m.group(1).replace("\\n", "\n") for m in RX_QSYM_MODEL.finditer(text))


def embedded(name: str) -> bool:
    return name.lower().endswith(".qsym")


def looks_binary(blob: bytes) -> bool:
    head = blob[:4096]
    if head.startswith((b"PK\x03\x04", b"%PDF", b"\x89PNG", b"GIF8", b"\xd0\xcf\x11\xe0")):
        return True
    nul = head.count(b"\x00")
    utf16 = head[:2] in (b"\xff\xfe", b"\xfe\xff") or nul > len(head) // 3
    return nul > 0 and not utf16


def logical_lines(text: str):
    """Yield (lineno, joined_line, comment_block) with SPICE `+` continuations joined."""
    buf, start, comments, pending = None, 0, [], []
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.rstrip().lstrip()
        if not s:
            continue
        if s.startswith("*"):
            pending.append(s.lstrip("*").strip())
            pending = pending[-8:]
            continue
        s = re.split(r";|\s\$\s", s, maxsplit=1)[0].rstrip()      # inline comments, LTspice and HSPICE styles
        if s.startswith("+"):
            if buf is not None:
                buf += " " + s[1:].strip()
            continue
        if buf is not None:
            yield start, buf, comments
        buf, start, comments, pending = s, i, pending, []
    if buf is not None:
        yield start, buf, comments


def parse_params(s: str) -> dict:
    return {k.lower(): v.strip('"') for k, v in RX_PARAM.findall(s) if k.lower() in KEEP_PARAMS}


def scan_file(path: Path, rel: str, source: str) -> list[dict]:
    """Every definition in one file. Returns [] for anything that is not SPICE text."""
    try:
        blob = path.read_bytes()
    except OSError:
        return []
    if len(blob) > MAX_BYTES or (looks_binary(blob) and not embedded(path.name)):
        return []
    text = model_text(blob, path.name)
    low = text.lower()
    if ".model" not in low and ".subckt" not in low:
        # A wholly LTspice-encrypted file: LTspice can use it, nobody can read it. The file name is the
        # only name available, so one record says "this part has a vendor model, and it is encrypted".
        if low.lstrip().startswith("* ltspice encrypted file"):
            name = re.sub(r"(_G\d_\d\d)?_LTspice.*$|_LT$|_enc$", "", path.stem, flags=re.I)
            return [{"name": name, "kind": "subckt", "type": "ENCRYPTED", "pins": [], "params": {},
                     "parent": None, "line": 1, "source": source, "file": rel, "encrypted": True,
                     "enc_kind": "ltspice", "mfg": None,
                     "comment": "LTspice-encrypted file; name taken from the file name"}]
        return []
    pspice_enc = "$cdnencstart" in low
    lt_enc = "ltspice encrypted" in low or ("* begin:" in low and "* end:" in low)
    recs: list[dict] = []
    sub_stack: list[str] = []
    for lineno, line, comments in logical_lines(text):
        m = RX_SUBCKT.match(line)
        if m:
            parts = re.split(r"\b(?:params|param)\s*:", m.group(2), maxsplit=1, flags=re.I)
            pins_part = parts[0]
            params_part = parts[1] if len(parts) > 1 else " ".join(p for p in pins_part.split() if "=" in p)
            recs.append({"name": m.group(1), "kind": "subckt", "type": "SUBCKT",
                         "pins": [p for p in pins_part.split() if "=" not in p],
                         "params": dict(RX_PARAM.findall(params_part)),
                         "parent": sub_stack[-1] if sub_stack else None, "line": lineno,
                         "comment": " | ".join(c for c in comments if c)[:400]})
            sub_stack.append(m.group(1))
            continue
        if RX_ENDS.match(line):
            if sub_stack:
                sub_stack.pop()
            continue
        m = RX_MODEL.match(line)
        if m:
            recs.append({"name": m.group(1), "kind": "model", "type": m.group(2).upper(), "pins": [],
                         "params": parse_params(m.group(3)),
                         "parent": sub_stack[-1] if sub_stack else None, "line": lineno,
                         "comment": " | ".join(c for c in comments if c)[:400]})
    for r in recs:
        r.update(source=source, file=rel, encrypted=bool(pspice_enc or lt_enc),
                 enc_kind="pspice" if pspice_enc else ("ltspice" if lt_enc else None))
        r["mfg"] = r["params"].pop("mfg", None) if r["kind"] == "model" else None
    return recs


def iter_files(root: Path):
    """Every file that could hold SPICE text: filter by what certainly is not one."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in NOT_MODELS and not fn.startswith("."):
                yield p


def scan(sources_dir: Path, only: list[str] | None = None) -> tuple[list[dict], int]:
    """Scan every source (or the named ones). Returns (records, files that yielded something)."""
    out: list[dict] = []
    n_files = 0
    for d in sorted(p for p in sources_dir.iterdir() if p.is_dir()):
        if only and d.name not in only:
            continue
        for p in iter_files(d):
            rel = f"sources/{p.relative_to(sources_dir)}"
            source = d.name
            parts = p.relative_to(d).parts                    # a source may hold sub-sources of its own
            if len(parts) > 1 and (d / parts[0] / "SOURCE.md").exists():
                source = f"{d.name}/{parts[0]}"
            recs = scan_file(p, rel, source)
            n_files += bool(recs)
            out.extend(recs)
    return out, n_files


def manifests(source: str) -> list[tuple[str, dict]]:
    """(folder, manifest) for this source's manifest and each one a sub-folder keeps of its own.

    Vishay's catalogues were fetched into `semis/`, `passives/` and `ic-and-power/`, each with a
    manifest whose paths are relative to that folder. The folder is returned so paths can be put back
    relative to the source, which is how the catalogue names files.
    """
    top = spice_source_manifest(source)
    found = [top] + sorted(top.parent.glob("*/manifest.json")) if top.parent.exists() else []
    out = []
    for mf in found:
        if mf.exists():
            folder = "" if mf == top else mf.parent.name
            out.append((folder, json.loads(mf.read_text(encoding="utf-8"))))
    return out


def under(folder: str, rel: str) -> str:
    return f"{folder}/{rel}" if folder else rel


def entry_paths(source: str) -> list[tuple[str, str]]:
    """(ledger key, path inside the source) for every file the manifests list.

    The ledger is public and holds only URLs; which local file each URL became is in the source's own
    manifests, which are private. This is the one place the two are joined. One URL may stand for
    several files — a forum thread's attachments, a data sheet and the model transcribed from it.
    """
    out = []
    for folder, man in manifests(source):
        for x in man.get("files", []):
            path, url = x.get("path") or "", x.get("url") or ""
            if path:
                out.append((url or f"manual:{under(folder, path)}", under(folder, path)))
    return out


def ledger_paths(source: str) -> dict[str, str]:
    """Ledger key -> the first path inside the source that key stands for."""
    out: dict[str, str] = {}
    for key, path in entry_paths(source):
        out.setdefault(key, path)
    return out


def yielded_into(entry: dict) -> str:
    """The folder a manifest entry's contents live in, when it says so.

    An archive is normally unpacked into `extracted/<its stem>/`, which is how its definitions find
    their way back to it. Many were not: Micro-Cap's installer zip was unpacked at `extracted/` itself,
    Toshiba's bulk zips into `extracted/<category>/`, and QSPICE's encrypted payload can only be
    installed, its library copied out of the install. The manifest entry then names that folder —
    `unpacked_to` (or the older `extracted_to`) for an archive, `installed.into` for an installer — and
    everything under it is credited to that entry's URL.
    """
    folder = (entry.get("unpacked_to") or entry.get("extracted_to")
              or (entry.get("installed") or {}).get("into") or "")
    return folder.strip("/")


def yields(source: str) -> list[tuple[str, str]]:
    """(ledger key, folder relative to the source) for each manifest entry that names where it went."""
    out = []
    for folder, man in manifests(source):
        for x in man.get("files", []):
            into = yielded_into(x)
            if into and x.get("url"):
                out.append((x["url"], under(folder, into)))
    return out


def credit(source: str, rels, keys: set[str]) -> dict[str, str]:
    """For each definition file of a source (its path inside the source), the ledger key it counts for.

    In order: a folder a manifest entry says it went into (the deepest one wins), the file itself as
    downloaded, or `extracted/<stem>/` for an archive whose stem it is. A file none of these reach is
    not credited — `pidx models reconcile` lists those.
    """
    pairs = [(k, rel) for k, rel in entry_paths(source) if k in keys]
    by_rel: dict[str, str] = {}
    by_stem: dict[str, str] = {}
    for k, rel in pairs:
        by_rel.setdefault(rel, k)
        by_stem.setdefault(Path(rel).stem.lower(), k)
    declared = sorted(((k, f) for k, f in yields(source) if k in keys), key=lambda x: -len(x[1]))
    out: dict[str, str] = {}
    for rel in rels:
        hit = next((k for k, f in declared if rel.startswith(f + "/")), None)
        if hit is None:
            parts = rel.split("/")
            hit = by_rel.get(rel) or (by_stem.get(parts[1].lower())
                                      if parts[0] == "extracted" and len(parts) > 1 else None)
        if hit:
            out[rel] = hit
    return out


def files_by_source(records: list[dict]) -> dict[str, Counter]:
    """{source: {path inside the source: definitions}}, the source as the registry names it."""
    out: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        parts = r["file"].split("/", 2)
        if parts[0] == "sources" and len(parts) == 3:
            out[parts[1]][parts[2]] += 1
    return out


def downloaded(led: Ledger) -> set[str]:
    return {k for k, r in led.rows.items() if not k.startswith("part:") and r["status"] == "downloaded"}


def stamp_ledgers(records: list[dict], at: str | None = None) -> dict[str, int]:
    """Record against each downloaded file how many definitions it turned out to hold."""
    files = files_by_source(records)
    touched: dict[str, int] = {}
    for reg in sorted(model_sources().glob("*.yaml")):
        source = reg.stem
        path = model_state(source)
        if not path.exists():
            continue
        led = Ledger(path, stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)
        keys = downloaded(led)
        counts: Counter = Counter()
        for rel, key in credit(source, files.get(source, {}), keys).items():
            counts[key] += files[source][rel]
        n = 0
        for key in sorted(keys):
            row, defs = led.rows[key], counts.get(key, 0)
            if row.get("index_v") == VERSION and row.get("index_at") and row.get("n_defs", "") == str(defs or ""):
                continue                    # nothing learnt: a stamp would only move the date
            led.stamp(key, "index", version=VERSION, when=at, n_defs=str(defs or ""))
            n += 1
        if n:
            led.save()
            touched[source] = n
    return touched


def missing(reference: Path, sources_dir: Path) -> list[dict]:
    """Files a previous catalogue recorded that the tree no longer holds, with what each yielded."""
    seen: dict[str, int] = defaultdict(int)
    with open(reference, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["file"].startswith("sources/"):
                seen[r["file"]] += 1
    gone = []
    for rel, n in sorted(seen.items()):
        if not (sources_dir.parent / rel).exists():
            gone.append({"file": rel, "source": rel.split("/")[1], "definitions": n})
    return gone


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--missing", action="store_true", help="report what a previous catalogue had and the tree lacks")
    ap.add_argument("--stats", action="store_true", help="also print counts per source")
    ap.add_argument("-o", "--out", help="where to write the catalogue")
    a = ap.parse_args(argv)

    sources_dir = require(spice_models_root() / "sources", "indexing the SPICE models")
    out = Path(a.out) if a.out else spice_definitions()

    if a.missing:
        if not out.exists():
            print(f"no catalogue at {out} to compare against", file=sys.stderr)
            return 1
        gone = missing(out, sources_dir)
        total = sum(g["definitions"] for g in gone)
        by = Counter(g["source"] for g in gone)
        print(f"{len(gone):,} files are gone, holding {total:,} definitions")
        for src, n in by.most_common():
            d = sum(g["definitions"] for g in gone if g["source"] == src)
            print(f"  {src:24s} {n:5,} files  {d:8,} definitions")
        return 0

    records, n_files = scan(sources_dir, a.source)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(records):,} definitions from {n_files:,} files -> {out}")

    touched = stamp_ledgers(records)
    print(f"stamped {sum(touched.values()):,} files across {len(touched)} source ledgers")
    if a.stats:
        by = Counter((r["source"], r["kind"] if r["kind"] == "subckt" else r["type"]) for r in records)
        for src in sorted({s for s, _ in by}):
            row = {t: c for (s, t), c in by.items() if s == src}
            print(f"  {src:<26} " + "  ".join(f"{t}={c}" for t, c in sorted(row.items(), key=lambda x: -x[1])[:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
