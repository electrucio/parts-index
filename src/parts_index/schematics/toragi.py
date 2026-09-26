"""トランジスタ技術 (Transistor Gijutsu): the free sample pages, listed from the publisher's own index and its sites.

CQ出版社 has published the monthly since October 1964 and gives three things away about it. TR.txt is its
index of every article — 20,054 rows in 738 issues, CP932, one comma-separated row per article — inside
TRDBWin25.zip. The current site, WordPress, hangs the first page or two of each article off the issue's
own page, /magazine/YYYYMM/, from 2004 on: one PDF per article, seventeen to twenty an issue, with the
table of contents, the English digest and the month's corrections beside them. The old site still
serves the same for 1998 to 2008, one static page per issue under TRBN/contents/.

Nothing here is guessed from a file name. The WordPress media API lists every upload; the `magazine`
endpoint says which issue a parent post is; the issue page says which article a link belongs to, with
its title and author next to it; and TR.txt gives that article its own row, by issue and start page.
The file name carries the start page (2026-4-p037-038.pdf) and is the last resort for the issue.

    pidx schematics list --source toragi          # the current site, newest issue first
    pidx schematics list --source toragi_trbn     # the old site, 1998–2008
    pidx schematics toragi                        # coverage by year and by issue, from the ledgers

Two sources because they are two hosts, so two ledgers; the report joins them by sha256, since the
3,252 PDFs uploaded to WordPress in 2022 are the old site's files carried across.

A sample is the first page of an article, and the schematic is on the pages that are sold. What CQ did
publish whole is the support material of its appendix boards and projects — circuit.pdf, pisoc_sch.pdf,
LV-1 headphone amplifier, a full-digital RF transceiver — under Portals/0/support/ and Portals/0/download/
on both hosts, the DotNetNuke tree of 2008–2020. No page indexes it any more, but the Wayback Machine's
CDX index names every file it ever captured there, and the files are still served live. `toragi_support`
lists them from the CDX index and the download stage fetches them from CQ; a file CQ no longer serves is
listed again from the archive on the next run, with its capture date, so nothing is lost either way.

    pidx schematics list --source toragi_support  # the support trees, from the archive's index, live URLs

Listed and not fetched: the ZIPs under /downloadYYYY/ are the programs that go with the articles, and
a sketch is not a document read for its circuit. They go into the list with a `skip`, so the download
stage records them in the ledger with their issue and never spends a request on them. The old site's
download archive (1997–2008, one page per program) is recorded the same way.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

from parts_index.core import http
from parts_index.core.config import listing_cache, schematics_state, source_list, toragi_index, toragi_reports
from parts_index.core.ledger import Ledger

UA = "ToragiResearchCrawler/1.0"          # CQ forbids nothing; there is nothing to look like a browser for
SITE = "https://toragi.cqpub.co.jp/"
API = SITE + "wp-json/wp/v2/"
ISSUE_PAGE = SITE + "magazine/{issue}/"
DOWNLOAD_PAGE = SITE + "download{year}/"
CORRECTION_PAGE = SITE + "teisei{year}/"
CORRECTION_CATEGORY = SITE + "category/correction/"
TRBN = "https://www.cqpub.co.jp/toragi/TRBN/html/backnumber.htm"
LEGACY_DOWNLOADS = "https://www.cqpub.co.jp/toragi/download/html/download.htm"
FIRST_WORDPRESS_YEAR = 2004
FIRST_DOWNLOAD_YEAR = 2010                # /downloadYYYY/ answers 200 from here; earlier is the old site
FIRST_CORRECTION_YEAR = 2021              # /teiseiYYYY/; earlier corrections sit in the category
PER_PAGE = 100
ARCHIVE = "archive, not opened"           # the `skip` a list row carries for a program ZIP
FILE = re.compile(r"\.(pdf|zip|lzh)(\?|$)", re.I)

# Where the issue hides in a file name, from the shapes the media API showed: 2026-4-p037-038.pdf,
# 2610_p236.pdf, 2607訂正とお詫び.pdf, TR2601P1S1-1.zip, TR202605_訂正.pdf, 202602_修正.pdf,
# teisei202301.pdf, TG1001ei_all.pdf, tr1001_t.pdf, 201001p056.pdf. Two-digit years are this century's.
ISSUE_IN_NAME = (
    re.compile(r"^(?P<y>20\d\d)-(?P<m>\d{1,2})-"),
    re.compile(r"^(?:TR|tr|TG|teisei)?(?P<y>20\d\d)(?P<m>\d\d)(?!\d)"),
    re.compile(r"^(?:TR|tr|TG)?(?P<yy>\d\d)(?P<m>\d\d)(?=[_p訂修]|P\d|[A-Za-z]|\.|$)"),
)
PAGE_IN_NAME = re.compile(r"(?<![A-Za-z])p(?P<p>\d{2,3})(?!\d)")        # 2607p038.pdf, never TR2601P1S1.zip
ISSUE_IN_TEXT = re.compile(r"(?P<y>(?:19|20)\d\d)年\s*(?P<m>\d{1,2})月号")
MONTH_IN_TEXT = re.compile(r"(?P<m>\d{1,2})月号")


@dataclass(frozen=True)
class Article:
    """One row of TR.txt."""
    issue: str            # YYYYMM
    title: str
    subtitle: str
    kind: str             # 種類: 特集, 連載, 一般 ...
    start: int | None
    pages: int | None
    authors: str

    @property
    def end(self) -> int | None:
        return None if self.start is None or self.pages is None else self.start + self.pages - 1


def _int(s: str) -> int | None:
    s = s.strip()
    return int(s) if s.isdigit() else None


def read_index(data: bytes) -> list[Article]:
    """TR.txt as the publisher writes it: CP932, a header row, then 発行年,月号,タイトル,サブタイトル,種類,開始ページ,ページ数,筆者."""
    text = data.decode("cp932", "replace")
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 8 or not row[0].isdigit():
            continue                                  # the header, and the odd short line
        year, month, title, subtitle, kind, start, pages, authors = (c.strip() for c in row)
        if not month.isdigit():
            continue
        out.append(Article(f"{year}{int(month):02d}", title, subtitle, kind, _int(start), _int(pages), authors))
    return out


def index(path=None) -> list[Article]:
    path = path or toragi_index()
    if not path.exists():
        raise SystemExit(f"the publisher's index is not at {path}: fetch TRDBWin25.zip from "
                         f"https://toragi.cqpub.co.jp/database/ and put it there")
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith("tr.txt"))
        return read_index(z.read(name))


def by_issue(articles: list[Article]) -> dict[str, list[Article]]:
    out: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        out[a.issue].append(a)
    return out


# --- what a name says ---------------------------------------------------------------------------------
def file_name(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def issue_of_name(name: str) -> str:
    """YYYYMM when the file name carries it, else ''."""
    for pat in ISSUE_IN_NAME:
        m = pat.match(name)
        if not m:
            continue
        year = m.groupdict().get("y") or ("20" + m.group("yy"))
        month = int(m.group("m"))
        if 1 <= month <= 12 and 1998 <= int(year) <= date.today().year + 1:
            return f"{year}{month:02d}"
    return ""


def page_of_name(name: str) -> int | None:
    m = PAGE_IN_NAME.search(name)
    return int(m.group("p")) if m else None


def kind_of_name(name: str) -> str:
    """What a file is, from the publisher's naming: the sample of an article, the contents, the digest,
    a supplement, a correction, or a program archive."""
    low = name.lower()
    if low.endswith((".zip", ".lzh")):
        return "archive"
    if "目次" in name or re.search(r"^(tr)?\d{4}_?\d?t(_new|-\d+)?\.pdf$", low):   # 2212_t.pdf, tr2010_2t.pdf
        return "toc"
    if re.search(r"訂正|修正|お詫び|teisei", name):
        return "correction"
    if re.search(r"ei(_all)?(-\d+)?\.pdf$|^tr\d{4}e\.pdf$", low):                 # the English digest
        return "digest"
    if "別冊" in name or "jr" in low or "ジュニア" in name:
        return "supplement"
    if page_of_name(name) is not None:
        return "sample"
    return "other"


def article_for(articles: list[Article], page: int | None, title: str = "") -> tuple[Article | None, str]:
    """The row of TR.txt this file belongs to, and how it was found: by its start page, by a page inside
    it, by its title, or not at all."""
    if page is not None:
        starts = [a for a in articles if a.start == page]
        if starts:
            return starts[0], "start page"
        inside = [a for a in articles if a.start is not None and a.end is not None and a.start <= page <= a.end]
        if inside:
            return min(inside, key=lambda a: a.pages or 0), "page"
    if title:
        want = _norm(title)
        for a in articles:
            if want and _norm(a.title) == want:
                return a, "title"
    return None, ""


def _norm(s: str) -> str:
    """Titles compared as the publisher would read them: full-width and half-width the same, no spaces."""
    s = unicodedata.normalize("NFKC", html.unescape(s))
    return re.sub(r"[\s　,，.．・:：!！?？()（）「」『』【】]", "", s).lower()


# --- the pages ----------------------------------------------------------------------------------------
class _IssuePage(HTMLParser):
    """An issue page of the current site: sections, and in each one the articles with their sample link.

        <h3 class="sec-ttl">イントロ</h3>
        <ul class="pages"><li>
          <div class="title-data"><p class="chapter">電子回路の基本「トランジスタ」のイメージ</p></div>
          <div class="auth-data"><p class="signater">猪熊 隆也</p>
            <a href=".../2026-4-p037-038.pdf" class="hover dl">...</a></div>
        </li></ul>
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: list[dict] = []
        self.section = ""
        self._reading: str | None = None
        self._text: dict[str, str] = {}
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "h3" and "sec-ttl" in cls:
            self._reading = "section"
            self._text["section"] = ""
        elif tag == "li":
            self._text = {"section": self._text.get("section", "")}
        elif tag == "p" and cls in ("chapter", "caption", "signater"):
            self._reading = cls
            self._text.setdefault(cls, "")
        elif tag == "a" and a.get("href") and FILE.search(a["href"]):
            self.found.append({"url": a["href"], "title": self._text.get("chapter", "").strip(),
                               "caption": self._text.get("caption", "").strip(),
                               "authors": self._text.get("signater", "").strip(), "section": self.section})

    def handle_endtag(self, tag):
        if tag == "h3" and self._reading == "section":
            self.section = re.sub(r"\s+", " ", self._text.get("section", "")).strip("　 ")
        if tag in ("h3", "p"):
            self._reading = None

    def handle_data(self, data):
        if self._reading:
            self._text[self._reading] = self._text.get(self._reading, "") + data


