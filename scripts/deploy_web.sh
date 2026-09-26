#!/usr/bin/env bash
# Publish the built site: copy web/dist into the GitHub Pages repository, commit, push.
#
#   make web-deploy                      build, copy, commit and push
#   make web-deploy NO_PUSH=1            everything but the push (look at the commit first)
#   PAGES_REPO=/elsewhere/x.github.io    where the Pages repository is checked out
#
# The site lives in a directory of the user site (electrucio.github.io/parts-index/), which is why vite's
# base is /parts-index/. The public site is the public build only: nothing private is read here, and
# what is copied is exactly web/dist. The Pages repository must be on main and clean, so a deploy never
# sweeps somebody's half-done work into the commit. Jekyll is switched off with .nojekyll: 43,000 part
# pages would otherwise go through its build, which has a time limit, and none of them needs it.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PAGES_REPO=${PAGES_REPO:-$ROOT/../electrucio.github.io}
SUBDIR=${SUBDIR:-parts-index}
DIST=$ROOT/web/dist
IDENTITY=(-c user.name=Electrucio -c user.email=electrucio@users.noreply.github.com)

die() { echo "deploy: $*" >&2; exit 1; }

[ -f "$DIST/index.html" ] && [ -f "$DIST/data/parts.json" ] || die "no built site in web/dist: run 'make web' first"
[ -d "$PAGES_REPO/.git" ] || die "no git repository at $PAGES_REPO (set PAGES_REPO)"
cd "$PAGES_REPO"
[ "$(git branch --show-current)" = main ] || die "$PAGES_REPO is not on main"
if [ -n "$(git status --porcelain | grep -v "^?? $SUBDIR/" || true)" ]; then
    die "$PAGES_REPO has uncommitted changes outside $SUBDIR/; commit or stash them first"
fi
git pull --ff-only --quiet || die "could not fast-forward $PAGES_REPO from its remote"

rsync -a --delete "$DIST/" "$PAGES_REPO/$SUBDIR/"
[ -f .nojekyll ] || { touch .nojekyll; echo "deploy: created .nojekyll (Jekyll off for the whole site)"; }

# What this deploy carries, for the commit message: the export's totals and the commit it was built from.
built=$(cd "$ROOT" && git rev-parse --short HEAD)
totals=$(cd "$ROOT" && "$ROOT/.venv/bin/python" - <<'PY'
import json
from parts_index.core.config import schematics_export_manifest as schematics_export
e = json.load(open(schematics_export(), encoding="utf-8"))
s = e["sources"].values()
print(f"{sum(x['documents'] for x in s):,} documents, {sum(x['uses'] for x in s):,} uses, "
      f"{len(e['sources'])} sources, export of {e['built']}")
PY
)
git add -A "$SUBDIR" .nojekyll
if git diff --cached --quiet; then
    echo "deploy: nothing changed since the last deploy"; exit 0
fi
files=$(git diff --cached --numstat | wc -l)
git "${IDENTITY[@]}" commit --quiet -m "$SUBDIR: built from parts-index $built

$totals; $files files changed."
echo "deploy: committed $(git rev-parse --short HEAD) in $PAGES_REPO ($files files)"
if [ "${NO_PUSH:-}" = 1 ]; then
    echo "deploy: NO_PUSH=1, not pushed. To publish: cd $PAGES_REPO && git push"; exit 0
fi
git push --quiet
echo "deploy: pushed. GitHub Pages builds in a minute or two: https://electrucio.github.io/$SUBDIR/"
