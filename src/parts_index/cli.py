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
