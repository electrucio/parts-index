"""A maker's product list, read whole: each part, its status and the sheet the maker gives for it."""
import json

from parts_index.datasheets import catalogues as cat


class Fake:
    """Answers each URL from a dict, as the kept tables would."""

    def __init__(self, pages: dict):
        self.pages = pages

    def text(self, url):
        return self.pages.get(url, "")

    def json(self, url):
        t = self.text(url)
        return json.loads(t) if t else None


def test_diotec_rows_give_the_article_its_sheet_and_life_cycle_but_not_competitors():
    first = ('<div class="listWrapper"><button class="listTrigger">BC856B</button>'
             '<a href="/request/datasheet/bc856.pdf" title="Download DataSheet">Datasheet</a></div>')
    table = {"data": [[first, "SMD", "SOT-23", "PNP", "active", ["2SC1620", "BC856BLT1G"], "BC856B", "x"]]}
    get = Fake({f"{cat.DIOTEC}/en/all-products.html": '<a href="/en/productlist/T.html">',
                f"{cat.DIOTEC}/request/family/T/products/en": json.dumps(table)})
    rows = list(cat.read_diotec("diotec_products", {"maker": "diotec"}, get))
    assert [(r["part"], r["status"], r["url"]) for r in rows] == [
        ("BC856B", "active", "https://diotec.com/request/datasheet/bc856.pdf")]


def test_toshiba_rows_find_the_sheet_and_life_cycle_columns_by_their_labels():
    menu = [{"id": 1, "category": "Bipolar Transistors", "parentID": -1, "link": ""},
            {"id": 2, "category": "Not Recommended for New Design and EOL announced", "parentID": 1,
             "link": "/parametric/product?code=eol_param_3"}]
    page = f'<input id="menuCategory" type="hidden" value="{json.dumps(menu).replace(chr(34), "&quot;")}">'
    head = {"headers": [{"key": 0, "label": {"name": "Part Number"}}, {"key": 1, "label": {"name": "<br />Datasheet"}},
                        {"key": 3, "label": {"name": "Life-cycle"}}]}
    link = "https://toshiba.semicon-storage.com/info/docget.jsp?did=20277&prodName=2SA1020&returnFlg=false"
    data = {"rows": [{"name": "2SA1020", "cells": [
        {"key": 1, "values": [{"value": "", "link": {"path": link}}]},
        {"key": 3, "values": [{"value": "EOL announced"}]}]}], "count": 1}
    q = "region=apc&lang=en&code=eol_param_3"
    get = Fake({f"{cat.TOSHIBA}/parametric/product?code=param_304": page,
                f"{cat.TOSHIBA}/parametric/rest/getHeaderData?{q}": json.dumps(head),
                f"{cat.TOSHIBA}/parametric/rest/getRowData?{q}": json.dumps(data)})
    (r,) = cat.read_toshiba("toshiba_parametric", {"maker": "toshiba"}, get)
    assert r["part"] == "2SA1020" and r["status"] == "EOL announced"
    assert r["url"] == "https://toshiba.semicon-storage.com/info/docget.jsp?did=20277&prodName=2SA1020"
    assert r["category"] == "Bipolar Transistors"   # the discontinued list is a status, not a category


def test_vishay_names_come_from_the_part_column_or_the_series_label():
    assert cat.vishay_names({"P1001": "BAT54, BAT54A, BAT54C, BAT54S"}) == ["BAT54", "BAT54A", "BAT54C", "BAT54S"]
    assert cat.vishay_names({"P1001": "BAS40-00 to BAS40-06"}) == ["BAS40-00", "BAS40-06"]
    assert cat.vishay_names({"P1001": "1N4148", "P1009": "1N4148-TAP"}) == ["1N4148-TAP"]


def test_a_tt_sheet_name_packs_its_parts_and_grades():
    assert cat.tt_names("2N6766 IRF250") == ["2N6766", "IRF250"]
    assert cat.tt_names("BDX66 A,B,C") == ["BDX66", "BDX66A", "BDX66B", "BDX66C"]
    assert cat.tt_names("1N4148D") == ["1N4148D"] and cat.tt_names("OPB 19 20") == []
