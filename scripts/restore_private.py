"""Put a private-data backup back where it belongs, and prove it arrived intact.

    python3 restore_private.py parts-index-private-2026-09-21.zip --into /path/to/parts-index

The archive holds files at the paths they occupy inside the checkout, so restoring is an unpack into the
repository root — but not a blind one. Every file was checksummed when the archive was written, and
`MANIFEST.csv` travels inside it, so this checks each file after writing it and says so.

Nothing already present is overwritten. A file that is already there and already correct is left alone,
which makes a second run cheap and a partial restore safe to resume. A file that is there and *differs*
is refused and named: that is either newer work or a corrupted download, and neither should be silently
replaced. `--force` overwrites those, `--verify-only` writes nothing at all.

Standard library only, so it runs from a plain Python on any machine that has just downloaded the file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path

MANIFEST = "MANIFEST.csv"
CHUNK = 1 << 20


def digest(f) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    while True:
        b = f.read(CHUNK)
        if not b:
            return h.hexdigest(), n
        h.update(b)
        n += len(b)


def recorded(zf: zipfile.ZipFile) -> dict[str, str]:
    """path -> sha256, as written when the archive was made."""
    if MANIFEST not in zf.namelist():
        return {}
    with zf.open(MANIFEST) as raw:
        rows = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
        return {r["path"]: r["sha256"] for r in rows}


def safe_target(into: Path, name: str) -> Path | None:
    """Where this member goes, or None if it would land outside the target directory."""
    if name.startswith("/") or ".." in Path(name).parts:
        return None
    target = into / name
    try:
        target.relative_to(into)
    except ValueError:
        return None
    return target


def restore(archive: Path, into: Path, *, force: bool = False, verify_only: bool = False) -> dict:
    counts = {"written": 0, "already_there": 0, "differs": 0, "bad_checksum": 0,
              "unsafe": 0, "bytes": 0}
    conflicts: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        want = recorded(zf)
        members = [m for m in zf.namelist() if not m.endswith("/") and m != MANIFEST]
        for i, name in enumerate(members, 1):
            target = safe_target(into, name)
            if target is None:
                counts["unsafe"] += 1
                continue
            expected = want.get(name, "")
            if target.exists():
                with open(target, "rb") as f:
                    have, _ = digest(f)
                if not expected or have == expected:
                    counts["already_there"] += 1
                    continue
                counts["differs"] += 1
                if not force:
                    conflicts.append(name)
                    continue
            if verify_only:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            with zf.open(name) as src, open(tmp, "wb") as out:
                got, n = hashlib.sha256(), 0
                while True:
                    b = src.read(CHUNK)
                    if not b:
                        break
                    got.update(b)
                    out.write(b)
                    n += len(b)
            if expected and got.hexdigest() != expected:
                tmp.unlink(missing_ok=True)
                counts["bad_checksum"] += 1
                conflicts.append(f"{name} (checksum after unpacking does not match)")
                continue
            tmp.replace(target)
            counts["written"] += 1
            counts["bytes"] += n
            if i % 5000 == 0:
                print(f"  {i:,}/{len(members):,} …", flush=True)
    counts["conflicts"] = conflicts
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("archive", help="the .zip downloaded from the backup")
    ap.add_argument("--into", default=".", help="the parts-index checkout to restore into (default: here)")
    ap.add_argument("--force", action="store_true", help="overwrite files that are there and differ")
    ap.add_argument("--verify-only", action="store_true", help="check and write nothing")
    a = ap.parse_args(argv)

    archive, into = Path(a.archive), Path(a.into).resolve()
    if not archive.is_file():
        print(f"{archive} is not here", file=sys.stderr)
        return 1
    if not (into / "pyproject.toml").is_file():
        print(f"{into} does not look like a parts-index checkout (no pyproject.toml).\n"
              f"Pass --into /path/to/parts-index.", file=sys.stderr)
        return 1

    c = restore(archive, into, force=a.force, verify_only=a.verify_only)
    print(f"{c['written']:,} files restored ({c['bytes'] / 1e9:.2f} GB), "
          f"{c['already_there']:,} already there and correct")
    if c["unsafe"]:
        print(f"{c['unsafe']} members refused: they named a path outside {into}", file=sys.stderr)
    if c["bad_checksum"]:
        print(f"{c['bad_checksum']} files did not match their checksum and were not kept — "
              f"the download is probably damaged", file=sys.stderr)
    if c["conflicts"]:
        print(f"\n{len(c['conflicts'])} file(s) already there and different, left untouched:",
              file=sys.stderr)
        for name in c["conflicts"][:20]:
            print(f"  {name}", file=sys.stderr)
        if not a.force:
            print("Re-run with --force to replace them.", file=sys.stderr)
    return 1 if (c["bad_checksum"] or c["unsafe"]) else 0


if __name__ == "__main__":
    sys.exit(main())
