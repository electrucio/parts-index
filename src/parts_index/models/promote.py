"""Turn the curated model directories into the public recipe for each part.

    pidx models promote

The curated tree — `config.spice_curated()`, one directory per part holding its `part.json` — is where
the judgement lives: every model found for a part, where each came from, how each scored against the
datasheet, and which one was preferred and why. That judgement is the most valuable thing the project
holds and the only part of it that cannot be downloaded again, so it belongs in git rather than in a
private tree.

What crosses the line is metadata, never model text. For each candidate this writes the source, the name
and shape of the definition, and a `get:` block saying exactly how to obtain it — URL, the member inside
the archive when there is one, the checksums and the line range. A reader ends up with the same bytes we
have, from the vendor, which is what rule 2 asks for: forbidding redistribution does not forbid indexing.

Everything naming the private tree is dropped, by allow-list rather than by blocking: local paths, the
manifest, the licence file and the downloaded datasheet PDF. The licence itself is **not** copied in — it
lives once in the source's registry entry, and a copy here would go stale the day a source is reviewed.
The part file names the source, and the reader joins.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from parts_index.core.config import (
    model_changes,
    model_part,
    model_sources,
    model_symbol,
    require,
    spice_curated,
)
from parts_index.models.fetch import archive_for, source_files


class Flow(list):
    """A list YAML writes inline. A line range reads as `[250, 250]`, not as three lines."""


yaml.SafeDumper.add_representer(
    Flow, lambda d, data: d.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True))

VERSION = "promote_models-1"
# `preferred_why` was written for the maintainer and ends by naming the tool that decided. That file is
# not published, so the sentence keeps its reasoning and loses the reference.
TOOL_REF = re.compile(r"\s*\((?:tools/)?[\w/]+\.py\)\s*$")
# A note is prose the maintainer wrote for themselves, and a judgement is sometimes signed. The date is
# worth keeping and the name is not: the public side of this project carries no personal names.
SIGNED = re.compile(r"\(\s*[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?\s*,\s*(\d{4}-\d{2}-\d{2})\s*\)")


def unsigned(text: str) -> str:
    """Prose with any `(Name, date)` attribution reduced to `(maintainer, date)`."""
    return SIGNED.sub(lambda m: f"(maintainer, {m.group(1)})", text or "")


def parts(root: Path) -> list[Path]:
    """Every curated part, in a stable order so a rerun produces the same files."""
    return sorted(root.glob("*/*/part.json"))


def installed_from(prov: dict) -> tuple[str, str] | None:
    """For a model that ships inside a simulator, which product it is and where in its library.

    Some definitions have no URL at all: LTspice installs its own library, and the way to obtain those
    models is to install LTspice. The recipe has to say that instead of publishing an empty link. The
    path is recorded against a variable, `$LTSPICE_LIB/cmp/standard.dio`, and only the part below the
    library is a fact about the product — the rest is wherever that machine happened to put it.
    """
    if prov.get("url"):
        return None
    origin, file = (prov.get("origin") or "").split(";")[0].strip(), prov.get("file") or ""
    m = re.match(r"\$[A-Z_]+/(.*)", file)
    return (origin, m.group(1)) if origin and m else None


def from_archive(prov: dict) -> dict | None:
    """The archive a definition was unpacked from, when the curation did not record its URL.

    Curation copied the provenance of the file it read, and for a file that came out of an archive that
    is a path under `extracted/`, with no link in it. The link was never lost — it is in the manifest,
    against the archive — so the recipe is completed by the same join that recovery makes. Without it
    seventy-one models would say where they were verified and not where to get them.
    """
    parts = (prov.get("file") or "").split("/")
    if prov.get("url") or len(parts) < 4 or parts[0] != "sources" or parts[2] != "extracted":
        return None
    files = source_files(parts[1])
    hit, inferred = archive_for(files, parts[3], strict=True), False
    if not hit:
        # The folder does not name any archive, so fall back to the source's only one. That is an
        # inference, not a record, and the recipe says so: a reader can tell a link we followed from a
        # link we worked out, which rule 4 asks for whenever a wrong link would be worse than none.
        hit, inferred = archive_for(files, parts[3]), True
    if not hit:
        return None
    member = prov.get("member") or "/".join(parts[4:])
    out = {"url": hit["url"], "member": member, "archive_sha256": hit.get("sha256", "")}
    if inferred:
        out["archive_inferred"] = True
    return out


def get_block(prov: dict) -> dict:
    """How to obtain this definition, with nothing in it that names the private tree.

    A definition found inside an archive needs three facts, not one: the URL serves the archive, the
    member says which file inside it holds the definition, and the two checksums answer different
    questions — whether the download is the one we saw, and whether the file inside it is.
    """
    installed = installed_from(prov)
    if installed:
        out = {"installed_with": installed[0], "file": installed[1]}
        if prov.get("file_sha256"):
            out["sha256"] = prov["file_sha256"]
        if prov.get("lines"):
            out["lines"] = {k: Flow(v) for k, v in sorted(prov["lines"].items())}
        return out
    recovered = from_archive(prov)
    if recovered:
        out = {k: v for k, v in recovered.items() if v not in ("", None)}
    else:
        out = {"url": prov.get("url") or ""}
        if prov.get("member"):
            out["member"] = prov["member"]
            archive = prov.get("archive") or {}
            if archive.get("sha256"):
                out["archive_sha256"] = archive["sha256"]
        if not out["url"]:
            # Honest about the gap: the model was read and scored, but nothing recorded where it came
            # from. Saying so is better than publishing an empty link.
            out.pop("url")
            out["how"] = "unknown"
    if prov.get("file_sha256"):
        out["sha256"] = prov["file_sha256"]
    if prov.get("lines"):
        # {definition: [first, last]}, 1-based and inclusive, as the extractor recorded them.
        out["lines"] = {k: Flow(v) for k, v in sorted(prov["lines"].items())}
    if prov.get("fetched"):
        out["fetched"] = prov["fetched"]
    return out


def symbols(part_dir: Path, part: str) -> dict[str, str]:
    """The symbols drawn for this part, by the curated file each one is for.

    A symbol is named `<PART>_<candidate>.asy`, so it says which model it draws. Ones left over from a
    candidate the curation has since dropped are not returned: they would name a model the part no
    longer offers, and a symbol pointing at nothing is worse than no symbol.
    """
    out = {}
    for asy in sorted(part_dir.glob("*.asy")):
        if asy.stem.startswith(part + "_"):
            out[asy.stem[len(part) + 1:] + ".lib"] = asy.name
    return out


def score_block(v: dict | None) -> dict | None:
    """One candidate's agreement with its datasheet, with the two cryptic keys spelled out."""
    if not v:
        return None
    c = v.get("counts") or {}
    out = {"score": v.get("score")}
    for src, dst in (("pass", "pass"), ("off", "marginal"), ("fail", "fail"),
                     ("na", "not_measurable"), ("typ_rows", "typical_rows")):
        if src in c:
            out[dst] = c[src]
    if v.get("error"):
        out["error"] = v["error"]
    return out