def parse_issue_page(page: str, base: str) -> list[dict]:
    p = _IssuePage()
    p.feed(page)
    out = []
    for f in p.found:
        url = urljoin(base, f.pop("url")).split("#")[0]
        title = f["title"] or f["section"] or f["caption"]
        out.append(f | {"url": url, "title": re.sub(r"\s+", " ", title).strip("　 "),
                        "authors": re.sub(r"\s+", " ", f["authors"]).strip("　 ")})
    return out


LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
HEADING = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I)


def parse_download_page(page: str, base: str) -> list[dict]:
    """A /downloadYYYY/ or /teiseiYYYY/ page: headings name the issue, links under them name the files.

        <h4>2026年1月号</h4>
        <p><a href=".../TR2601P1S1-1.zip">第1部 第1章　手強い磁気ノイズまる見え！...</a><br />
    """
    out = []
    issue = ""
    for kind, m in sorted([("h", m) for m in HEADING.finditer(page)] + [("a", m) for m in LINK.finditer(page)],
                          key=lambda km: km[1].start()):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2 if kind == "a" else 1)))).strip()
        if kind == "h":
            hit = ISSUE_IN_TEXT.search(text)
            issue = f"{hit.group('y')}{int(hit.group('m')):02d}" if hit else issue
        elif FILE.search(m.group(1)):                    # a link, and to a file
            url = urljoin(base, m.group(1)).split("#")[0]
            # a correction heading carries the link itself: "2026年1月号の訂正 ... <a>PDFファイル</a>"
            out.append({"url": url, "title": text, "issue": issue or issue_of_name(file_name(url))})
    return out


