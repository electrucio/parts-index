"""Does the tree still hold what the ledger says was downloaded, and does it matter that it does not?

Most of what a ledger knows about is meant to be gone: a scanned document is temporary here, and the
retention rule deletes it once its text has been read. What must not happen is losing one *before*
anything read it. The ledger would go on saying "downloaded", no stage would ever ask for it again,
and the document would simply be missing from the index with nobody the wiser. That is the hole this
looks for, and the only one worth a request to fix.

So each item the ledger says was downloaded is one of:

    held       the file is here
    released   it is gone, and something has read it — OCR, or the index for a page that needs no OCR
    lost       it is gone and nothing has read it: the hole
    changed    it is here and no longer matches the checksum written down when it arrived (--deep)
    unknown    the ledger never recorded what kind of file it was, so its name cannot be worked out

    pidx schematics verify                          every source, presence only
    pidx schematics verify --source esp --deep      also read every file and check its checksum
    pidx schematics verify --repair                 fetch back exactly the ones nothing has read yet
"""
from __future__ import annotations

import argparse
import hashlib

import yaml

from parts_index.core import http
from parts_index.core.config import downloads, schematics_registry, schematics_state
from parts_index.core.ledger import Ledger
from parts_index.schematics.download import Downloader, safe_name, say

STATES = ("held", "released", "lost", "changed", "unknown")


def was_read(row: dict) -> bool:
    """Whether anything has taken the text out of this file yet, which is what makes it disposable."""
    if row["ocr_at"]:
        return True
    needs_no_ocr = row["type"] == "html" or row["text_method"] == "text"
    return bool(needs_no_ocr and row["index_at"])


def state_of(source: str, row: dict, deep: bool = False) -> tuple[str, str]:
    """(state, path) for one ledger row. The path is "" when it cannot be worked out."""
    if row["skip_reason"] or not row["download_at"]:
        return "", ""
    if not row["type"]:
        return "unknown", ""
    path = downloads(source) / row["type"] / safe_name(row["key"], row["type"])
    if not path.exists():
        return ("released" if was_read(row) else "lost"), str(path)
    if deep and row["sha256"] and hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        return "changed", str(path)
    return "held", str(path)


def look(source: str, deep: bool = False) -> dict:
    """What state every item of one source is in, and which keys are the holes."""
    led = Ledger(schematics_state(source))
    counts = dict.fromkeys(STATES, 0)
    broken: list[str] = []
    for row in led.rows.values():
        state, _ = state_of(source, row, deep)
        if not state:
            continue
        counts[state] += 1
        if state in ("lost", "changed"):
            broken.append(row["key"])
    return {"source": source, "counts": counts, "broken": broken, "ledger": led}


def repair(report: dict, *, delay: float = http.DELAY, limit: int = 0, log=say) -> dict:
    """Fetch back what was lost before anything read it, and say whether the same bytes came back."""
    led, source = report["ledger"], report["source"]
    keys = report["broken"][:limit] if limit else report["broken"]
    job = Downloader(source, {}, led, delay=delay, log=log)
    outcome = {"recovered": 0, "differs": 0, "gone": 0}
    try:
        for key in keys:
            had = led.get(key)["sha256"]
            kind, _ = job.item(key, led.get(key)["role"] or "document", force=True)
            if not kind:
                outcome["gone"] += 1
                continue
            now = led.get(key)["sha256"]
            if had and now != had:
                outcome["differs"] += 1        # the source serves something else today; later stages were cleared
                log(f"  different bytes now: {key}")
            else:
                outcome["recovered"] += 1
    finally:
        led.save()
    return outcome


def sources() -> list[str]:
    registry = yaml.safe_load(schematics_registry().read_text(encoding="utf-8")) or {}
    return [name for name, entry in registry.items() if schematics_state(name).exists()
            and entry.get("status") not in ("excluded",)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics verify", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--deep", action="store_true", help="read every file and check it against its checksum")
    ap.add_argument("--repair", action="store_true", help="fetch back what was lost before anything read it")
    ap.add_argument("--limit", type=int, default=0, help="at most this many repairs")
    ap.add_argument("--delay", type=float, default=http.DELAY)
    args = ap.parse_args(argv)

    total = dict.fromkeys(STATES, 0)
    holes = 0
    for source in args.source or sources():
        report = look(source, deep=args.deep)
        counts = report["counts"]
        for state, n in counts.items():
            total[state] += n
        if counts["lost"] or counts["changed"]:
            say(f"{source}: " + " · ".join(f"{n} {s}" for s, n in counts.items() if n))
            holes += counts["lost"] + counts["changed"]
            if args.repair:
                say(f"  repairing {len(report['broken'])}…")
                say("  " + " · ".join(f"{n} {k}" for k, n in repair(report, delay=args.delay, limit=args.limit).items()))
    say("all sources: " + " · ".join(f"{n} {s}" for s, n in total.items() if n))
    if not holes:
        say("nothing was lost before it was read")
    return 1 if holes and not args.repair else 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
