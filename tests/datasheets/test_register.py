"""Reading a manufacturer's product page: the facts, and nothing it wrote in its own words."""
from parts_index.datasheets.register import cut_short, read_renesas, read_ti

# Shaped like a TI product page, written for this test: meta tags in the head, the data sheet as a link
# whose text is its title and revision.
PAGE = """<html><head><title>X</title>
    <meta
      name="description"
      content="A sentence the manufacturer wrote about the part."
    />
    <meta name="PartNumber" content="XY1234" />
    <meta name="gpnFamily" content="1562_General-purpose op amps" />
    <meta name="status" content="NRND" />
</head><body>
  <a href="https://www.ti.com/lit/gpn/XY1234" navtitle="data sheet" class="icon"><ti-svg-icon>document-pdfAcrobat</ti-svg-icon></a>
  <a href="https://www.ti.com/lit/gpn/XY1234" navtitle="data sheet"
     >XY123x Low-Noise,     Dual Operational Amplifiers datasheet (Rev. C)</a
  >
</body></html>"""


def test_a_product_page_gives_category_status_and_the_sheet():
    got = read_ti(PAGE)
    assert got == {"page_part": "XY1234", "status": "NRND", "category": "General-purpose op amps",
                   "title": "XY123x Low-Noise, Dual Operational Amplifiers", "revision": "C",
                   "url": "https://www.ti.com/lit/gpn/XY1234"}


def test_the_manufacturers_own_sentence_is_not_taken():
    assert "sentence" not in " ".join(str(v) for v in read_ti(PAGE).values())


def test_a_page_that_is_not_a_product_gives_nothing():
    assert read_ti("<html><head><title>Search</title></head></html>") == {}


def test_a_sheet_without_a_revision_still_has_a_title():
    page = PAGE.replace(" (Rev. C)", "")
    assert read_ti(page)["title"] == "XY123x Low-Noise, Dual Operational Amplifiers" and read_ti(page)["revision"] == ""


# Shaped like a Renesas product page, written for this test.
REN = """<html><head><title>AB3140 - 4.5MHz, Operational Amplifier | Renesas</title>
<style>.product__label{display:none}</style></head><body>
<nav role="navigation" aria-labelledby="system-breadcrumb"><ol>
  <li><a href="/en">Home</a></li><li><a href="/en/products">Products</a></li>
  <li><a href="/en/products/amplifiers">Amplifiers</a></li>
  <li><a href="/en/products/op-amps">General-purpose Op Amps</a></li><li>AB3140</li></ol></nav>
<span class="part__label product__label">Active</span>
<h2 class="subtitle">4.5MHz, Operational Amplifier</h2>
<p>A paragraph the manufacturer wrote.</p>
<a href="/en/document/dst/ab3140-datasheet?r=1" class="document-link" title="Datasheet">Datasheet</a>
</body></html>"""


def test_a_renesas_page_gives_category_status_name_and_sheet():
    assert read_renesas(REN) == {
        "page_part": "AB3140", "category": "General-purpose Op Amps", "status": "ACTIVE",
        "name": "4.5MHz, Operational Amplifier", "url": "https://www.renesas.com/en/document/dst/ab3140-datasheet"}


def test_a_sheet_covers_its_series_and_not_what_it_mentions():
    from parts_index.datasheets.harvest import covered
    parts = {"BC546", "BC547", "BC547B", "BC548", "BC556", "S12", "LED1"}
    first = ("BC546B, BC547A, B, C, BC548B, C Amplifier Transistors NPN Silicon\n"
             "BC547 BC547B BC548 BC546\nComplementary PNP type: BC556\n")
    rest = "Ordering: BC547BZL1G BC548 BC547B\nS12 S12 S12 LED1 LED1 LED1 BC556"
    got = covered([first, rest], parts, "BC546")
    assert {"BC546", "BC547", "BC547B", "BC548"} <= set(got)
    assert "BC556" not in got                        # the complement is named, not covered
    assert "S12" not in got and "LED1" not in got    # a parameter and a pin are not parts


def test_a_makers_sentence_is_not_taken_for_a_sheets_title():
    from parts_index.datasheets.harvest import title_of
    page = "TDA8920B\n2 x 100 W class-D power amplifier\nThe TDA8920B is a high efficiency amplifier\n"
    assert title_of([page], {"title": "The TDA8920B is a high efficiency class-D audio power amplifier"},
                    "TDA8920B") == ""
    assert title_of([page], {"title": "TDA8920B 2 x 100 W class-D power amplifier"}, "TDA8920B") \
        == "TDA8920B 2 x 100 W class-D power amplifier"


def test_a_page_kept_short_of_todays_limit_is_fetched_again():
    # ATL431: TI served 352 KB, 60 KB were kept, and the data sheet link sits at 61.5 KB.
    assert cut_short("x" * 60_000, {"bytes": "352231"}, 250_000)
    assert not cut_short("x" * 60_000, {"bytes": "352231"}, 60_000)  # the limit has not moved
    assert not cut_short("x" * 90_000, {"bytes": "90000"}, 250_000)  # the whole page was kept
    assert not cut_short("x" * 60_000, None, None) and cut_short("x" * 60_000, {"bytes": "70000"}, None)


