#!/usr/bin/env python3
"""Verify ldr.sub: the static power law and dark floor, the GL55 presets against their
datasheet table (R10 range, gamma, 10-second dark resistance, rise and decay times),
attack/decay behaviour, the light-history memory, .ac, .step and the demo.
Run with the shell sandbox off. Exit 1 on any failure."""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bench.ltbatch import run        # noqa: E402

SUB = HERE / "ldr.sub"
ROWS, FAIL = [], 0
# GL55 manual p.2: R10 range (ohm), dark resistance min (ohm), gamma, rise, decay (s)
GL55 = {"GL5516": (5e3, 10e3, 0.5e6, 0.5, 30e-3, 30e-3),
        "GL5528": (10e3, 20e3, 1e6, 0.6, 20e-3, 30e-3),
        "GL5537_1": (20e3, 30e3, 2e6, 0.6, 20e-3, 30e-3),
        "GL5539": (50e3, 100e3, 5e6, 0.8, 20e-3, 30e-3)}


def check(name, got, want, tol):
    global FAIL
    ok = abs(got - want) <= tol
    FAIL += not ok
    ROWS.append((name, got, want, tol, ok))


def check_ge(name, got, lim):
    global FAIL
    ok = got >= lim
    FAIL += not ok
    ROWS.append((name, got, lim, ">=", ok))


def check_lt(name, got, lim):
    global FAIL
    ok = got < lim
    FAIL += not ok
    ROWS.append((name, got, lim, "<", ok))


