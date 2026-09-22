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


# --- the local backend ------------------------------------------------------------------------------
def _reply(content, prompt_tokens=100, completion_tokens=10):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}}


def test_the_local_backend_caches_and_writes_down_the_seconds(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: _reply('{"line": "a valve preamp"}'))
    got = llm.ask_local("t", "sys", [{"key": "p1", "prompt": "..."}], model="local", say=lambda *a: None)
    assert got == {"p1": {"line": "a valve preamp"}}

    answers, ledger = llm._paths("t")
    assert json.loads(answers.read_text(encoding="utf-8"))["key"] == "p1"
    row = json.loads(ledger.read_text(encoding="utf-8"))
    assert row["usd"] == 0.0 and row["in"] == 100 and "s" in row

    # asked again, it goes nowhere near the server
    def refuse(*a, **k):
        raise AssertionError("asked for an answer it already had")
    monkeypatch.setattr(llm, "_post", refuse)
    assert llm.ask_local("t", "sys", [{"key": "p1", "prompt": "..."}], model="local",
                         say=lambda *a: None) == {"p1": {"line": "a valve preamp"}}


def test_an_unreadable_answer_is_left_to_be_asked_again(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: _reply("sorry, I cannot do that"))
    got = llm.ask_local("t", "sys", [{"key": "p1", "prompt": "..."}], model="local", say=lambda *a: None)
    assert got == {}
    answers, _ = llm._paths("t")
    assert not answers.exists() or not answers.read_text(encoding="utf-8").strip()


def test_the_local_backend_does_not_need_an_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    monkeypatch.setattr(llm, "KEY_FILE", tmp_path / "there-is-no-key")
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: _reply('{"ok": true}'))
    assert llm.ask_local("t", "sys", [{"key": "a", "prompt": "..."}], model="local",
                         say=lambda *a: None) == {"a": {"ok": True}}


def test_the_server_address_is_not_written_into_the_repository():
    # rule 6: the maintainer's machine is named in the environment, never here
    assert llm.LOCAL_URL.startswith("http://127.0.0.1") or "PIDX_LLM_URL" in __import__("os").environ
