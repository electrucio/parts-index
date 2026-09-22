"""Does this tree still hold every model file it was given, byte for byte?

These files are not scratch: they are the models the site serves in private mode, and several of them
came from vendors who will not serve them again the same way. So the question "is what we downloaded
still here" has to be answerable from something other than the tree itself — and it is, twice over: a
manifest per source with a checksum and a path per file, and a ledger row per URL with that same
checksum and the day it arrived. Both are written when the file lands, and the ledger is committed.

`models index --missing` cannot answer it. It compares the tree against a catalogue rebuilt from that
same tree, so a file lost between two runs disappears from both and the comparison reports nothing.
That is how 59,407 definitions were pruned by mistake and noticed only after the archives had gone.

    held       the file is here and matches the checksum recorded when it arrived
    changed    it is here and does not match
    unpacked   an archive that is gone, whose contents are in the tree: what is kept is the models
               inside it, and the archive itself is pruned on purpose
    pruned     gone, and the indexer found no model definition in it when it read it
    material   gone, and it could never have held a model: an image, a plot, a datasheet, a script.
               These came alongside the models and were deleted to keep the tree small
    lost       gone, and nothing says it was expendable. This is the one that costs something
    not_kept   fetched and checked and then deliberately not kept — because a licence forbids storing
               it, or because a prune decided it was not worth the room. A manifest entry says so with
               `"kept": false`, and that is how a deliberate deletion stops looking like a loss
    unrecorded the ledger says a file was downloaded from this URL and no manifest entry names it

    pidx models verify [--source onsemi] [--repair] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import PurePath

from parts_index.core.config import model_state, spice_models_root, spice_source
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger
from parts_index.models.fetch import ARCHIVE_SUFFIXES, Manifest, fetch
from parts_index.schematics.download import say

# Nothing with one of these suffixes has ever been a SPICE model: they arrive with the models, in an
# archive or a cloned repository, and deleting them costs nothing the project needs.
NOT_A_MODEL = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".plt", ".dat", ".raw", ".m", ".py",
               ".sh", ".html", ".htm", ".md", ".rst", ".schx", ".exe", ".dll", ".doc", ".docx")
STATES = ("held", "unpacked", "pruned", "material", "not_kept", "changed", "lost", "unrecorded")


def ledger_of(source: str) -> Ledger:
    return Ledger(model_state(source), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)


def unpacked_into_the_tree(source: str, entry: dict) -> bool:
    """Whether this is an archive whose contents are here although the archive itself is not."""
    name = PurePath(entry["path"]).name
    if not name.lower().endswith(ARCHIVE_SUFFIXES):
        return False
    folder = spice_source(source) / "extracted" / PurePath(name).stem
    return folder.is_dir() and any(folder.iterdir())


def held_nothing(led: Ledger, url: str) -> bool:
    """Whether the indexer read this file and found no definition in it. The ledger keeps that count,
    which is why a file that was never a model can be told from one that was."""
    row = led.get(url)
    return bool(row and row["index_at"] and row["n_defs"].isdigit() and int(row["n_defs"]) == 0)


def look(source: str) -> dict:
    """The state of every file this source is supposed to hold."""
    counts = dict.fromkeys(STATES, 0)
    broken: list[dict] = []
    led = ledger_of(source)
    entries = Manifest(source).files
    for entry in entries:
        if entry.get("kept") is False:
            counts["not_kept"] += 1          # somebody decided this one goes; that is not a loss
            continue
        if not entry.get("path"):
            counts["not_kept"] += 1          # its checksum is the whole record, by decision, not by loss
            continue
        path = spice_source(source) / entry["path"]
        if not path.exists():
            if unpacked_into_the_tree(source, entry):
                counts["unpacked"] += 1
            elif held_nothing(led, entry["url"]):
                counts["pruned"] += 1
            elif entry["path"].lower().endswith(NOT_A_MODEL):
                counts["material"] += 1
            else:
                counts["lost"] += 1
                broken.append(entry)
        elif entry.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            counts["changed"] += 1
            broken.append(entry)
        else:
            counts["held"] += 1

    known = {e["url"] for e in entries}
    for row in led.rows.values():
        if row["key"].startswith("part:") or row["status"] != "downloaded" or row["key"] in known:
            continue
        counts["unrecorded"] += 1            # fetched once, and no manifest entry says where it went
    return {"source": source, "counts": counts, "broken": broken}


def repair(report: dict, *, limit: int = 0, log=say) -> dict:
    """Fetch each lost or changed file back into the exact place it was, and check what came back."""
    source = report["source"]
    entries = report["broken"][:limit] if limit else report["broken"]
    outcome = {"recovered": 0, "differs": 0, "gone": 0}
    for entry in entries:
        got = fetch(source, entry["url"], rel=entry["path"], force=True, keep_anything=True)
        if got["status"] != "downloaded":
            outcome["gone"] += 1
            log(f"  could not get it back ({got.get('why') or got['status']}): {entry['url']}")
            continue
        now = hashlib.sha256((spice_source(source) / entry["path"]).read_bytes()).hexdigest()
        if entry.get("sha256") and now != entry["sha256"]:
            outcome["differs"] += 1
            log(f"  the vendor serves different bytes today: {entry['url']}")
        else:
            outcome["recovered"] += 1
    return outcome


def sources() -> list[str]:
    root = spice_models_root() / "sources"
    return sorted(d.name for d in root.iterdir() if d.is_dir()) if root.exists() else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx models verify", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--repair", action="store_true", help="fetch back what is lost or no longer matches")
    ap.add_argument("--limit", type=int, default=0, help="at most this many repairs per source")
    args = ap.parse_args(argv)

    total = dict.fromkeys(STATES, 0)
    wrong = 0
    for source in args.source or sources():
        report = look(source)
        counts = report["counts"]
        for state, n in counts.items():
            total[state] += n
        if counts["lost"] or counts["changed"] or counts["unrecorded"]:
            say(f"{source}: " + " · ".join(f"{n} {s}" for s, n in counts.items() if n))
            wrong += counts["lost"] + counts["changed"]
            if args.repair and report["broken"]:
                say("  " + " · ".join(f"{n} {k}" for k, n in repair(report, limit=args.limit).items()))
    say("all sources: " + " · ".join(f"{n} {s}" for s, n in total.items() if n))
    if not wrong:
        say("every file the manifests name is here, and matches")
    return 1 if wrong and not args.repair else 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
