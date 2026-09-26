"""Gather a source's file URLs again, from the site's own listing, and add what is new to its list.

    pidx schematics list --source audiocircuit [--limit 20] [--dry]

`download` walks the list under `core.config.source_list`; this is where that list comes from when it
ages or turns out to be short. It only ever **appends**: a URL already listed keeps its place and its
ledger row, so a re-listing costs nothing for what is already held and a download that is running reads
its own copy undisturbed.

audiocircuit: the sitemap names one page per brand, and each brand page shows a hundred files at a time
behind `?eeListID=1&ee=1&eePage=N`. The list gathered in September took page 0 only, so 48 of the 358
brands stopped at exactly a hundred files — Akai alone has 789. Walk the pages until one brings nothing
new, which is how the site says there is no more.

A dead site has no listing of its own, and asking it is how you learn it is dead. What it published is
still readable in the Wayback Machine, and the CDX API will say what it held: a source with a `wayback:`
block is listed from there instead, one row per document the archive holds a good capture of.

A site that publishes a sitemap has already written the list, and a `sitemap:` block says to read it
rather than walk the site. It is the polite way in and usually the complete one: TI names its own in
robots.txt, and one of the files it points at holds 29,562 documents that no amount of crawling would
have found, because nothing links to most of them from anywhere a crawler starts.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import quote, urljoin

from parts_index.core import http, parts
from parts_index.core.config import listing_cache, parts_census, source_list
from parts_index.schematics.download import registry_entry

PAGE_SIZE_GUESS = 100
MAX_PAGES = 60

SITEMAP_LOC = re.compile(r"<loc>([^<]+)</loc>")
PDF_HREF = re.compile(r'href="([^"]+\.pdf)"', re.I)
TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def _unescape(s: str) -> str:
    import html

    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _brand(html_text: str, url: str) -> str:
    m = TITLE.search(html_text)
    name = _unescape(m.group(1)) if m else ""
    name = re.sub(r"\s*(Schematics|Service Manuals?|and|&)\s*", " ", name).strip(" -–|")
    return name or url.rstrip("/").rsplit("/", 1)[-1].title()


def _title_of(pdf_url: str) -> str:
    stem = pdf_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[-_]+", " ", stem).strip()


def audiocircuit(delay: float, limit: int = 0):
    """-> one batch of rows per brand, as each brand is finished. A batch at a time, because a listing run
    is long and a run that saves only at the end saves nothing when it is interrupted."""
    r = http.get("https://audiocircuit.dk/sitemap.xml", delay=delay)
    if not r.ok:
        raise SystemExit(f"audiocircuit sitemap: {r.status} {r.why}")
    pages = [u for u in SITEMAP_LOC.findall(r.text())
             if re.fullmatch(r"https://audiocircuit\.dk/[a-z0-9._-]+/", u)]
    print(f"{len(pages)} pages in the sitemap", file=sys.stderr)
    fetched = 0
    for page in pages:
        seen_here: set[str] = set()
        brand = ""
        rows = []
        for n in range(MAX_PAGES):
            url = page if n == 0 else f"{page}?eeListID=1&ee=1&eePage={n}"
            if limit and fetched >= limit:
                yield rows
                return
            resp = http.get(url, delay=delay)
            fetched += 1
            if not resp.ok:
                break
            body = resp.text()
            brand = brand or _brand(body, page)
            found = [urljoin(url, h) for h in PDF_HREF.findall(body)]
            fresh = [u for u in found if u not in seen_here]
            if not fresh:
                break
            seen_here.update(fresh)
            rows += [{"url": u, "title": _title_of(u), "brand_hint": brand, "kind": "schematic",
                      "origin": "factory", "page": page, "source": "audiocircuit"} for u in fresh]
            if len(found) < PAGE_SIZE_GUESS:
                break
        if rows:
            yield rows
            print(f"  {brand or page}: {len(seen_here)}", file=sys.stderr)


CDX = "https://web.archive.org/cdx/search/cdx"
# `id_` asks for the bytes as they were archived, without the banner the Wayback Machine puts on a page.
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
CDX_TIMEOUT = 300           # a page of this index is a database query, not a file


def _cached(source: str, url: str, delay: float) -> str:
    """One index page, from the copy kept last time when there is one.

    Narrowing a `keep` pattern is a decision about what we want, not a reason to ask a site for its
    sitemap again. Renesas was walked three times in one morning — once for the census, once to list it
    and once because the pattern changed — and the third walk was 118 requests for files already on
    this disk.
    """
    path = listing_cache(source) / hashlib.sha1(url.encode()).hexdigest()[:16]
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    r = http.get(url, delay=delay, timeout=CDX_TIMEOUT, max_bytes=SITEMAP_SIZE)
    if not r.ok:
        raise SystemExit(f"sitemap: {r.status} {r.why}  ({url})")
    body = (gzip.decompress(r.body).decode("utf-8", "replace")
            if r.body[:2] == b"\x1f\x8b" else r.text())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return body


def _cdx(params: list[tuple[str, str]], delay: float) -> list[list[str]]:
    """One CDX query. A list of pairs, not a mapping: `filter` is given more than once."""
    query = "&".join(f"{k}={v}" for k, v in params)
    r = http.get(f"{CDX}?{query}", delay=delay, timeout=CDX_TIMEOUT)
    if not r.ok:
        raise SystemExit(f"wayback cdx: {r.status} {r.why}  ({query})")
    return [line.split(" ") for line in r.text().splitlines() if line.strip()]


def wayback(source: str, cfg: dict):
    """-> one batch per page of the CDX index: every document the archive holds a good capture of.

    `collapse=urlkey` asks for one capture per URL rather than every visit the crawler ever made, which
    is the difference between a few thousand rows and a few hundred thousand.
    """
    domain, types = cfg["domain"], cfg.get("types", ["application/pdf"])
    # What a dead site left behind is not all of one kind. mutable-instruments.net left 196 PDFs in the
    # archive, of which 63 are schematics and the rest are user manuals, panel drawings and photographs
    # of boards — so `keep` picks the folders that hold a circuit, the same job it does for a sitemap.
    keep = re.compile(cfg["keep"]) if cfg.get("keep") else None
    common = [("url", domain), ("matchType", "domain"), ("collapse", "urlkey"),
              ("filter", "statuscode:200"), ("filter", f"mimetype:({'|'.join(types)})")]

    def lister(delay: float, limit: int = 0):
        # `showNumPages` counts the index's own blocks, before the filters: a page of it can yield
        # anything from nothing to everything, and the count is only there to say when to stop.
        pages = int(_cdx(common + [("showNumPages", "true")], delay)[0][0])
        print(f"{domain}: {pages} pages of CDX index", file=sys.stderr)
        for n in range(pages):
            rows = _cdx(common + [("fl", "original,timestamp,length"), ("page", str(n))], delay)
            if keep:
                rows = [r for r in rows if r and keep.search(r[0])]
            batch = [{"url": REPLAY.format(stamp=stamp, url=original), "title": _title_of(original),
                      "kind": cfg.get("kind", "schematic"), "origin": cfg.get("origin", "factory"),
                      "page": original, "archived": stamp, "bytes": int(size) if size.isdigit() else 0,
                      "source": source}
                     for original, stamp, size in (r for r in rows if len(r) == 3)]
            if batch:
                yield batch
            print(f"  page {n + 1}/{pages}: {len(batch)}", file=sys.stderr)
            if limit and n + 1 >= limit:
                return

    return lister


SITEMAP_SIZE = 64 << 20         # an index of a large site, not a page
SITEMAP_DEPTH = 3               # a sitemap index may point at sitemap indexes


def _locs(source: str, url: str, delay: float, depth: int = SITEMAP_DEPTH) -> list[str]:
    """Every URL a sitemap names, following the indexes that point at other sitemaps.

    Several sites serve theirs gzipped as a file rather than as an encoding — vishay.com/sitemap.xml.gz
    — which arrives as the bytes it is, so `_cached` unpacks it rather than the client.
    """
    body = _cached(source, url, delay)
    found = SITEMAP_LOC.findall(body)
    if "<sitemapindex" in body[:2000] and depth:
        out: list[str] = []
        for inner in found:
            out += _locs(source, inner, delay, depth - 1)
        return out
    return found


def sitemap(source: str, cfg: dict):
    """-> one batch of rows, from the list the site publishes about itself.

    `keep` is what makes this usable rather than indiscriminate. TI's literature sitemap names every
    document it has, marketing bulletins and processor manuals included; the pattern says which families
    hold a circuit — application notes, reference design guides, and the user guides of the evaluation
    boards, which carry the board's own schematic.
    """
    keep = re.compile(cfg["keep"]) if cfg.get("keep") else None

    def lister(delay: float, limit: int = 0):
        locs = list(dict.fromkeys(_locs(source, cfg["url"], delay)))    # TI names a document in two of its sitemaps
        print(f"{source}: {len(locs)} URLs in the sitemap", file=sys.stderr)
        wanted = [u for u in locs if not keep or keep.search(u)]
        print(f"  {len(wanted)} of them kept by `keep`", file=sys.stderr)
        yield [{"url": u, "title": u.rsplit("/", 1)[-1].upper(), "kind": cfg.get("kind", "schematic"),
                "origin": cfg.get("origin", "factory"), "page": u, "source": source}
               for u in (wanted[:limit] if limit else wanted)]

    return lister


# --- open hardware, by the API and never the HTML ------------------------------------------------------
# A repository is a listing somebody else already made: `git/trees/{sha}?recursive=1` names every file in
# one request. What is wanted is the schematic sources, which carry the part numbers as fields rather than
# as characters a reader guessed — see schematics/cad.py.
#
# This is also the route GitHub asks for. Its robots.txt opens with "If you would like to crawl GitHub
# contact us ... We also provide an extensive API", and api.github.com and raw.githubusercontent.com
# answer 404 for robots.txt, which under RFC 9309 is no restriction at all. So the API is the polite door
# and the HTML is not.
GH = "https://api.github.com"
GH_EXT = (".kicad_sch", ".sch", ".brd")           # KiCad new and old, EAGLE; .brd is a board, kept for its link
GH_PER_PAGE = 100
GH_MAX_PAGES = 40                                 # 4,000 repositories, and adafruit has 2,027
GH_SEARCH_DELAY = 6.0                             # 30 repository searches a minute
GH_CODE_DELAY = 15.0                              # ... and 10 code searches a minute, the tighter limit
GH_RATE_WAIT = 65.0                               # both are per-minute windows, so one is waited out
GH_SEARCH_PAGES = 5                               # 100 a page; a topic of more than 500 is not a topic
GH_CODE_HITS = 100                                # one page of a code search names enough repositories
GH_REPO_URL = re.compile(r"github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?(?:[/#?\s\"'<)\]]|$)")


def _gh_token() -> str:
    """Whatever `gh auth login` stored, so this needs no second credential. Empty when there is none."""
    try:
        import subprocess
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:                                      # noqa: BLE001  no gh, no token, no matter
        return ""


def _gh_raw(path: str, delay: float) -> http.Response:
    """One GitHub API call, with the token the `gh` command already holds when there is one."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or _gh_token()
    return http.get(f"{GH}{path}", delay=delay, ua=http.BROWSER_UA, robots=False,
                    headers={"Accept": "application/vnd.github+json",
                             **({"Authorization": f"Bearer {token}"} if token else {})})


