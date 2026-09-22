"""Which names are put to a judge at all, and what the extractor does with the answer."""
from parts_index.core.parts import extractor as parts
from parts_index.core.parts import judge


def test_only_the_names_that_rest_on_the_census_alone_are_judged():
    """A name a family recognises, or the dictionary holds, is not the census's word alone — and every
    false link measured came from names that were."""
    assert not judge.census_only("2N3904")            # a strict family knows the shape
    assert not judge.census_only("12AX7")             # the dictionary holds it
    assert judge.census_only("TTC004B") or not parts.CENSUS   # no family covers Toshiba's TT-


def test_a_verdict_keeps_a_name_out_whatever_the_census_says(monkeypatch):
    mk = lambda ts: {"w": 1000, "h": 1000,
                     "blocks": [{"box": [0, 0, 9, 9], "text": t, "conf": 0.99} for t in ts]}
    monkeypatch.setattr(parts, "CENSUS", {"MH40": ("MH40", "tube"), "12AX7": ("12AX7", "tube")})
    monkeypatch.setattr(parts, "NOT_HERE", set())
    page = "V1 V2 R1 C1 MH40 12AX7 6SN7".split()
    assert "MH40" in [h.part for h in parts.extract_page(mk(page))]
    monkeypatch.setattr(parts, "NOT_HERE", {"MH40"})  # judged: here it is a headphone model
    assert "MH40" not in [h.part for h in parts.extract_page(mk(page))]
