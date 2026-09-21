"""One-off steps that carry the pre-monorepo pipeline's state across, and are then deleted.

Nothing here is part of the project: it exists because the old pipeline wrote its state in places the
new one does not read. `make migrate` runs all of it. When the last pipeline stage is ported and the old
trees are gone, this package goes with them.
"""