def _gh(path: str, delay: float) -> list | dict:
    r = _gh_raw(path, delay)
    if not r.ok:
        raise SystemExit(f"github: {r.status} {r.why}  ({path})")
    return json.loads(r.text())


def _gh_try(path: str, delay: float, tries: int = 3) -> list | dict | None:
    """A search that may be refused for pace, waited out rather than given up on.

    The search limits are per minute and not per hour — thirty repository searches, ten code searches —
    so a 403 here is the complaint about pace that rule 3 tells apart from a refusal of consent, and the
    answer to it is a minute of patience. Learnt by exceeding it: two code searches every seven seconds
    bought about fifty seconds of work and then nothing.
    """
    for _ in range(tries):
        r = _gh_raw(path, delay)
        if r.ok:
            return json.loads(r.text())
        if r.status not in (403, 429):
            return None
        print(f"  github asked for less pace; waiting {GH_RATE_WAIT:.0f}s", file=sys.stderr)
        time.sleep(GH_RATE_WAIT)
    return None


def _searched(source: str, path: str, delay: float) -> list[str]:
    """The repository names one search returns, kept on disk under the source's listing cache.

    Only the names are kept and not the answer, because that is all any caller wants from a search and
    because there are a great many of them: asking GitHub about 6,889 part numbers is a day and a half of
    work that will be interrupted, and the next run must not pay for it twice. Same reason the sitemaps
    are cached, and the same mechanism.
    """
    keep = listing_cache(source) / f"search-{hashlib.sha1(path.encode()).hexdigest()[:16]}.txt"
    if keep.exists():
        return [n for n in keep.read_text(encoding="utf-8").split() if n]
    got = _gh_try(path, delay)
    if got is None:
        return []
    items = got.get("items", []) if isinstance(got, dict) else []
    # A repository search names the repository at the top level; a code search names the file, with its
    # repository inside it. Both are asked the same question here: which repositories are worth reading.
    names = [n for n in dict.fromkeys(
        (it.get("full_name") or (it.get("repository") or {}).get("full_name") or "") for it in items) if n]
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("\n".join(names), encoding="utf-8")
    return names


