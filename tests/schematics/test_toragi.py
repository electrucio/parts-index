"""トランジスタ技術: the publisher's index, what its file names and pages say, and the order the list comes in.

No network: the WordPress API and the pages are canned, keyed by URL, and the listing cache is a tmp dir.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from parts_index.schematics import toragi as T

TR_TXT = (
    "発行年,月号,メイン・タイトル,サブタイトル,種類,開始ページ,ページ数,筆者\n"
    "1964,10,中出力HiFiアンプの製作,家族そろって楽しめる,一般,34,6,山川勝治\n"
    "2010,1,本格的なUSB機器が簡単に作れる時代に,,特集,56,4,編集部\n"
    "2010,1,USB端末の回路設計と実験,,特集,73,14,森田 義一/中 幸政\n"
    "2010,1,電流/電圧モニタ付き実験用電源の製作,,一般,176,7,よし ひろし\n"
    "2005,1,超定番！USB-シリアル変換IC FT232BM,8ビット・パラレルI/O変換もサポートする,特集,45,8,芹井 滋喜\n"
)

ISSUE_PAGE = """<html><body>
<h3 class="sec-ttl">イントロ</h3><ul class="pages"><li>
  <div class="title-data"><p class="chapter">本格的なUSB機器が簡単に作れる時代に</p></div>
  <div class="auth-data"><p class="signater">
      編集部    </p>
    <a href="https://toragi.cqpub.co.jp/wp-content/uploads/p056-057-6.pdf" class="hover dl"><p>1 MB</p></a></div>
</li></ul>
<h3 class="sec-ttl">　【第1章】　USB端末を作る</h3><ul class="pages"><li>
  <div class="title-data"><p class="caption">①回路 ②実験</p></div>
  <div class="auth-data"><p class="signater"></p>
    <a href="/wp-content/uploads/p073-6.pdf" class="hover dl"><p>1 MB</p></a></div>
</li></ul>
</body></html>"""

DOWNLOAD_PAGE = """<html><body><div class="post-txt-area">
<h4>2026年1月号</h4>
<p>特集　小回路アレイの数理</p>
<p><a href="https://toragi.cqpub.co.jp/wp-content/uploads/TR2601P1S1-1.zip">第1部 第1章　高感度センサ・アレイの製作</a><br />
<a href="https://toragi.cqpub.co.jp/wp-content/uploads/TR2601_Arduino3.zip">Arduino純正IoT実験ラボ〈3〉</a></p>
<h4>2026年2月号の訂正　　<a href="https://toragi.cqpub.co.jp/wp-content/uploads/202602_訂正とお詫び.pdf">PDFファイル</a></h4>
</div></body></html>"""

TRBN_PAGE = """<html><body>
<b>第1章</b><i> 8ビット・パラレルI/O変換もサポートする</i><br>
<b><font size="+1">超定番<i>！</i>USB-シリアル変換IC FT232BM </font></b>　芹井 滋喜　　　<a href="../../contents/2005/tr0501/0501sp1.pdf"><img src="../../../Images/pdficon.gif" alt="見本PDF"></a> <font size="-1">273Kバイト</font><br>
<a href="../../contents/2005/tr0501/0501toku.pdf">特集扉</a>
<td><font size="+1" color="white">　</font><strong>第1部　電池，マイコン回路編</strong></td>
<p><b>第1章</b><em>安全にそして無駄無く電池を活用するために</em><br>
  <font size="+1"><strong>知っておきたいトラブル対策</strong></font>　下間 憲行<font size="+1"><b>　</b></font>　　<a href="./tr0806/p092-093.pdf"><img src="x.gif"></a>