def test_a_stem_of_a_covered_part_is_not_a_part():
    from parts_index.datasheets.harvest import covered
    parts = {"1N400", "1N400X", "1N4001", "1N4007", "BC846", "BC846A"}
    first = "1N4001 thru 1N4007 1N400x series\n1N4001 1N4007 1N400X 1N400\nBC846 BC846A BC846 BC846A\n"
    got = covered([first], parts, "1N4001")
    assert {"1N4001", "1N4007", "BC846", "BC846A"} <= set(got)
    assert "1N400" not in got and "1N400X" not in got


def test_a_one_word_title_field_is_not_a_title():
    from parts_index.datasheets.harvest import title_of
    for junk in ("BC447.rev3", "Document:", "FDG6304P.Rev9", "untitled"):
        assert title_of([""], {"title": junk}, "") == ""
    assert title_of([""], {"title": "BC447 NPN amplifier transistor"}, "") == "BC447 NPN amplifier transistor"


def test_a_makers_prefix_written_apart_is_read_with_the_number():
    from parts_index.datasheets.harvest import covered
    parts = {"THAT1606", "THAT1646", "THAT2015"}
    first = ("Copyright 2015, THAT Corporation; Document 600078 Rev. 07\n"
             "The THAT 1606 and 1646 are monolithic audio differential line drivers. 1646 1606\n")
    got = covered([first], parts, "THAT1606", prefix="THAT")
    assert {"THAT1606", "THAT1646"} <= set(got)
    assert "THAT2015" not in got           # a year once on the page is not a part


def test_a_listing_page_gives_its_pdfs(monkeypatch):
    from parts_index.datasheets import harvest
    page = ('<a href="/images/stories/product/power_tubes/pdf/el34_e34l.pdf" class="wf_file">EL34</a>'
            '<a href="/images/stories/product/capacitors/MNH_EN_web.pdf" class="wf_file">MNH</a>')
    monkeypatch.setattr(harvest, "fetch_text", lambda url, entry: page)
    entry = {"kind": "document page", "pages": ["https://www.jj-electronic.com/en/download"],
             "keep": r"/images/stories/product/(preamplifying|power|rectifying)_tubes/.+\.pdf$"}
    assert list(harvest.listing("jj", entry)) == [
        "https://www.jj-electronic.com/images/stories/product/power_tubes/pdf/el34_e34l.pdf"]


def test_a_sheet_read_own_only_covers_its_series_and_not_its_companions():
    from parts_index.datasheets.harvest import covered
    parts = {"THAT1510", "THAT1512", "THAT1570", "THAT6261", "THAT6263", "7X7", "THAT1606", "THAT1646"}
    first = "THAT 1570 digital preamplifier controller for the THAT 1510 and 1512. 1570 1510 1512 7X7 7X7"
    got = covered([first], parts, "THAT1570", prefix="THAT", series=3, own_only=True)
    assert set(got) == {"THAT1570"}
    got = covered(["THAT 6261 6263 626x family"], parts, "THAT626X", prefix="THAT", series=3, own_only=True)
    assert set(got) == {"THAT6261", "THAT6263"}
    got = covered(["The THAT 1606 and 1646"], parts, "THAT1606", prefix="THAT", heads=("THAT1646",),
                  series=3, own_only=True)
    assert set(got) == {"THAT1606", "THAT1646"}


def test_a_jedec_series_counts_three_digits_and_a_number_filed_as_a_sheet_is_its_part():
    from parts_index.datasheets.harvest import covered, same_series
    assert same_series("2N4393", "2N4391") and not same_series("2N4351", "2N4391")
    assert same_series("3N164", "3N163") and not same_series("3N170", "3N163")
    assert same_series("BC548C", "BC546")
    got = covered(["6550\nbeam power tube 6550 103 103"], {"6550", "103"}, "6550", own_only=True)
    assert set(got) == {"6550"}


def test_wayback_groups_one_file_under_the_makers_addresses(monkeypatch):
    import json as _json

    from parts_index.datasheets import harvest
    rows = [["original", "timestamp", "digest"],
            ["http://www.st.com:80/resource/en/datasheet/tl072a.pdf", "20180417023754", "D1"],
            ["https://www.st.com/resource/en/datasheet/tl072.pdf?x=1", "20190101000000", "D1"],
            ["https://www.st.com/resource/en/datasheet/tda7294.pdf", "20200101000000", "D2"]]
    monkeypatch.setattr(harvest, "fetch_text", lambda url, entry: _json.dumps(rows))
    got = harvest.wayback({"prefixes": ["www.st.com/resource/en/datasheet/"], "keep": "/datasheet/"})
    tl = got["https://www.st.com/resource/en/datasheet/tl072.pdf"]
    assert tl["also"] == ["https://www.st.com/resource/en/datasheet/tl072a.pdf"]
    assert tl["copy"] == ("https://web.archive.org/web/20190101000000id_/"
                          "https://www.st.com/resource/en/datasheet/tl072.pdf?x=1")
    assert "https://www.st.com/resource/en/datasheet/tda7294.pdf" in got
