"""Reading a manufacturer's product page: the facts, and nothing it wrote in its own words."""
from parts_index.datasheets.register import read_ti

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