def _by_topic(source: str, topics: list[str], delay: float) -> list[str]:
    """Every repository GitHub files under these topics.

    Measured on 2026-09-25 over seven audio and analogue topics: 554 repositories, 185 of which held a
    schematic, 1,376 schematic files between them. Eurorack is the bulk of it and it is the opposite of a
    museum — a VCF built this year, on parts a distributor still stocks.
    """
    out: list[str] = []
    for topic in topics:
        for page in range(1, GH_SEARCH_PAGES + 1):
            names = _searched(source, f"/search/repositories?q={quote('topic:' + topic)}"
                                      f"&per_page={GH_PER_PAGE}&page={page}", GH_SEARCH_DELAY)
            out += names
            if len(names) < GH_PER_PAGE:
                break
        print(f"  topic:{topic}: {len(set(out))} repositories so far", file=sys.stderr)
    return list(dict.fromkeys(out))


def _by_part(source: str, part: str, exts: list[str], delay: float) -> list[str]:
    """Which repositories hold a schematic file that names this part.

    The other direction, and the one that earns its cost. A sweep finds what people happen to have
    published; this asks GitHub which published designs use a part we already care about, so the answer
    cannot be a valve amplifier from 1974. Measured on 2026-09-25: TL072 appears in 1,276 `.kicad_sch`
    files, NE5532 in 1,600, OPA1612 in 89, LT3045 in 97, THAT1512 in 5.
    """
    out: list[str] = []
    for ext in exts:
        out += _searched(source, f"/search/code?q={quote(f'{part} extension:{ext}')}"
                                 f"&per_page={GH_CODE_HITS}", GH_CODE_DELAY)
    return list(dict.fromkeys(out))


