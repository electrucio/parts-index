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


def test_the_parser_is_given_the_item_so_it_can_check_the_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: _reply("6V6 6L6"))
    got = llm.ask_local("t", "sys", [{"key": "a", "prompt": "...", "asked": ["6V6"]}], model="local",
                        parse=lambda text, item: [p for p in item["asked"] if p in text],
                        say=lambda *a: None)
    assert got == {"a": ["6V6"]}


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


def test_an_item_can_ask_for_more_room_than_the_default(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    seen = {}

    def capture(url, body, timeout):
        seen["max_tokens"] = body["max_tokens"]
        return _reply('{"ok": true}')

    monkeypatch.setattr(llm, "_post", capture)
    llm.ask_local("t", "sys", [{"key": "a", "prompt": "...", "max_tokens": 1200}], model="local",
                  max_tokens=700, say=lambda *a: None)
    assert seen["max_tokens"] == 1200


# --- questions worth asking in order --------------------------------------------------------------
def test_a_chain_gives_each_question_what_the_ones_before_it_answered(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    seen = []

    def echo(url, body, timeout):
        prompt = body["messages"][1]["content"]
        seen.append(prompt)
        return _reply(json.dumps({"said": prompt}))

    monkeypatch.setattr(llm, "_post", echo)
    chain = [{"key": "p1"}, {"key": "p2"}, {"key": "p3"}]
    llm.ask_local_chains("t", "sys", [chain], model="local", say=lambda *a: None,
                         build=lambda item, earlier: f"{item['key']} after {[i['key'] for i, _ in earlier]}")
    assert seen == ["p1 after []", "p2 after ['p1']", "p3 after ['p1', 'p2']"]


def test_a_resumed_chain_carries_what_it_answered_before_it_stopped(monkeypatch, tmp_path):
    """A cache hit is not re-asked but still becomes context, so a resumed run is not a different run."""
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    answers, _ = llm._paths("t")
    answers.write_text(json.dumps({"model": "local", "key": "p1", "answer": {"line": "page one"}}) + "\n",
                       encoding="utf-8")
    seen = []
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: seen.append(body["messages"][1]["content"])
                        or _reply('{"line": "page two"}'))
    llm.ask_local_chains("t", "sys", [[{"key": "p1"}, {"key": "p2"}]], model="local", say=lambda *a: None,
                         build=lambda item, earlier: f"{item['key']} after {[a['line'] for _, a in earlier]}")
    assert seen == ["p2 after ['page one']"]


def test_a_chain_carries_what_it_knows_not_what_it_guessed(monkeypatch, tmp_path):
    """An unreadable answer does not become context for the next page."""
    monkeypatch.setattr(llm, "llm_cache", lambda: tmp_path)
    seen = []
    replies = iter(["not json at all", '{"line": "page two"}'])
    monkeypatch.setattr(llm, "_post", lambda url, body, timeout: seen.append(body["messages"][1]["content"])
                        or _reply(next(replies)))
    llm.ask_local_chains("t", "sys", [[{"key": "p1"}, {"key": "p2"}]], model="local", say=lambda *a: None,
                         build=lambda item, earlier: f"{item['key']} after {len(earlier)}")
    assert seen == ["p1 after 0", "p2 after 0"]
