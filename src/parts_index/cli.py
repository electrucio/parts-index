"""pidx — command line entry point.

Subcommands are named after the pipeline stage they run, so the command, the ledger column and STATUS.md
all use one vocabulary. Commands arrive as the pipelines are ported; `pidx --help` is always the truth.

These need nothing but the repository: `status`, `paths`, `parts extract`, and later `web build|dev|check`.
Everything else reads or writes the private data root.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx", description="Open database for analog-audio electronics.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="what has been processed and what comes next, per source")
    st.add_argument("--write", action="store_true", help="rewrite STATUS.md instead of printing")

    pa = sub.add_parser("paths", help="where everything is, and which side of the public/private line it is on")
    pa.add_argument("--private", action="store_true", help="only the private data root")
    pa.add_argument("--public", action="store_true", help="only what is committed")
    pa.add_argument("--missing", action="store_true", help="only locations that do not exist here")

    mod = sub.add_parser("models", help="SPICE models").add_subparsers(dest="mod_cmd", required=True)
    mi = mod.add_parser("index", help="find every definition in the model sources and stamp the ledgers")
    mi.add_argument("--source", action="append", help="only these sources (repeatable)")
    mi.add_argument("--missing", action="store_true", help="what a previous catalogue had and the tree lacks")
    mi.add_argument("--stats", action="store_true", help="also print counts per source")
    mi.add_argument("-o", "--out", help="where to write the catalogue")

    mf = mod.add_parser("fetch", help="download one URL into a source")
    mf.add_argument("source")
    mf.add_argument("--url", required=True)
    mf.add_argument("--name", help="file name to store it under")
    mf.add_argument("--note", default="")
    mf.add_argument("--curl", action="store_true", help="some vendors answer curl and nothing else")
    mp = mod.add_parser("promote", help="write the public recipe for every curated part")
    mp.add_argument("--kind", help="only one kind (bjt, jfet, ...)")
    mp.add_argument("--dry", action="store_true", help="say what would be written and write nothing")
    mr = mod.add_parser("recover", help="fetch again what the catalogue says the tree has lost")
    mr.add_argument("--source")
    mr.add_argument("--limit", type=int, default=0)
    mr.add_argument("--dry", action="store_true")

    sch = sub.add_parser("schematics", help="the schematic index").add_subparsers(
        dest="sch_cmd", required=True)
    se = sch.add_parser("export", help="write the index into data/, where the site is built from")
    se.add_argument("--source", action="append", help="only these sources (repeatable)")
    se.add_argument("--dry", action="store_true", help="count what would be written and write nothing")

    bk = sub.add_parser("backup", help="pack the private trees into one archive to carry off this machine")
    bk.add_argument("--level", choices=("essential", "full", "all"), default="essential")
    bk.add_argument("--out", help="where to write it")
    bk.add_argument("--dry", action="store_true", help="say what would be packed and write nothing")

    web = sub.add_parser("web", help="the static site").add_subparsers(dest="web_cmd", required=True)
    wb = web.add_parser("build", help="write the site's data from data/ (never reads the private root)")
    wb.add_argument("--out", help="output directory (default: web/public/data)")

    args = ap.parse_args(argv)

    if args.cmd == "status":
        from parts_index import status
        print(status.write() if args.write else status.render())
        return 0

    if args.cmd == "paths":
        from parts_index.core import config
        rows = config.describe()
        if args.public or args.private:
            want = "public" if args.public else "private"
            rows = [r for r in rows if r[1] == want]
        if args.missing:
            rows = [r for r in rows if not r[3]]
        if not rows:
            print("nothing to show")
            return 0
        width = max(len(name) for name, *_ in rows)
        print(f"spice models: {config.spice_models_root()}")
        print(f"material:     {config.material_root()}\n")
        for name, visibility, path, exists in rows:
            mark = " " if exists else "?"
            try:
                shown = path.relative_to(config.REPO_ROOT)
            except ValueError:
                shown = path
            print(f"{mark} {visibility:8s} {name:{width}s}  {shown}")
        if any(not exists for *_, exists in rows):
            print("\n? = not present here. Private locations are absent unless you hold the corpus.")
        return 0

    if args.cmd == "models" and args.mod_cmd == "index":
        from parts_index.models import index as model_index
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--missing"] if args.missing else []
        argv2 += ["--stats"] if args.stats else []
        argv2 += ["-o", args.out] if args.out else []
        return model_index.main(argv2)

    if args.cmd == "models" and args.mod_cmd == "promote":
        from parts_index.models import promote as model_promote
        argv2 = ["--kind", args.kind] if args.kind else []
        argv2 += ["--dry"] if args.dry else []
        return model_promote.main(argv2)

    if args.cmd == "models" and args.mod_cmd in ("fetch", "recover"):
        from parts_index.models import fetch as model_fetch
        if args.mod_cmd == "fetch":
            argv2 = ["fetch", args.source, "--url", args.url, "--note", args.note]
            argv2 += ["--name", args.name] if args.name else []
            argv2 += ["--curl"] if args.curl else []
        else:
            argv2 = ["recover"]
            argv2 += ["--source", args.source] if args.source else []
            argv2 += ["--limit", str(args.limit)] if args.limit else []
            argv2 += ["--dry"] if args.dry else []
        return model_fetch.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "export":
        from parts_index.schematics import export as sch_export
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        return sch_export.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "backup":
        from parts_index import backup
        argv2 = ["--level", args.level] + (["--out", args.out] if args.out else [])
        return backup.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "web" and args.web_cmd == "build":
        from parts_index.web import build as web_build
        manifest = web_build.build(args.out)
        t = manifest["totals"]
        missing = [k for k, v in manifest["have"].items() if not v]
        first = manifest["sizes"].get("parts.json", 0) + manifest["sizes"].get("sources.json", 0)
        print(f"{sum(manifest['sizes'].values()) / 1e6:.0f} MB  "
              f"{t['sources']} schematic sources, {t['modelSources']} model sources, "
              f"{manifest.get('parts', 0):,} part pages")
        print(f"{first / 1024:.0f} KB before compression is what a visitor loads to start searching")
        if missing:
            print(f"not built yet: {', '.join(missing)}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