def sim(body, name, analysis=".op"):
    return run(f"* {name}\n.include \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=180)


def r_of(d, src, idx=0):
    return -1 / float(d[f"i({src})"][idx])


def main():
    # 1. static law of the bare ldr: R = R10 (E/10)^-gamma, dark floor Rdark
    lux = [0, 0.1, 1, 10, 100, 1000]
    body = "\n".join(f"V{k} a{k} 0 1\nX{k} a{k} 0 l{k} ldr R10=14.14k gamma=0.6 Rdark=10Meg\n"
                     f"VL{k} l{k} 0 {E}" for k, E in enumerate(lux))
    d, _ = sim(body, "law")
    R10, g, Rd = 14.14e3, 0.6, 10e6
    eth = (Rd / R10) ** (-1 / g)
    for k, E in enumerate(lux):
        want = R10 * (E / 10 + eth) ** (-g)       # exact model incl. the thermal floor
        check(f"ldr static R at {E:g} lux, ohm", r_of(d, f"v{k}"), want, 1e-3 * want)
    check("  (power law alone at 100 lux, ohm)", r_of(d, "v4"), R10 * 10 ** -g, 2e-3 * R10 * 10 ** -g)

    # 2. GL55 presets: R10 inside the table range, gamma = lg(R10/R100)
    body = []
    for j, p in enumerate(GL55):
        for k, E in enumerate((10, 100)):
            body += [f"V{j}_{k} a{j}_{k} 0 1", f"X{j}_{k} a{j}_{k} 0 l{j}_{k} {p}",
                     f"VL{j}_{k} l{j}_{k} 0 {E}"]
    d, _ = sim("\n".join(body), "gl55")
    for j, (p, (lo, hi, rdmin, gam, tr, tf)) in enumerate(GL55.items()):
        r10, r100 = r_of(d, f"v{j}_0"), r_of(d, f"v{j}_1")
        mid = math.sqrt(lo * hi)
        check(f"{p}: R at 10 lux (table {lo / 1e3:g}-{hi / 1e3:g}k), kohm", r10 / 1e3, mid / 1e3,
              min(mid - lo, hi - mid) / 1e3)
        check(f"{p}: gamma = lg(R10/R100) (table {gam})", math.log10(r10 / r100), gam, 0.01)

    # 3. GL55 dynamics: rise to 63 % conductance at 10 lux from dark, decay to R10*e,
    #    dark resistance 10 s after the 10 lux light is shut off
    for p, (lo, hi, rdmin, gam, tr, tf) in GL55.items():
        d, _ = sim(f"V1 a 0 1\nX1 a 0 l {p}\nVL l 0 PWL(0 0 1m 0 1.001m 10 400m 10 400.001m 0)",
                   f"dyn_{p}", ".tran 0 800m 0 20u")
        t, G = d["time"], -d["i(v1)"]
        Gf, G0 = float(np.interp(0.399, t, G)), float(G[0])
        t63 = float(t[np.argmax(G >= G0 + 0.632 * (Gf - G0))]) - 1.001e-3
        R = 1 / G
        r10 = 1 / Gf
        tdec = float(t[np.argmax((t > 0.4) & (R >= r10 * math.e))]) - 0.400001
        check(f"{p}: rise time (63 % conductance), ms", t63 * 1e3, tr * 1e3, 0.05 * tr * 1e3)
        check(f"{p}: decay time (conductance to 37 %), ms", tdec * 1e3, tf * 1e3, 0.05 * tf * 1e3)
        d, _ = sim(f"V1 a 0 1\nX1 a 0 l {p}\nVL l 0 PWL(0 10 1m 10 1.001m 0)", f"dark_{p}",
                   ".tran 0 10.001 0 5m")
        check_ge(f"{p}: R 10 s after 10 lux off, Mohm (table min)", r_of(d, "v1", -1) / 1e6, rdmin / 1e6)

    # 4. faster when bright: GL5528 rise time at 100 lux vs 10 lux (same measurement)
    d, _ = sim("V1 a 0 1\nX1 a 0 l GL5528\nVL l 0 PWL(0 0 1m 0 1.001m 100)", "bright",
               ".tran 0 300m 0 10u")
    t, G = d["time"], -d["i(v1)"]
    Gf, G0 = float(G[-1]), float(G[0])
    t63b = float(t[np.argmax(G >= G0 + 0.632 * (Gf - G0))]) - 1.001e-3
    check_lt("GL5528: rise time at 100 lux < at 10 lux (20 ms), ms", t63b * 1e3, 20)
    ROWS.append((f"  (rise at 100 lux: {t63b * 1e3:.2f} ms; decay is slower than rise at the "
                 f"same level: 30 vs 20 ms)", None, None, None, True))

    # 5. light-history memory: dark adapted (hist=0) vs light adapted (hist=1) at 10 lux,
    #    and the drift of an adapting cell (thist shortened to 1 s for the test)
    d, _ = sim("V1 a 0 1\nX1 a 0 l GL5528 hist=1\nVL l 0 10\n"
               "V2 b 0 1\nX2 b 0 l GL5528 hist=0", "hist")
    check("GL5528: R(light adapted)/R(dark adapted) = kLH", r_of(d, "v1") / r_of(d, "v2"), 1.2, 1e-4)
    d, _ = sim("V1 a 0 1\nX1 a 0 l ldr hist=0 thist=1\nVL l 0 1000", "adapt", ".tran 0 5 0 1m")
    h = 1000 / 1300 * (1 - math.exp(-5))
    want = 14.14e3 * (100 + (10e6 / 14.14e3) ** (-1 / 0.6)) ** -0.6 * (1 + 0.2 * h) / 1.2
    check("ldr hist=0, 5 s at 1000 lux, thist=1 s: R, ohm", r_of(d, "v1", -1), want, 1e-3 * want)

    # 6. .ac: small-signal impedance of the cell at 10 lux equals its resistance
    d, _ = sim("V1 a 0 AC 1\nX1 a 0 l GL5528\nVL l 0 10", "ac", ".ac dec 3 100 10k")
    z = 1 / np.abs(d["i(v1)"])
    check(".ac |Z| at 10 lux (GL5528), kohm, max error", float(np.max(np.abs(z - 14.14e3))) / 1e3, 0,
          0.01)

    # 7. .step over the light level
    d, _ = sim(".param E=1\nV1 a 0 1\nX1 a 0 l GL5528\nVL l 0 {E}\n.step param E list 10 100",
               "step")
    check(".step E=10: R, kohm", r_of(d, "v1", 0) / 1e3, 14.14, 0.02)
    check(".step E=100: R, kohm", r_of(d, "v1", -1) / 1e3, 14.14 * 10 ** -0.6, 0.02)

    # 8. demo: light-controlled attenuator
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_ldr.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib ldr.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=180)
    t, v = d["time"], d["v(out)"]

    def amp(t0, t1):
        w = (t > t0) & (t < t1)
        return float((np.max(v[w]) - np.min(v[w])) / 2)
    rl = 1e6
    dark = 1 / (1 / 10e6 + 1 / rl)
    lit = 1 / (1 / (14.14e3 * 10 ** -0.6) + 1 / rl)
    check("demo: amplitude in the dark, V", amp(0.01, 0.045), dark / (10e3 + dark), 0.01)
    check("demo: amplitude at 100 lux, V", amp(0.25, 0.295), lit / (10e3 + lit), 0.005)
    a1, a2 = amp(0.30, 0.31), amp(0.79, 0.80)
    check_lt("demo: slow recovery after the light: amplitude at 305 ms < at 795 ms", a1, a2)

    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, ok in ROWS:
        if got is None:
            print(name)
        elif isinstance(tol, str):
            print(f"{name:<{w}}  got {got:11.5g}  {tol:>4} {want:<11.5g}          {'ok' if ok else 'FAIL'}")
        else:
            print(f"{name:<{w}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<8.3g} "
                  f"{'ok' if ok else 'FAIL'}")
    n = sum(r[1] is not None for r in ROWS)
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