def parse_backnumber(page: str, base: str) -> list[tuple[str, str]]:
    """(issue, url) for every issue page the old site's back-number index links."""
    out = []
    for m in re.finditer(r'href="([^"]*contents/(\d{4})/TR(\d{6})\.(?:htm|HTM))"', page):
        out.append((m.group(3), urljoin(base, m.group(1))))
    return sorted(set(out))


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip("　 \n")


def parse_trbn_page(page: str, base: str) -> list[dict]:
    """An issue page of the old site: the title in a big font, the author after it, then the PDF icon.

        <b><font size="+1">超定番<i>！</i>USB-シリアル変換IC FT232BM </font></b>　芹井 滋喜　　　<a href="../../contents/2005/tr0501/0501sp1.pdf">
        <font size="+1"><strong>知っておきたいトラブル対策</strong></font>　下間 憲行<font size="+1"><b>　</b></font>　　<a href="./tr0806/p092-093.pdf">

    Eleven years of hand-written HTML, so the title is found by walking back from each link to the last
    big font that says anything, and the author is whatever stands between the two.
    """
    out = []
    seen = set()
    prev_end = 0
    for m in re.finditer(r'<a href="([^"]+\.pdf)"', page, re.I):
        url = urljoin(base, m.group(1)).split("#")[0]
        chunk, prev_end = page[prev_end:m.start()], m.end()
        title = authors = ""
        fonts = [f for f in re.finditer(r'<font size="\+1"[^>]*>(.*?)</font>', chunk, re.S | re.I) if _clean(f.group(1))]
        if fonts:
            title, authors = _clean(fonts[-1].group(1)), _clean(chunk[fonts[-1].end():])
        if url not in seen:
            seen.add(url)
            out.append({"url": url, "title": title, "authors": authors})
    return out


def parse_legacy_downloads(page: str, base: str) -> list[dict]:
    """The old download archive: a table per year, a row per program, the month in its first cell."""
    out = []
    year = ""
    for kind, m in sorted([("y", m) for m in re.finditer(r'<a name="(\d{4})">', page)]
                          + [("r", m) for m in re.finditer(r"<td[^>]*>(\d{1,2})月号</td>\s*<td>" + LINK.pattern, page, re.S | re.I)],
                          key=lambda km: km[1].start()):
        if kind == "y":
            year = m.group(1)
        elif year:
            month, href, text = m.group(1), m.group(2), m.group(3)
            out.append({"url": urljoin(base, href), "issue": f"{year}{int(month):02d}",
                        "title": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()})
    return out


