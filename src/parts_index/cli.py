"""pidx — command line entry point. Commands are added as the pipelines are ported."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="what has been processed and what comes next, per source")
    st.add_argument("--write", action="store_true", help="rewrite STATUS.md instead of printing")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        from parts_index import status
        if args.write:
            print(status.write())
        else:
            print(status.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
