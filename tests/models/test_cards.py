"""What a card cannot represent is read from which parameters it lacks. Every card here is invented."""
import json

import pytest

from parts_index.bench import record
from parts_index.core import config
from parts_index.models import cards as C


def read(text):
    return C.read("model", text)


def test_a_bipolar_card_without_collector_capacitance_cannot_give_a_cob():
    card = read(".MODEL QX NPN (IS=1E-14 BF=200 CJE=20P CJC=0 TF=400P VAF=100)")
    assert card["family"] == "gummel-poon"
    assert card["absent"] == ["CJC", "TR", "IKF", "RB", "KF", "XTB"]
    assert C.cannot(card, "cob") == ("CJC",)
    assert C.cannot(card, "cib") is None and C.cannot(card, "ft") is None
    assert C.cannot(card, "hFE") is None                       # nothing is needed for a DC gain


def test_a_zero_is_absent_and_an_expression_is_unknown():
    card = read(".MODEL QX NPN (IS=1E-14 BF=200 TF=0 KF={kf} VAF=0)")
    assert "TF" in card["absent"] and "VAF" in card["absent"]
    assert card["unknown"] == ["KF"]


def test_no_gummel_poon_card_has_a_breakdown_unless_it_carries_an_extension_for_it():
    assert C.cannot(read(".MODEL QX NPN (IS=1E-14 BF=200)"), "vbrceo") == ()
    assert C.cannot(read(".MODEL QX NPN (IS=1E-14 BF=200 BVCEO=40)"), "vbrceo") is None


def test_a_card_of_another_family_is_named_and_nothing_is_claimed_about_it():
    vbic = read(".MODEL QV NPN (LEVEL=9 IS=1E-16)")
    assert vbic == {"family": "bjt-level-9", "type": "NPN"}
    assert C.cannot(vbic, "cob") is None
    assert read(".MODEL QA AKO:QBASE NPN (BF=300)")["family"] == "ako"
    assert C.read("subckt", ".SUBCKT X 1 2 3\n.ENDS") == {"family": "subckt"}


def test_a_jfet_card_lacking_cgd_has_no_reverse_transfer_capacitance():
    card = read(".MODEL JX NJF (VTO=-0.5 BETA=40M LAMBDA=0 CGS=30P IS=1F)")
    assert card["family"] == "jfet" and "CGD" in card["absent"] and "LAMBDA" in card["absent"]
    assert C.cannot(card, "crss") == ("CGD",)
    assert C.cannot(card, "ciss") is None                      # CGS alone gives an input capacitance
    assert C.cannot(card, "vbrgss") == ()


def test_a_diode_without_transit_time_has_no_reverse_recovery():
    card = read(".MODEL DX D (IS=2.5N RS=0.5 N=1.8 CJO=4P BV=100)")
    assert C.cannot(card, "trr") == ("TT",) and C.cannot(card, "cd") is None and C.cannot(card, "vbr") is None


@pytest.mark.parametrize("text, flag", [
    (".MODEL QX NPN (IS=1E-14 BF=200 IKF=10A)", "unit-a"),
    (".MODEL QX NPN (IS=1E-14 BF=200 mfg=Acme Vceo=40)", "catalogue-fields"),
    (".MODEL QX NPN (IS=1E-14 BF=200 NK=4.8)", "nk-above-1"),
    (".MODEL JX NJF (VTO=-1 BETA=1M ISR=1P NR=2)", "jfet-extensions"),
    (".MODEL DX D (Ron=0.1 Roff=1G Vfwd=0.6)", "ltspice-diode"),
])
def test_what_one_simulator_reads_differently_is_noted(text, flag):
    assert flag in read(text).get("dialect", [])


def test_milliamperes_are_not_mistaken_for_the_ampere_unit():
    assert "dialect" not in read(".MODEL QX NPN (IS=1E-14 BF=200 IKF=100MA)")


def test_a_step_rewrites_its_own_section_of_the_record_and_keeps_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DATA", tmp_path)
    assert record.write_section("bjt", "QX", "claims", {"h1": {"no": ["distortion"]}})
    assert record.write_section("bjt", "QX", "cards", {"h1": {"family": "gummel-poon"}})
    assert not record.write_section("bjt", "QX", "cards", {"h1": {"family": "gummel-poon"}})   # no change
    doc = json.loads(config.verification("bjt", "QX").read_text())
    assert doc["claims"] and doc["cards"] and doc["schema"] == 1
    # a part nothing is known about has no record at all
    record.write_section("bjt", "QX", "claims", {})
    record.write_section("bjt", "QX", "cards", {})
    assert not config.verification("bjt", "QX").exists()
    assert not record.write_section("bjt", "QY", "claims", {})
