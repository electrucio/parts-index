#!/usr/bin/env python3
"""Verify ntc.sub against the datasheets: TDK K164 R/T characteristic 2904, the
Ametherm material-C multiplier table, Ametherm SL10 resistance at 100 % / 50 % of the
maximum current, TDK S236 Rmin and its resistance-versus-current graph, dissipation
constants and thermal time constants, .ac, and the inrush demo.
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

SUB = HERE / "ntc.sub"
ROWS, FAIL = [], 0
X100 = 1 / 373.15 - 1 / 298.15
# preset: R25, B, D, dth, Cth
PRE = {"SL10_10003": (10, 3058, 0, 11e-3, 0.33), "B57236S0100": (10, 2817, 0, 10e-3, 0.7),
       "B57164K0103": (10e3, 4300, -1.939e5, 7.5e-3, 0.15)}
# TDK K164 datasheet p.9, R/T characteristic 2904: RT/R25
K164 = {-40: 41.938, -20: 11.466, 0: 3.5563, 50: 0.33363, 85: 0.089928, 100: 0.054941,
        125: 0.026006, 150: 0.013321}
# Ametherm R/T multiplier table, material C
AMC = {0: 2.500, 50: 0.454, 100: 0.1258, 150: 0.0463}
# TDK S236 p.9, B57236S0100 resistance vs current, read off the graph (README)
S236_RI = {1.2: 0.749, 1.5: 0.556, 2.0: 0.379, 2.5: 0.281, 3.0: 0.220}


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
    return run(f"* {name}\n.lib \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=300)


def temp_of(R, p):
    """body temperature (K) from resistance, inverting the preset's R/T law"""
    R25, B, D, _, _ = PRE[p]
    lo, hi = 150.0, 700.0
    for _ in range(80):
        m = 0.5 * (lo + hi)
        x = 1 / m - 1 / 298.15
        r = R25 * math.exp(B * x + D * x * (x - X100))
        lo, hi = (m, hi) if r > R else (lo, m)
    return 0.5 * (lo + hi)


