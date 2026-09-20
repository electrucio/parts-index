#!/usr/bin/env python3
"""Verify vactrol.sub against the datasheets: cell resistance vs LED current, LED
forward voltage, turn-on (63 % of final conductance), turn-off (time to a given
resistance), the 10-second off resistance, the light-history memory, a reversed LED,
.ac, the optical-tremolo demo, and that its ldr_cell core is the one in ../ldr/ldr.sub.
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

SUB = HERE / "vactrol.sub"
ROWS, FAIL = [], 0
CURVE_TOL = math.log(1.6)     # times read off small log-log/log-lin plots: factor 1.6

# datasheet data, README "Provenance"
P = {
    "VTL5C1": dict(static=[(1, 20e3), (10, 600), (40, 200)], i_on=40, t63=2.5e-3,
                   off_curve=[(10e3, 11e-3), (100e3, 21e-3)], off_max=(100e3, 35e-3),
                   r10s_min=50e6, vf=(20, 1.65, 0.03)),
    "VTL5C3": dict(static=[(1, 30e3), (10, 5e3), (40, 1.5e3)], i_on=40, t63=2.5e-3,
                   off_curve=[(10e3, 6e-3), (100e3, 16e-3), (1e6, 110e-3)],
                   off_max=(100e3, 35e-3), r10s_min=10e6, vf=(20, 1.65, 0.03)),
    "VTL5C4": dict(static=[(1, 1.2e3), (10, 125), (40, 75)], i_on=40, t63=6.0e-3,
                   off_curve=[(1e3, 68e-3), (10e3, 340e-3), (100e3, 760e-3)],
                   off_max=(100e3, 1.5), r10s_min=400e6, vf=(20, 1.65, 0.03)),
    "VTL5C6": dict(static=[(0.5, 60e3), (5, 6e3)], i_on=16, t63=3.5e-3,
                   off_curve=[(1e6, 50e-3)], off_max=None, r10s_min=1e6, vf=(16, 1.99, 0.03)),
    "NSL32SR2": dict(static=[(0.1, 1800), (1, 247), (10, 58.3), (20, 41.1), (40, 31.9)], i_on=20,
                     t63=5e-3, off_curve=[(100e3, 80e-3)], off_max=None, r10s_min=1e6,
                     vf=None),
}


def check(name, got, want, tol):
    global FAIL
    ok = abs(got - want) <= tol
    FAIL += not ok
    ROWS.append((name, got, want, tol, ok))


def check_cmp(name, got, lim, op):
    global FAIL
    ok = got >= lim if op == ">=" else got <= lim
    FAIL += not ok
    ROWS.append((name, got, lim, op, ok))


def note(text):
    ROWS.append((text, None, None, None, True))


def sim(body, name, analysis=".op"):
    return run(f"* {name}\n.include \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=240)


def main():
    # 0. the core is a verbatim copy of ../ldr/ldr.sub
    begin, end = "* >>> ldr_cell", "* <<< ldr_cell"
    a = (HERE.parent / "ldr" / "ldr.sub").read_text()
    b = SUB.read_text()
    same = a[a.index(begin):a.index(end)] == b[b.index(begin):b.index(end)]
    check("ldr_cell block identical to components/ldr/ldr.sub", float(same), 1, 0)

    # 1. static: cell resistance at the datasheet LED currents (+ LED VF), one .op
    body = []
    for p, dd in P.items():
        for k, (i, _) in enumerate(dd["static"]):
            body += [f"I_{p}_{k} 0 a_{p}_{k} {i}m", f"X_{p}_{k} a_{p}_{k} 0 c_{p}_{k} 0 {p}",
                     f"V_{p}_{k} c_{p}_{k} 0 1"]
        if dd["vf"]:
            body += [f"If_{p} 0 f_{p} {dd['vf'][0]}m", f"Xf_{p} f_{p} 0 g_{p} 0 {p}",
                     f"Vg_{p} g_{p} 0 0"]
    d, _ = sim("\n".join(body), "static")
    for p, dd in P.items():
        for k, (i, rw) in enumerate(dd["static"]):
            r = -1 / float(d[f"i(v_{p}_{k})".lower()][0])
            check(f"{p}: R at {i:g} mA, ohm", r, rw, 0.06 * rw)
        if dd["vf"]:
            i, vf, tol = dd["vf"]
            check(f"{p}: LED VF at {i} mA, V", float(d[f"v(f_{p})".lower()][0]), vf, tol)
    # NSL-32SR2: table limits
    d, _ = sim("I1 0 a 20m\nX1 a 0 c 0 NSL32SR2\nV1 c 0 1\nI2 0 b 1m\nX2 b 0 e 0 NSL32SR2\n"
               "V2 e 0 1", "nsl")
    note(f"  NSL32SR2 at 20 mA: {-1 / float(d['i(v1)'][0]):.1f} ohm; the table gives 40 ohm max, "
         f"its own typical curve 41.1 ohm (checked above against the curve)")
    check_cmp("NSL32SR2: VF at 20 mA <= 2.5 V (table max)", float(d["v(a)"][0]), 2.5, "<=")
    note(f"  NSL32SR2 at 1 mA: {-1 / float(d['i(v2)'][0]):.0f} ohm; the table's 140 ohm typ. "
         f"disagrees with its own curve (247 ohm), the fit follows the curve")

    # 2. dynamics: turn-on 63 % and turn-off crossings; 10-second off resistance
    for p, dd in P.items():
        i_on = dd["i_on"]
        tend = 0.2 if dd["off_curve"][-1][1] < 0.2 else 2.0
        d, _ = sim(f"I1 0 a PWL(0 0 1m 0 1.001m {i_on}m 100m {i_on}m 100.001m 0)\n"
                   f"X1 a 0 c 0 {p}\nV1 c 0 1", f"dyn_{p}", f".tran 0 {100e-3 + tend} 0 5u")
        t, G = d["time"], -d["i(v1)"]
        Gf, G0 = float(np.interp(0.0999, t, G)), float(G[0])
        t63 = float(t[np.argmax(G >= G0 + 0.632 * (Gf - G0))]) - 1.001e-3
        check(f"{p}: turn-on to 63 % conductance at {i_on} mA, ms", t63 * 1e3, dd["t63"] * 1e3,
              0.05 * dd["t63"] * 1e3)
        R = 1 / G

        def t_reach(L):
            # first sample strictly after the LED current has reached zero (100.001 ms)
            hit = np.nonzero((t > 0.100001) & (R >= L))[0]
            return max(float(t[hit[0]]) - 0.100001, 1e-9) if len(hit) else float("inf")
        for L, tw in dd["off_curve"]:
            tt = t_reach(L)
            check(f"{p}: turn-off to {L / 1e3:g}k (curve read {tw * 1e3:g} ms), log ratio",
                  math.log(tt / tw) if math.isfinite(tt) else float("inf"), 0, CURVE_TOL)
            ROWS[-1] = (ROWS[-1][0] + f" -> {tt * 1e3:.1f} ms (max R {float(np.max(R)):.3g})",) \
                + ROWS[-1][1:]
        if dd["off_max"]:
            L, tmax = dd["off_max"]
            tt = t_reach(L)
            check_cmp(f"{p}: turn-off to {L / 1e3:g}k <= datasheet max, ms", tt * 1e3, tmax * 1e3, "<=")
        d, _ = sim(f"I1 0 a PWL(0 {i_on}m 1m {i_on}m 1.001m 0)\nX1 a 0 c 0 {p}\nV1 c 0 1",
                   f"r10_{p}", ".tran 0 10.001 0 5m")
        check_cmp(f"{p}: R 10 s after the LED is off, Mohm (datasheet min)",
                  -1 / float(d["i(v1)"][-1]) / 1e6, dd["r10s_min"] / 1e6, ">=")

    # 3. light-history memory: light-adapted cell (hist=1) is kLH times higher
    d, _ = sim("I1 0 a 10m\nX1 a 0 c 0 VTL5C1 hist=1\nV1 c 0 1\n"
               "I2 0 b 10m\nX2 b 0 e 0 VTL5C1 hist=0\nV2 e 0 1", "hist")
    check("VTL5C1: R(light adapted)/R(dark adapted) at 10 mA (kLH, type 1)",
          (-1 / float(d["i(v1)"][0]) - 154.7) / (-1 / float(d["i(v2)"][0]) - 154.7), 1.5, 1e-3)

    # 4. reversed LED (2 V across it backwards): no light, cell stays dark
    d, _ = sim("V0 0 a 2\nX1 a 0 c 0 VTL5C3\nV1 c 0 1", "rev")
    check_cmp("VTL5C3: reversed LED, cell resistance, Mohm", -1 / float(d["i(v1)"][0]) / 1e6, 30, ">=")

    # 5. .ac: small-signal impedance of the cell at 10 mA equals its resistance
    d, _ = sim("I1 0 a 10m\nX1 a 0 c 0 VTL5C1\nV1 c 0 AC 1", "ac", ".ac dec 3 20 20k")
    z = 1 / np.abs(d["i(v1)"])
    check(".ac |Z| of VTL5C1 at 10 mA, ohm (max error vs 600)", float(np.max(np.abs(z - 600.1))), 0, 1)

    # 6. demo: optical tremolo (VTL5C3), last 0.6 s
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_vactrol.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib vactrol.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=240)
    t, v, iled = d["time"], d["v(out)"], d["i(rled)"]
    env = []
    for k in range(int(0.4 / (1 / 440)), int(1.0 / (1 / 440)) - 1):
        w = (t >= k / 440) & (t < (k + 1) / 440)
        env.append((k / 440 + 0.5 / 440, float(np.max(np.abs(v[w])))))
    et, ev = np.array(env).T
    ipk = float(np.max(iled))
    rmin = 30.58e3 * (ipk * 1e3) ** -0.8087
    want_min = 0.5 * rmin / (22e3 + rmin)
    check("demo: LED peak current, mA ((5 - VF)/220)", ipk * 1e3, (5 - 1.64) / 220 * 1e3, 0.3)
    check("demo: envelope minimum, V (static R at the LED peak)", float(np.min(ev)), want_min,
          0.2 * want_min)
    check_cmp("demo: envelope maximum, V (cell dark between LED peaks)", float(np.max(ev)), 0.3, ">=")
    note(f"  demo depth: {20 * math.log10(np.max(ev) / np.min(ev)):.1f} dB")

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
