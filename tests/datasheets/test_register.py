"""Reading a manufacturer's product page: the facts, and nothing it wrote in its own words."""
from parts_index.datasheets.register import read_renesas, read_ti

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
