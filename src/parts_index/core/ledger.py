"""Processing ledger: what has been done to every item, so nothing is processed twice.

One CSV per source, committed under data/<pillar>/state/<source>.csv, one row per item (a URL). Every
pipeline stage asks the ledger before working and stamps it afterwards:

    led = Ledger(path, stages=SCHEMATIC_STAGES, fields=SCHEMATIC_FIELDS)
    for url in urls:
        if led.done(url, "ocr", version=OCR_VERSION):
            continue                                   # same input, same stage version: skip
        ...work...
        led.stamp(url, "ocr", version=OCR_VERSION, n_pages=12, text_method="ocr_boxes")
    led.save()

Rules
  * A stage is done when its `<stage>_at` is set and, if the stage is versioned, `<stage>_v` equals the
    version asked for. Bump the version constant to reprocess; never delete state to force a rerun.
  * Stages are ordered. When the input changes (a new sha256 on download) every later stamp is cleared,
    so the item flows through the pipeline again. Stamping a stage never touches earlier stages.
  * `skip_reason` marks an item that must not be retried (404, not a document, login wall ...). It counts
    as done for every stage until somebody clears it.
  * Files are rewritten atomically, sorted by key, so diffs are small and an interrupted run loses nothing
    that was saved.
"""
from __future__ import annotations

import csv
import os
import tempfile
from datetime import date
from pathlib import Path

# pillar 1: a document or page of a source site, magazine or book
SCHEMATIC_STAGES = ("download", "ocr", "index", "linkcheck")
SCHEMATIC_VERSIONED = ("ocr", "index")
SCHEMATIC_FIELDS = (
    "key", "url", "role", "type", "http", "bytes", "sha256", "download_at",
    "n_pages", "text_method", "ocr_at", "ocr_v", "index_at", "index_v",
    "linkcheck_at", "link_ok", "skip_reason",
    # Not a stage: the crawler's own note that it has read this page's links and written what they
    # pointed at into this ledger. A page with it is never asked for again, even when the file it was
    # read from has been deleted — which it will be, since a downloaded document is temporary and the
    # OCR of it is what the project keeps. Clear it to walk a site again looking for what is new.
    "crawl_at",
)

# the vocabulary: one index page of a census source (a type list, a databook's numerical index). No OCR
# stage — these lists are read, not scanned — and no linkcheck, because the URL read is the URL published.
CENSUS_STAGES = ("fetch", "read")
CENSUS_VERSIONED = ("read",)
CENSUS_FIELDS = (
    "key", "url", "http", "bytes", "sha256", "fetch_at", "n_parts", "read_at", "read_v", "skip_reason",
)

# pillar 2: a model file of a model source, or the attempt to find the model of one part at that source.
# Verification is per part and candidate, not per file: its state lives in data/verification/.
MODEL_STAGES = ("fetch", "index")
MODEL_VERSIONED = ("index",)
MODEL_FIELDS = (
    "key", "url", "part", "status", "bytes", "sha256", "fetch_at", "n_defs", "index_at", "index_v", "skip_reason",
)


# pillar 3: one part's models held against its data sheet (key `<kind>/<part>`), or one data sheet read
# (key `sheet:<doc>`). The stages do not feed each other in a line as a download feeds its OCR: each reads
# its own inputs — the recipe's model files, the sheet's pages, the bench's results — so each keeps a
# fingerprint of them in `<stage>_in`, and is fresh while its version and that fingerprint are unchanged.
VERIFY_STAGES = ("cards", "claims", "rows", "figures", "bench")
VERIFY_VERSIONED = VERIFY_STAGES
VERIFY_FIELDS = ("key", *(f"{s}_{x}" for s in VERIFY_STAGES for x in ("in", "at", "v")), "skip_reason")


def today() -> str:
    return date.today().isoformat()


