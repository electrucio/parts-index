"""Which names are put to a judge at all, and what the extractor does with the answer."""
from parts_index.core.parts import extractor as parts
from parts_index.core.parts import judge


def test_every_name_the_census_carries_is_judged_not_only_the_familyless_ones():
    """6V3 has a family and so does 6V6; neither is strict, so neither reaches the gate without the
    census. The first definition here asked only about names no family covered, and 6V3 — the 6.3 V
    heater on every valve drawing — was published on 105 documents without anyone looking at it."""
    assert not judge.needs_judging("2N3904")          # a strict family settles it, census or no census
    assert not judge.needs_judging("12AX7")           # the dictionary holds it
    if parts.CENSUS:
        assert judge.needs_judging("6V3") and judge.needs_judging("6V6")   # loose family, census carries
        assert judge.needs_judging("TTC004B")                              # no family at all


def test_a_verdict_keeps_a_name_out_whatever_the_census_says(monkeypatch):
    def mk(ts):
        return {"w": 1000, "h": 1000,
                "blocks": [{"box": [0, 0, 9, 9], "text": t, "conf": 0.99} for t in ts]}

    monkeypatch.setattr(parts, "CENSUS", {"MH40": ("MH40", "tube"), "12AX7": ("12AX7", "tube")})
    monkeypatch.setattr(parts, "NOT_HERE", set())
    page = "V1 V2 R1 C1 MH40 12AX7 6SN7".split()
    assert "MH40" in [h.part for h in parts.extract_page(mk(page))]
    monkeypatch.setattr(parts, "NOT_HERE", {"MH40"})  # judged: here it is a headphone model
    assert "MH40" not in [h.part for h in parts.extract_page(mk(page))]
