"""The one way this project asks a model a question, and the record of what that cost.

    from parts_index.core import llm
    answers = llm.ask_batch("judge-parts", SYSTEM, items, SCHEMA, model="gpt-5-mini", budget=5.0)

Used to build data, never in the path of anything the site serves: a model decides what a token means
once, the answer is committed as a file with its evidence, and the extractor stays deterministic. What
it decides can be read, diffed, corrected by hand and re-judged; what it costs is written down.

  * every answer is cached by (task, model, key), so a re-run asks for nothing it already knows and an
    interrupted run resumes where it stopped;
  * every call appends to a cost ledger, and the run stops at `budget` dollars rather than going past it;
  * the key is read from the file the maintainer keeps outside the repository, and never printed.

Cache and ledger live under the private data root — they hold corpus text, which does not get committed.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parts_index.core.config import llm_cache

# Dollars per million tokens, (input, output). Checked 2026-09-22; a model not listed here cannot be
# charged for, and `ask_batch` refuses it rather than spending an unknown amount.
PRICES = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}
KEY_FILE = Path(os.environ.get("PIDX_OPENAI_KEY", "~/.config/parts-index/openai_key.txt")).expanduser()


def _key() -> str:
    """From outside the repository, always, and never printed (rule 6). $PIDX_OPENAI_KEY moves it."""
    if not KEY_FILE.exists():
        raise SystemExit(f"no API key: put one in {KEY_FILE}, or set PIDX_OPENAI_KEY to where it is")
    return KEY_FILE.read_text(encoding="utf-8").strip()


def _paths(task: str):
    root = llm_cache() / task
    root.mkdir(parents=True, exist_ok=True)
    return root / "answers.jsonl", root / "cost.jsonl"


def spent(task: str) -> float:
    _, ledger = _paths(task)
    if not ledger.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in ledger.open(encoding="utf-8") if line.strip())


def cached(task: str, model: str) -> dict:
    answers, _ = _paths(task)
    out = {}
    if answers.exists():
        for line in answers.open(encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                if d["model"] == model:
                    out[d["key"]] = d["answer"]
    return out


def ask_batch(task: str, system: str, items: list[dict], schema: dict, *, model: str = "gpt-5-mini",
              budget: float = 5.0, per_call: int = 20, effort: str = "low", workers: int = 8,
              say=print) -> dict:
    """items: [{"key": ..., anything else the prompt should see}] -> {key: answer}. Cached, budgeted.

    Calls go out `workers` at a time: a reasoning model takes tens of seconds to answer, and a few
    thousand questions asked one after another is hours of waiting for nothing. The cache, the ledger and
    the running total are written under one lock, so a run can be stopped at any point and resumed."""
    if model not in PRICES:
        raise SystemExit(f"{model} has no price here; add it to llm.PRICES before spending on it")
    answers, ledger = _paths(task)
    have = cached(task, model)
    todo = [it for it in items if it["key"] not in have]
    say(f"{task}: {len(items)} items, {len(have)} already answered, {len(todo)} to ask, "
        f"${spent(task):.2f} spent so far (budget ${budget:.2f})")
    if not todo:
        return have

    from openai import OpenAI
    client = OpenAI(api_key=_key())
    lock = threading.Lock()
    state = {"usd": spent(task), "done": 0, "stop": False}

    def one(chunk):
        with lock:
            if state["stop"] or state["usd"] >= budget:
                state["stop"] = True
                return
        user = "\n".join(json.dumps(it, ensure_ascii=False) for it in chunk)
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=model, reasoning_effort=effort,
                    response_format={"type": "json_schema", "json_schema": schema},
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                break
            except Exception as e:                                   # noqa: BLE001
                say(f"  retry {attempt + 1}: {str(e)[:90]}")
                time.sleep(5 * (attempt + 1))
        else:
            return
        usage = resp.usage
        usd = (usage.prompt_tokens * PRICES[model][0] + usage.completion_tokens * PRICES[model][1]) / 1e6
        keys = {c["key"] for c in chunk}
        got = [x for x in json.loads(resp.choices[0].message.content)["items"] if x.get("key") in keys]
        with lock:
            state["usd"] += usd
            state["done"] += len(chunk)
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"model": model, "n": len(chunk), "in": usage.prompt_tokens,
                                    "out": usage.completion_tokens, "usd": round(usd, 6),
                                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            with answers.open("a", encoding="utf-8") as f:
                for item in got:
                    have[item["key"]] = item
                    f.write(json.dumps({"model": model, "key": item["key"], "answer": item},
                                       ensure_ascii=False) + "\n")
            if state["done"] % (per_call * workers * 4) < per_call:
                say(f"  {len(have)}/{len(items)} answered, ${state['usd']:.2f}")

    chunks = [todo[i:i + per_call] for i in range(0, len(todo), per_call)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, chunks))
    if state["stop"]:
        say(f"budget of ${budget:.2f} reached, stopping with {len(have)} answered")
    say(f"{task}: {len(have)}/{len(items)} answered, ${spent(task):.2f} spent")
    return have
