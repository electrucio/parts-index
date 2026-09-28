"""Make every downloaded model count: join each definition file to the download it came from.

    pidx models reconcile [--source S] [--write]

The public ledger holds one row per downloaded URL, and credits it with the definitions found in it;
which local files a URL became is written in the source's private manifests. Where that join was never
recorded, definitions sit in the catalogue — and in the part recipes — while the ledger, STATUS.md and
the site's source table say the source holds nothing. This finds those joins and, with `--write`,
records them:

1. **Rows the ledger lacks.** A manifest entry with a URL and no ledger row — Vishay's three
   sub-folder manifests were never read — gets its `downloaded` row, with the checksum, size and date
   the manifest recorded.
2. **Folders nobody claims.** An archive unpacked somewhere other than `extracted/<its stem>/` is
   matched to its folder by the first rule that names exactly one folder holding uncredited
   definitions, and the manifest entry gets `unpacked_to`:
     - `extracted/<the archive's folder under raw/>/<stem>` — murata's raw/mlcc/x.zip — or
       `extracted/<stem>` when that is in a sub-manifest, which the usual stem rule does not reach;
     - `extracted/<the archive's folder under raw/>` when that folder holds one archive — toshiba's
       raw/pspice-all/PSpice_20260827.zip;
     - `extracted/<one word of the stem>` — ayumi's tubemodel_3.20_win.zip is extracted/win,
       robrobinette's Deluxe_LTSpice.zip extracted/Deluxe;
     - `extracted` itself, when the manifest holds a single archive.
   Without `--write` every proposal is printed, so a wrong one is seen before it is recorded.
3. **What is left** is listed by folder: files no download accounts for, to be declared by hand.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from parts_index.core.config import model_sources, model_state, require, spice_definitions, spice_source
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger
from parts_index.models import index as ix
from parts_index.models.found import excluded

ARCHIVES = (".zip", ".7z", ".rar", ".tgz", ".gz", ".tar", ".msi", ".exe")


def ledger(source: str) -> Ledger:
    return Ledger(model_state(source), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)


def missing_rows(source: str, led: Ledger) -> list[dict]:
    """Manifest entries with a URL that the ledger has no row for."""
    out, seen = [], set(led.rows)
    for folder, man in ix.manifests(source):
        for x in man.get("files", []):
            url = x.get("url")
            if url and url not in seen and (x.get("path") or x.get("sha256")):
                seen.add(url)
                out.append(dict(x, fetched=x.get("fetched") or man.get("fetched") or ""))
    return out


def misfiled(source: str, led: Ledger) -> list[tuple[str, dict]]:
    """(URL, manifest entry) for a URL the ledger says gave nothing, whose file the manifest lists with
    the same checksum.

    ADI's ad8051_5.cir was downloaded and holds the AD8051 macromodel; its row said `not_published`,
    because the same row had been used to note that the AD8052 has no model of its own. Those are two
    facts, and each gets its row.
    """
    out = []
    for _, man in ix.manifests(source):
        for x in man.get("files", []):
            row = led.rows.get(x.get("url") or "")
            if row and row["status"] != "downloaded" and x.get("path") and x.get("sha256") \
                    and row.get("sha256") in ("", x["sha256"]):
                out.append((x["url"], x))
    return out


def refile(led: Ledger, found: list[tuple[str, dict]]) -> None:
    for url, x in found:
        row = led.rows[url]
        part_row = led.rows.get(f"part:{row['part']}") if row.get("part") else None
        if row.get("part") and (part_row is None or part_row["status"] == "not_tried"):
            # the search that row recorded was made; a part row saying "not tried" is behind
            led.skip(f"part:{row['part']}", row.get("skip_reason") or row["status"],
                     url=(part_row or {}).get("url") or url, part=row["part"], status=row["status"])
        row.update(part="", skip_reason="")
        led.stamp(url, "fetch", when=row.get("fetch_at") or x.get("fetched") or None,
                  status="downloaded", sha256=x["sha256"], bytes=str(x.get("bytes") or row.get("bytes") or ""))


def add_rows(led: Ledger, entries: list[dict]) -> None:
    for x in entries:
        values = {"status": "downloaded"}
        if x.get("sha256"):
            values["sha256"] = x["sha256"]
        if x.get("bytes"):
            values["bytes"] = str(x["bytes"])
        led.stamp(x["url"], "fetch", when=x.get("fetched") or None, **values)


def is_archive(x: dict) -> bool:
    name = (x.get("path") or x.get("url") or "").split("?")[0].lower()
    return name.endswith(ARCHIVES)


def stem_of(x: dict) -> str:
    name = Path((x.get("path") or x.get("url") or "").split("?")[0]).name
    for ext in ARCHIVES:
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return Path(name).stem


def candidates(x: dict, archives_in: Counter, n_archives: int) -> list[list[str]]:
    """Folder guesses for one archive entry, relative to its manifest, one list per rule, in order."""
    raw = Path(x.get("path") or "")
    sub = "/".join(raw.parts[1:-1]) if raw.parts[:1] == ("raw",) else ""
    stem = stem_of(x)
    rules = [[f"extracted/{sub}/{stem}", f"extracted/{stem}"] if sub else [f"extracted/{stem}"]]
    if sub and archives_in[sub] == 1:
        rules.append([f"extracted/{sub}"])
    words = [w for w in re.split(r"[_\-. ]+", stem) if len(w) >= 3 or w.lower() in ("win",)]
    rules.append([f"extracted/{w}" for w in words])
    if n_archives == 1:
        rules.append(["extracted"])
    return rules


def propose(source: str, uncredited: set[str]) -> list[tuple[str, dict, str]]:
    """(manifest folder, entry, folder relative to the manifest) for each archive whose folder is found."""
    out = []
    taken: set[str] = set()
    for folder, man in ix.manifests(source):
        entries = [x for x in man.get("files", []) if x.get("url") and is_archive(x) and not ix.yielded_into(x)]
        archives_in = Counter("/".join(Path(x.get("path") or "").parts[1:-1]) for x in entries)
        for x in entries:
            for rule in candidates(x, archives_in, len(entries)):
                hits = [c for c in rule if c not in taken
                        and any(r.startswith(ix.under(folder, c) + "/") for r in uncredited)]
                if len(hits) == 1:
                    taken.add(hits[0])
                    out.append((folder, x, hits[0]))
                    break
    return out


def record(source: str, proposals: list[tuple[str, dict, str]]) -> None:
    """Write `unpacked_to` into the manifests, keeping everything else in them as it was."""
    by_folder = defaultdict(dict)
    for folder, x, into in proposals:
        # keyed by URL and path: two archives may share a URL (a vendor's PSpice and LTspice zips
        # behind one product link), and only the one that was unpacked there gets the folder
        by_folder[folder][(x["url"], x.get("path"))] = into
    for folder, found in by_folder.items():
        mf = spice_source(source) / folder / "manifest.json" if folder else spice_source(source) / "manifest.json"
        man = json.loads(mf.read_text(encoding="utf-8"))
        for x in man.get("files", []):
            key = (x.get("url"), x.get("path"))
            if key in found and not ix.yielded_into(x):
                x["unpacked_to"] = found[key]
        mf.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def uncredited_files(source: str, files: Counter, led: Ledger) -> set[str]:
    return set(files) - set(ix.credit(source, files, ix.downloaded(led)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", action="append", help="only these sources (repeatable)")
    ap.add_argument("--write", action="store_true", help="record the rows and folders found; otherwise only say")
    a = ap.parse_args(argv)
    records = [json.loads(line) for line in
               require(spice_definitions(), "reconciling the ledgers").open(encoding="utf-8")]
    files = ix.files_by_source(records)
    sources = a.source or sorted(p.stem for p in model_sources().glob("*.yaml"))
    left_total = 0
    for source in sources:
        if not model_state(source).exists():
            continue
        led = ledger(source)
        rows = missing_rows(source, led)
        wrong = misfiled(source, led)
        if (rows or wrong) and a.write:
            add_rows(led, rows)
            refile(led, wrong)
            led.save()
        # a row added in a dry run still counts, so the proposals below are the ones --write makes
        keys = ix.downloaded(led) | {x["url"] for x in rows} | {u for u, _ in wrong}
        mine = files.get(source, Counter())
        unc = set(mine) - set(ix.credit(source, mine, keys))
        props = propose(source, unc)
        if props and a.write:
            record(source, props)
        if a.write:
            led = ledger(source)
        # A file the curation excludes on purpose — an edit made here that nobody publishes — is not
        # waiting for a download to account for it; it is still credited if one does.
        left = {r for r in unc if not excluded(f"sources/{source}/{r}")} \
            - {r for f, _, into in props for r in unc if r.startswith(ix.under(f, into) + "/")}
        n_left = sum(mine[r] for r in left)
        left_total += n_left
        if not (rows or wrong or props or left):
            continue
        print(f"== {source}: {len(rows)} ledger rows to add, {len(wrong)} to correct, {len(props)} folders found, "
              f"{n_left:,} definitions left unaccounted")
        for f, x, into in props:
            n = sum(mine[r] for r in unc if r.startswith(ix.under(f, into) + "/"))
            print(f"   {x.get('path') or x['url']}  ->  {ix.under(f, into)}/   ({n:,} definitions)")
        by_dir = Counter()
        for r in left:
            by_dir["/".join(r.split("/")[:2]) if r.count("/") > 1 else r] += mine[r]
        for d, n in by_dir.most_common(6):
            print(f"   left: {n:>7,}  {d}")
    print(f"{left_total:,} definitions no download accounts for"
          + ("" if a.write else " — dry run, nothing written; --write records the above"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