</body></html>"""

BACKNUMBER = """<a href="../contents/1998/TR199801.HTM">1月号</a> <a href="../contents/2005/TR200501.htm">1月号</a>
<a href="../../download/database/TRDB07/TRDB07.html">database</a>"""

LEGACY = """<a name="1998"></a><table>
<tr><td align="right" width=50>9月号</td><td><a href="../1998/TR9809A/TR9809A.htm">特集◆モータ制御技術の基礎と応用</a></td></tr>
</table><a name="1997"></a><table>
<tr><td align="right" width=50>2月号</td><td><a href="../1997/TR9702P2/TR9702P2.htm">ＰＲＯＭ＆ＧＡＬライタの製作</a></td></tr>
</table>"""


@pytest.fixture
def index_zip(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("TRDBWin25/TR.txt", TR_TXT.encode("cp932"))
    path = tmp_path / "TRDBWin25.zip"
    path.write_bytes(buf.getvalue())
    monkeypatch.setattr(T, "toragi_index", lambda: path)
    return path


# --- the publisher's index --------------------------------------------------------------------------
def test_tr_txt_is_cp932_with_commas_and_a_header(index_zip):
    arts = T.index()
    assert len(arts) == 5
    first = arts[0]
    assert (first.issue, first.title, first.kind, first.start, first.pages, first.end, first.authors) == \
        ("196410", "中出力HiFiアンプの製作", "一般", 34, 6, 39, "山川勝治")
    assert T.by_issue(arts)["201001"][1].authors == "森田 義一/中 幸政"


def test_a_missing_index_says_where_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "toragi_index", lambda: tmp_path / "none.zip")
    with pytest.raises(SystemExit, match="toragi.cqpub.co.jp/database"):
        T.index()


# --- what a file name says --------------------------------------------------------------------------
@pytest.mark.parametrize("name, issue", [
    ("2026-4-p037-038.pdf", "202604"), ("2610_p236.pdf", "202610"), ("2607訂正とお詫び.pdf", "202607"),
    ("TR2601P1S1-1.zip", "202601"), ("TR202605_訂正とお詫び.pdf", "202605"), ("202602_修正.pdf", "202602"),
    ("teisei202301.pdf", "202301"), ("TG1001ei_all.pdf", "201001"), ("tr1001_t.pdf", "201001"),
    ("201001p056.pdf", "201001"), ("2607p038.pdf", "202607"), ("TR2603_Jr.zip", "202603"),
    ("p138-139.pdf", ""), ("p110-9.pdf", ""), ("1234abcd.pdf", ""), ("open_umeda.zip", ""),
])
def test_the_issue_in_a_file_name(name, issue):
    assert T.issue_of_name(name) == issue


@pytest.mark.parametrize("name, page", [
    ("2026-4-p037-038.pdf", 37), ("p138-139.pdf", 138), ("p110-9.pdf", 110), ("2607p038.pdf", 38),
    ("202608p045-046.pdf", 45), ("TR2601P1S1-1.zip", None), ("2026-4-目次.pdf", None),
])
def test_the_start_page_in_a_file_name(name, page):
    assert T.page_of_name(name) == page


@pytest.mark.parametrize("name, kind", [
    ("2026-4-p037-038.pdf", "sample"), ("2026-4-目次.pdf", "toc"), ("2212_t.pdf", "toc"), ("tr2010_2t-1.pdf", "toc"),
    ("2610_訂正とお詫び.pdf", "correction"), ("teisei202301.pdf", "correction"), ("202602_修正.pdf", "correction"),
    ("TG1001ei_all.pdf", "digest"), ("TR0910e.pdf", "digest"), ("別冊付録p26.pdf", "supplement"),
    ("TR2603_Jr.zip", "archive"), ("TR9808A.LZH", "archive"), ("TR2306_USBハブ_部品表.pdf", "other"),
])
def test_what_a_file_is(name, kind):
    assert T.kind_of_name(name) == kind


# --- which article -----------------------------------------------------------------------------------
def test_a_sample_belongs_to_the_article_that_starts_on_its_page(index_zip):
    arts = T.by_issue(T.index())["201001"]
    art, how = T.article_for(arts, 56)
    assert (art.title, how) == ("本格的なUSB機器が簡単に作れる時代に", "start page")
    art, how = T.article_for(arts, 80)                     # inside 73..86
    assert (art.title, how) == ("USB端末の回路設計と実験", "page")
    assert T.article_for(arts, 300) == (None, "")


def test_or_to_the_article_with_its_title_when_the_name_says_no_page(index_zip):
    arts = T.by_issue(T.index())["200501"]
    art, how = T.article_for(arts, None, "超定番！USB-シリアル変換IC FT232BM ")
    assert (art.start, how) == (45, "title")
    art, how = T.article_for(arts, None, "超定番!USB-シリアル変換IC FT232BM")     # half-width, no trailing space
    assert how == "title"


# --- the pages ---------------------------------------------------------------------------------------
def test_an_issue_page_gives_each_link_its_title_and_author():
    found = T.parse_issue_page(ISSUE_PAGE, "https://toragi.cqpub.co.jp/magazine/201001/")
    assert [(f["url"].rsplit("/", 1)[-1], f["title"], f["authors"], f["section"]) for f in found] == [
        ("p056-057-6.pdf", "本格的なUSB機器が簡単に作れる時代に", "編集部", "イントロ"),
        ("p073-6.pdf", "【第1章】 USB端末を作る", "", "【第1章】 USB端末を作る"),     # no chapter: the section names it
    ]
    assert found[1]["url"].startswith("https://toragi.cqpub.co.jp/")               # relative href resolved


def test_a_download_page_puts_each_file_under_the_issue_its_heading_names():
    found = T.parse_download_page(DOWNLOAD_PAGE, "https://toragi.cqpub.co.jp/download2026/")
    assert [(f["issue"], f["url"].rsplit("/", 1)[-1], f["title"]) for f in found] == [
        ("202601", "TR2601P1S1-1.zip", "第1部 第1章 高感度センサ・アレイの製作"),
        ("202601", "TR2601_Arduino3.zip", "Arduino純正IoT実験ラボ〈3〉"),
        ("202602", "202602_訂正とお詫び.pdf", "PDFファイル"),        # the heading carries the link itself
    ]


def test_the_old_site_names_title_author_and_pdf_in_one_line():
    found = T.parse_trbn_page(TRBN_PAGE, "https://www.cqpub.co.jp/toragi/TRBN/contents/2005/TR200501.htm")
    assert found[0] == {"url": "https://www.cqpub.co.jp/toragi/TRBN/contents/2005/tr0501/0501sp1.pdf",
                        "title": "超定番！USB-シリアル変換IC FT232BM", "authors": "芹井 滋喜"}
    assert found[1]["url"].endswith("0501toku.pdf") and found[1]["title"] == ""
    assert (found[2]["title"], found[2]["authors"]) == ("知っておきたいトラブル対策", "下間 憲行")   # the 2008 shape


def test_the_back_number_index_and_the_program_archive():
    assert T.parse_backnumber(BACKNUMBER, T.TRBN) == [
        ("199801", "https://www.cqpub.co.jp/toragi/TRBN/contents/1998/TR199801.HTM"),
        ("200501", "https://www.cqpub.co.jp/toragi/TRBN/contents/2005/TR200501.htm"),
    ]
    rows = T.parse_legacy_downloads(LEGACY, T.LEGACY_DOWNLOADS)
    assert [(r["issue"], r["url"].rsplit("/", 1)[-1], r["title"]) for r in rows] == [
        ("199809", "TR9809A.htm", "特集◆モータ制御技術の基礎と応用"),
        ("199702", "TR9702P2.htm", "ＰＲＯＭ＆ＧＡＬライタの製作"),
    ]


# --- the list, newest first ---------------------------------------------------------------------------
class Site:
    """The API and the pages, canned by URL; 400 past the last page, as WordPress answers."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def get(self, url, **kw):
        from parts_index.core.http import Response
        self.asked.append(url)
        if url in self.answers:
            body = self.answers[url]
            return Response(200, url, "text/html", body if isinstance(body, bytes) else body.encode("utf-8"))
        return Response(400 if "wp-json" in url else 404, url)


