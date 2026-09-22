"""The diagnosis: an extractor problem and a coverage problem must not read the same."""
from parts_index.core.parts import explain


def line(out, field):
    return next(x.split(maxsplit=1)[1].strip() for x in out if x.strip().startswith(field))


def test_a_part_no_family_covers_is_an_extractor_problem():
    out = explain.explain("TTC004B")
    assert "none covers it" in line(out, "family")
    assert line(out, "verdict").startswith("extractor:")


def test_a_part_read_correctly_and_absent_is_a_coverage_problem():
    out = explain.explain("2SC3334")
    assert "strict" in line(out, "family")
    assert line(out, "verdict").startswith("coverage:")


def test_a_part_the_index_has_says_so():
    out = explain.explain("BCP56")
    assert line(out, "verdict").startswith("fine")
    assert "documents in the index" in line(out, "can answer")
