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
    mf.add_argument("--force", action="store_true", help="fetch it again even if this source already holds it")
    mv = mod.add_parser("verify", help="whether this tree still holds every model file it was given")
    mv.add_argument("--source", action="append", help="only these sources (repeatable)")
    mv.add_argument("--repair", action="store_true", help="fetch back what is lost or no longer matches")
    mv.add_argument("--limit", type=int, default=0, help="at most this many repairs per source")
    mp = mod.add_parser("promote", help="write the public recipe for every curated part")
    mp.add_argument("--kind", help="only one kind (bjt, jfet, ...)")
    mp.add_argument("--dry", action="store_true", help="say what would be written and write nothing")
    mr = mod.add_parser("recover", help="fetch again what the catalogue says the tree has lost")
    mr.add_argument("--source")
    mr.add_argument("--limit", type=int, default=0)
    mr.add_argument("--dry", action="store_true")

    sch = sub.add_parser("schematics", help="the schematic index").add_subparsers(
        dest="sch_cmd", required=True)
    sd = sch.add_parser("download", help="fetch a source whose URLs are already listed")
    sd.add_argument("--source", action="append", required=True, help="a source with a `list:` block (repeatable)")
    sd.add_argument("--limit", type=int, default=0, help="only the first N URLs of the list")
    sd.add_argument("--delay", type=float, default=0.0, help="seconds between two requests to one host")
    sd.add_argument("--dry", action="store_true", help="say what would be fetched and fetch nothing")
    sd.add_argument("--detach", action="store_true", help="run it in the background, under a lock, into a log")
    sd.add_argument("--after", help="wait for that job to finish first (its name, as its log is called)")
    sd.add_argument("--wait-hours", type=float, default=24.0, help="how long to wait for it before giving up")

    sl = sch.add_parser("list", help="gather a source's file URLs again from the site's own listing")
    sl.add_argument("--source", action="append", required=True, help="a source with a lister (repeatable)")
    sl.add_argument("--limit", type=int, default=0, help="at most this many listing pages fetched")
    sl.add_argument("--delay", type=float, default=0.0, help="seconds between two requests to one host")
    sl.add_argument("--dry", action="store_true", help="say what would be added and add nothing")

    st = sch.add_parser("toragi", help="トランジスタ技術: coverage by year and by issue, from the lists and ledgers")
    st.add_argument("--source", action="append", help="only these sources (default: toragi, toragi_trbn and toragi_support)")

    sc = sch.add_parser("crawl", help="walk a site from its start pages and take what it shows")
    sc.add_argument("--source", action="append", required=True, help="a source with a `crawl:` block (repeatable)")
    sc.add_argument("--max", type=int, default=None, help="pages to fetch before stopping; 0 runs until the queue is empty")
    sc.add_argument("--delay", type=float, default=0.0, help="seconds between two requests to one host")
    sc.add_argument("--detach", action="store_true", help="run it in the background, under a lock, into a log")
    sc.add_argument("--after", help="wait for that job to finish first (its name, as its log is called)")
    sc.add_argument("--wait-hours", type=float, default=24.0, help="how long to wait for it before giving up")
    so = sch.add_parser("ocr", help="read what is downloaded and not read yet, page by page, with boxes")
    so.add_argument("--source", action="append", required=True, help="a source with documents downloaded (repeatable)")
    so.add_argument("--limit", type=int, default=0, help="at most this many documents")
    so.add_argument("--gpu", type=int, default=None, help="which GPU to give the OCR")
    so.add_argument("--shard", default="0/1", help="k/n: every nth document, for running several at once")
    so.add_argument("--dry", action="store_true", help="say how much there is to read and read nothing")

    sv = sch.add_parser("verify", help="whether the tree still holds what was downloaded, and whether it matters")
    sv.add_argument("--source", action="append", help="only these sources (repeatable)")
    sv.add_argument("--deep", action="store_true", help="read every file and check it against its checksum")
    sv.add_argument("--repair", action="store_true", help="fetch back what was lost before anything read it")
    sv.add_argument("--retry", action="append", metavar="REASON",
                    help="first forget refusals recorded under this reason (repeatable)")
    sv.add_argument("--limit", type=int, default=0, help="at most this many repairs")
    sp = sch.add_parser("prune", help="drop what a source's rules no longer want, and say it was on purpose")
    sp.add_argument("--source", action="append", help="only these sources (repeatable)")
    sp.add_argument("--dry", action="store_true", help="say what would go and delete nothing")
    si = sch.add_parser("ingest", help="put the documents that have been read into the index database")
    si.add_argument("--source", action="append", help="only these sources (repeatable)")
    si.add_argument("--limit", type=int, default=0, help="at most this many documents per source")
    si.add_argument("--dry", action="store_true", help="say how much there is to index and write nothing")
    sr = sch.add_parser("release", help="delete the downloaded files whose text has already been read")
    sr.add_argument("--source", action="append", help="only these sources (repeatable)")
    sr.add_argument("--dry", action="store_true", help="say what would go and delete nothing")
    sr.add_argument("--all-kinds", action="store_true",
                    help="release the CAD sources too, which are kept by default")
    sr = sch.add_parser("reindex", help="read the corpus again with the current extractor, from the OCR on disk")
    sr.add_argument("--source", action="append", help="only these sources (repeatable)")
    sr.add_argument("--limit", type=int, default=0, help="at most this many documents")
    sr.add_argument("--workers", type=int, default=12, help="how many processes read at once")
    sr.add_argument("--dry", action="store_true", help="say how much there is to read and write nothing")

    ss = sch.add_parser("summarise", help="one line per published use: what that part does on that page")
    ss.add_argument("--source", action="append", help="only these sources (repeatable)")
    ss.add_argument("--limit", type=int, default=0, help="at most this many pages per source")
    ss.add_argument("--workers", type=int, default=4, help="calls in flight (the server has four slots)")
    ss.add_argument("--detach", action="store_true", help="run it in the background, under a lock, into a log")
    ss.add_argument("--dry", action="store_true", help="say what would be asked and ask nothing")
    ss.add_argument("--preview", action="store_true",
                    help="write what has been answered so far, with its links, and stop")

    se = sch.add_parser("export", help="write the index into data/, where the site is built from")
    se.add_argument("--source", action="append", help="only these sources (repeatable)")
    se.add_argument("--dry", action="store_true", help="count what would be written and write nothing")

    pt = sub.add_parser("parts", help="the part vocabulary: which numbers exist and what they are").add_subparsers(
        dest="pt_cmd", required=True)
    pj = pt.add_parser("judge", help="decide which census names mean a component in this corpus")
    pj.add_argument("--collect", action="store_true", help="walk the corpus and gather the evidence")
    pj.add_argument("--ask", action="store_true", help="put the evidence to a model (spends money)")
    pj.add_argument("--per-source", type=int, default=60)
    pj.add_argument("--budget", type=float, default=15.0)
    pj.add_argument("--model", default="gpt-5-mini")

    pb = pt.add_parser("benchmark", help="labelled decisions on real pages, and today's score against them")
    pb.add_argument("--build", action="store_true", help="sample pages and label them (spends money)")
    pb.add_argument("--per-source", type=int, default=6, help="documents sampled per source")
    pb.add_argument("--budget", type=float, default=12.0, help="dollars this run may spend")
    pb.add_argument("--model", default="gpt-5")

    pe = pt.add_parser("explain", help="why a part gives nothing: the extractor, or no document that has it")
    pe.add_argument("part", nargs="+")

    pc = pt.add_parser("census", help="read the lists that say which part numbers exist, and link them")
    pc.add_argument("--source", action="append", help="only these sources (repeatable)")
    pc.add_argument("--read", action="store_true", help="parse the pages already cached; fetch nothing")
    pc.add_argument("--limit", type=int, default=0, help="at most this many pages fetched, per source")
    pc.add_argument("--delay", type=float, default=0.0, help="seconds between two requests to one host")

    ds = sub.add_parser("datasets", help="the distilled research datasets").add_subparsers(
        dest="ds_cmd", required=True)
    dr = ds.add_parser("repos", help="read how much attention each open-source project has")
    dr.add_argument("--all", action="store_true", help="read every repository again, however recent")
    dr.add_argument("--limit", type=int, default=0)
    dr.add_argument("--days", type=int, default=30, help="how old a reading may be")

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

    if args.cmd == "models" and args.mod_cmd == "verify":
        from parts_index.models import verify as model_verify
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--repair"] if args.repair else []
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        return model_verify.main(argv2)

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
            argv2 += ["--force"] if args.force else []
        else:
            argv2 = ["recover"]
            argv2 += ["--source", args.source] if args.source else []
            argv2 += ["--limit", str(args.limit)] if args.limit else []
            argv2 += ["--dry"] if args.dry else []
        return model_fetch.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "download":
        from parts_index.schematics import download as sch_download
        argv2 = [x for pair in (("--source", s) for s in args.source) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--delay", str(args.delay)] if args.delay else []
        argv2 += ["--dry"] if args.dry else []
        argv2 += ["--after", args.after, "--wait-hours", str(args.wait_hours)] if args.after else []
        return sch_download.main(argv2 + (["--detach"] if args.detach else []))

    if args.cmd == "schematics" and args.sch_cmd == "list":
        from parts_index.schematics import listing as sch_listing
        argv2 = [x for pair in (("--source", s) for s in args.source) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--delay", str(args.delay)] if args.delay else []
        return sch_listing.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "schematics" and args.sch_cmd == "toragi":
        from parts_index.schematics import toragi as sch_toragi
        return sch_toragi.main([x for pair in (("--source", s) for s in args.source or []) for x in pair])

    if args.cmd == "schematics" and args.sch_cmd == "crawl":
        from parts_index.schematics import crawl as sch_crawl
        argv2 = [x for pair in (("--source", s) for s in args.source) for x in pair]
        argv2 += ["--max", str(args.max)] if args.max is not None else []
        argv2 += ["--delay", str(args.delay)] if args.delay else []
        argv2 += ["--after", args.after, "--wait-hours", str(args.wait_hours)] if args.after else []
        return sch_crawl.main(argv2 + (["--detach"] if args.detach else []))

    if args.cmd == "schematics" and args.sch_cmd == "ocr":
        from parts_index.schematics import ocr as sch_ocr
        argv2 = [x for pair in (("--source", s) for s in args.source) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--gpu", str(args.gpu)] if args.gpu is not None else []
        argv2 += ["--shard", args.shard] if args.shard != "0/1" else []
        return sch_ocr.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "schematics" and args.sch_cmd == "verify":
        from parts_index.schematics import verify as sch_verify
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--deep"] if args.deep else []
        argv2 += [x for pair in (("--retry", r) for r in args.retry or []) for x in pair]
        argv2 += ["--repair"] if args.repair else []
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        return sch_verify.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "ingest":
        from parts_index.schematics import ingest as sch_ingest
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--dry"] if args.dry else []
        return sch_ingest.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "release":
        from parts_index.schematics import release as sch_release
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--dry"] if args.dry else []
        argv2 += ["--all-kinds"] if args.all_kinds else []
        return sch_release.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "prune":
        from parts_index.schematics import prune as sch_prune
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--dry"] if args.dry else []
        return sch_prune.main(argv2)

    if args.cmd == "schematics" and args.sch_cmd == "reindex":
        from parts_index.schematics import reindex as sch_reindex
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--workers", str(args.workers)]
        return sch_reindex.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "schematics" and args.sch_cmd == "summarise":
        from parts_index.schematics import summarise as sch_summarise
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--limit", str(args.limit), "--workers", str(args.workers)]
        argv2 += ["--detach"] if args.detach else []
        argv2 += ["--preview"] if args.preview else []
        return sch_summarise.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "schematics" and args.sch_cmd == "export":
        from parts_index.schematics import export as sch_export
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        return sch_export.main(argv2 + (["--dry"] if args.dry else []))

    if args.cmd == "parts" and args.pt_cmd == "judge":
        from parts_index.core.parts import judge
        argv2 = ["--per-source", str(args.per_source), "--budget", str(args.budget), "--model", args.model]
        argv2 += ["--collect"] if args.collect else []
        return judge.main(argv2 + (["--ask"] if args.ask else []))

    if args.cmd == "parts" and args.pt_cmd == "benchmark":
        from parts_index.core.parts import benchmark
        argv2 = ["--per-source", str(args.per_source), "--budget", str(args.budget), "--model", args.model]
        return benchmark.main(argv2 + (["--build"] if args.build else []))

    if args.cmd == "parts" and args.pt_cmd == "explain":
        from parts_index.core.parts import explain
        return explain.main(args.part)

    if args.cmd == "parts" and args.pt_cmd == "census":
        from parts_index.core.parts import census
        argv2 = [x for pair in (("--source", s) for s in args.source or []) for x in pair]
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        argv2 += ["--delay", str(args.delay)] if args.delay else []
        return census.main(argv2 + (["--read"] if args.read else []))

    if args.cmd == "datasets" and args.ds_cmd == "repos":
        from parts_index.datasets import repos as ds_repos
        argv2 = ["--days", str(args.days)] + (["--all"] if args.all else [])
        argv2 += ["--limit", str(args.limit)] if args.limit else []
        return ds_repos.main(argv2)

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