def candidate(c: dict, scores: dict, syms: dict[str, str] | None = None) -> dict:
    """One model offered for this part: what it is, how to get it, how well it did."""
    prov = c.get("provenance") or {}
    changes = c.get("changes") or []
    out: dict = {
        "source": c.get("source") or prov.get("source", ""),
        "name": c.get("name", ""),
        "def": c.get("def", ""),
    }
    if c.get("type"):
        out["type"] = c["type"]
    if c.get("pins"):
        out["pins"] = list(c["pins"])
    if c.get("deps"):
        # Other top-level definitions this one references; they must travel with it.
        out["deps"] = list(c["deps"])
    out["verbatim"] = not changes
    if changes:
        # Our own fixups, named. What changed is our work and is worth publishing; the text is not.
        out["changes"] = [x["id"] if isinstance(x, dict) else str(x) for x in changes]
    out["get"] = get_block(prov)
    if prov.get("note"):
        out["get"]["note"] = unsigned(prov["note"])
    v = score_block(scores.get(c.get("file", "")))
    if v:
        out["verification"] = v
    if syms and c.get("file") in syms:
        out["symbol"] = syms[c["file"]]
    if c.get("note"):
        out["note"] = unsigned(c["note"])
    return out


def datasheet_block(d: dict | None) -> dict | None:
    """The datasheet the scores were read from: the link and what it is, never the downloaded copy."""
    if not d or not d.get("url"):
        return None
    return {k: d[k] for k in ("url", "maker", "doc", "date") if d.get(k)}