def main():
    # 1. zero-power R/T (1 mV, self-heating negligible)
    body = []
    for T in K164:
        body += [f"V_k{T + 100} k{T + 100} 0 1m", f"X_k{T + 100} k{T + 100} 0 B57164K0103 Ta={T}"]
    for T in AMC:
        body += [f"V_a{T} a{T} 0 1m", f"X_a{T} a{T} 0 SL10_10003 Ta={T}"]
    body += ["V_k25 k25 0 1m", "X_k25 k25 0 B57164K0103 Ta=25", "V_a25 a25 0 1m",
             "X_a25 a25 0 SL10_10003 Ta=25"]
    d, _ = sim("\n".join(body), "rt")
    r = lambda n: -1e-3 / float(d[f"i(v_{n})"][0])
    for T, want in K164.items():
        check(f"B57164K0103: R({T} C)/R25 (TDK R/T 2904, K164 p.9)", r(f"k{T + 100}") / r("k25"),
              want, 0.025 * want)
    b = math.log(r("k25") / r("k200")) / (1 / 298.15 - 1 / 373.15)
    check("B57164K0103: B25/100, K (K164 p.3: 4300 K +-3 %)", b, 4300, 4.3)
    for T, want in AMC.items():
        check(f"SL10_10003: R({T} C)/R25 (Ametherm material C table)", r(f"a{T}") / r("a25"),
              want, 0.05 * want)

    # 2. self-heated resistance at DC current (still air, 25 C)
    body = ["I1 0 s1 3", "X1 s1 0 SL10_10003", "I2 0 s2 1.5", "X2 s2 0 SL10_10003"]
    for k, I in enumerate(list(S236_RI) + [3.5]):
        body += [f"I_t{k} 0 t{k} {I}", f"X_t{k} t{k} 0 B57236S0100"]
    d, _ = sim("\n".join(body), "selfheat")
    check("SL10_10003: R at 100 % Imax (3 A), ohm (Ametherm 0.26; +-20 %)",
          float(d["v(s1)"][0]) / 3, 0.26, 0.2 * 0.26)
    check("SL10_10003: R at 50 % Imax (1.5 A), ohm (Ametherm 0.57; +-20 %)",
          float(d["v(s2)"][0]) / 1.5, 0.57, 0.2 * 0.57)
    Tb = temp_of(float(d["v(s1)"][0]) / 3, "SL10_10003") - 273.15
    note(f"  SL10 body at 3 A: {Tb:.0f} C (Ametherm: 151 C; with 11 mW/C and beta 3058 K the "
         f"datasheet numbers are not mutually consistent, README)")
    for k, (I, want) in enumerate(S236_RI.items()):
        check(f"B57236S0100: R at {I} A, ohm (S236 p.9 graph; +-10 %)",
              float(d[f"v(t{k})"][0]) / I, want, 0.10 * want)
    k = len(S236_RI)
    note(f"  B57236S0100 at Imax 3.5 A: {float(d[f'v(t{k})'][0]) / 3.5:.3f} ohm "
         f"(Rmin 0.180, the point B is fitted to)")

    # 3. dissipation constant: K164 at 2 mA, dth = P/(T - Ta)
    d, _ = sim("I1 0 a 2m\nX1 a 0 B57164K0103", "dth")
    R = float(d["v(a)"][0]) / 2e-3
    P = 2e-3 ** 2 * R
    check("B57164K0103: dissipation constant P/dT at 2 mA, mW/K (K164 p.2: 7.5)",
          P / (temp_of(R, "B57164K0103") - 298.15) * 1e3, 7.5, 0.075)

    # 4. thermal cooling time constant: heat, then sense with a small current;
    #    63.2 % of the temperature drop
    for p, tau_ds, Ih, Is in (("B57164K0103", 20, 4e-3, 10e-6), ("B57236S0100", 70, 2.0, 1e-3),
                              ("SL10_10003", 30, 2.0, 1e-3)):
        tend = 6 * tau_ds
        d, _ = sim(f"I1 0 a PWL(0 {Ih} {tend / 2} {Ih} {tend / 2 + 1e-3} {Is})\nX1 a 0 {p}",
                   f"tau_{p}", f".tran 0 {tend} 0 {tau_ds / 200}")
        t, v = d["time"], d["v(a)"]
        i_ = np.where(t <= tend / 2, Ih, Is)
        T = np.array([temp_of(vv / ii, p) for vv, ii in zip(v, i_)])
        w = t > tend / 2 + 2e-3
        T0, Tend = float(T[w][0]), 298.15
        k = int(np.argmax(T[w] <= Tend + 0.368 * (T0 - Tend)))
        tau = float(t[w][k]) - tend / 2
        check(f"{p}: thermal cooling time constant, s (datasheet {tau_ds} s)", tau, tau_ds,
              0.03 * tau_ds)

    # 5. .ac: well above the thermal corner the NTC is its static V/I
    d, _ = sim("I1 0 a 2m AC 1\nX1 a 0 B57164K0103", "ac", ".ac list 1k")
    ds, _ = sim("I1 0 a 2m\nX1 a 0 B57164K0103", "acop")
    check(".ac |Z| of B57164K0103 at 1 kHz = static V/I at 2 mA, ohm", float(np.abs(d["v(a)"][0])),
          float(ds["v(a)"][0]) / 2e-3, 0.002 * float(ds["v(a)"][0]) / 2e-3)

    # 6. demo: inrush into a 470 uF half-wave capacitor-input rectifier, switched on at the crest
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_ntc.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib ntc.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=300)
    t, i = d["time"], -d["i(bac)"]
    ipk = float(np.max(np.abs(i)))
    vd = 1.8 * 0.025852 * math.log(ipk / 10e-9) + 0.03 * ipk      # the demo's rectifier model
    want = (169.7 - vd) / 10.0
    check("demo: first inrush peak, A ((169.7 V - Vd)/R25)", ipk, want, 0.03 * want)
    e = float(np.trapezoid(np.abs(d["v(l)"] - d["v(ln)"]) * np.abs(i), t))
    note(f"  demo: energy into the NTC in 0.3 s {e:.2f} J (SL10: 17 J max recommended); "
         f"line current at 0.3 s {float(np.max(np.abs(i[t > 0.25]))):.2f} A peak")

    w_ = max(len(r_[0]) for r_ in ROWS)
    for name, got, want, tol, ok in ROWS:
        if got is None:
            print(name)
        elif isinstance(tol, str):
            print(f"{name:<{w_}}  got {got:11.5g}  {tol:>4} {want:<11.5g}          {'ok' if ok else 'FAIL'}")
        else:
            print(f"{name:<{w_}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<8.3g} "
                  f"{'ok' if ok else 'FAIL'}")
    n = sum(r_[1] is not None for r_ in ROWS)
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
