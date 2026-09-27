"""What the letters and digits of a part number say, read off the standard that assigned them.

    decode("BC548B", ("bjt",))
    -> Pro Electron: B = silicon · C = transistor, low power, audio frequency · 548 = serial number ·
       B = suffix (the maker's selection group)

One file per numbering system under `data/parts/schemes/`, transcribed from the standard or from a
manufacturer that printed it, each citing its references. This module only applies them; it knows no
letter itself.

Two rules keep it from saying something false with confidence:

**A scheme reads only the kinds of device it numbers.** AD633 fits the Pro Electron pattern letter for
letter — A germanium, D audio power transistor — and it is an analogue multiplier from Analog Devices. So
the caller says what kind of part it is (the device kinds of the site, from the dictionary, the model
curation or the extractor's family), and a scheme whose `applies_to` does not include it is not tried. A
part of unknown kind is read by no scheme.

**A letter the table does not have fails the reading.** A Pro Electron number with an unknown function
letter is not Pro Electron with one gap; it is something else, and the page says nothing rather than
four-fifths of an explanation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache

import yaml

from parts_index.core.config import naming_schemes


@dataclass
class Segment:
    text: str
    field: str
    meaning: str


@dataclass
class Decoding:
    scheme: str
    label: str
    segments: list[Segment]
    caveats: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"scheme": self.scheme, "label": self.label,
                "segments": [[s.text, s.field, s.meaning] for s in self.segments],
                "caveats": self.caveats, "refs": self.refs}


@cache
def schemes() -> dict[str, dict]:
    """Every scheme by id, in the order they are tried."""
    d = naming_schemes()
    out = {}
    if d.is_dir():
        for p in sorted(d.glob("*.yaml")):
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            doc["id"] = p.stem
            doc["_forms"] = [(re.compile(f["pattern"]), f) for f in doc.get("forms") or ()]
            out[p.stem] = doc
    return dict(sorted(out.items(), key=lambda kv: (kv[1].get("order", 99), kv[0])))


def _tokens(text: str, table: dict[str, str]) -> list[str] | None:
    """Split `text` into the longest keys of `table`, left to right; None if something is left over."""
    keys = sorted(table, key=len, reverse=True)
    out, i = [], 0
    while i < len(text):
        k = next((k for k in keys if text.startswith(k, i)), None)
        if k is None:
            return None
        out.append(table[k])
        i += len(k)
    return out


def meaning_of(value: str, spec: dict) -> str | None:
    """What one piece of a part number means under its field's rules, or None if the rules do not know it."""
    values = spec.get("values") or {}
    if value in values:
        return values[value]
    if "each" in spec:
        parts = [spec["each"].get(c) for c in value]
        if None not in parts:
            return (spec.get("joiner") or ", ").join(parts)
        return None
    if "tokens" in spec:
        parts = _tokens(value, spec["tokens"])
        return "; ".join(parts) if parts is not None else None
    if "ranges" in spec and value.isdigit():
        n = int(value)
        hit = next((m for lo, hi, m in spec["ranges"] if lo <= n <= hi), None)
        if hit:
            return hit
    if "meaning" in spec:
        text = spec["meaning"]
        hint = (spec.get("first") or {}).get(value[:1])
        return f"{text} {hint}" if hint else text
    return None


def read_with(scheme: dict, part: str, known: frozenset[str] | set[str] | None = None) -> Decoding | None:
    """The first form of `scheme` that reads `part` completely.

    A form marked `unless_known_without: <group>` stands aside when the number without that group is a
    part in its own right: the Soviet envelope letters A, B and D are also American revision letters,
    and 1X2A is the 1X2 revised, not a Soviet subminiature. Without the list of known parts such a form
    is not tried at all.
    """
    fields = scheme.get("fields") or {}
    for rx, form in scheme["_forms"]:
        m = rx.fullmatch(part)
        if not m:
            continue
        g = form.get("unless_known_without")
        if g and (known is None or part[:m.start(g)] in known):
            continue
        segments, ok = [], True
        for name, value in sorted(((k, v) for k, v in m.groupdict().items() if v is not None),
                                  key=lambda kv: m.start(kv[0])):
            spec = fields.get(name) or {}
            if value == "" and ("" not in (spec.get("values") or {})):
                continue                              # an optional piece that is not there
            meaning = meaning_of(value, spec)
            if meaning is None:
                ok = False
                break
            segments.append(Segment(value, spec.get("label", name), meaning))
        if ok and segments:
            return Decoding(scheme["id"], scheme.get("label", scheme["id"]), segments,
                            list(scheme.get("caveats") or ()), list(scheme.get("refs") or ()))
    return None


def decode(part: str, devices: tuple[str, ...] | list[str],
           known: frozenset[str] | set[str] | None = None) -> Decoding | None:
    """How the number reads under the first scheme that numbers this kind of device and knows every letter.

    `known` is every part number the project knows, for the forms that must not read a revision letter as
    something else; without it those forms are skipped.
    """
    if not part or not devices:
        return None
    for s in schemes().values():
        if not set(devices) & set(s.get("applies_to") or ()):
            continue
        d = read_with(s, part, known)
        if d:
            return d
    return None


def check(references: set[str]) -> list[str]:
    """Each scheme reads its own examples, cites references that exist, and names only fields it defines."""
    out = []
    for sid, s in schemes().items():
        for r in s.get("refs") or ():
            if r not in references:
                out.append(f"scheme {sid}: reference {r} is not in references.csv")
        if not s.get("applies_to"):
            out.append(f"scheme {sid}: applies_to is empty, so it would read nothing")
        for rx, form in s["_forms"]:
            for g in rx.groupindex:
                if g not in (s.get("fields") or {}):
                    out.append(f"scheme {sid}: pattern group {g} has no field")
            ex = form.get("example")
            d = read_with(s, ex, frozenset()) if ex else None
            if not d:
                out.append(f"scheme {sid}: its own example {ex} does not decode")
    return out
