"""Delete the downloaded files whose text has already been read, and keep the ones nothing has read.

This is the half of the retention rule that was written down and never built. `verify` has always known
the difference — `released` is a file that is gone and was read, `lost` is one that is gone and was not —
but nothing did the deleting, so the deleting happened by hand, and by hand there is no difference between
the two. A scan deleted before OCR saw it leaves a ledger still saying "downloaded", no stage ever asks
for it again, and the document is simply missing from the index with nobody the wiser.

So the rule here is a single condition, `verify.was_read`: OCR has stamped the row, or the document needed
no OCR and the index has stamped it. Anything else is left alone however much room it would free.

The ledger is not touched. It goes on saying the file was downloaded, which is true, and `verify` reads
the missing file plus the stamp and calls it `released`. Nothing is asked for twice.

CAD is kept by default, and that is deliberate. A `.kicad_sch` is a few kilobytes and it is the one kind
of document whose reader is still changing — gEDA, EAGLE boards and the package guard all arrived in a
single day — so it is the kind most likely to be read again, and re-reading needs the file. `--all-kinds`
overrides that for somebody who means it.

    pidx schematics release --dry                      what would go, and how much room that is
    pidx schematics release --source audiocircuit      free it
"""
from __future__ import annotations

import argparse
from pathlib import Path

from parts_index.core.config import schematics_state
from parts_index.core.ledger import Ledger
from parts_index.schematics import cad
from parts_index.schematics.download import say
from parts_index.schematics.verify import sources, state_of, was_read

KEPT_KINDS = cad.KINDS         # small, and their reader is the one still changing


def look(source: str, all_kinds: bool = False) -> dict:
    """Which files of one source may go, and how many bytes that is."""
    led = Ledger(schematics_state(source))
    paths, freed = [], 0
    for row in led.rows.values():
        state, path = state_of(source, row)
        if state != "held":
            continue
        if not all_kinds and row["type"] in KEPT_KINDS:
            continue
        # The one condition. `state_of` already said the file is here and the row says it was downloaded;
        # this asks whether anything has taken the text out of it yet.
        if not was_read(row):
            continue
        paths.append(path)
        freed += int(row["bytes"] or 0)
    return {"source": source, "paths": paths, "bytes": freed}


def drop(report: dict) -> int:
    """Delete them. Returns how many went."""
    n = 0
    for path in report["paths"]:
        p = Path(path)
        if p.exists():
            p.unlink()
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics release", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--dry", action="store_true", help="say what would go and delete nothing")
    ap.add_argument("--all-kinds", action="store_true",
                    help="release the CAD sources too, which are kept by default")
    args = ap.parse_args(argv)

    total = files = 0
    for source in args.source or sources():
        report = look(source, all_kinds=args.all_kinds)
        if not report["paths"]:
            continue
        total += report["bytes"]
        files += len(report["paths"])
        say(f"{source}: {len(report['paths'])} files read already, {report['bytes'] / (1 << 30):.2f} GB")
        if not args.dry:
            drop(report)
    say(f"{'would free' if args.dry else 'freed'} {files} files, {total / (1 << 30):.2f} GB")
    say("nothing unread was touched; `pidx schematics verify` will call these released")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
