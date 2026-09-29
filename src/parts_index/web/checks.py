"""What the part page shows of each model against its data sheet: the sheet's rows, one column per model.

Joins, per recipe, the data sheet it names (published by `pidx datasheets rows` when that sheet has
been read) with the part's record in data/verification/ — what each card lacks, what each model's author
declares, what the bench measured — into cells the page only has to draw. Each cell is one of:

    ["in", value]            inside the sheet's limits            ["out", value, "below"|"above"]
    ["typ", value, ratio]    the sheet gives only a typical      ["grade", value, grade]  another grade's row
    ["card", [params]]       the card lacks what the row needs ([] : its model family has nothing for it)
    ["author", [claims]]     its author declares it not modelled ["none"]  not measured
    ["err", message]         the simulation failed or returned no value a device can have

Values are in the unit the sheet prints the row in, with the sheet's sign, to four significant figures,
so they read against its min/typ/max. The netlists behind them go to a file of their own per part,
fetched when a reader asks how a value was measured.
"""
from __future__ import annotations

import csv
import json
from functools import cache

from parts_index.core.config import datasheet_values, datasheet_values_index, verification
from parts_index.datasheets.rows import unit_factor
from parts_index.models import behaviours
from parts_index.models import cards as C

STATUS_TEXT = {"no-bench": "no bench for this quantity yet", "temperature": "not at 25 °C: the bench runs at 25 °C"}


@cache
def sheets() -> dict[str, dict]:
    p = datasheet_values_index()
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {r["url"].lower(): r for r in csv.DictReader(f) if r["url"]}


@cache
def sheet_rows(doc: str) -> list[dict]:
    with open(datasheet_values(doc), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def record_of(kind: str, part: str) -> dict:
    p = verification(kind, part)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def printed(v: float, row: dict) -> float:
    """An SI magnitude in the row's printed unit, with the sheet's sign."""
    f = unit_factor(row["unit"]) or 1.0
    neg = any(row[c].startswith("-") for c in ("min", "typ", "max") if row[c])
    return float(f"{(-v if neg else v) / f:.4g}")


def cell(kind: str, row: dict, card: dict | None, claims: dict | None, got: list | None) -> list:
    sym = row["sym"]
    cannot = C.cannot(card, sym) if card else None
    if cannot is not None:
        return ["card", list(cannot)]
    if got and got[0] is not None:
        v, verdict = got
        shown = printed(v, row)
        if verdict == "inside":
            return ["in", shown]
        if verdict in ("below", "above"):
            return ["out", shown, verdict]
        if verdict == "typical":
            typ = abs(float(row["typ"])) * (unit_factor(row["unit"]) or 1.0)
            return ["typ", shown, float(f"{v / typ:.3g}") if typ else None]
        if verdict == "grade":
            return ["grade", shown, row["variant"]]
        return ["in" if verdict == "inside" else "err", shown]
    if got and got[1] in ("error", "suspect"):
        return ["err", got[1]]
    beh = behaviours.of_row(kind, sym, json.loads(row["cond"] or "{}"))
    if claims and claims.get("scope") != "file" and beh:
        said = [c for c in claims.get("no", []) if behaviours.CLAIMS.get(c) == beh]
        if said:
            return ["author", said]
    return ["none"]


def facts(m: dict, card: dict | None, claims: dict | None, bench: dict | None) -> dict:
    """What the page lists under a model's column: where it runs, what its card lacks, what its author
    says, what was changed in it before it was simulated."""
    out: dict = {}
    if bench:
        runs = {}
        for e, vals in bench["values"].items():
            runs[e] = "ok" if any(v[0] is not None for v in vals.values()) else "failed"
        out["runs"] = runs
        q, n = bench["values"].get("qspice", {}), bench["values"].get("ngspice", {})
        if q and n:
            out["differs"] = sorted(int(k) for k in q if k in n and q[k][1] != n[k][1])
        out["changes"] = sorted({c for ch in bench["changes"].values() for c in ch})
    if card:
        out["family"] = card["family"]
        if card.get("absent"):
            out["absent"] = card["absent"]
        if card.get("dialect"):
            out["dialect"] = card["dialect"]
    if claims:
        out["claims"] = {k: claims[k] for k in ("yes", "no", "limits", "simulator", "lines", "scope") if k in claims}
    return out


def page_block(recipe: dict, trimmed: dict) -> dict | None:
    """The block the page folds under the models table, and each model's cells and facts."""
    kind, part = recipe.get("kind", ""), recipe.get("part", "")
    rec = record_of(kind, part)
    sheet = sheets().get(((recipe.get("datasheet") or {}).get("url") or "").lower())
    if not rec and not sheet:
        return None
    cards, claims, bench = rec.get("cards", {}), rec.get("claims", {}), rec.get("bench", {})
    rows = sheet_rows(sheet["doc"]) if sheet else []
    status = bench.get("rows", {}) if bench.get("sheet") == (sheet or {}).get("doc") else {}
    any_fact = False
    for m, t in zip(recipe.get("models") or [], trimmed["models"]):
        h = m.get("hash")
        if not h:
            continue
        b = (bench.get("models") or {}).get(h)
        chk = facts(m, cards.get(h), claims.get(h), b)
        if rows:
            vals = (b or {}).get("values", {}).get(bench.get("primary", "qspice"), {})
            chk["cells"] = {r["row"]: cell(kind, r, cards.get(h), claims.get(h), vals.get(r["row"])) for r in rows}
        if chk:
            t["chk"] = chk
            any_fact = True
    if not rows and not any_fact:
        return None
    out: dict = {"dialects": {k: v for k, v in C.DIALECT.items()},
                 "changes": bench.get("changes", {})}
    if sheet:
        out["sheet"] = {k: sheet[k] for k in ("doc", "maker", "title", "url", "sha256", "read_by", "read_on", "checked_by")}
        out["sheet"]["rows"] = [[int(r["row"]), int(r["page"]), r["symbol"], r["conditions"], r["min"], r["typ"],
                                 r["max"], r["unit"], r["variant"], STATUS_TEXT.get(status.get(r["row"], ""), ""),
                                 bool(r["box"])] for r in rows]
    if bench.get("engines"):
        out["engines"] = {e: {"version": x["version"], "image": x["image"], "bench": x["bench"], "on": x["on"]}
                          for e, x in bench["engines"].items()}
        out["primary"] = bench.get("primary", "qspice")
    return out


def netlists(recipe: dict) -> dict | None:
    """The netlists each simulator ran for each model, by the model's place in the page's list, with the
    command and the simulators' identities: the file behind "how was this measured"."""
    bench = record_of(recipe.get("kind", ""), recipe.get("part", "")).get("bench", {})
    if not bench.get("models"):
        return None
    models = {}
    for i, m in enumerate(recipe.get("models") or []):
        b = bench["models"].get(m.get("hash") or "")
        if b:
            models[i] = {"netlists": b["netlists"], "changes": b["changes"]}
    return {"engines": bench["engines"], "changes": bench.get("changes", {}), "models": models} if models else None
