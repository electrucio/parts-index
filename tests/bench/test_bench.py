"""How a model becomes a bench job, and how what the bench returns is published. Cards are invented."""
import pytest

from parts_index.bench import publish as P
from parts_index.bench import run as R
from parts_index.datasheets import rows as rows_mod
from parts_index.models import found as F


def test_a_card_is_renamed_cleaned_of_catalogue_fields_and_made_readable_by_ngspice(tmp_path):
    lib = tmp_path / "sources" / "acme" / "raw" / "q.lib"
    lib.parent.mkdir(parents=True)
    lib.write_text(".MODEL Q2N9999 NPN (IS=1E-14 BF=200 IKF=10A mfg=Acme Vceo=40)\n")
    files = F.Files(tmp_path)
    card, changes = R.card_for(files, "sources/acme/raw/q.lib", "Q2N9999", "qspice")
    assert card.startswith(".MODEL DUT NPN") and "mfg" not in card and "IKF=10A" in card
    assert changes == ["renamed", "catalogue-fields"]
    card, changes = R.card_for(files, "sources/acme/raw/q.lib", "Q2N9999", "ngspice")
    assert "IKF=10 " in card or "IKF=10)" in card
    assert changes == ["renamed", "catalogue-fields", "unit-a"]
    assert set(changes) <= set(R.CHANGES)          # every change has its published reason


def test_a_row_the_bench_cannot_measure_says_why(tmp_path, monkeypatch):
    values = tmp_path / "QX.csv"
    values.write_text(rows_mod.csv_text(rows_mod.FIELDS, [
        {"row": 0, "sym": "vbrceo", "cond": "{}", "min": 40, "unit": "V"},
        {"row": 1, "sym": "hFE", "cond": '{"IC": 0.01, "VCE": 1.0}', "min": 100, "max": 300, "unit": ""},
        {"row": 2, "sym": "hFE", "cond": '{"IC": 0.01, "TA": -55.0, "VCE": 1.0}', "min": 45, "unit": ""},
        {"row": 3, "sym": "cob", "cond": '{"VCB": 5.0}', "max": 4.0, "unit": "pF"},
    ]))
    monkeypatch.setattr(R, "datasheet_values", lambda doc: values)
    rows, why = R.sheet_rows("QX", "bjt")
    assert why == {0: "no-bench", 2: "temperature"}
    assert [r["id"] for r in rows] == [1, 3]
    assert rows[1]["max"] == pytest.approx(4e-12) and rows[1]["min"] is None


def test_a_failed_measurement_has_no_value_and_a_typical_ratio_is_left_to_the_page():
    assert P.value({"value": 1.23456789e-3, "verdict": "inside"}) == [1.235e-3, "inside"]
    assert P.value({"value": 0.93, "verdict": "x0.93 of typ"}) == [0.93, "typical"]
    assert P.value({"value": {"error": "no waveform"}, "verdict": "error"}) == [None, "error"]
    assert P.value({"value": None, "verdict": "not measured"}) == [None, "not measured"]