# --- fetching, with the copy kept last time ---------------------------------------------------------
def _get(source: str, url: str, delay: float, keep=lambda status, body: status == 200) -> tuple[int, bytes]:
    """One page, from the listing cache when it is there. `keep` says whether this answer is worth keeping:
    the last page of a paginated API is not, since the next run wants to see what was added to it."""
    path = listing_cache(source) / hashlib.sha1(url.encode()).hexdigest()[:16]
    if path.exists():
        return 200, path.read_bytes()
    r = http.get(url, ua=UA, delay=delay)
    if keep(r.status, r.body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.body)
    return r.status, r.body


def _api(source: str, kind: str, delay: float, mime: str = "") -> list[dict]:
    """Every item of one WordPress collection, oldest first — the order in which pages stay put, so a
    full page can be kept and only the last one is asked for again. 400 is how it says there is no more."""
    fields = "id,date,slug,link,source_url,post,title,mime_type"
    items: list[dict] = []
    page = 1
    while True:
        url = (f"{API}{kind}?per_page={PER_PAGE}&page={page}&orderby=date&order=asc&_fields={fields}"
               + (f"&mime_type={mime}" if mime else ""))
        status, body = _get(source, url, delay, keep=lambda s, b: s == 200 and b.count(b'"id"') >= PER_PAGE)
        if status == 400:
            break
        if status != 200:
            raise SystemExit(f"{source}: {status} from {url}")
        batch = json.loads(body)
        items += batch
        print(f"  {kind}{' ' + mime if mime else ''}: page {page}, {len(items)} so far", file=sys.stderr)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return items


def _page(source: str, url: str, delay: float, encoding: str = "utf-8") -> str | None:
    status, body = _get(source, url, delay)
    return body.decode(encoding, "replace") if status == 200 else None


# --- the listers --------------------------------------------------------------------------------------
def _row(source: str, url: str, kind: str, issue: str, title: str, authors: str, page_url: str,
         articles: dict[str, list[Article]], page: int | None = None, section: str = "", match: str = "") -> dict:
    """One line of the list: what the download stage needs, and what a later stage will want to know."""
    art, how = article_for(articles.get(issue, []), page, title) if issue else (None, "")
    if art and not title:
        title, authors = art.title, art.authors
    row = {"url": url, "title": title or file_name(url), "kind": kind, "origin": "magazine", "page": page_url,
           "issue": issue, "year": issue[:4] if issue else "", "month": str(int(issue[4:])) if issue else "",
           "start_page": art.start if art else page, "authors": authors or (art.authors if art else ""),
           "section": section, "article_type": art.kind if art else "", "match": match or how, "source": source}
    if kind == "archive":
        row["skip"] = ARCHIVE
    return row


def toragi(source: str, cfg: dict):
    """-> batches, newest issue first: the current site's samples, contents, corrections and archives."""
    since = int(cfg.get("since", FIRST_WORDPRESS_YEAR))

    def lister(delay: float, limit: int = 0):
        articles = by_issue(index())
        magazines = {m["id"]: m["slug"] for m in _api(source, "magazine", delay) if re.fullmatch(r"\d{6}", m["slug"])}
        issues = sorted((s for s in magazines.values() if int(s[:4]) >= since), reverse=True)
        media = _api(source, "media", delay, "application/pdf") + _api(source, "media", delay, "application/zip")
        print(f"{source}: {len(issues)} issues, {len(media)} uploads", file=sys.stderr)

        # what each issue page says about its links: title and author beside each one
        said: dict[str, dict] = {}
        for n, issue in enumerate(issues[:limit] if limit else issues, 1):
            page_url = ISSUE_PAGE.format(issue=issue)
            body = _page(source, page_url, delay)
            if body is None:
                continue
            for f in parse_issue_page(body, page_url):
                said.setdefault(f["url"], f | {"issue": issue, "page_url": page_url})
            print(f"  {issue}: {sum(1 for v in said.values() if v['issue'] == issue)} links  ({n}/{len(issues)})", file=sys.stderr)
        this_year = date.today().year + 1
        for url in [DOWNLOAD_PAGE.format(year=y) for y in range(this_year, FIRST_DOWNLOAD_YEAR - 1, -1)] + \
                   [CORRECTION_PAGE.format(year=y) for y in range(this_year, FIRST_CORRECTION_YEAR - 1, -1)] + \
                   [CORRECTION_CATEGORY] + [f"{CORRECTION_CATEGORY}page/{n}/" for n in range(2, 6)]:
            body = _page(source, url, delay)
            if body is None:
                continue
            for f in parse_download_page(body, url):
                said.setdefault(f["url"], {"title": f["title"], "authors": "", "section": "", "issue": f["issue"], "page_url": url})

        rows: dict[str, dict] = {}
        for m in media:
            url = m["source_url"]
            name = file_name(url)
            s = said.get(url, {})
            issue = s.get("issue") or magazines.get(m.get("post") or 0, "") or issue_of_name(name)
            kind = kind_of_name(name)
            rows[url] = _row(source, url, kind, issue, s.get("title", ""), s.get("authors", ""),
                             s.get("page_url", ISSUE_PAGE.format(issue=issue) if issue else ""), articles,
                             page=page_of_name(name) if kind == "sample" else None, section=s.get("section", ""),
                             match="issue page" if s.get("title") else "")
        for url, s in said.items():                      # linked from a page and not an upload the API knows
            if url not in rows and FILE.search(urlparse(url).path):
                name = file_name(url)
                kind = kind_of_name(name)
                rows[url] = _row(source, url, kind, s["issue"], s.get("title", ""), s.get("authors", ""),
                                 s["page_url"], articles, page=page_of_name(name) if kind == "sample" else None,
                                 match="issue page" if s.get("title") else "")
        # newest issue first, and inside an issue by page; what has no issue goes last
        ordered = sorted(rows.values(), key=lambda r: (r["issue"] == "", -int(r["issue"] or 0), r["start_page"] or 0))
        for issue, batch in _grouped(ordered):
            yield batch

    return lister


