"""One-off steps that carry the pre-monorepo pipeline's state across, and are then deleted.

Nothing here is part of the project: it exists because the old pipeline wrote its state in places the new
one does not read. `make migrate` runs what is left. When the last pipeline stage is ported, this package
goes with it.

The step that seeded the schematic ledgers has already been removed: it read the old corpus, which is now
retired, and what it produced is committed under `data/schematics/state/`. Git history holds how.
"""
