"""Starting a job that lasts hours: one at a time, detached, and one after another."""
from __future__ import annotations

import pytest

from parts_index.core import jobs


@pytest.fixture(autouse=True)
def private_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))


def test_a_second_launch_of_the_same_job_is_refused():
    """Two sessions starting one source is how a ledger gets two writers."""
    with jobs.only_one("crawl_tubecad"):
        assert jobs.running("crawl_tubecad")
        with pytest.raises(SystemExit, match="already running"):
            with jobs.only_one("crawl_tubecad"):
                pass
    assert not jobs.running("crawl_tubecad")
    with jobs.only_one("crawl_tubecad"):        # and the lock is free again for the next run
        pass


def test_a_job_can_wait_for_the_one_before_it():
    waits = []
    assert jobs.wait_for("nobody_holds_this", sleep=waits.append) is True
    assert waits == []                          # nothing to wait for: no sleeping, no polling


def test_waiting_gives_up_when_the_one_before_it_never_ends():
    slept = []

    def sleep(seconds):
        slept.append(seconds)

    with jobs.only_one("download_audiocircuit"):
        assert jobs.wait_for("download_audiocircuit", timeout=0, poll=5, sleep=sleep) is False
    assert slept == []                          # the deadline is checked before sleeping on it


def test_a_detached_job_outlives_the_shell_that_started_it(monkeypatch):
    started = {}

    class Child:
        pid = 4242

    monkeypatch.setattr(jobs.subprocess, "Popen", lambda cmd, **kw: started.update(cmd=cmd, kw=kw) or Child())
    pid = jobs.detach("parts_index.schematics.crawl", ["--source", "tubecad"], "crawl_tubecad")

    assert pid == 4242
    # -u because the log is the only window into a job that runs for days: block-buffered, a progress
    # line sits unseen for hours and a live job is indistinguishable from a hung one
    assert started["cmd"][1:] == ["-u", "-m", "parts_index.schematics.crawl", "--source", "tubecad"]
    assert started["kw"]["start_new_session"] is True
    assert started["kw"]["stdin"] is jobs.subprocess.DEVNULL       # nothing is ever waiting for a terminal
    assert jobs.run_log("crawl_tubecad").exists()