class Ledger:
    def __init__(self, path, stages=SCHEMATIC_STAGES, fields=SCHEMATIC_FIELDS, versioned=SCHEMATIC_VERSIONED):
        self.path = Path(path)
        self.stages, self.fields, self.versioned = tuple(stages), tuple(fields), tuple(versioned)
        self.rows: dict[str, dict[str, str]] = {}
        self.dirty = False
        if self.path.exists():
            with open(self.path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    self.rows[r["key"]] = {k: r.get(k, "") or "" for k in self.fields}

    def __len__(self):
        return len(self.rows)

    def __contains__(self, key):
        return key in self.rows

    def get(self, key) -> dict[str, str] | None:
        return self.rows.get(key)

    def row(self, key) -> dict[str, str]:
        if key not in self.rows:
            self.rows[key] = dict.fromkeys(self.fields, "")
            self.rows[key]["key"] = key
            self.dirty = True
        return self.rows[key]

    # ---- questions -------------------------------------------------------------------------------
    def done(self, key, stage, version: str | None = None) -> bool:
        r = self.rows.get(key)
        if r is None:
            return False
        if r["skip_reason"]:
            return True
        if not r[f"{stage}_at"]:
            return False
        if stage in self.versioned and version is not None and r[f"{stage}_v"] != version:
            return False
        return True

    def fresh(self, key, stage, version: str, digest: str) -> bool:
        """Done at this version from exactly these inputs: for stages that keep a fingerprint of what they
        read (`<stage>_in`), where a changed input, not only a new version, means the work is redone."""
        r = self.rows.get(key)
        return self.done(key, stage, version) and r is not None and (r["skip_reason"] != "" or r[f"{stage}_in"] == digest)

    def pending(self, stage, version: str | None = None) -> list[str]:
        """Keys whose earlier stages are done and this one is not."""
        i = self.stages.index(stage)
        out = []
        for key, r in self.rows.items():
            if r["skip_reason"] or not self._applies(r, stage) or self.done(key, stage, version):
                continue
            if all(r[f"{s}_at"] for s in self.stages[:i] if self._applies(r, s)):
                out.append(key)
        return out

    @staticmethod
    def _applies(r, stage) -> bool:
        # born-digital text and HTML pages need no OCR pass
        return not (stage == "ocr" and (r.get("text_method") == "text" or r.get("type") == "html"))

    # ---- stamps ----------------------------------------------------------------------------------
    def stamp(self, key, stage, version: str | None = None, when: str | None = None, **values) -> None:
        r = self.row(key)
        new_sha = values.get("sha256")
        if stage == self.stages[0] and new_sha and r["sha256"] and new_sha != r["sha256"]:
            self._clear_after(r, stage)                       # the input changed: later stages run again
        for k, v in values.items():
            if k not in self.fields:
                raise KeyError(f"{k!r} is not a ledger field")
            r[k] = "" if v is None else str(v)
        r[f"{stage}_at"] = when or today()
        if stage in self.versioned:
            r[f"{stage}_v"] = version or ""
        self.dirty = True

    def skip(self, key, reason: str, **values) -> None:
        r = self.row(key)
        r.update({k: "" if v is None else str(v) for k, v in values.items()})
        r["skip_reason"] = reason
        self.dirty = True

    def _clear_after(self, r, stage) -> None:
        for s in self.stages[self.stages.index(stage) + 1:]:
            r[f"{s}_at"] = ""
            if s in self.versioned:
                r[f"{s}_v"] = ""

    # ---- persistence -----------------------------------------------------------------------------
    def save(self) -> None:
        if not self.dirty and self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.fields, lineterminator="\n")
            w.writeheader()
            for key in sorted(self.rows):
                w.writerow(self.rows[key])
        os.replace(tmp, self.path)
        self.dirty = False

    # ---- reporting -------------------------------------------------------------------------------
    def summary(self) -> dict[str, int]:
        out = {"items": len(self.rows), "skipped": sum(1 for r in self.rows.values() if r["skip_reason"])}
        for s in self.stages:
            out[s] = sum(1 for r in self.rows.values() if r[f"{s}_at"] and not r["skip_reason"])
        return out
