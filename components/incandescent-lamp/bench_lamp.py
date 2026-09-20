#!/usr/bin/env python3
"""Verify lamp.sub against published lamp data: ratings (V, I), cold resistance,
R. Elliott's measurements on a #327 (sound-au.com/articles/sinewave.htm 4.2), the
I ~ V^0.55 lamp law (J. Dunn, EDN 2016), the tungsten resistivity table it is built
on, the Draper point, the thermal response time, .ac, and the Wien-bridge demo.
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
sys.path.insert(0, str(HERE))
from bench.ltbatch import run        # noqa: E402
from fit_lamp import rho             # noqa: E402  (White-Minges polynomial, for the table check)

SUB = HERE / "lamp.sub"
ROWS, FAIL = [], 0
# preset: (Vr, Ir, Rc)
PRE = {"LAMP_327": (28, 0.040, 65.0), "LAMP_47": (6.3, 0.150, 3.9),
       "LAMP_12V40": (12, 0.040, 27.86), "LAMP_6V60": (6, 0.060, 10.0)}


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
    return run(f"* {name}\n.lib \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=600)


def main():
    # 1. static: cold R, rating, half-voltage current, #327 measured points
    body = []
    for p in PRE:
        Vr = PRE[p][0]
        body += [f"Vc_{p} c_{p} 0 1m", f"Xc_{p} c_{p} 0 {p}",
                 f"Vr_{p} r_{p} 0 {Vr}", f"Xr_{p} r_{p} 0 {p}",
                 f"Vh_{p} h_{p} 0 {Vr / 2}", f"Xh_{p} h_{p} 0 {p}"]
    body += ["I1 0 m1 4.5m", "XM1 m1 0 LAMP_327", "I2 0 m2 7.4m", "XM2 m2 0 LAMP_327",
             "I3 0 m3 10m", "XM3 m3 0 LAMP_327", "I4 0 m4 13m", "XM4 m4 0 LAMP_327",
             "V6 m6 0 0.5", "XM6 m6 0 LAMP_6V60"]
    d, _ = sim("\n".join(body), "static")
    for p, (Vr, Ir, Rc) in PRE.items():
        rc = -1e-3 / float(d[f"i(vc_{p})".lower()][0])
        ir = -float(d[f"i(vr_{p})".lower()][0])
        ih = -float(d[f"i(vh_{p})".lower()][0])
        check(f"{p}: cold R at 1 mV, ohm", rc, Rc, 0.005 * Rc)
        check(f"{p}: current at rated {Vr} V, mA (rating)", ir * 1e3, Ir * 1e3, 0.005 * Ir * 1e3)
        want = Ir * 0.5 ** 0.55
        check(f"{p}: current at Vr/2, mA (I = Ir (V/Vr)^0.55, EDN)", ih * 1e3, want * 1e3,
              0.05 * want * 1e3)
        note(f"  {p}: hot/cold ratio {Vr / Ir / rc:.2f}, I ~ V^{math.log(ih / ir) / math.log(0.5):.3f}")
    rh327 = 28 / 0.040
    rc327 = -1e-3 / float(d["i(vc_lamp_327)"][0])
    check_cmp("#327: hot/cold ratio >= 8 (about 10: Elliott 700/65, sound-au p179 'one tenth')",
              rh327 / rc327, 8, ">=")
    check_cmp("#327: hot/cold ratio <= 14", rh327 / rc327, 14, "<=")
    r45 = float(d["v(m1)"][0]) / 4.5e-3
    note(f"  #327 at 4.5 mA: {r45:.1f} ohm (Elliott 0.5 V -> 111 ohm; the point fc is fitted to)")
    r74 = float(d["v(m2)"][0]) / 7.4e-3
    check("#327: R at 7.4 mA, ohm (Elliott: 1.39 V -> 188 ohm)", r74, 1.39 / 7.4e-3, 0.08 * 188)
    # filament temperature from the simulated resistance: rho(T)/rho(298.15 K) = R/Rc
    # (the .op raw file carries no subckt-internal nodes)
    def temp(R, Rc=65.0):
        lo, hi = 298.15, 3600.0
        for _ in range(60):
            m = 0.5 * (lo + hi)
            lo, hi = (m, hi) if rho(m) / rho(298.15) < R / Rc else (lo, m)
        return 0.5 * (lo + hi)
    T10 = temp(float(d["v(m3)"][0]) / 10e-3)
    T13 = temp(float(d["v(m4)"][0]) / 13e-3)
    check_cmp("#327: filament at 13 mA above the Draper point 798 K (Elliott: glow above 13 mA)",
              T13, 798, ">=")
    note(f"  #327 filament: {T10:.0f} K at 10 mA, {T13:.0f} K at 13 mA (Elliott saw it dark in room"
         f" light at 10 mA; 798 K is the faint glow seen in darkness)")
    r6 = 0.5 / -float(d["i(v6)"][0])
    note(f"  LAMP_6V60 at 0.5 V: {r6:.2f} ohm (sound-au p179: 30 ohm, 17 mA; the point fc is fitted"
         f" to; with the #327 fc it would be 35.3 ohm)")

    # 2. thermal response: #327 at rated current, current step -10 %, 63 % of the
    #    voltage change after the instantaneous jump
    d, _ = sim("I1 0 a PWL(0 40m 0.2 40m 0.20001 36m)\nX1 a 0 LAMP_327", "tau",
               ".tran 0 0.5 0 50u")
    t, v = d["time"], d["v(a)"]
    v0 = float(np.interp(0.1999, t, v))
    vj = float(np.interp(0.20002, t, v))
    vf = float(v[-1])
    k = np.nonzero((t > 0.20002) & (v <= vj + 0.632 * (vf - vj)))[0][0]
    tau = float(t[k]) - 0.20001
    check_cmp("#327: response time at rated current (63 %), ms, >= 2 (sound-au p179:"
              " 'a few to tens of ms')", tau * 1e3, 2, ">=")
    check_cmp("#327: response time at rated current (63 %), ms, <= 50", tau * 1e3, 50, "<=")
    note(f"  #327: V {v0:.2f} -> jump {vj:.2f} -> {vf:.2f} V, time constant {tau * 1e3:.1f} ms")

    # 3. cold switch-on: peak current Vr/Rc, then settles to Ir
    d, _ = sim("V1 a 0 PWL(0 0 1u 28)\nX1 a 0 LAMP_327", "inrush", ".tran 0 0.3 0 10u")
    i = -d["i(v1)"]
    check("#327: switch-on peak current, mA (Vr/Rc = 28/65)", float(np.max(i)) * 1e3,
          28 / 65 * 1e3, 0.02 * 28 / 65 * 1e3)
    check("#327: current 0.3 s after switch-on, mA (rating)", float(i[-1]) * 1e3, 40, 0.4)

    # 4. .ac: above the thermal corner the lamp is its static resistance; at very low
    #    frequency it is the slope dV/dI of the static curve
    d, _ = sim("V1 a 0 14 AC 1\nX1 a 0 LAMP_327", "ac", ".ac list 0.001 10k")
    z = 1 / np.abs(d["i(v1)"])
    ds, _ = sim("V1 a 0 13.9\nX1 a 0 LAMP_327\nV2 b 0 14.1\nX2 b 0 LAMP_327\n"
                "V3 c 0 14\nX3 c 0 LAMP_327", "slope")
    i1, i2, i3 = (-float(ds[f"i(v{n})"][0]) for n in (1, 2, 3))
    check(".ac |Z| at 10 kHz = static V/I at 14 V, ohm", float(z[1]), 14 / i3, 0.005 * 14 / i3)
    check(".ac |Z| at 1 mHz = dV/dI at 14 V, ohm", float(z[0]), 0.2 / (i2 - i1),
          0.01 * 0.2 / (i2 - i1))

    # 5. demo: Wien-bridge oscillator, RF = 375 (Elliott: 1.39 V on the lamp, 4.16 V RMS)
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_lamp.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib lamp.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=900)
    t, vo, vn = d["time"], d["v(out)"], d["v(n)"]
    w = t >= t[-1] - 0.3
    tw, vow, vnw = t[w], vo[w], vn[w]
    rms = lambda y: math.sqrt(np.trapezoid(y * y, tw) / (tw[-1] - tw[0]))
    zc = tw[1:][(vow[:-1] < 0) & (vow[1:] >= 0)]
    f = (len(zc) - 1) / (zc[-1] - zc[0])
    f0 = 1 / (2 * math.pi * 1.6e3 * 470e-9)
    check("demo: frequency, Hz (1/(2 pi 1.6k 470n))", f, f0, 0.01 * f0)
    check("demo: output, V RMS (Elliott 4.16)", rms(vow), 4.16, 0.10 * 4.16)
    check("demo: lamp voltage, V RMS (Elliott 1.39)", rms(vnw), 1.39, 0.10 * 1.39)
    env = [float(np.max(np.abs(vo[(t >= a) & (t < a + 0.05)]))) for a in np.arange(0, t[-1] - 0.05, 0.05)]
    note(f"  demo: peak output per 50 ms, first 1 s: {' '.join(f'{e:.1f}' for e in env[:20])}")

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