def _grouped(rows: list[dict]):
    """Rows in batches by issue, keeping the order given."""
    batch: list[dict] = []
    current = None
    for r in rows:
        if r["issue"] != current and batch:
            yield current, batch
            batch = []
        current = r["issue"]
        batch.append(r)
    if batch:
        yield current, batch


def toragi_trbn(source: str, cfg: dict):
    """-> batches, newest issue first: the old site's samples for 1998–2008, and its program archive."""
    def lister(delay: float, limit: int = 0):
        articles = by_issue(index())
        top = _page(source, TRBN, delay, "cp932")
        if top is None:
            raise SystemExit(f"{source}: the back-number index at {TRBN} did not answer")
        issues = sorted(parse_backnumber(top, TRBN), reverse=True)
        print(f"{source}: {len(issues)} issue pages", file=sys.stderr)
        for n, (issue, page_url) in enumerate(issues[:limit] if limit else issues, 1):
            body = _page(source, page_url, delay, "cp932")
            if body is None:
                continue
            batch = []
            for f in parse_trbn_page(body, page_url):
                kind = kind_of_name(file_name(f["url"]))          # 0501sp1.pdf says nothing: a sample, then
                batch.append(_row(source, f["url"], kind if kind in ("toc", "correction") else "sample", issue,
                                  f["title"], f["authors"], page_url, articles, page=page_of_name(file_name(f["url"])),
                                  match="issue page" if f["title"] else ""))
            print(f"  {issue}: {len(batch)}  ({n}/{len(issues)})", file=sys.stderr)
            if batch:
                yield batch
        archive = _page(source, LEGACY_DOWNLOADS, delay, "cp932")
        if archive:
            rows = [_row(source, f["url"], "archive", f["issue"], f["title"], "", LEGACY_DOWNLOADS, articles, match="")
                    for f in parse_legacy_downloads(archive, LEGACY_DOWNLOADS)]
            rows.sort(key=lambda r: -int(r["issue"] or 0))
            print(f"  program archive: {len(rows)} listed, none fetched", file=sys.stderr)
            if rows:
                yield rows

    return lister


# --- the support trees, from the archive's index -----------------------------------------------------
CDX = "https://web.archive.org/cdx/search/cdx"
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
SUPPORT_PREFIXES = ("toragi.cqpub.co.jp/Portals/0/support/", "toragi.cqpub.co.jp/Portals/0/download/",
                    "www.cqpub.co.jp/toragi/2008-2020/Portals/0/support/",
                    "www.cqpub.co.jp/toragi/2008-2020/Portals/0/download/")
SUPPORT_TYPES = {"application/pdf": "pdf", "application/x-zip-compressed": "zip", "application/zip": "zip",
                 "image/png": "png", "image/gif": "gif", "image/jpeg": "jpeg", "image/bmp": "bmp"}
# A name or a folder that says what the file is. `board/` and `pcb/` are layouts, which is the one thing
# the LV-1 tree taught: the schematics are under circuit/ and the copper is under board/.
SCHEMATIC_NAME = re.compile(r"(?i)sch|circuit|kairo|回路|diagram|\.brd|kicad|eagle")
LAYOUT_NAME = re.compile(r"(?i)/board/|/pcb/|layout|pattern|gerber|silk")
# How CQ says a file is gone: 404, or a 200 that is its "ERROR 404" page served as application/pdf, which
# the download stage records as "not the declared file type". Both are listed again from the archive.
GONE = ("http 404", "http 410", "not the declared file type")


def _cdx_rows(source: str, prefix: str, delay: float) -> list[list[str]]:
    """Every capture of a file under this prefix, one per URL, from the copy kept last time."""
    url = (f"{CDX}?url={prefix}&matchType=prefix&collapse=urlkey&filter=statuscode:200"
           f"&fl=original,mimetype,timestamp,length&limit=100000")
    status, body = _get(source, url, delay)
    if status != 200:
        raise SystemExit(f"{source}: {status} from the CDX index for {prefix}")
    return [line.split(" ") for line in body.decode("utf-8", "replace").splitlines() if line.strip()]


