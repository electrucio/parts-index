"""Pack the private trees into one archive to carry off this machine.

    pidx backup                 what cannot be regenerated      ~2.6 GB
    pidx backup --level full    + the downloaded vendor files   ~3.8 GB
    pidx backup --level all     + everything still in transit   ~9 GB

The archive holds files at the paths they occupy inside the checkout, carries its own `MANIFEST.csv` of
checksums and its own `restore.py`, so a download years from now needs nothing from this repository to
be put back.

**Compression buys almost nothing here and bundling buys a great deal.** The OCR is 57,072 files that
are already gzipped — re-compressing one makes it 112 bytes *bigger* — so anything already compressed is
stored as-is and only the rest is deflated. What the archive is for is turning 57,000 files into one,
which is the difference between an upload that finishes and one that does not.

The default level is deliberately not everything. `index.sqlite` is 3.9 GB and rebuilds from the OCR in
about eight minutes; the downloaded vendor files are 1.3 GB and every one of them has a URL and a
checksum in a public ledger, which is exactly how 59,407 definitions were recovered after they were
deleted by mistake. Backing those up costs more than it saves. What genuinely cannot be fetched again is
the OCR — the PDFs are gone and the image that read them was deleted — and the curation, which is human
judgement. Those are the default.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from datetime import date
from pathlib import Path

from parts_index.core.config import (
    REPO_ROOT,
    backups,
    datasheets,
    download_manifest,
    guard_extra_patterns,
    index_db,
    legacy,
    material_root,
    ocr_root,
    page_sizes,
    simulators,
    source_list,
    spice_curated,
    spice_definitions,
    spice_models_root,
    staging,
)

LEVELS = ("essential", "full", "all")
CHUNK = 1 << 20
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "restore_private.py"
# Compressing these again costs time and gains nothing, so they go in as they are.
ALREADY_COMPRESSED = {".gz", ".zip", ".7z", ".rar", ".xz", ".bz2", ".tgz", ".png", ".jpg", ".jpeg",
                      ".webp", ".pdf", ".djvu", ".msi", ".exe", ".sqlite"}


def contents(level: str) -> list[tuple[Path, str]]:
    """Every tree or file to pack at this level, with why it is worth carrying."""
    out: list[tuple[Path, str]] = [
        (ocr_root(), "irreplaceable: the PDFs are gone and the image that read them was deleted"),
        (page_sizes(), "page geometry; without it 133,000 pages lose their zoom link"),
        (source_list("x").parent, "URL lists for sources that cannot be crawled again"),
        (download_manifest("x").parent, "what each schematic source downloaded"),
        (spice_curated(), "the curation: human judgement, and the symbols and patches with it"),
        (guard_extra_patterns(), "the local patterns the guard checks against"),
    ]
    # Each source's own record of itself: 4.4 MB that reconstructs 1.3 GB of downloads.
    out += [(p, "the recipe for one source's downloads")
            for p in sorted(spice_models_root().glob("sources/*/manifest.json"))]
    out += [(p, "one source's licence note") for p in sorted(spice_models_root().glob("sources/*/SOURCE.md"))]
    if level in ("full", "all"):
        out += [
            (spice_models_root() / "sources", "the downloaded vendor files themselves"),
            (datasheets(), "manufacturer datasheets, still needed by the simulation phase"),
            (simulators(), "simulator installers and tools"),
        ]
    if level == "all":
        out += [
            (index_db(), "the schematic index; rebuilds from the OCR in about eight minutes"),
            (spice_definitions(), "the model catalogue; regenerated from the sources in minutes"),
            (staging(), "the old code still to be ported"),
            (legacy(), "the retired repositories"),
        ]
    return [(p, why) for p, why in out if p.exists()]


def files_under(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def digest(path: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                return h.hexdigest(), n
            h.update(b)
            n += len(b)


def readme(level: str, n_files: int, n_bytes: int) -> str:
    return f"""# parts-index — private data backup

Written {date.today().isoformat()} at level `{level}`: {n_files:,} files, {n_bytes / 1e9:.2f} GB.

This is the half of the project that is **not** in git: third-party material that may not be
redistributed, and the working state around it. It is a backup, not a publication — keep it private.

## Restoring

    python3 restore.py {archive_name(level)} --into /path/to/parts-index

Files go back to the paths they came from. Nothing already there is overwritten: a file that is present
and correct is skipped, and one that is present and *different* is named and left alone, because that is
either newer work or a damaged download. `--force` replaces those, `--verify-only` checks and writes
nothing.

