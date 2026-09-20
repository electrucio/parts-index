"""Two synthetic pages that must stay on their side of the threshold. The real measurement uses labelled magazine pages."""
from parts_index.core import adfilter


def page(lines, w=1000, h=1400):
    blocks = [{"box": [60, 40 + 28 * i, 60 + 9 * len(t), 62 + 28 * i], "text": t, "conf": 0.98} for i, t in enumerate(lines)]
    return {"w": w, "h": h, "blocks": blocks}


ADVERT = page(["SEMICONDUCTORS - ALL BRAND NEW", "BC107 12p", "BC108 12p", "BC109 14p", "2N3053 22p", "2N3054 55p",
               "2N3055 £1.25", "NE555 35p", "uA741 28p", "TL072 £0.85", "Postage and packing 50p. Please add VAT at 15%",
               "Mail order only. Access and Barclaycard welcome", "Tel: 01-452 1500  Dept PE12"])
ARTICLE = page(["The output stage", "The circuit diagram of the amplifier is shown in Fig. 2. The input signal is applied",
                "to the base of TR1 through C1, and R3 sets the quiescent current of the output pair.",
                "TR1 BC109", "TR2 2N3055", "R3 4k7", "C1 10uF", "IC1 NE5534", "Fig. 3. Waveform at the collector of TR2"])


def test_component_price_list_is_an_advert():
    points, fired = adfilter.score(ADVERT)
    assert adfilter.is_ad(ADVERT), (points, fired)


def test_article_with_a_parts_list_is_not():
    points, fired = adfilter.score(ARTICLE)
    assert not adfilter.is_ad(ARTICLE), (points, fired)


def test_catalogue_runs():
    assert adfilter.seq_run(["BC107", "BC108", "BC109", "2N3053", "2N3054", "2N3055"]) == 1.0
    assert adfilter.seq_run(["BC109", "2N3055", "NE5534", "TL072", "1N4148", "BD139"]) == 0.0
