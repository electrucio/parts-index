# parts-index

An open database for analog-audio electronics hobbyists, served as a static website with no backend.

When you start out in this hobby it is hard to know where to find SPICE models, which of them can be
trusted, where the datasheets are, what a part number means, and which real circuits use a given part.
This project collects those answers per part number (for example `2N2222`, `TL072`, `12AX7`), with an
emphasis on audio and analog electronics.

> **Status: early.** The code and data are being migrated from two private working repositories, so the
> command line and the website are still arriving piece by piece. [STATUS.md](STATUS.md) records what has
> been processed: today 57,160 documents from 62 sources, and 12,751 model files from 71 vendors and
> collections.

## What it contains

| Pillar | What you get |
|---|---|
| **Schematic and reference index** | For each part number, links to factory schematics, project sites, classic electronics magazines, books and historical references that use it, with the page and the position on the page. |
| **SPICE models and datasheets** | Where each model can be found, who published it, under which terms, and links to the datasheets of the main manufacturers. |
| **Model verification** | Each model is simulated (ngspice, LTspice, QSPICE) and the results are compared with the datasheet figures, so you can see how far to trust it. |
| **Extra LTspice components** | Original, tested models with `.asy` symbols for parts LTspice lacks: potentiometers, relays, transformers, pickups, speakers, vactrols and more. See [components/](components/). |

## Links, not copies

The repository stores **no third-party documents**. Schematics, magazine scans, books and datasheets are
referenced by public URL only. Manufacturer SPICE models that may not be redistributed are indexed and
linked, with a recipe (URL + checksum) that lets you download them yourself; model files are hosted here
only when their licence allows it. If something listed here should not be, see [TAKEDOWN.md](TAKEDOWN.md).

## Repository layout

```
src/parts_index/   Python package and the `pidx` command line tool
components/        extra LTspice components (original work, MIT)
circuits/          reference circuits used to compare models
data/              the public dataset (CC BY 4.0): source registries, processing ledgers, the part
                   dictionary, and — as the migration proceeds — the index itself and model recipes
private_uncommitted/   local only, git-ignored: downloaded documents, OCR text, vendor model files,
                   datasheet PDFs. `pidx paths` prints what is public and what is not.
```

The website (`web/`) and the documentation (`docs/`) are not in the repository yet.

## Contributing

Most contributions need neither the private corpus nor a GPU: adding a reference for a part, reporting a
wrong link, proposing a source site, adding a model link or datasheet figures, writing a component, or
working on the website. See [CONTRIBUTING.md](CONTRIBUTING.md). The repository is set up for working with
Claude Code; [CLAUDE.md](CLAUDE.md) holds the project rules.

## Licence

Code: [Apache-2.0](LICENSE). Data under `data/`: CC BY 4.0. Components and circuits: MIT.
Third-party model files keep their original licence, stated next to each file. See [NOTICE](NOTICE).
