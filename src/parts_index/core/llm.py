"""The one way this project asks a model a question, and the record of what that cost.

    from parts_index.core import llm
    answers = llm.ask_batch("judge-parts", SYSTEM, items, SCHEMA, model="gpt-5-mini", budget=5.0)
    answers = llm.ask_local("summarise-pages", SYSTEM, items, model="qwen3.8-27b")

Two backends, one cache. `ask_batch` spends money at OpenAI and is for the judgements worth paying a
strong model for; `ask_local` spends hours on the maintainer's own machine and is for the passes that
have to see the whole corpus. Both write the same answer file, so a task can change its mind later.

Used to build data, never in the path of anything the site serves: a model decides what a token means
once, the answer is committed as a file with its evidence, and the extractor stays deterministic. What
it decides can be read, diffed, corrected by hand and re-judged; what it costs is written down.

  * every answer is cached by (task, model, key), so a re-run asks for nothing it already knows and an
    interrupted run resumes where it stopped;
  * every call appends to a cost ledger — dollars for the paid path, seconds for the local one — and a
    paid run stops at `budget` rather than going past it;
  * the key is read from the file the maintainer keeps outside the repository, and never printed, and
    the local server's address is read from the environment for the same reason.

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
                try:
                    d = json.loads(line)
                except ValueError:
                    continue            # a run stopped mid-write leaves half a line: that one is asked again
                if d["model"] == model:
                    out[d["key"]] = d["answer"]
    return out


def models_in(task: str) -> list[str]:
    """Which models this task has answers from. A task is usually asked with one model, but the model
    name comes from the environment, so a reader that guesses it wrong sees an empty cache and concludes
    there is nothing there."""
    answers, _ = _paths(task)
    if not answers.exists():
        return []
    seen = {}
    for line in answers.open(encoding="utf-8"):
        if line.strip():
            seen[json.loads(line)["model"]] = True
    return list(seen)


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


# --- the model on the other machine -----------------------------------------------------------------
# An OpenAI-compatible server on the local network (llama.cpp), which costs hours instead of dollars.
# That changes what is worth asking: a pass over the whole corpus is unaffordable on the paid API and
# merely slow here. The address is the maintainer's and belongs in the environment, not in the
# repository, so this default is the one a contributor running their own server would use.
LOCAL_URL = os.environ.get("PIDX_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")


class Endpoints:
    """One server or several, given as URLs separated by commas, all serving the same model.

    Each call goes to the server with the fewest calls in flight, so a faster card takes more of the
    work without anyone saying how much faster it is, and a retry goes somewhere other than the server
    that just failed it. One server is the degenerate case and behaves exactly as before.
    """

    def __init__(self, urls: str):
        self.urls = [u.strip() for u in urls.split(",") if u.strip()]
        self.busy = {u: 0 for u in self.urls}
        self.lock = threading.Lock()

    def take(self, avoid: str | None = None) -> str:
        with self.lock:
            url = min(self.urls, key=lambda u: (self.busy[u] + (len(self.urls) * 1000 if u == avoid else 0),
                                                self.urls.index(u)))
            self.busy[url] += 1
            return url

    def give(self, url: str) -> None:
        with self.lock:
            self.busy[url] -= 1

    def __str__(self) -> str:
        return ", ".join(u.split("/v1")[0] for u in self.urls)


def _post(url: str, body: dict, timeout: float):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _asker(url, system, model, temperature, max_tokens, timeout, parse, answers, ledger, have,
           lock, state, total, say, every):
    """One item, asked and written down. Shared by the flat and the chained entry points."""
    def one(item, prompt=None):
        body = {"model": model, "temperature": temperature,
                "max_tokens": int(item.get("max_tokens") or max_tokens),
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt if prompt is not None else item["prompt"]}]}
        t0 = time.time()
        failed_at = None
        for attempt in range(3):
            where = url.take(avoid=failed_at)
            try:
                resp = _post(where, body, timeout)
                break
            except Exception as e:                                   # noqa: BLE001
                failed_at = where
                say(f"  retry {attempt + 1} ({where.split('/v1')[0]}): {str(e)[:90]}")
                time.sleep(5 * (attempt + 1))
            finally:
                url.give(where)
        else:
            with lock:
                state["failed"] += 1
            return None
        took = time.time() - t0
        try:
            answer = parse(resp["choices"][0]["message"]["content"], item)
        except Exception as e:                                       # noqa: BLE001
            with lock:
                state["failed"] += 1
                say(f"  unreadable answer for {item['key']}: {str(e)[:60]}")
            return None
        usage = resp.get("usage") or {}
        with lock:
            state["done"] += 1
            state["seconds"] += took
            have[item["key"]] = answer
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"model": model, "key": item["key"], "usd": 0.0, "s": round(took, 2),
                                    "in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            with answers.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"model": model, "key": item["key"], "answer": answer},
                                   ensure_ascii=False) + "\n")
            if state["done"] % every == 0:
                rate = (time.time() - state["started"]) / state["done"]
                left = rate * (total - state["done"]) / 3600
                say(f"  {state['done']}/{total} asked this run, {rate:.2f}s each, {left:.1f} h to go")
        return answer
    return one


def ask_local(task: str, system: str, items: list[dict], *, model: str, parse=None, workers: int = 4,
              max_tokens: int = 700, temperature: float = 0.2, timeout: float = 300.0,
              url: str | None = None, say=print, every: int = 250) -> dict:
    """items: [{"key": ..., "prompt": ...}] -> {key: answer}. One call per item, cached like `ask_batch`.

    The same cache file and the same key rule as the paid path, so a task can be moved between the two
    and a re-run asks for nothing it already knows. What is written down is seconds and tokens rather
    than dollars: on a corpus-wide pass the number that matters is when it finishes.

    An item may carry its own `max_tokens`, because a cut-off answer is an unreadable one and how long
    an answer needs to be is the caller's business, not this module's.

    `parse(text, item)` turns the model's text into the answer that gets cached; it is given the item
    back so it can check the answer against what was asked. It may raise, and an item whose answer
    cannot be read is left unanswered, so the next run asks again rather than caching rubbish.
    """
    url = Endpoints(url or LOCAL_URL)
    parse = parse or (lambda text, item: json.loads(text))
    answers, ledger = _paths(task)
    have = cached(task, model)
    todo = [it for it in items if it["key"] not in have]
    say(f"{task}: {len(items)} items, {len(items) - len(todo)} already answered, {len(todo)} to ask, "
        f"{model} at {url}")
    if not todo:
        return have

    lock = threading.Lock()
    state = {"done": 0, "failed": 0, "seconds": 0.0, "started": time.time()}
    one = _asker(url, system, model, temperature, max_tokens, timeout, parse, answers, ledger, have,
                 lock, state, len(todo), say, every)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    wall = (time.time() - state["started"]) / 3600
    done = sum(1 for it in items if it["key"] in have)
    say(f"{task}: {done}/{len(items)} answered, {state['failed']} unanswered, {wall:.2f} h this run")
    return have


def ask_local_chains(task: str, system: str, chains: list[list[dict]], build, *, model: str, parse=None,
                     workers: int = 4, max_tokens: int = 700, temperature: float = 0.2,
                     timeout: float = 300.0, url: str | None = None, say=print, every: int = 250) -> dict:
    """Like `ask_local`, but some questions are worth asking in order.

    `chains` is a list of lists. Items inside a chain are asked one after another and each one's prompt
    is built by `build(item, earlier)`, where `earlier` is what the chain has answered so far — cache
    hits included, so a resumed run gives the same context as an uninterrupted one. Chains run `workers`
    at a time, which is where the parallelism comes from: a magazine issue is answered in order while
    fifty other issues are answered beside it.

    The cache, the ledger and the key rule are `ask_local`'s, unchanged. An item whose answer cannot be
    read is left unanswered and does not join `earlier`: a chain carries what it knows, not what it
    guessed.
    """
    url = Endpoints(url or LOCAL_URL)
    parse = parse or (lambda text, item: json.loads(text))
    answers, ledger = _paths(task)
    have = cached(task, model)
    flat = [it for chain in chains for it in chain]
    todo = [it for it in flat if it["key"] not in have]
    say(f"{task}: {len(flat)} items in {len(chains)} chains, {len(flat) - len(todo)} already answered, "
        f"{len(todo)} to ask, {model} at {url}")
    if not todo:
        return have

    lock = threading.Lock()
    state = {"done": 0, "failed": 0, "seconds": 0.0, "started": time.time()}
    one = _asker(url, system, model, temperature, max_tokens, timeout, parse, answers, ledger, have,
                 lock, state, len(todo), say, every)

    def chain(items):
        earlier: list[tuple[dict, dict]] = []
        for item in items:
            answer = have.get(item["key"])
            if answer is None:
                answer = one(item, build(item, earlier))
            if answer is not None:
                earlier.append((item, answer))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(chain, chains))
    wall = (time.time() - state["started"]) / 3600
    done = sum(1 for it in flat if it["key"] in have)
    say(f"{task}: {done}/{len(flat)} answered, {state['failed']} unanswered, {wall:.2f} h this run")
    return have
