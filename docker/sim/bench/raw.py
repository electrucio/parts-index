"""Read the waveform files the three simulators write.

ngspice and LTspice both write the Berkeley "raw" layout: a text header (UTF-8 for ngspice, UTF-16-LE for
LTspice), then the values, either as text ("Values:") or as packed numbers ("Binary:"). QSPICE's .qraw is
the same layout. Several plots may follow one another in one file (ngspice writes one per analysis).

Text values are read line by line into arrays of doubles, never as one string cut into tokens: a packed
transient can be hundreds of megabytes of text, and holding it as Python strings took a worker past 5 GB.
"""

import array
import re
import struct
from pathlib import Path


def _encoding(path):
    with open(path, "rb") as f:
        head = f.read(64)
    return "utf-16-le" if head[:2] == b"\xff\xfe" or b"\x00" in head else "utf-8"


def _number(token):
    if "," in token:
        re_, im = token.split(",")
        return complex(float(re_), float(im))
    return float(token)


def read(path):
    """Every plot in the file, as dicts: name, flags, variables, and data {canonical name: values}."""
    enc = _encoding(path)
    plots = []
    with open(path, encoding=enc, errors="replace", newline="") as f:
        while True:
            head, variables, kind = _header(f)
            if head is None:
                break
            if kind == "Binary":
                return _read_binary(path, enc)
            nvars = int(head["No. Variables"])
            npoints = int(head["No. Points"])
            flags = head.get("Flags", "").lower().split()
            is_complex = "complex" in flags
            columns = [[] if is_complex else array.array("d") for _ in range(nvars)]
            col = 0
            got = 0
            for line in f:
                fields = line.split()
                if not fields:
                    continue
                if col == 0:
                    if len(fields) < 2:
                        break  # the next plot's header, or a run cut short
                    token = fields[1]
                else:
                    token = fields[0]
                columns[col].append(_number(token))
                col += 1
                if col == nvars:
                    col = 0
                    got += 1
                    if got == npoints:
                        break
            if col:  # a point cut short: drop it
                for c in columns[:col]:
                    c.pop()
            plots.append(_plot(head, variables, flags, columns))
    return plots


def _header(f):
    """Read header lines up to Values:/Binary:. (None, None, None) at the end of the file."""
    head, variables, in_vars = {}, [], False
    for line in f:
        line = line.rstrip("\r\n").lstrip("﻿")
        if not line.strip():
            continue
        if line.startswith(("Values:", "Binary:")):
            return head, variables, line[:-1]
        if in_vars and line[:1] in (" ", "\t"):
            fields = line.split()
            variables.append((fields[1], fields[2] if len(fields) > 2 else ""))
            continue
        key, _, value = line.partition(":")
        if key == "Variables":
            in_vars = True
            continue
        in_vars = False
        head[key.strip()] = value.strip()
    return None, None, None


def _plot(head, variables, flags, columns):
    names = [_canon(n) for n, _ in variables]
    if names and names[0] == "time":  # LTspice marks some time points with a negative sign
        columns[0] = array.array("d", (abs(t) for t in columns[0]))
    return {"name": head.get("Plotname", ""), "flags": flags, "variables": variables,
            "data": dict(zip(names, columns))}


def _read_binary(path, enc):
    """Packed values (not what the bench asks for, kept for files written elsewhere)."""
    blob = Path(path).read_bytes()
    width = 2 if enc == "utf-16-le" else 1
    marker = "Binary:\n".encode(enc)
    start = blob.index(marker) + len(marker)
    text = blob[:start].decode(enc, errors="replace")
    head = dict((k.strip(), v.strip()) for k, _, v in (ln.partition(":") for ln in text.splitlines())
                if k.strip() and not k.startswith(("\t", " ")))
    variables = [(m[1], m[2]) for m in re.finditer(r"^[ \t]+\d+[ \t]+(\S+)[ \t]+(\S+)", text, re.M)]
    nvars, npoints = int(head["No. Variables"]), int(head["No. Points"])
    flags = head.get("Flags", "").lower().split()
    is_complex = "complex" in flags
    double = "double" in flags or is_complex or width == 1
    fmt = "<" + ("dd" * nvars if is_complex else "".join("d" if double or i == 0 else "f" for i in range(nvars)))
    columns = [[] for _ in range(nvars)]
    size = struct.calcsize(fmt)
    for p in range(npoints):
        vals = struct.unpack_from(fmt, blob, start + p * size)
        if is_complex:
            vals = [complex(vals[2 * i], vals[2 * i + 1]) for i in range(nvars)]
        for i, v in enumerate(vals):
            columns[i].append(v)
    return [_plot(head, variables, flags, columns)]


def _canon(name):
    """One spelling for a vector across simulators: v(node) and i(source), lower case."""
    n = name.lower()
    m = re.fullmatch(r"(.+)#branch", n)
    if m:
        return f"i({m[1]})"
    if n in ("time", "frequency", "freq"):
        return "frequency" if n.startswith("freq") else "time"
    if n.startswith(("v(", "i(", "ix(", "ib(", "ic(", "ie(")) or n in ("v-sweep", "i-sweep"):
        return n
    return f"v({n})"
