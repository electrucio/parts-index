"""The cells the page draws for each model at each of its data sheet's rows."""
from parts_index.web import checks as K

ROW = {"row": "5", "sym": "cob", "cond": '{"VCB": 5.0}', "min": "", "typ": "", "max": "4.0", "unit": "pF", "variant": ""}
GP = {"family": "gummel-poon", "absent": []}


def test_a_measured_value_is_shown_in_the_sheets_unit_and_coloured_by_its_limits():
    assert K.cell("bjt", ROW, GP, None, [2.027e-12, "inside"]) == ["in", 2.027]
    assert K.cell("bjt", ROW, GP, None, [5.1e-12, "above"]) == ["out", 5.1, "above"]


def test_a_card_that_lacks_what_the_row_needs_says_so_even_where_the_bench_gave_a_number():
    """With CJC=0 the bench measures Cob = 0 pF, which is under "≤ 4 pF": the card, not the model, passed."""
    assert K.cell("bjt", ROW, {"family": "gummel-poon", "absent": ["CJC"]}, None, [0.0, "inside"]) == ["card", ["CJC"]]


def test_an_authors_declaration_stands_where_nothing_was_measured():
    thd = {"row": "9", "sym": "thd", "cond": "{}", "min": "", "typ": "0.0003", "max": "", "unit": "%", "variant": ""}
    K.behaviours.SYMBOLS.setdefault("amplifier", {})["thd"] = "distortion"
    try:
        assert K.cell("opamp", thd, None, {"no": ["distortion"]}, None) == ["author", ["distortion"]]
        # a declaration heading a library of several models may be about another one: not used
        assert K.cell("opamp", thd, None, {"no": ["distortion"], "scope": "file"}, None) == ["none"]
    finally:
        del K.behaviours.SYMBOLS["amplifier"]["thd"]


def test_a_typical_is_a_ratio_another_grades_row_is_not_judged_and_a_negative_sheet_keeps_its_sign():
    vgs = {"row": "2", "sym": "vgs", "cond": "{}", "min": "", "typ": "-0.5", "max": "", "unit": "V", "variant": ""}
    assert K.cell("jfet", vgs, {"family": "jfet", "absent": []}, None, [0.19, "typical"]) == ["typ", -0.19, 0.38]
    idss = {"row": "4", "sym": "idss", "cond": "{}", "min": "6.0", "typ": "", "max": "12.0", "unit": "mA", "variant": "LSK170B"}
    assert K.cell("jfet", idss, {"family": "jfet", "absent": []}, None, [0.004475, "grade"]) == ["grade", 4.475, "LSK170B"]


def test_a_failed_simulation_is_said_and_an_unmeasured_row_is_a_dash():
    assert K.cell("bjt", ROW, GP, None, [None, "error"]) == ["err", "error"]
    assert K.cell("bjt", ROW, GP, None, None) == ["none"]
