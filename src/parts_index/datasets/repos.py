"""How much attention each open-source project that places a part has.

    pidx datasets repos            only the ones not checked recently
    pidx datasets repos --all      every one of them again

`part_repos.csv` says that 287 GitHub projects place a TL072. That is a list, not an answer: what makes
it useful is knowing which five of the 287 anybody has looked at. Stars, forks and watchers turn the
list into an order.

**`watchers_count` in the REST API is not the watchers.** It is a legacy alias for the star count —
measured on `oomlout/oomlout_oomp_project_bot_v_2`, which reports 0 stars, 0 `watchers_count` and 1
`subscribers_count`. GraphQL's `watchers { totalCount }` is the real figure, and KiCad's mirror shows
why it is worth having separately: 2,983 stars against 130 watchers.

GraphQL also makes this cheap. One query carries a hundred repositories as aliases and costs a single
rate-limit point, so 13,322 of them are about 134 queries against an hourly allowance of 5,000 — minutes
rather than the nine days the unauthenticated REST limit of sixty an hour would need.

Authentication is the `gh` command's, not ours: it already holds the maintainer's login, and this way no
token is read, stored or passed by this project. A read-only token with no scopes is enough.

These numbers age. Every row carries the day it was read, and a repository that has been deleted or made
private is recorded as `gone` rather than dropped — a project that has disappeared is worth knowing
about, being one more dead link.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta

from parts_index.core.config import dataset_table

# The repository is written as its URL, not as `owner/name`, for the same reason `part_repos.csv` is:
# an owner's name is third-party text that can coincide with anything, and the guard blanks a public URL
# before it looks — which is what a GitHub account name is a part of.
FIELDS = ("url", "status", "stars", "forks", "watchers", "pushed", "archived", "moved_to", "checked")
HOST = "https://github.com/"
BATCH = 100          # repositories per query; the whole query still costs one rate-limit point
FRESH_DAYS = 30      # a count read this recently is not worth reading again
NODE = ("{ nameWithOwner stargazerCount forkCount watchers { totalCount } pushedAt isArchived }")


def query(repos: list[str]) -> str:
    """One query asking for a hundred repositories at once, each under its own alias."""
    parts = []
    for i, full in enumerate(repos):
        owner, _, name = full.partition("/")
        parts.append(f"r{i}: repository(owner:{json.dumps(owner)}, name:{json.dumps(name)}) {NODE}")
    return "query { " + " ".join(parts) + " }"


def ask(repos: list[str]) -> dict[str, dict | None]:
    """Run one batch through `gh`. A repository that is gone answers `null`, which is an answer."""
    proc = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query(repos)}"],
        capture_output=True, text=True)
    if not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip()[:300] or "gh returned nothing")
    # `gh` prints the NOT_FOUND errors on stderr and still returns the data for everything else.
    data = (json.loads(proc.stdout) or {}).get("data") or {}
    return {full: data.get(f"r{i}") for i, full in enumerate(repos)}


def row(full: str, node: dict | None, when: str) -> dict:
    """One reading, keyed by the name we asked for rather than the one that answered.

    A repository that has been renamed or transferred still answers, under its new name — GitHub
    redirects — and keeping that name instead would break the join with `part_repos.csv`, which is
    where our links come from. Both are kept: `repo` is what we hold, `moved_to` is where it went.
    """
    if node is None:
        return {"url": HOST + full, "status": "gone", "stars": "", "forks": "", "watchers": "",
                "pushed": "", "archived": "", "moved_to": "", "checked": when}
    now = node["nameWithOwner"]
    return {
        "url": HOST + full,
        "moved_to": "" if now.lower() == full.lower() else HOST + now,
        "status": "archived" if node["isArchived"] else "live",
        "stars": node["stargazerCount"],
        "forks": node["forkCount"],
        "watchers": node["watchers"]["totalCount"],
        "pushed": (node["pushedAt"] or "")[:10],
        "archived": 1 if node["isArchived"] else 0,
        "checked": when,
    }


def known() -> dict[str, dict]:
    path = dataset_table("repo_stats")
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["url"].replace(HOST, "").lower(): r for r in csv.DictReader(f)}


def wanted() -> list[str]:
    """Every repository named by the part index, in the order it is first mentioned."""
    path = dataset_table("part_repos")
    seen: dict[str, None] = {}
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            repo = r["url"].replace(HOST, "").strip("/")
            if repo.count("/") == 1:
                seen.setdefault(repo, None)
    return list(seen)


def stale(repo: str, have: dict[str, dict], days: int) -> bool:
    row_ = have.get(repo.lower())
    if not row_ or not row_.get("checked"):
        return True
    try:
        return datetime.strptime(row_["checked"], "%Y-%m-%d").date() < date.today() - timedelta(days=days)
    except ValueError:
        return True


def refresh(all_: bool = False, limit: int = 0, days: int = FRESH_DAYS) -> dict:
    if not shutil.which("gh"):
        raise RuntimeError("this needs the `gh` command, which holds the login: "
                           "https://cli.github.com, then `gh auth login`")
    have = known()
    todo = [r for r in wanted() if all_ or stale(r, have, days)]
    if limit:
        todo = todo[:limit]
    counts = {"repositories": len(wanted()), "asked": len(todo), "live": 0, "archived": 0,
              "gone": 0, "moved": 0}
    when = date.today().isoformat()
    for at in range(0, len(todo), BATCH):
        batch = todo[at:at + BATCH]
        for full, node in ask(batch).items():
            r = row(full, node, when)
            counts[r["status"]] += 1
            counts["moved"] += 1 if r["moved_to"] else 0
            have[full.lower()] = r
        if at and at % (BATCH * 20) == 0:
            print(f"  {at:,}/{len(todo):,} …", flush=True)

    out = dataset_table("repo_stats")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for key in sorted(have):
            w.writerow(have[key])
    counts["rows"] = len(have)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--all", action="store_true", help="read every repository again, however recent")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many")
    ap.add_argument("--days", type=int, default=FRESH_DAYS, help="how old a reading may be")
    a = ap.parse_args(argv)
    try:
        c = refresh(all_=a.all, limit=a.limit, days=a.days)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{c['asked']:,} of {c['repositories']:,} repositories read: "
          f"{c['live']:,} live, {c['archived']:,} archived, {c['gone']:,} gone, "
          f"{c['moved']:,} renamed or transferred")
    print(f"{c['rows']:,} rows -> {dataset_table('repo_stats')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