def live_url(original: str) -> str:
    """The URL as CQ serves it now: https, no :80, no cache-busting query."""
    return re.sub(r"^http://", "https://", original).replace(":80/", "/").split("?")[0]


def support_row(source: str, original: str, mime: str, stamp: str, articles: dict, url: str | None = None) -> dict | None:
    """One line of the list for an archived support file, or None when it is not a kind worth holding."""
    kind = SUPPORT_TYPES.get(mime.split(";")[0].strip())
    if not kind:
        return None
    url = url or live_url(original)
    path = unquote(urlparse(original).path)
    name = path.rsplit("/", 1)[-1]
    if kind == "jpeg" and not SCHEMATIC_NAME.search(path):
        return None                                       # a photograph of the board, almost always
    if LAYOUT_NAME.search(path) and not SCHEMATIC_NAME.search(name):
        return None
    m = re.search(r"/(20\d\d)/(\d\d)/", path)
    y = re.search(r"/(20[012]\d)/", path)
    issue = f"{m.group(1)}{m.group(2)}" if m and 1 <= int(m.group(2)) <= 12 else ""
    folder = path.split("/Portals/0/")[-1].rsplit("/", 1)[0]
    role = ("archive" if kind == "zip" else "schematic" if SCHEMATIC_NAME.search(path)
            else "figure" if kind in ("png", "gif", "jpeg", "bmp") else "support")
    row = _row(source, url, role, issue, f"{folder}/{name}", "", live_url(original).rsplit("/", 1)[0] + "/",
               articles, match="")
    row |= {"year": issue[:4] if issue else (y.group(1) if y else ""), "archived": stamp, "original": live_url(original)}
    return row


def toragi_support(source: str, cfg: dict):
    """-> batches, newest year first: the support and download trees, live where CQ still serves them."""
    prefixes = cfg.get("prefixes") or list(SUPPORT_PREFIXES)

    def lister(delay: float, limit: int = 0):
        articles = by_issue(index())
        led = Ledger(schematics_state(source))
        rows: dict[str, dict] = {}
        for prefix in prefixes:
            for parts in _cdx_rows(source, prefix, delay):
                if len(parts) != 4:
                    continue
                original, mime, stamp, length = parts
                if length.isdigit() and int(length) < 1500 and "pdf" in mime:
                    continue                              # CQ's own 404 page, captured as a PDF
                row = support_row(source, original, mime, stamp, articles)
                if row and row["url"] not in rows:
                    rows[row["url"]] = row
            print(f"  {prefix}: {len(rows)} files so far", file=sys.stderr)
        # what CQ no longer serves is listed again from the archive, as its own row, once the ledger says so
        for url, row in list(rows.items()):
            gone = led.get(url)
            if gone and gone["skip_reason"].startswith(GONE):
                replay = REPLAY.format(stamp=row["archived"], url=row["original"])
                rows[replay] = row | {"url": replay, "page": REPLAY.format(stamp=row["archived"], url=row["page"])}
        ordered = sorted(rows.values(), key=lambda r: (-int(r["year"] or 0), r["url"]))
        print(f"{source}: {len(ordered)} files, {sum(1 for r in ordered if r['kind'] == 'schematic')} named as a "
              f"schematic, {sum(1 for r in ordered if r['kind'] == 'archive')} archives listed and not fetched", file=sys.stderr)
        if ordered:
            yield ordered[:limit] if limit else ordered

    return lister


LISTERS = {"toragi": toragi, "toragi_trbn": toragi_trbn, "toragi_support": toragi_support}


# --- the program archives, opened for the schematics inside -----------------------------------------
# What is kept out of a program archive: the circuit as a PDF, as a CAD source, or as a picture that
# says it is one. Screenshots, photographs, sources and binaries stay in the archive on CQ's server,
# which is where the public link points anyway.
# `.net` and `.cir` are the netlists OrCAD/PSpice writes beside a `.DSN`: plain text naming every part and
# its model, which is the schematic in the one form nothing has to guess at.
WANTED_MEMBER = re.compile(r"(?i)\.(pdf|asc|kicad_sch|sch|brd|ce3|dsn|sp7|net|cir)$")
WANTED_IMAGE = re.compile(r"(?i)\.(png|gif|jpe?g|bmp)$")


def wanted(member: str) -> bool:
    name = member.rsplit("/", 1)[-1]
    if WANTED_MEMBER.search(name):
        return True
    return bool(WANTED_IMAGE.search(name) and SCHEMATIC_NAME.search(member))


