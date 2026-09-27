# Contributing

Thank you for helping. The project rules are short and live in [CLAUDE.md](CLAUDE.md); they apply to people
and to AI assistants alike. The two that matter most: **publish links, never copies**, and **a wrong link
is worse than no link**.

## Set-up

```
git clone git@github.com:electrucio/parts-index.git
cd parts-index
make setup      # installs dependencies and enables the pre-commit guard
make            # lists every step
```

`make check` runs what CI runs. The pre-commit hook runs `scripts/licence_guard.py`, which refuses PDFs,
archives, large files, manufacturer model text outside the allowed folders, local paths and secrets.

## What you can contribute without any private data

| Contribution | Where |
|---|---|
| A reference for a part (article, book page, app note, schematic) | `data/schematics/curated/<part>.yaml` |
| A wrong or dead link | `data/schematics/overrides.csv` |
| A new site worth indexing | an entry in `data/schematics/sources.yaml` with status `proposed` |
| Where to find a SPICE model | `data/models/links.csv` |
| What a family of parts is | `data/parts/families.yaml` |
| How two parts relate, with the document that says so | `data/parts/relations.csv` |
| The family a maker's own sheet gives a part | `data/parts/part_families.csv` |
| What the letters of a numbering system mean | `data/parts/schemes/<system>.yaml` |
| An organisation: headquarters, founding, acquisitions | `data/parts/makers.yaml` |
| A book, standard or history the above cite | `data/parts/references.csv` |
| Datasheet figures for a part | `data/datasheets/refs/<kind>/<PART>.yaml` |
| A new LTspice component | `components/<name>/` (see `docs/COMPONENTS.md`) |
| A part-number extraction bug | a failing test case in `tests/` plus the fix |
| The website | `web/` |

These paths are created as the migration proceeds; if one does not exist yet, open an issue instead.

Everything in the catalogue of what a part *is* names its source: an id of `references.csv`, or a URL
you opened. A family, a relation, a date or a country without one is left out rather than written from
memory, and a relation is never an equivalence — "sold as one product with", "offered by its maker as a
replacement for", "documented in one datasheet with" — only what the source says. Write it in your own
words: a fact and a link, never a manufacturer's sentence. `make test` checks that every id you cite
exists.

## Licensing of contributions

By contributing you agree that your contribution is licensed as the folder it goes into: Apache-2.0 for
code, CC BY 4.0 for `data/`, MIT for `components/` and `circuits/`. Only add third-party files whose licence
allows redistribution, keep them unmodified, and include their licence file.

## Pull requests

Keep them small and single-purpose. Say what you checked and how. For links, confirm that you opened the
URL and that the part really appears on the page you cite.
