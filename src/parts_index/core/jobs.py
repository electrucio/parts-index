"""Long jobs: one at a time, in a session of their own, with a log to watch them through.

A crawl or a download of a large source runs for hours, which rules out a job of the terminal: it dies
with the session that started it. It also rules out starting one by hand twice, which is the failure
this project has actually had — two sessions launching the same source within a second of each other,
both writing one ledger.

    with only_one("audiocircuit"):        # a second launch refuses instead of racing
        ...
    detach(MODULE, args, "audiocircuit")  # the same command again, detached, writing to its log
    wait_for("audiocircuit")              # ... or after that one finishes, for jobs that queue up

A job is named after what it does — usually its sources joined by a dash — and owns two files in the
private log directory: `<name>.log`, appended to so a relaunch keeps the history, and `<name>.lock`.
"""
from __future__ import annotations

import fcntl
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from parts_index.core.config import logs

POLL = 30.0          # how often a queued job asks whether the one before it has finished


def run_log(name: str) -> Path:
    return logs() / f"{name}.log"


def run_lock(name: str) -> Path:
    return logs() / f"{name}.lock"


def _handle(name: str):
    logs().mkdir(parents=True, exist_ok=True)
    return open(run_lock(name), "w", encoding="utf-8")


@contextmanager
def only_one(name: str):
    """Hold this job's lock for as long as the work lasts, or refuse to start."""
    handle = _handle(name)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit(f"{name} is already running; its lock is held ({run_lock(name)})") from None
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def running(name: str) -> bool:
    """Whether some process holds that job's lock. Asked by looking, never by matching process names:
    a pattern that matches a running job also matches the shell that asks about it."""
    handle = _handle(name)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        handle.close()
    return False


def wait_for(name: str, timeout: float = 86400, poll: float = POLL, sleep=time.sleep) -> bool:
    """Block until that job is not running. True when it is free, False when the wait ran out.

    This is how one long job follows another without a person in between, and why a job takes a lock
    even when nothing else would contend for it.
    """
    deadline = time.time() + timeout
    while running(name):
        if time.time() >= deadline:
            return False
        sleep(poll)
    return True


def wait_for_all(names: list[str], timeout: float = 86400, poll: float = POLL, sleep=time.sleep) -> str:
    """Block until none of those jobs is running. "" when they are all free, else the one still going.

    Waiting for them one after another is enough however they finish: each wait returns only when that
    job is over, so the last one to end is the one the caller is left waiting on.
    """
    deadline = time.time() + timeout
    for name in names:
        if not wait_for(name, timeout=max(deadline - time.time(), 0), poll=poll, sleep=sleep):
            return name
    return ""


def detach(module: str, args: list[str], name: str) -> int:
    """Start `python -m <module> <args>` in its own session, writing to this job's log. Returns its pid.

    Unbuffered (`-u`), because the log is the only window into a job that runs for days: with the usual
    block buffering a progress line sits in a 4 KB buffer for hours and `tail -f` shows nothing, which
    is indistinguishable from a job that has hung."""
    logs().mkdir(parents=True, exist_ok=True)
    with open(run_log(name), "a", encoding="utf-8") as out:
        child = subprocess.Popen([sys.executable, "-u", "-m", module, *args], stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    return child.pid
