"""The one way a model is asked anything here: cached, budgeted, and written down."""
import json

import pytest

from parts_index.core import llm


def test_a_model_with_no_price_cannot_be_spent_on(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    with pytest.raises(SystemExit, match="no price"):
        llm.ask_batch("t", "sys", [{"key": "a"}], {}, model="some-new-model")


def test_what_was_answered_before_is_not_asked_again(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    answers, _ = llm._paths("t")
    answers.write_text(json.dumps({"model": "gpt-5-mini", "key": "a", "answer": {"key": "a", "v": 1}}) + "\n",
                       encoding="utf-8")
    # every item is already answered, so this returns without importing the client at all
    got = llm.ask_batch("t", "sys", [{"key": "a"}], {}, model="gpt-5-mini", say=lambda *a: None)
    assert got == {"a": {"key": "a", "v": 1}}


def test_the_cache_is_per_model(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    answers, _ = llm._paths("t")
    answers.write_text(json.dumps({"model": "gpt-5", "key": "a", "answer": {"key": "a"}}) + "\n", encoding="utf-8")
    assert llm.cached("t", "gpt-5") and not llm.cached("t", "gpt-5-mini")


def test_the_cost_is_added_up_from_the_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    _, ledger = llm._paths("t")
    ledger.write_text("".join(json.dumps({"usd": u}) + "\n" for u in (0.01, 0.02, 0.005)), encoding="utf-8")
    assert llm.spent("t") == pytest.approx(0.035)
