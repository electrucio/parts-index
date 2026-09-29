"""Which way round a transistor is — NPN or PNP, N- or P-channel — and only when something says so.

Three things say it. The letters of a Japanese name, because JIS C7012 gives 2SA and 2SB to PNP
transistors, 2SC and 2SD to NPN ones, 2SJ to P-channel and 2SK to N-channel field-effect transistors. The
device type a SPICE model library defines the part as, because an NPN model is an NPN model. And a
manufacturer's catalogue, where its category or its data sheet's title names the polarity in words.

A bipolar transistor's polarity and a field-effect transistor's channel are two questions, asked apart:
a JEDEC number that could be either answers each with what is said of it. When the sources that answer a
question disagree, it has no answer — a wrong NPN in the list is worse than none.
"""
from __future__ import annotations

import re

VALUES = ("NPN", "PNP", "N-channel", "P-channel")
CLASS = {"NPN": "bipolar", "PNP": "bipolar", "N-channel": "fet", "P-channel": "fet"}

# A SPICE device type, by the polarity it is. VDMOS carries its channel as a flag the model catalogue does
# not keep, and a sub-circuit says nothing about what is inside it, so neither is here.
SPICE = {"NPN": "NPN", "PNP": "PNP", "NJF": "N-channel", "PJF": "P-channel",
         "NMOS": "N-channel", "PMOS": "P-channel"}

# How many libraries one polarity needs for each library that says the other. Libraries copy one another
# and a hobbyist's file gets one wrong now and then: groups.io's standard.bjt defines 2N4403 as NPN,
# where ten other libraries, onsemi's among them, say PNP. Ten to one is not doubt; four to three is.
MAJORITY = 3

WORDS = [
    ("NPN", re.compile(r"\bNPN\b", re.I)),
    ("PNP", re.compile(r"\bPNP\b", re.I)),
    ("N-channel", re.compile(r"\bN[- ]?channel\b", re.I)),
    ("P-channel", re.compile(r"\bP[- ]?channel\b", re.I)),
]
# "N- and P-channel", "N/P-channel", "complementary": a sheet for a pair, which says nothing of one part.
# Nor does "Complement to type 2SA1295", which is the title of the 2SC3264's sheet, filed under both.
BOTH = re.compile(r"\b[NP]\s*-?\s*(?:/|and|&)\s*[NP]\b|\bcomplement", re.I)


def by_libraries(votes: dict[str, set[str]]) -> list[str]:
    """What the model libraries settle, from the libraries that define the part as each polarity."""
    out = []
    for value in VALUES:
        mine = len(votes.get(value) or ())
        other = max((len(s) for v, s in votes.items() if v != value and CLASS.get(v) == CLASS[value]), default=0)
        if mine and mine >= MAJORITY * other:
            out.append(value)
    return out


def in_words(text: str) -> str:
    """The one polarity a catalogue's words name, or "" when they name none, or both."""
    if BOTH.search(text):
        return ""
    found = {value for value, rx in WORDS if rx.search(text)}
    return found.pop() if len(found) == 1 else ""


def settled(claims: list[list[str]]) -> dict[str, str]:
    """Each question's answer, when every source that answers it agrees: {"bipolar": "NPN"}."""
    said: dict[str, set[str]] = {}
    for value, *_ in claims:
        said.setdefault(CLASS[value], set()).add(value)
    return {c: vs.pop() for c, vs in said.items() if len(vs) == 1}


# --- a page somebody found for the part -------------------------------------------------------------
# How far either side of the part's number a page may say which way round it is. A data sheet's first
# line names the part and says "NPN silicon planar" within a sentence or two; further off, the words are
# as likely to be about the next part in a table.
NEAR = 300
# "PNP complement: BC557", "complementary to BD140 (PNP)": the polarity of another part, blanked out
# before the page is read.
COMPLEMENT = re.compile(r"(?:\b(?:NPN|PNP|[NP][- ]?channel)\W{0,3})?\bcomplement\w*[^.;]{0,60}", re.I)


def name_in(part: str) -> re.Pattern:
    """The part's number as a page prints it: BC109 also as "BC 109" or "BC-109", with a grade letter
    after it (BC109C), and never inside a longer number (BC1090, ABC109)."""
    pieces = re.findall(r"[A-Z]+|\d+", part.upper())
    return re.compile(r"(?<![A-Z0-9])" + r"[\s-]?".join(map(re.escape, pieces)) + r"(?!\d)")


def read_sheet(text: str, part: str, claimed: str, near: int = NEAR) -> str:
    """The words on a page that say `claimed` of `part`, or "" when it does not — or says the other too.

    Every place the part's number is printed is read, up to ten, with what is printed around it. The
    page says it when those places name this polarity and never the other one of its question; what is
    returned is a few words either side of the mention nearest the number, for a reader to check.
    """
    if claimed not in CLASS:
        return ""
    flat = " ".join(text.split())
    upper = flat.upper()
    seen: set[str] = set()
    best: tuple[int, int, int] | None = None                    # (distance, start, end) of the nearest mention
    for i, m in enumerate(name_in(part).finditer(upper)):
        if i == 10:
            break
        lo = max(0, m.start() - near)
        window = COMPLEMENT.sub(lambda c: " " * len(c.group(0)), flat[lo:m.end() + near])
        for value, rx in WORDS:
            if CLASS[value] != CLASS[claimed]:
                continue
            for w in rx.finditer(window):
                seen.add(value)
                if value == claimed:
                    s, e = lo + w.start(), lo + w.end()
                    d = max(m.start() - e, s - m.end(), 0)
                    if best is None or d < best[0]:
                        best = (d, s, e)
    if seen != {claimed} or best is None:
        return ""
    _, s, e = best
    s, e = max(0, s - 60), min(len(flat), e + 60)
    words = flat[s:e]
    if s > 0:
        words = words.split(" ", 1)[-1]
    if e < len(flat):
        words = words.rsplit(" ", 1)[0]
    return words
