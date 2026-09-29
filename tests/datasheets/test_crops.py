"""A published row's box, cut from its PDF for the site."""
import json

import pytest

from parts_index.datasheets import crops as K
from parts_index.datasheets import rows as R

pymupdf = pytest.importorskip("pymupdf")


def test_each_located_row_gets_its_crop_and_a_row_found_nowhere_gets_none(tmp_path, monkeypatch):
    store, out = tmp_path / "store", tmp_path / "crops"
    (store / "bjt").mkdir(parents=True)
    pdf = pymupdf.open()
    pdf.new_page().insert_text((60, 100), "Collector-Emitter Breakdown Voltage 40 Vdc", fontsize=9)
    pdf.save(store / "bjt" / "QX_acme.pdf")
    (store / "manifest.json").write_text(json.dumps({"files": [{"path": "datasheets/bjt/QX_acme.pdf", "sha256": "ab"}]}))
    index, values = tmp_path / "values.csv", tmp_path / "QX_acme.csv"
    index.write_text(R.csv_text(R.INDEX_FIELDS, [{"doc": "QX_acme", "sha256": "ab"}]))
    values.write_text(R.csv_text(R.FIELDS, [{"row": 0, "page": 1, "box": "[57, 88, 300, 105]"},
                                            {"row": 1, "page": 1, "box": ""}]))
    monkeypatch.setattr(K, "datasheet_store", lambda: store)
    monkeypatch.setattr(R, "datasheet_store", lambda: store)
    monkeypatch.setattr(K, "datasheet_values_index", lambda: index)
    monkeypatch.setattr(K, "datasheet_values", lambda doc: values)
    monkeypatch.setattr(K, "web_crops", lambda: out)
    c = K.run()
    assert c["made"] == 1 and (out / "QX_acme" / "r0.webp").read_bytes()[8:12] == b"WEBP"
    assert not (out / "QX_acme" / "r1.webp").exists()
    assert K.run()["kept"] == 1                          # made once