def _listed_repos(url: str, delay: float) -> list[str]:
    """A list somebody else maintains, one repository URL per line.

    Kitspace keeps its whole catalogue this way — 151 projects in `boards.txt` — and a list its own
    maintainers edit is a better list than anything a crawl of their site would produce.
    """
    r = http.get(url, delay=delay)
    if not r.ok:
        raise SystemExit(f"repository list: {r.status} {r.why}  ({url})")
    return list(dict.fromkeys(m.group(1) for m in GH_REPO_URL.finditer(r.text())))


def _repos_listed_by(sources: list[str]) -> set[str]:
    """Which repositories other sources have already listed, read from their own lists.

    Two sources that find the same repository would each list its files, each download them and each
    count them as a use, because a list and a ledger belong to one source. The part-seeded search finds
    what the topic sweep already found — that is the point of a popular repository — so it is told what
    not to ask about again. Rule 5 by another route: never do what is done.
    """
    out: set[str] = set()
    for source in sources:
        path = source_list(source)
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    repo = json.loads(line).get("repo")
                    if repo:
                        out.add(repo)
    return out


def _seed_parts(cfg: dict) -> list[str]:
    """The part numbers to ask GitHub about, read from the census this project already built.

    This is what turns a sweep into an aim. The corpus leans vintage because its sources do; a question
    asked of parts still in production cannot answer with a valve. `from` names census files, `also` adds
    any by hand, `modern` keeps what `parts.MODERN` vouches for, and `max` caps a run that would
    otherwise take days.
    """
    want: list[str] = []
    for name in cfg.get("from") or []:
        path = parts_census(name)
        if not path.exists():
            raise SystemExit(f"no census file for {name} at {path}")
        with open(path, encoding="utf-8") as f:
            want += [(row.get("part") or "").strip().upper() for row in csv.DictReader(f)]
    want += [str(p).strip().upper() for p in cfg.get("also", [])]
    if cfg.get("modern", True):
        want = [p for p in want if p and parts.MODERN.match(p)]
    out = [p for p in dict.fromkeys(want) if p]
    return out[:cfg["max"]] if cfg.get("max") else out


