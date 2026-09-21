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

    if args.cmd == "web" and args.web_cmd == "build":
        from parts_index.web import build as web_build
        manifest = web_build.build(args.out)
        t = manifest["totals"]
        missing = [k for k, v in manifest["have"].items() if not v]
        print(f"{sum(manifest['sizes'].values()) / 1024:.0f} KB  "
              f"{t['sources']} schematic sources, {t['modelSources']} model sources")
        if missing:
            print(f"not built yet: {', '.join(missing)}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
