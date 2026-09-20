#!/usr/bin/env python3
"""Verify ecap.sub against Nichicon (UPW, UVR) and Cornell Dubilier (381LX) datasheet
numbers and the CDE application guide: capacitance and ESR at 120 Hz, impedance at
100 kHz and ESR at 20 kHz, the low-temperature impedance, the falling ESR(f), the
low-temperature impedance ratios, leakage at rated voltage, dielectric absorption,
the self-resonance, and the HT-supply demo.
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

SUB = HERE / "ecap.sub"
ROWS, FAIL = [], 0
W120 = 2 * math.pi * 120
# preset: C, Vr, ESR120 (tan d / wC or CDE table), HF point (f, kind, value), leakage limit
PRE = {
    "UPW1V102MHD": (1000e-6, 35, 0.12 / (W120 * 1000e-6), (100e3, "Z", 0.030), 1050e-6),
    "UPW1H471MHD": (470e-6, 50, 0.10 / (W120 * 470e-6), (100e3, "Z", 0.060), 705e-6),
    "UVR2W470MHD": (47e-6, 450, 0.25 / (W120 * 47e-6), None, 946e-6),
    "381LX101M450H022": (100e-6, 450, 1.99, (20e3, "ESR", 0.71), 3 * math.sqrt(100 * 450) * 1e-6),
    "381LX471M450A052": (470e-6, 450, 0.353, (20e3, "ESR", 0.123), 3 * math.sqrt(470 * 450) * 1e-6),
}
FREQS = [20, 50, 120, 1e3, 10e3, 20e3, 100e3, 1e6]


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


def main():
    # 1. small-signal impedance of every preset at 20 C, and some at low temperature
    body, names = [], []
    for k, p in enumerate(PRE):
        body += [f"V{k} a{k} 0 0 AC 1", f"X{k} a{k} 0 {p}"]
        names.append((k, p, 20))
    extra = [("UPW1V102MHD", -10), ("UPW1H471MHD", -10), ("UVR2W470MHD", -25),
             ("381LX101M450H022", -20), ("381LX101M450H022", 25)]
    for j, (p, T) in enumerate(extra):
        k = 10 + j
        body += [f"V{k} a{k} 0 0 AC 1", f"X{k} a{k} 0 {p} Temp={T}"]
        names.append((k, p, T))
    fl = " ".join(f"{f:g}" for f in FREQS)
    d, _ = sim("\n".join(body), "ac", f".ac list {fl}")
    f = np.real(d["frequency"])
    Z = {(p, T): -1 / d[f"i(v{k})"] for k, p, T in names}
    i120 = FREQS.index(120)
    for p, (C, Vr, esr120, hf, ilk) in PRE.items():
        z = Z[(p, 20)]
        # series-equivalent C at 120 Hz, with the ESL reactance removed
        Cs = -1 / (W120 * (float(np.imag(z[i120])) - W120 * 20e-9))
        check(f"{p}: capacitance (series-equivalent) at 120 Hz, uF", Cs * 1e6, C * 1e6, 0.02 * C * 1e6)
        check(f"{p}: ESR at 120 Hz, ohm (tan d/(w C) or CDE table)", float(np.real(z[i120])),
              esr120, 0.03 * esr120)
        if hf:
            fr, kind, val = hf
            zz = z[FREQS.index(fr)]
            got = abs(zz) if kind == "Z" else float(np.real(zz))
            check(f"{p}: {kind} at {fr / 1e3:g} kHz, ohm (datasheet max)", got, val, 0.03 * val)
        esr = np.real(z)
        check_cmp(f"{p}: ESR falls monotonically 20 Hz..1 MHz (CDE guide p.6): min step, ohm",
                  float(np.min(-np.diff(esr))), 0, ">=")
    # low temperature
    z = Z[("UPW1H471MHD", -10)]
    check("UPW1H471MHD: |Z| at 100 kHz, -10 C, ohm (UPW table 0.12; kT fitted on UPW1V102MHD)",
          abs(z[FREQS.index(100e3)]), 0.12, 0.06 * 0.12)
    z = Z[("UPW1V102MHD", -10)]
    note(f"  UPW1V102MHD |Z| at 100 kHz, -10 C: {abs(z[FREQS.index(100e3)]):.4f} ohm "
         f"(table 0.060, the point kT is fitted to)")
    r = abs(Z[("UVR2W470MHD", -25)][i120]) / abs(Z[("UVR2W470MHD", 20)][i120])
    check_cmp("UVR2W470MHD: Z(-25 C)/Z(20 C) at 120 Hz <= 15 (UVR, 450 V)", r, 15, "<=")
    r = abs(Z[("381LX101M450H022", -20)][i120]) / abs(Z[("381LX101M450H022", 25)][i120])
    check_cmp("381LX101M450H022: Z(-20 C)/Z(25 C) at 120 Hz <= 3 (381LX, 150-450 V)", r, 3, "<=")
    # self-resonance: the |Z| minimum is Rs (a fine sweep)
    d, _ = sim("V1 a 0 0 AC 1\nX1 a 0 381LX101M450H022", "srf", ".ac dec 200 10k 10Meg")
    zz = np.abs(-1 / d["i(v1)"])
    fmin = float(np.real(d["frequency"])[np.argmin(zz)])
    check("381LX101M450H022: |Z| minimum (at self-resonance) = Rs, ohm", float(np.min(zz)), 0.702,
          0.01 * 0.702)
    note(f"  381LX101M450H022 self-resonance {fmin / 1e3:.0f} kHz (1/(2 pi sqrt(ESL C120)) = "
         f"{1 / (2 * math.pi * math.sqrt(20e-9 * 100e-6)) / 1e3:.0f} kHz; C falls with f)")

    # 2. leakage at rated voltage (DC operating point)
    body = []
    for k, p in enumerate(PRE):
        body += [f"V{k} a{k} 0 {PRE[p][1]}", f"X{k} a{k} 0 {p}"]
    d, _ = sim("\n".join(body), "dcl", ".op")
    for k, (p, pr) in enumerate(PRE.items()):
        check_cmp(f"{p}: leakage at {pr[1]} V, uA, <= datasheet limit {pr[4] * 1e6:.0f}",
                  -float(d[f"i(v{k})"][0]) * 1e6, pr[4] * 1e6 * 1.0001, "<=")

    # 3. dielectric absorption: 60 s at Vr, 1 s short (1 ohm), open 60 s: rebound
    d, _ = sim("V1 a 0 PWL(0 0 1 450 61 450 61.001 0 62 0)\nS1 a b c 0 SW1\n"
               "Vc c 0 PWL(0 1 62 1 62.001 0)\n.model SW1 SW(Ron=1 Roff=1T Vt=0.5 Vh=0.1)\n"
               "X1 b 0 381LX101M450H022", "da", ".tran 0 122 0 50m")
    rb = float(d["v(b)"][-1]) / 450
    check_cmp("381LX101M450H022: DA rebound after 60 s at Vr, 1 s short, 60 s open, % "
              "(> 0)", rb * 100, 0.1, ">=")
    check_cmp("  ... and <= 10 % (CDE guide p.10: 'up to 10%')", rb * 100, 10, "<=")

    # 4. demo: HT supply, ripple
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_ecap.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib ecap.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=300)
    t, v = d["time"], d["v(ht)"]
    i = np.maximum(np.abs(d["i(r1)"]), np.abs(d["i(r2)"]))
    w = t > 0.3
    rip = float(np.max(v[w]) - np.min(v[w]))
    bound = 0.1 / (2 * 60 * 100e-6)
    # I/(2 f C) assumes the reservoir feeds the load for a whole half-cycle: an upper
    # bound; the diodes conduct for part of it, so the true ripple is somewhat lower
    check_cmp("demo: HT ripple p-p, V, <= I/(2 f C) = 8.33 V", rip, bound, "<=")
    check_cmp("demo: HT ripple p-p, V, >= 0.7 I/(2 f C)", rip, 0.7 * bound, ">=")
    note(f"  demo: HT {float(np.mean(v[w])):.1f} V mean, ripple {rip:.2f} V p-p; charging pulses"
         f" {float(np.max(i[w])):.2f} A peak (x ESR120 1.99 ohm)")

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