def api(kind, page, mime=""):
    return (f"{T.API}{kind}?per_page={T.PER_PAGE}&page={page}&orderby=date&order=asc"
            f"&_fields=id,date,slug,link,source_url,post,title,mime_type" + (f"&mime_type={mime}" if mime else ""))


@pytest.fixture
def site(index_zip, tmp_path, monkeypatch):
    monkeypatch.setattr(T, "listing_cache", lambda source: tmp_path / "cache" / source)
    up = "https://toragi.cqpub.co.jp/wp-content/uploads/"
    answers = {
        api("magazine", 1): json.dumps([{"id": 941, "slug": "201001"}, {"id": 9600, "slug": "202601"},
                                        {"id": 979, "slug": "magazine-979"}]),
        api("media", 1, "application/pdf"): json.dumps([
            {"id": 1, "source_url": up + "p056-057-6.pdf", "post": 941},
            {"id": 2, "source_url": up + "p073-6.pdf", "post": 941},
            {"id": 3, "source_url": up + "p176-2.pdf", "post": 941},
            {"id": 4, "source_url": up + "2601_p038.pdf", "post": 9600},
            {"id": 5, "source_url": up + "p035-036.pdf", "post": None},
            {"id": 6, "source_url": up + "2026-1-目次.pdf", "post": 9600},
        ]),
        api("media", 1, "application/zip"): json.dumps([{"id": 7, "source_url": up + "TR2601P1S1-1.zip", "post": 9600}]),
        T.ISSUE_PAGE.format(issue="201001"): ISSUE_PAGE,
        T.DOWNLOAD_PAGE.format(year=2026): DOWNLOAD_PAGE,
    }
    server = Site(answers)
    monkeypatch.setattr(T.http, "get", server.get)
    return server


