#!/usr/bin/env python3
"""Verify neon.sub against the Chicago Miniature Lighting (CML) neon indicator table,
GE's glow-lamp equivalent circuit (GE Glow Lamp Manual 1965, Fig. 1.5) and
relaxation-oscillator formula (Fig. 2.4), and W. G. Miller's handbook (ionization
time, maintaining voltage): breakdown, glow line, hysteresis, extinction, AC
operation, ionization time, the relaxation oscillator and the demo.
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

SUB = HERE / "neon.sub"
ROWS, FAIL = [], 0
# preset: (Vb, Ve, Ri, CML max DC breakdown, CML max AC breakdown (V RMS), design mA)
PRE = {"NE2": (75, 55, 5.5e3, 90, 65, 0.6), "NE2E": (75, 55.5, 4e3, 90, 65, 0.7),
       "NE2H": (110, 60, 2.5e3, 135, 95, 1.9)}
IMIN = 100e-6


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


def period_formula(Vs, R, C, Vb, Ve, Ri):
    """GE Fig. 2.4 charge time R C ln((Vs - Vx)/(Vs - Vb)), plus the discharge of C
    through the glowing lamp (GE Fig. 1.5 circuit: Ve + Ri) while the supply still feeds
    it through R: time constant (R || Ri) C towards Vinf = (Vs Ri + Ve R)/(R + Ri),
    from Vb down to the extinguishing voltage Vx = Ve + Ri Imin."""
    Vx = Ve + Ri * IMIN
    Vinf = (Vs * Ri + Ve * R) / (R + Ri)
    return (R * C * math.log((Vs - Vx) / (Vs - Vb))
            + R * Ri / (R + Ri) * C * math.log((Vb - Vinf) / (Vx - Vinf)))


def main():
    for p, (Vb, Ve, Ri, bdc, bac, idz) in PRE.items():
        # 1. DC breakdown: 0 -> 1.5 Vb in 1 s through 100k; strike = lamp voltage
        #    just before the current exceeds 1 uA
        d, _ = sim(f"V1 a 0 PWL(0 0 1 {1.5 * Vb})\nR1 a b 100k\nX1 b 0 {p}", f"bd_{p}",
                   ".tran 0 1 0 100u")
        t, vb, i = d["time"], d["v(b)"], d["i(r1)"]
        k = int(np.argmax(i > 1e-6))
        vs = float(vb[k - 1])
        check_cmp(f"{p}: DC breakdown, V, <= CML max {bdc} VDC", vs, bdc, "<=")
        note(f"  {p}: strikes at {vs:.2f} V; then glows at {float(vb[-1]):.2f} V, "
             f"{float(i[-1]) * 1e3:.3f} mA")

        # 2. glow line: V = Ve + Ri I (GE Fig. 1.5) at 0.5x, 1x, 1.5x the design current;
        #    a current source first charges the lamp to Vb, it strikes, then settles
        for f in (0.5, 1.0, 1.5):
            I = f * idz * 1e-3
            d, _ = sim(f"I1 0 a {I}\nX1 a 0 {p}\nC1 a 0 1n", f"gl_{p}", ".tran 0 20m 0 10u")
            check(f"{p}: glow voltage at {I * 1e3:.2f} mA, V (GE: {Ve} + {Ri / 1e3:g}k I)",
                  float(d["v(a)"][-1]), Ve + Ri * I, 0.002 * (Ve + Ri * I))

        # 3. AC: at the CML maximum AC breakdown (V RMS), through a resistor setting the
        #    design current, every lamp must light on both half cycles
        Rs = (bac * math.sqrt(2) * 0.8 - Ve) / (idz * 1e-3)
        d, _ = sim(f"V1 a 0 SINE(0 {bac * math.sqrt(2)} 60)\nR1 a b {Rs:.0f}\nX1 b 0 {p}",
                   f"ac_{p}", ".tran 0 100m 0 10u")
        t, i = d["time"], d["i(r1)"]
        w = t > 1 / 60
        pos = np.sum(np.diff((i[w] > 5e-6).astype(int)) == 1)
        neg = np.sum(np.diff((i[w] < -5e-6).astype(int)) == 1)
        ncyc = (0.1 - 1 / 60) * 60          # whole cycles after the first
        check(f"{p}: strikes per positive half-cycle at {bac} V RMS (CML max AC breakdown)",
              pos / ncyc, 1, 0.2)
        check(f"{p}: strikes per negative half-cycle at {bac} V RMS", neg / ncyc, 1, 0.2)

    # 4. NE-2 maintaining voltage at 0.5 mA (Miller p.26: NE-2 class 50-60 V)
    d, _ = sim("I1 0 a 0.5m\nX1 a 0 NE2\nC1 a 0 1n", "m05", ".tran 0 20m 0 10u")
    v05 = float(d["v(a)"][-1])
    check_cmp("NE2: maintaining voltage at 0.5 mA >= 50 V (Miller p.26: 50-60 V)", v05, 50, ">=")
    check_cmp("NE2: maintaining voltage at 0.5 mA <= 60 V", v05, 60, "<=")

    # 5. hysteresis: 65 V through 10k never struck = dark; struck by a 100 V pulse = lit
    d, _ = sim("V1 a 0 65\nR1 a b 10k\nX1 b 0 NE2\n"
               "V2 c 0 PWL(0 65 1m 65 1.01m 100 2m 100 2.01m 65)\nR2 c e 10k\nX2 e 0 NE2",
               "hyst", ".tran 0 20m 0 10u")
    check_cmp("NE2: 65 V via 10k, never struck: current, uA (dark)", float(d["i(r1)"][-1]) * 1e6,
              0.01, "<=")
    want = (65 - 55) / (10e3 + 5.5e3)
    check("NE2: 65 V via 10k after a 100 V pulse: current, mA (lit, (65-55)/15.5k)",
          float(d["i(r2)"][-1]) * 1e3, want * 1e3, 0.005 * want * 1e3)

    # 6. extinction: lit at 1 mA, then the supply falls so the lamp could carry only
    #    50 uA < Imin: it goes out (no current at all)
    d, _ = sim("V1 a 0 PWL(0 100 5m 100 5.1m 57)\nR1 a b 36k\nX1 b 0 NE2", "ext",
               ".tran 0 20m 0 10u")
    t, i = d["time"], d["i(r1)"]
    check_cmp("NE2: lit before the drop, mA", float(np.interp(4e-3, t, i)) * 1e3, 0.5, ">=")
    check_cmp("NE2: current 10 ms after the supply drops below the sustaining level, uA",
              abs(float(i[-1])) * 1e6, 0.01, "<=")

    # 7. ionization time: 1.3 Vb applied through 10k; time to 90 % of the final current
    #    < 50 us (Miller p.7)
    d, _ = sim("V1 a 0 PWL(0 0 1u 97.5)\nR1 a b 10k\nX1 b 0 NE2", "ion", ".tran 0 200u 0 0.1u")
    t, i = d["time"], d["i(r1)"]
    k = int(np.argmax(i >= 0.9 * float(i[-1])))
    check_cmp("NE2: ionization time at 1.3 Vb (to 90 % current), us, <= 50 (Miller p.7)",
              float(t[k]) * 1e6, 50, "<=")

    # 8. relaxation oscillator: 150 V, 2.2 Meg, 0.47 uF (and 1 Meg / 0.1 uF)
    for R, C in ((2.2e6, 0.47e-6), (1e6, 0.1e-6)):
        # the supply rises from 0 (as a real one does): with a DC source at t = 0 the
        # .op may start the lamp lit
        d, _ = sim(f"V1 a 0 PWL(0 0 1m 150)\nR1 a b {R}\nC1 b 0 {C}\nX1 b 0 NE2", "relax",
                   f".tran 0 {40 * R * C} 0 {R * C / 2000}")
        t, v = d["time"], d["v(b)"]
        w = t > 10 * R * C
        dv = np.diff(v[w])
        pk = t[w][1:-1][(dv[:-1] > 0) & (dv[1:] <= 0)]
        T = float(np.mean(np.diff(pk)))
        want = period_formula(150, R, C, 75, 55, 5.5e3)
        check(f"NE2 relaxation osc. {R / 1e6:g} Meg / {C * 1e6:g} uF: period, ms (GE Fig. 2.4"
              f" + glow discharge)", T * 1e3, want * 1e3, 0.02 * want * 1e3)
        note(f"  sawtooth {float(np.min(v[w])):.2f} .. {float(np.max(v[w])):.2f} V; GE formula "
             f"alone {R * C * math.log((150 - 55.55) / 75) * 1e3:.1f} ms")

    # 9. .ac of a dark lamp: shunt capacitance only
    d, _ = sim("V1 a 0 0 AC 1\nX1 a 0 NE2", "acdark", ".ac list 1k")
    check(".ac dark NE2 at 1 kHz: |Y|, S (0.5 pF + 100 G)", float(np.abs(d["i(v1)"][0])),
          math.hypot(2 * math.pi * 1e3 * 0.5e-12, 1e-11), 1e-12)

    # 10. demo: neon LFO
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_neon.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib neon.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=300)
    t, v = d["time"], d["v(saw)"]
    w = t > 1
    dv = np.diff(v[w])
    pk = t[w][1:-1][(dv[:-1] > 0) & (dv[1:] <= 0)]
    T = float(np.mean(np.diff(pk)))
    want = period_formula(150, 2.2e6, 0.47e-6, 75, 55, 5.5e3)
    check("demo: LFO period, ms", T * 1e3, want * 1e3, 0.02 * want * 1e3)
    note(f"  demo: {1 / T:.2f} Hz sawtooth, {float(np.min(v[w])):.1f} .. {float(np.max(v[w])):.1f} V")

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