Every file's sha256 is in `MANIFEST.csv` and is checked as it is unpacked, so a truncated download is
caught rather than restored.

## What is not in here, and why

The public half — the registries, the ledgers, the 1,717 model recipes, the symbols — is in the git
repository. Clone it; do not look for it here.

At level `essential` the downloaded vendor files and the two big derived indexes are left out on
purpose. Every downloaded file has its URL and checksum in a public ledger and in the per-source
manifests, both of which *are* in here, and `pidx models recover` fetches them again from those. The
indexes rebuild from the OCR. What cannot be remade is the OCR itself and the curation, and those are in
every level.
"""


def archive_name(level: str) -> str:
    stamp = date.today().isoformat()
    return f"parts-index-private-{stamp}.zip" if level == "essential" \
        else f"parts-index-private-{level}-{stamp}.zip"


def build(out_dir: Path, level: str = "essential", dry: bool = False) -> dict:
    picked = contents(level)
    seen: dict[str, Path] = {}
    for root, _why in picked:
        for f in files_under(root):
            seen.setdefault(rel(f), f)          # a tree may be named twice; pack each file once
    total = sum(p.stat().st_size for p in seen.values())
    counts = {"files": len(seen), "bytes": total, "trees": len(picked), "packed": 0, "archive": ""}
    if dry:
        return counts

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / archive_name(level)
    tmp = target.with_name(target.name + ".part")
    rows: list[dict] = []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for i, (name, path) in enumerate(sorted(seen.items()), 1):
            sha, n = digest(path)
            how = (zipfile.ZIP_STORED if path.suffix.lower() in ALREADY_COMPRESSED
                   else zipfile.ZIP_DEFLATED)
            zf.write(path, name, compress_type=how)
            rows.append({"path": name, "bytes": n, "sha256": sha})
            counts["packed"] += 1
            if i % 5000 == 0:
                print(f"  {i:,}/{len(seen):,} files …", flush=True)
        buf = ["path,bytes,sha256"]
        buf += [f'{r["path"]},{r["bytes"]},{r["sha256"]}' for r in rows]
        zf.writestr("MANIFEST.csv", "\n".join(buf) + "\n")
        zf.writestr("RESTORE.md", readme(level, counts["files"], counts["bytes"]))
        if RESTORE_SCRIPT.is_file():
            zf.write(RESTORE_SCRIPT, "restore.py")
    tmp.replace(target)
    # The script also goes beside the archive: needing to unpack the archive to get the thing that
    # unpacks the archive is a trap worth not setting.
    if RESTORE_SCRIPT.is_file():
        (out_dir / "restore.py").write_bytes(RESTORE_SCRIPT.read_bytes())
    counts["archive"] = str(target)
    counts["archive_bytes"] = target.stat().st_size
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--level", choices=LEVELS, default="essential")
    ap.add_argument("--out", help=f"where to write it (default: {backups()})")
    ap.add_argument("--dry", action="store_true", help="say what would be packed and write nothing")
    a = ap.parse_args(argv)

    if not material_root().exists():
        print("there is no private data root on this machine", file=sys.stderr)
        return 1
    print(f"level {a.level}:")
    for path, why in contents(a.level):
        if path.is_dir() or path.name in ("manifest.json", "SOURCE.md"):
            continue
        print(f"  {rel(path):44s} {why}")
    for path, why in contents(a.level):
        if path.is_dir():
            n = len(files_under(path))
            size = sum(p.stat().st_size for p in files_under(path))
            print(f"  {rel(path) + '/':44s} {size / 1e9:6.2f} GB  {n:>7,} files  {why}")

    c = build(Path(a.out) if a.out else backups(), a.level, dry=a.dry)
    if a.dry:
        print(f"\nwould pack {c['files']:,} files, {c['bytes'] / 1e9:.2f} GB")
        return 0
    saved = 1 - c["archive_bytes"] / c["bytes"] if c["bytes"] else 0
    print(f"\n{c['packed']:,} files -> {c['archive']}")
    print(f"{c['archive_bytes'] / 1e9:.2f} GB, {saved:.1%} smaller than the {c['bytes'] / 1e9:.2f} GB "
          f"on disk — most of it was already compressed, so what this buys is one file instead of "
          f"{c['packed']:,}")
    print(f"restore.py is beside it and inside it. Upload both, then:\n"
          f"  python3 restore.py {archive_name(a.level)} --into /path/to/parts-index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
