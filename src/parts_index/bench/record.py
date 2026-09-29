"""One part's record in data/verification/, which several steps write a section of each.

    {"schema": 1, "part": "2N3904", "kind": "bjt", "cards": {<hash>: …}, "claims": {…}, "bench": {…}}

Models are keyed by the `hash` their recipe gives them, so a result stays attached to the code it was
measured on however the recipe is reordered. A step rewrites its own section and leaves the others as
they are; the file is replaced atomically, with sorted keys, so a rerun that changes nothing changes no
byte of it.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

from parts_index.core.config import verification, verification_state
from parts_index.core.ledger import VERIFY_FIELDS, VERIFY_STAGES, VERIFY_VERSIONED, Ledger

SCHEMA = 1
HEAD = {"schema", "part", "kind"}


def load(kind: str, part: str) -> dict:
    p = verification(kind, part)
    if not p.exists():
        return {"schema": SCHEMA, "part": part, "kind": kind}
    return json.loads(p.read_text(encoding="utf-8"))


def write_section(kind: str, part: str, section: str, data: dict) -> bool:
    """Replace one section of the part's record. Returns whether the file changed."""
    doc = load(kind, part)
    if data:
        doc[section] = data
    else:
        doc.pop(section, None)
    p = verification(kind, part)
    if not set(doc) - HEAD:                     # nothing is known about this part's models: no record
        if p.exists():
            p.unlink()
            return True
        return False
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
    return True


def ledger() -> Ledger:
    return Ledger(verification_state(), stages=VERIFY_STAGES, fields=VERIFY_FIELDS, versioned=VERIFY_VERSIONED)


def digest(obj) -> str:
    """A fingerprint of what a step read, for `Ledger.fresh`."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]
