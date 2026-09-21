"""A title worth showing, from a `<title>` written for a browser tab.

Sites use that tag for whatever they like. One large archive puts the whole abstract of the article in
it; hundreds of pages leave the default their CMS generated, so `Index of /_pdf/2SK/` and `index.html`
turn up as the name of a document. Both are useless in a list of results, and the second is worse than
useless because every such page looks the same.

Where the tag says nothing, the URL usually does: the last path segment that is not itself a filler word
is what a person would call the page. Ported unchanged from the old pipeline, which is where the three
regexes were learned; `tests/schematics/test_titles.py` pins what they do.
"""
from __future__ import annotations

import re

SITE_NAME = re.compile(r"^(?:[\w.-]+\.(?:com|net|org|co\.uk|cl|fr|de)|ESP)\s*[|:]\s*", re.I)
SITE_TAIL = re.compile(r"\s*[|–-]\s*(?:[\w.-]+\.(?:com|net|org|co\.uk)"
                       r"|Elliott Sound Products|The Valve Wizard|ESP)\s*$", re.I)
NO_TITLE = re.compile(r"index(\.\w+)*|Index of /.*|default(\.\w+)*|untitled document", re.I)
MAX = 110
LONG = 70        # past this, a title is usually a title followed by a description


def from_url(url: str) -> str:
    """The last path segment that means something, as a name."""
    seg = [s for s in re.sub(r"[?#].*", "", url or "").split("/") if s]
    host, seg = (seg[1] if len(seg) > 1 else "?"), seg[2:]
    for s in reversed(seg):          # walk up: .../index.php is as useless as the <title> that sent us here
        name = re.sub(r"[-_+]+", " ", re.sub(r"\.\w{1,5}$", "", s) or s).strip()
        if name and not NO_TITLE.fullmatch(name):
            return name if any(c.isupper() for c in name) else name.capitalize()
    return host


def clean(title: str | None, url: str) -> str:
    """The name to show for this document."""
    t = re.sub(r"\s+", " ", (title or "").replace("\xa0", " ")).strip()
    if not t or NO_TITLE.fullmatch(t):
        return from_url(url)
    t = SITE_TAIL.sub("", SITE_NAME.sub("", t)).strip()
    if len(t) > LONG:                 # cut the description off at a sentence end, or a dash that leaves a real name
        for rx in (r"\s[–-]\s", r"(?<=[a-z])\.\s"):
            m = re.search(rx, t)
            if m and m.start() >= 15:
                t = t[:m.start()]
                break
    return t.strip(" .-–")[:MAX] or from_url(url)