def member_name(info: zipfile.ZipInfo) -> str:
    """A member's name as it was written. A ZIP made on a Japanese Windows names its members in CP932
    and says nothing about it, and the zip module then reads them as CP437 — `回路図.pdf` comes out as
    `ë±ÿHÉ}.pdf`. The repacked archive names them in UTF-8, so the ledger key reads as the author wrote it."""
    if info.flag_bits & 0x800:
        return info.filename                             # written as UTF-8, and flagged so
    try:
        return info.filename.encode("cp437").decode("cp932")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def _lzh_as_zip(data: bytes) -> bytes | None:
    """An LHA archive, the format of the old download archive (1997–2008), rewritten as a ZIP so one
    repacking serves both. Names come out as the CP437 reading of CP932, as from a Japanese ZIP."""
    import tempfile

    import lhafile
    with tempfile.NamedTemporaryFile(suffix=".lzh") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            src = lhafile.Lhafile(tmp.name)
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as dst:
                seen = set()
                for info in src.infolist():
                    name = info.filename.replace("\\", "/")
                    if not name.endswith("/") and name not in seen:
                        seen.add(name)
                        dst.writestr(zipfile.ZipInfo(name), src.read(info.filename))
            return out.getvalue()
        except Exception:                                   # a damaged or unknown LHA method
            return None


def _repack(data: bytes, depth: int = 1) -> tuple[bytes | None, Counter]:
    """The same archive with only the members worth holding; None when there are none."""
    kept = Counter()
    out = io.BytesIO()
    if data[2:5] == b"-lh":                                 # LHA: `-lh5-` at offset 2
        data = _lzh_as_zip(data) or b""
    try:
        src = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None, kept
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        seen = set()
        for info in src.infolist():
            name = member_name(info)
            # A member behind a password is a door the author locked: it is left shut, never opened.
            if info.is_dir() or info.flag_bits & 0x1 or name in seen:
                continue
            seen.add(name)
            try:
                body = src.read(info.filename)
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError):
                continue                                    # damaged, or a method the zip module lacks
            if name.lower().endswith(".zip") and body[:2] == b"PK" and depth:
                inner, sub = _repack(body, depth - 1)
                if inner:
                    dst.writestr(name, inner)
                    kept.update(sub)
            elif wanted(name):
                dst.writestr(name, body)
                kept[name.rsplit(".", 1)[-1].lower()] += 1
    return (out.getvalue(), kept) if kept else (None, kept)


def pack_archives(folder, urls: dict[str, str], out, log=print) -> dict:
    """One delivery archive out of the program archives fetched to `folder`: each ZIP that holds a
    schematic goes in again, repacked to the members worth holding, under the path of its public URL —
    cq/toragi.cqpub.co.jp/wp-content/uploads/TR2602P1S1.zip — so the delivery's link rule can say where
    it came from. `urls` maps a file name in the folder to its URL."""
    from pathlib import Path
    folder, out = Path(folder), Path(out)
    counts, kept_kinds = Counter(), Counter()
    rows = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as dst:
        done_urls = set()
        for f in sorted(p for p in folder.iterdir() if p.suffix.lower() in (".zip", ".lzh")):
            url = urls.get(f.name)
            if not url:
                counts["no url"] += 1
                continue
            if url in done_urls:                            # the same archive listed under two issues
                continue
            done_urls.add(url)
            counts["archives"] += 1
            packed, kept = _repack(f.read_bytes())
            rows.append({"file": f.name, "url": url, "kept": sum(kept.values()), "kinds": " ".join(f"{k}:{n}" for k, n in sorted(kept.items()))})
            if not packed:
                continue
            counts["with something worth holding"] += 1
            kept_kinds.update(kept)
            dst.writestr("cq/" + re.sub(r"(?i)\.lzh$", ".lzh.zip", re.sub(r"^https?://", "", url)), packed)
    log(f"{counts['archives']} archives, {counts['with something worth holding']} hold a schematic or a document: "
        + ", ".join(f"{n} {k}" for k, n in kept_kinds.most_common()) + f" -> {out}")
    return {"counts": dict(counts), "kinds": dict(kept_kinds), "rows": rows}


# --- the report ---------------------------------------------------------------------------------------
YEAR_FIELDS = ("year", "issues_expected", "issues_listed", "issues_with_sample", "articles_total",
               "articles_with_sample", "samples_listed", "samples_downloaded", "unique_sha256", "corrections",
               "archives_listed", "bytes")
ISSUE_FIELDS = ("issue", "source", "articles_total", "issue_page", "samples_listed", "samples_downloaded",
                "unique_sha256", "articles_with_sample", "corrections", "archives_listed", "bytes", "unmatched")
PDF_KINDS = ("sample", "toc", "digest", "supplement", "correction", "other")