def _tree_rows(source: str, full: str, cfg: dict, delay: float, exts: tuple,
               deny, extra: dict | None = None, keep=None, most: int = 0) -> list[dict]:
    """The schematic sources one repository holds, in one request whatever its size.

    `most` throws away a repository that holds more schematics than a board has sheets, because that is
    what such a repository is: a library, a test suite or a term's coursework. The part-seeded search
    listed 85,142 files from 3,694 repositories, and a sixth of them came from five — oomlout's parts
    catalogue, a KiCad 6 file collection kept for testing, eSim's examples and two student forks of them.
    Measured over that list: a limit of 20 keeps 83% of the repositories and 20% of the files.

    `keep` is for a source whose schematics are PDFs. Kitspace is "ready to order", so its projects
    publish gerbers and a schematic PDF and keep the CAD elsewhere — 0 of the first six repositories hold
    a `.kicad_sch`. Taking every PDF in a repository would take the datasheets and the assembly notes
    with it, so the pattern says which PDF is the schematic, and rule 4 settles the rest: a schematic
    whose file name does not say so is missed, and nothing wrong is published.
    """
    try:
        tree = _gh(f"/repos/{full}/git/trees/HEAD?recursive=1", delay)
    except SystemExit:
        return []                                          # an empty repository has no tree
    # A board layout is taken only when its schematic was never published. 1,415 of SparkFun and
    # Adafruit's 2,059 `.brd` files sit beside a `.sch` of the same name, and reading both would fetch
    # the same board twice and count its parts as two uses; the other 653 are the only copy there is.
    blobs = [n.get("path", "") for n in tree.get("tree", []) if n.get("type") == "blob"]
    drawn = {p.rsplit(".", 1)[0] for p in blobs if p.lower().endswith((".sch", ".kicad_sch"))}
    rows = []
    for node in tree.get("tree", []):
        path = node.get("path", "")
        if node.get("type") != "blob" or not path.lower().endswith(exts):
            continue
        if path.lower().endswith(".brd") and path.rsplit(".", 1)[0] in drawn:
            continue
        if deny and deny.search(path):
            continue
        if keep and not keep.search(path):
            continue
        rows.append({"url": f"https://raw.githubusercontent.com/{full}/HEAD/{quote(path)}",
                     "title": f"{full}: {path.rsplit('/', 1)[-1]}",
                     "kind": cfg.get("kind", "schematic"), "origin": cfg.get("origin", "community"),
                     "page": f"https://github.com/{full}/blob/HEAD/{quote(path)}",
                     "repo": full, "source": source, **(extra or {})})
    if most and len(rows) > most:
        print(f"  {full}: {len(rows)} schematics, which is a library and not a design", file=sys.stderr)
        return []
    return rows