def recipe(data: dict, syms: dict[str, str] | None = None) -> dict:
    """The public record for one part."""
    scores = data.get("verification") or {}
    cands = [candidate(c, scores, syms) for c in data.get("candidates") or []]
    by_file = {c.get("file", ""): c for c in data.get("candidates") or []}
    pref = data.get("preferred") or ""
    out: dict = {"part": data.get("part", ""), "kind": data.get("kind", "")}
    if data.get("priority"):
        out["priority"] = data["priority"]
    if data.get("group"):
        out["group"] = data["group"]
    if pref and pref in by_file:
        out["preferred"] = by_file[pref].get("source") or by_file[pref].get("file", "")
    if data.get("preferred_why"):
        why = unsigned(TOOL_REF.sub("", data["preferred_why"]).strip())
        # The sentence names rivals by their curated file, `kicad-spice-library.lib`; the fields around
        # it name sources, so it says source too and the two agree.
        for f, c in by_file.items():
            if f and c.get("source"):
                why = why.replace(f, c["source"])
        out["preferred_why"] = why
    out["models"] = cands
    ds = datasheet_block(data.get("datasheet"))
    if ds:
        out["datasheet"] = ds
    return out


def change_kinds(root: Path) -> dict[str, str]:
    """Every fixup the curation names, with the reason recorded once instead of at each use.

    The reason is the valuable half and it is our own writing: that LTspice reads `^` as Boolean XOR,
    so an author's `2^3` silently evaluates to zero, is the kind of thing this project exists to record.
    The patch itself stays private — a diff carries the vendor's surrounding lines, which is model text.
    """
    out: dict[str, str] = {}
    for p in parts(root):
        for c in json.loads(p.read_text(encoding="utf-8")).get("candidates") or []:
            for ch in c.get("changes") or []:
                if isinstance(ch, dict) and ch.get("id"):
                    out.setdefault(ch["id"], unsigned(ch.get("why", "")))
    return out


def write(path: Path, doc: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def known_sources() -> set[str]:
    return {p.stem for p in model_sources().glob("*.yaml")}


def promote(only: str | None = None, dry: bool = False) -> dict:
    root = require(spice_curated(), "promoting the curated models")
    known = known_sources()
    counts = {"parts": 0, "models": 0, "verified": 0, "with_datasheet": 0, "bytes": 0,
              "symbols": 0, "orphan_symbols": 0, "unknown_sources": 0}
    unknown: set[str] = set()
    for p in parts(root):
        data = json.loads(p.read_text(encoding="utf-8"))
        if only and data.get("kind") != only:
            continue
        syms = symbols(p.parent, data.get("part", ""))
        doc = recipe(data, syms)
        if not doc["part"] or not doc["kind"]:
            continue
        kept = {m["symbol"] for m in doc["models"] if m.get("symbol")}
        counts["symbols"] += len(kept)
        counts["orphan_symbols"] += len(list(p.parent.glob("*.asy"))) - len(kept)
        if not dry:
            for name in sorted(kept):
                target = model_symbol(doc["kind"], doc["part"], name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((p.parent / name).read_bytes())
        counts["parts"] += 1
        counts["models"] += len(doc["models"])
        counts["verified"] += sum(1 for m in doc["models"] if m.get("verification"))
        counts["with_datasheet"] += 1 if doc.get("datasheet") else 0
        for m in doc["models"]:
            if m["source"] not in known:
                unknown.add(m["source"])
        if not dry:
            counts["bytes"] += write(model_part(doc["kind"], doc["part"]), doc)
    kinds = change_kinds(root)
    counts["change_kinds"] = len(kinds)
    if kinds and not dry:
        model_changes().parent.mkdir(parents=True, exist_ok=True)
        model_changes().write_text(yaml.safe_dump(
            {"changes": [{"id": k, "why": kinds[k]} for k in sorted(kinds)]},
            sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    counts["unknown_sources"] = len(unknown)
    if unknown:
        counts["unknown"] = sorted(unknown)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", help="only one kind (bjt, jfet, ...)")
    ap.add_argument("--dry", action="store_true", help="say what would be written and write nothing")
    a = ap.parse_args(argv)

    counts = promote(only=a.kind, dry=a.dry)
    print(f"{counts['parts']:,} parts, {counts['models']:,} candidate models "
          f"({counts['verified']:,} scored against a datasheet, {counts['with_datasheet']:,} parts "
          f"with a datasheet link)" + (" — dry run" if a.dry else ""))
    print(f"{counts['change_kinds']} kinds of fixup, each with its reason, in {model_changes().name}")
    print(f"{counts['symbols']:,} LTspice symbols published"
          + (f", {counts['orphan_symbols']:,} left behind for candidates the curation dropped"
             if counts["orphan_symbols"] else ""))
    if not a.dry:
        print(f"{counts['bytes'] / 1e6:.1f} MB into {model_part('<kind>', '<PART>').parent.parent}")
    if counts.get("unknown"):
        print(f"! {counts['unknown_sources']} sources are named by a model but have no registry entry: "
              + ", ".join(counts["unknown"][:8]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
