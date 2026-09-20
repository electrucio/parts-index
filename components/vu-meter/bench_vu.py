#!/usr/bin/env python3
"""Verify vu.sub against the standard volume indicator (ANSI C16.5-1942 / IEC 60268-17,
as quoted by Wikipedia and sound-au project 55): 0 VU at 1.228 V RMS, 7.5 kohm,
99 % of the reading in 300 ms, overshoot 1-1.5 %, frequency response, level
linearity, and the demo.
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

SUB = HERE / "vu.sub"
ROWS, FAIL = [], 0
VPK0 = 1.228 * math.sqrt(2)


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


def sim(body, name, analysis):
    return run(f"* {name}\n.lib \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=300)


def burst(f, vrms, t_on=0.1, t_off=10.0):
    return (f"B1 in 0 V={vrms * math.sqrt(2)}*sin(2*pi*{f}*time)*(time > {t_on})"
            f"*(time < {t_off})\nX1 in 0 d vu_meter")


def main():
    # 1. step to 0 VU (1 kHz), rise, overshoot, steady reading
    d, _ = sim(burst(1e3, 1.228), "rise", ".tran 0 1.6 0 20u")
    t, x = d["time"], d["v(d)"]
    xf = float(np.mean(x[t > 1.4]))
    check("steady reading at 1.228 V RMS, 1 kHz (0 VU), DEFL", xf, 1.0, 0.005)
    k = int(np.argmax((t > 0.1) & (x >= 0.99 * xf)))
    check("time to 99 % of the reading, ms (standard: 300 ms)", (float(t[k]) - 0.1) * 1e3, 300, 9)
    os_ = (float(np.max(x)) / xf - 1) * 100
    check_cmp("overshoot, % (standard: >= 1 %)", os_, 1.0, ">=")
    check_cmp("overshoot, % (standard: <= 1.5 %)", os_, 1.5, "<=")
    ripple = float(np.max(x[t > 1.4]) - np.min(x[t > 1.4]))
    note(f"  2 kHz ripple on the pointer at 0 VU: {ripple * 100:.4f} % of full reading")

    # 2. release: from 0 VU to silence, the same movement falls back
    d, _ = sim(burst(1e3, 1.228, 0.0, 1.0), "fall", ".tran 0 2 0 20u")
    t, x = d["time"], d["v(d)"]
    x0 = float(np.interp(0.999, t, x))
    k = int(np.argmax((t > 1.0) & (x <= 0.01 * x0)))
    note(f"  fall to 1 % after the tone stops: {(float(t[k]) - 1.0) * 1e3:.1f} ms (symmetric movement)")

    # 3. input impedance
    d, _ = sim("V1 in 0 0 AC 1\nX1 in 0 d vu_meter", "zin", ".ac list 1k")
    check("input impedance at 1 kHz, ohm (standard: 7500)", float(1 / np.abs(d["i(v1)"][0])), 7500, 1)

    # 4. level linearity (-10 VU, +3 VU) and frequency response (35 Hz, 10 kHz)
    for f, db in ((1e3, -10), (1e3, 3), (35, 0), (10e3, 0)):
        vr = 1.228 * 10 ** (db / 20)
        d, _ = sim(burst(f, vr, 0.0), f"lv{f}{db}", f".tran 0 1.5 0 {min(20e-6, 1 / (f * 50))}")
        t, x = d["time"], d["v(d)"]
        # average over whole periods of the input in the last 0.2 s
        w = t > 1.5 - math.floor(0.2 * f) / f
        xm = float(np.trapezoid(x[w], t[w]) / (t[w][-1] - t[w][0]))
        if f == 1e3:
            check(f"reading at {db:+d} VU, VU", 20 * math.log10(xm), db, 0.05)
        else:
            check(f"reading at 0 VU, {f:g} Hz, dB re 1 kHz (standard: within +-0.2 dB)",
                  20 * math.log10(xm), 0, 0.2)

    # 5. demo
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_vu.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib vu.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=300)
    t, x = d["time"], d["v(defl)"]
    check("demo: reading just before the burst ends, DEFL", float(np.interp(1.099, t, x)), 1.0, 0.02)
    note(f"  demo: peak {float(np.max(x)):.4f} at {float(t[np.argmax(x)]):.3f} s")

    w_ = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, ok in ROWS:
        if got is None:
            print(name)
        elif isinstance(tol, str):
            print(f"{name:<{w_}}  got {got:11.5g}  {tol:>4} {want:<11.5g}          {'ok' if ok else 'FAIL'}")
        else:
            print(f"{name:<{w_}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<8.3g} "
                  f"{'ok' if ok else 'FAIL'}")
    n = sum(r[1] is not None for r in ROWS)
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