def github(source: str, cfg: dict):
    """-> one batch per repository: the schematic sources it holds.

    Five ways to name repositories, and they compose. `repos` and `orgs` are the ones chosen by hand or by
    owner. `topics` is GitHub's own filing. `list_url` is a list somebody else maintains. `parts` is the
    other direction — which designs use a part from the census — and it is the one that fights the bias.
    `skip` names the ones none of them should have offered, and `avoid` the ones another source holds.

    Discovery and reading are interleaved on purpose. A part-seeded run is a day and a half long; a
    generator that discovered everything before yielding anything would save nothing when interrupted,
    and a repository with no schematic in it yields nothing and costs one request, which is what makes
    reading an organisation of two thousand affordable at all.
    """
    exts = tuple(cfg.get("ext", GH_EXT))
    deny = re.compile(cfg["deny"]) if cfg.get("deny") else None
    keep = re.compile(cfg["keep"]) if cfg.get("keep") else None
    most = int(cfg.get("most", 0))

    def lister(delay: float, limit: int = 0):
        # `skip` is for the repositories a list names that are not designs. A curated list of eurorack
        # modules links KiCad itself and FreeCAD, and KiCad's own tree holds hundreds of `.kicad_sch`
        # demonstration files — real KiCad, and not one of them a board anybody built.
        # `avoid` is for the ones another source has already taken.
        done: set[str] = set(cfg.get("skip", [])) | _repos_listed_by(cfg.get("avoid", []))
        if cfg.get("avoid"):
            print(f"{source}: {len(done)} repositories already held by {', '.join(cfg['avoid'])}",
                  file=sys.stderr)
        read = 0

        def take(names, why: str = ""):
            nonlocal read
            for full in names:
                if full in done:
                    continue
                done.add(full)
                if limit and read >= limit:
                    return
                read += 1
                rows = _tree_rows(source, full, cfg, delay, exts, deny, keep=keep, most=most)
                if rows:
                    print(f"  {full}: {len(rows)}{why}", file=sys.stderr)
                    yield rows

        yield from take(cfg.get("repos", []))
        for org in cfg.get("orgs", []):
            names: list[str] = []
            for page in range(1, GH_MAX_PAGES + 1):
                got = _gh(f"/orgs/{org}/repos?per_page={GH_PER_PAGE}&page={page}&type=public", delay)
                names += [r["full_name"] for r in got if not r.get("archived")]
                if len(got) < GH_PER_PAGE:
                    break
            print(f"  {org}: {len(names)} repositories", file=sys.stderr)
            yield from take(names)
        if cfg.get("list_url"):
            yield from take(_listed_repos(cfg["list_url"], delay))
        if cfg.get("topics"):
            yield from take(_by_topic(source, cfg["topics"], delay))
        seeds = _seed_parts(cfg["parts"]) if cfg.get("parts") else []
        if seeds:
            print(f"{source}: {len(seeds)} part numbers to ask about", file=sys.stderr)
        for n, part in enumerate(seeds, 1):
            if n % 50 == 0:
                print(f"  ... {n}/{len(seeds)} parts asked, {len(done)} repositories seen", file=sys.stderr)
            yield from take(_by_part(source, part, cfg["parts"].get("ext", ["kicad_sch"]), delay),
                            f"  ({part})")

    return lister


# --- a journal of open hardware, read through the archive that holds it --------------------------------
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EPMC_PAGE = 100
EPMC_MAX_PAGES = 30
# Where a paper puts its design files when they are not on GitHub. Recorded rather than fetched: an
# archive is a zip of a whole project, which the hand-delivery path takes and this one does not.
ARCHIVE = re.compile(r"(?i)(10\.5281/zenodo\.\d+|osf\.io/[a-z0-9]{4,8}|10\.17605/OSF\.IO/[A-Z0-9]+"
                     r"|data\.mendeley\.com/datasets/[a-z0-9]+)")