def test_the_list_comes_newest_issue_first_with_what_each_page_and_the_index_say(site):
    batches = list(T.toragi("toragi", {})(0, 0))
    rows = [r for b in batches for r in b]
    assert [r["issue"] for r in rows] == ["202602"] + ["202601"] * 4 + ["201001"] * 3 + [""]
    by_name = {r["url"].rsplit("/", 1)[-1]: r for r in rows}

    intro = by_name["p056-057-6.pdf"]                    # the issue page named it, and TR.txt has its row
    assert (intro["title"], intro["authors"], intro["start_page"], intro["article_type"], intro["match"]) == \
        ("本格的なUSB機器が簡単に作れる時代に", "編集部", 56, "特集", "issue page")
    assert (intro["kind"], intro["year"], intro["month"], intro["page"]) == \
        ("sample", "2010", "1", "https://toragi.cqpub.co.jp/magazine/201001/")

    psu = by_name["p176-2.pdf"]                          # not on the page: TR.txt alone, by start page
    assert (psu["title"], psu["authors"], psu["match"]) == ("電流/電圧モニタ付き実験用電源の製作", "よし ひろし", "start page")

    assert by_name["2026-1-目次.pdf"]["kind"] == "toc"
    assert (by_name["2601_p038.pdf"]["title"], by_name["2601_p038.pdf"]["match"]) == ("2601_p038.pdf", "")   # not in TR.txt yet

    zipped = by_name["TR2601P1S1-1.zip"]
    assert (zipped["kind"], zipped["skip"], zipped["title"]) == ("archive", T.ARCHIVE, "第1部 第1章 高感度センサ・アレイの製作")
    assert by_name["p035-036.pdf"]["issue"] == ""        # no parent post and nothing in the name: an orphan
    assert by_name["202602_訂正とお詫び.pdf"]["kind"] == "correction"       # linked from a page, not an upload the API knows
    assert set(rows[0].keys()) >= {"url", "title", "kind", "origin", "page", "issue", "source"}


def test_a_full_api_page_is_kept_and_the_last_one_is_asked_for_again(site):
    list(T.toragi("toragi", {})(0, 0))
    first = len(site.asked)
    list(T.toragi("toragi", {})(0, 0))
    again = site.asked[first:]
    assert api("media", 1, "application/pdf") in again          # six items: a last page, asked again
    assert T.ISSUE_PAGE.format(issue="201001") not in again      # a page is kept