def _list_rows(source: str) -> list[dict]:
    path = source_list(source)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def report(sources=("toragi", "toragi_trbn", "toragi_support"), articles: list[Article] | None = None, out=None, log=print) -> dict:
    """Coverage by year and by issue, from the lists and the ledgers, written as CSV and shown as a table."""
    out = out or toragi_reports()
    arts = by_issue(articles if articles is not None else index())
    ledgers = {s: Ledger(schematics_state(s)) for s in sources}
    rows = {s: _list_rows(s) for s in sources}

    by_iss: dict[tuple[str, str], dict] = {}
    sha_where: dict[str, set] = defaultdict(set)
    orphans: list[dict] = []
    for s in sources:
        for r in rows[s]:
            issue = r.get("issue") or ""
            if not issue:
                orphans.append(r)
                continue
            d = by_iss.setdefault((issue, s), Counter())
            led = ledgers[s].get(r["url"]) or {}
            kind = r.get("kind", "")
            if kind == "archive":
                d["archives_listed"] += 1
                continue
            d["samples_listed"] += 1
            if kind == "correction":
                d["corrections"] += 1
            if r.get("match") in ("start page", "page", "title", "issue page") and kind == "sample":
                d.setdefault("matched", set()).add((r.get("title"), r.get("start_page")))
            elif kind == "sample":
                d["unmatched"] += 1
            if led.get("download_at") and led.get("type") == "pdf":
                d["samples_downloaded"] += 1
                d["bytes"] += int(led.get("bytes") or 0)
                d.setdefault("shas", set()).add(led["sha256"])
                sha_where[led["sha256"]].add(s)

    issue_rows = []
    for (issue, s), d in sorted(by_iss.items(), reverse=True):
        issue_rows.append({"issue": issue, "source": s, "articles_total": len(arts.get(issue, [])),
                           "issue_page": 1, "samples_listed": d["samples_listed"],
                           "samples_downloaded": d["samples_downloaded"], "unique_sha256": len(d.get("shas", ())),
                           "articles_with_sample": len(d.get("matched", ())), "corrections": d["corrections"],
                           "archives_listed": d["archives_listed"], "bytes": d["bytes"], "unmatched": d["unmatched"]})

    years: dict[str, dict] = {}
    expected: dict[str, set] = defaultdict(set)
    for issue in arts:
        expected[issue[:4]].add(issue)
    for y in sorted(set(expected) | {i["issue"][:4] for i in issue_rows}):
        mine = [i for i in issue_rows if i["issue"][:4] == y]
        shas = set()
        for (issue, s), d in by_iss.items():
            if issue[:4] == y:
                shas |= d.get("shas", set())
        years[y] = {"year": y, "issues_expected": len(expected[y]), "issues_listed": len({i["issue"] for i in mine}),
                    "issues_with_sample": len({i["issue"] for i in mine if i["samples_listed"]}),
                    "articles_total": sum(len(arts[i]) for i in expected[y]),
                    "articles_with_sample": sum(i["articles_with_sample"] for i in mine),
                    "samples_listed": sum(i["samples_listed"] for i in mine),
                    "samples_downloaded": sum(i["samples_downloaded"] for i in mine), "unique_sha256": len(shas),
                    "corrections": sum(i["corrections"] for i in mine), "archives_listed": sum(i["archives_listed"] for i in mine),
                    "bytes": sum(i["bytes"] for i in mine)}
    duplicates = {sha: sorted(where) for sha, where in sha_where.items() if len(where) > 1}

    out.mkdir(parents=True, exist_ok=True)
    _write(out / "coverage_by_year.csv", YEAR_FIELDS, list(years.values()))
    _write(out / "coverage_by_issue.csv", ISSUE_FIELDS, issue_rows)
    _write(out / "orphans.csv", ("source", "url", "kind", "title"), [{k: r.get(k, "") for k in ("source", "url", "kind", "title")} for r in orphans])
    _write(out / "duplicates.csv", ("sha256", "sources"), [{"sha256": k, "sources": " ".join(v)} for k, v in sorted(duplicates.items())])

    log(f"{'year':>4} {'issues':>6} {'listed':>6} {'w/pdf':>5} {'articles':>8} {'w/pdf':>5} {'pdfs':>5} {'got':>5} {'uniq':>5} {'corr':>4} {'zip':>4} {'MB':>7}")
    for y in years.values():
        if y["samples_listed"] or y["archives_listed"]:
            log(f"{y['year']:>4} {y['issues_expected']:>6} {y['issues_listed']:>6} {y['issues_with_sample']:>5} "
                f"{y['articles_total']:>8} {y['articles_with_sample']:>5} {y['samples_listed']:>5} {y['samples_downloaded']:>5} "
                f"{y['unique_sha256']:>5} {y['corrections']:>4} {y['archives_listed']:>4} {y['bytes'] / 1e6:>7.1f}")
    log(f"{len(orphans)} listed with no issue · {len(duplicates)} files held under both sites · written to {out}")
    return {"years": years, "issues": issue_rows, "orphans": len(orphans), "duplicates": len(duplicates)}


def _write(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pidx schematics toragi", description=__doc__.splitlines()[0])
    ap.add_argument("--source", action="append", help="only these sources (default: toragi, toragi_trbn and toragi_support)")
    a = ap.parse_args(argv)
    report(tuple(a.source) if a.source else ("toragi", "toragi_trbn", "toragi_support"))
    return 0


if __name__ == "__main__":      # pragma: no cover
    raise SystemExit(main())
