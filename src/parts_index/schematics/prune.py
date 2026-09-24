"""Drop what a source's rules no longer want, and remember that it was dropped on purpose.

A scope narrows after the fact. radiomanual turned out to be mostly user manuals in six languages, and
xdevs mostly photographs of instrument interiors; both were already on disk by the time anyone counted.
Changing the registry stops the next run fetching more of the same, and does nothing about the forty
gigabytes already taken.

This makes the past agree with the registry. It reads no patterns of its own — the source's own `deny`
and `figures: false` are the rule, in one place — and for every row those rules would refuse today it
deletes the file and writes down `out of scope`.

That reason is the whole point. The ledger keeps saying the URL was fetched, so nothing asks for it
again; `verify` reads the reason and stops calling the missing file a hole; and

    pidx schematics verify --retry 'out of scope'

is how the judgement is undone if it was wrong, by the reason it was made under rather than by hand.

    pidx schematics prune --source radiomanual --dry     what it would drop, and how much that is
    pidx schematics prune --source radiomanual           drop it
"""
from __future__ import annotations

import argparse
import re

from parts_index.core.config import downloads, schematics_state
from parts_index.core.ledger import Ledger
from parts_index.schematics.download import IMAGE_KINDS, registry_entry, safe_name, say
from parts_index.schematics.verify import sources

REASON = "out of scope"
# A crawl keeps the pages it walked so a later run can read their links again without asking for them.
KEPT_ROLES = ("page", "project_page")


def rule_for(source: str):
    """What this source would refuse today, as a function of one ledger row. None when nothing would.

    Only a crawl has rules of this kind. A `list:` source is defined by its list, and a URL that should
    not be on it is a question for whatever gathered the list, not for this.
    """
    cfg = registry_entry(source).get("crawl")
    if cfg is None:
        return None
    deny = re.compile(cfg["deny"]) if cfg.get("deny") else None
    figures = cfg.get("figures", True)
    if deny is None and figures:
        return None

    def refused(row: dict) -> bool:
        if row["role"] in KEPT_ROLES or row["skip_reason"] or not row["download_at"]:
            return False
        # `figures: false` refuses a site's pictures, not everything reached as one: 92 of the URLs
        # xdevs shows as images answer with a PDF, and a PDF is a document wherever it was found.
        if not figures and row["role"] == "figure" and row["type"] in IMAGE_KINDS:
            return True
        return bool(deny and deny.search(row["key"]))

    return refused


def look(source: str) -> dict:
    """Which of this source's rows its own rules would refuse today, and what they weigh."""
    refused = rule_for(source)
    led = Ledger(schematics_state(source))
    out = {"source": source, "ledger": led, "keys": [], "bytes": 0}
    if refused is None:
        return out
    for row in led.rows.values():
        if refused(row):
            out["keys"].append(row["key"])
            out["bytes"] += int(row["bytes"] or 0)
    return out


def drop(report: dict, log=say) -> dict:
    """Delete the files and write the reason. Counts what went and what was already gone."""
    led, source = report["ledger"], report["source"]
    counts = {"deleted": 0, "already gone": 0}
    for key in report["keys"]:
        row = led.get(key)
        path = downloads(source) / row["type"] / safe_name(key, row["type"]) if row["type"] else None
        if path is not None and path.exists():
            path.unlink()
            counts["deleted"] += 1
        else:
            counts["already gone"] += 1
        row["skip_reason"] = REASON
        led.dirty = True
    led.save()
    log(f"{source}: {counts['deleted']} files deleted, {counts['already gone']} were gone already, "
        f"{len(report['keys'])} rows now say '{REASON}'")
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics prune", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--dry", action="store_true", help="say what would go and delete nothing")
    args = ap.parse_args(argv)

    total = files = 0
    for source in args.source or sources():
        report = look(source)
        if not report["keys"]:
            continue
        total += report["bytes"]
        files += len(report["keys"])
        say(f"{source}: {len(report['keys'])} files, {report['bytes'] / (1 << 30):.2f} GB")
        if not args.dry:
            drop(report)
    say(f"{'would drop' if args.dry else 'dropped'} {files} files, {total / (1 << 30):.2f} GB")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