def europepmc(source: str, cfg: dict):
    """-> one batch per paper: the design files it publishes, found through its own full text.

    HardwareX is a peer-reviewed journal of open hardware, and it will not publish a paper whose design
    files are not released under an open licence. Measured on 2026-09-25: 744 papers, 723 of them open
    access, 99 naming KiCad and 151 an amplifier. That is modern analogue instrumentation described by
    the people who built it, and the way in is an API built for reading in bulk rather than a site to
    crawl — Europe PMC holds the open-access full text of everything the journal has published.

    The paper itself is not fetched. Elsevier serves the PDF and does not serve it to us; what is fetched
    is the full text, to read what it points at. One paper measured on 2026-09-25 named ADS1299 sixty-three
    times and linked `eeg_acq.kicad_sch` in a GitHub repository, and that file says what is on the board
    in fields rather than in prose. So the file is the row and the paper is its `paper`, which is the
    citation a reader of this index should be given.
    """
    exts = tuple(cfg.get("ext", GH_EXT))
    deny = re.compile(cfg["deny"]) if cfg.get("deny") else None
    keep = re.compile(cfg["keep"]) if cfg.get("keep") else None

    def lister(delay: float, limit: int = 0):
        done: set[str] = set()
        cursor, seen, elsewhere = "*", 0, 0
        for page in range(1, EPMC_MAX_PAGES + 1):
            r = http.get(f"{EPMC}/search?query={quote(cfg['query'])}&format=json"
                         f"&pageSize={EPMC_PAGE}&cursorMark={quote(cursor)}&resultType=core", delay=delay)
            if not r.ok:
                raise SystemExit(f"europepmc: {r.status} {r.why}")
            got = json.loads(r.text())
            results = got.get("resultList", {}).get("result", [])
            if page == 1:
                print(f"{source}: {got.get('hitCount')} papers", file=sys.stderr)
            for art in results:
                pmcid, doi = art.get("pmcid"), art.get("doi")
                if not pmcid:
                    continue
                seen += 1
                if limit and seen > limit:
                    print(f"  {elsewhere} papers keep their design files in an archive, not on GitHub",
                          file=sys.stderr)
                    return
                paper = f"https://doi.org/{doi}" if doi else f"https://europepmc.org/articles/{pmcid}"
                try:
                    body = _cached(source, f"{EPMC}/{pmcid}/fullTextXML", delay)
                except SystemExit:
                    continue                               # a paper whose full text is not there
                if ARCHIVE.search(body):
                    elsewhere += 1
                rows = []
                for full in dict.fromkeys(m.group(1) for m in GH_REPO_URL.finditer(body)):
                    if full in done:
                        continue
                    done.add(full)
                    rows += _tree_rows(source, full, cfg, delay, exts, deny,
                                       {"paper": paper, "title_hint": art.get("title", "")[:200]},
                                       keep=keep)
                if rows:
                    print(f"  {pmcid}: {len(rows)}  {art.get('title', '')[:60]}", file=sys.stderr)
                    yield rows
            cursor = got.get("nextCursorMark") or ""
            if not cursor or len(results) < EPMC_PAGE:
                break
        print(f"  {elsewhere} papers keep their design files in an archive, not on GitHub", file=sys.stderr)

    return lister


LISTERS = {"audiocircuit": audiocircuit}


def lister_for(source: str):
    """The lister written for this source, or the one its own sitemap or the Wayback Machine gives."""
    if source in LISTERS:
        return LISTERS[source]
    entry = registry_entry(source)
    if entry.get("toragi") is not None or entry.get("toragi_trbn") is not None:
        from parts_index.schematics import toragi  # a publisher with an index of its own: see there
        return toragi.LISTERS[source](source, entry.get("toragi") or entry.get("toragi_trbn") or {})
    if entry.get("github"):
        return github(source, entry["github"])
    if entry.get("europepmc"):
        return europepmc(source, entry["europepmc"])
    if entry.get("sitemap"):
        return sitemap(source, entry["sitemap"])
    if entry.get("wayback"):
        return wayback(source, entry["wayback"])
    raise SystemExit(f"no lister for {source}: it needs one in LISTERS, or a "
                     f"`github:`, `europepmc:`, `sitemap:`, `wayback:` or `toragi:` block")


def append_new(source: str, rows: list[dict], dry: bool = False) -> int:
    """Add the rows whose URL the list does not have yet. Returns how many were added."""
    path = source_list(source)
    have = set()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    have.add((json.loads(line).get("url") or "").split("#")[0])
    new = [r for r in rows if r["url"].split("#")[0] not in have]
    if new and not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:       # append only: a running download is reading it
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics list", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", required=True,
                    help=f"one of: {', '.join(LISTERS)}, or any source with a `wayback:` block")
    ap.add_argument("--limit", type=int, default=0, help="at most this many listing pages fetched")
    ap.add_argument("--delay", type=float, default=http.DELAY, help="seconds between two requests to one host")
    ap.add_argument("--dry", action="store_true", help="say what would be added and add nothing")
    a = ap.parse_args(argv)
    for source in a.source:
        lister = lister_for(source)
        listed = added = 0
        for batch in lister(a.delay, a.limit):
            listed += len(batch)
            added += append_new(source, batch, a.dry)          # saved as each brand finishes, not at the end
        print(f"{source}: {listed} files listed, {added} of them new{' (dry)' if a.dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
