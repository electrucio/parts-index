#!/usr/bin/env python3
"""Verify wah-inductor.sub: DC resistance and inductance of every preset against the
published LCR readings, the core-loss and self-capacitance options, and the Dunlop Cry
Baby GCB-95 wah circuit built around the inductor against ElectroSmash's published sweep
(450 Hz .. 1.6 kHz, peak up to 18 dB). Run with the shell sandbox off. Exit 1 on any
failure."""
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
from bench.ltbatch import run          # noqa: E402
from wi_presets import PRESETS         # noqa: E402

SUB = HERE / "wah-inductor.sub"
BJT = ROOT / "models/bjt"
MPSA18 = BJT / "MPSA18/ltwiki-2.lib"         # preferred model (models/bjt/MPSA18/README.md)
MPSA13 = BJT / "MPSA13/bordodynov.lib"
ROWS, FAIL = [], 0

# Cry Baby GCB-95 wah circuit, ElectroSmash part list (crybaby-gcb-95), topology as in
# sources/audio-effects-ltspice/.../dunlop_crybaby.asc (same parts, Rin2 1.8 Meg per
# ElectroSmash). VR1 (100 k) is split Rtone (wiper to ground) / 100k - Rtone (to output).
# Output = the pedal output after C4 (the pot's top end).
def crybaby(ind, rtone_list):
    steps = " ".join(f"{r:g}" for r in rtone_list)
    return f"""* crybaby
.include "{SUB}"
.include "{MPSA18}"
.include "{MPSA13}"
.param Rtone=50k
V1 v9 0 9
Vin in 0 AC 1
Cin1 in b0 10n
Rin1 b0 0 2.2Meg
Cin2 b0 0 22p
Rin2 c0 b0 1.8Meg
Rin3 v9 c0 1k
X0 c0 b0 e0 MPSA13
Rin4 e0 0 10k
R1 e0 n8 68k
C1 n8 b1 10n
R2 b1 lo 1.5k
Q1 c1 b1 e1 MPSA18
R4 e1 0 390
R3 v9 c1 22k
R5 c1 hi 470k
XL1 hi lo {ind}
R7 hi lo 33k
C3 hi 0 4.7u
R8 hi 0 82k
C4 out c1 0.22u
Rpa out w {{100k-Rtone+1}}
Rpb w 0 {{Rtone}}
R6 b2 c1 470k
C5 b2 w 0.22u
Q2 c2 b2 fb MPSA18
R9 v9 c2 1k
R10 fb 0 10k
C2 fb lo 10n
.step param Rtone list {steps}
.ac dec 400 50 10k
"""


def check(name, got, want, tol, rel=False):
    global FAIL
    err = abs(got - want) / (abs(want) if rel and want else 1)
    ok = err <= tol
    FAIL += not ok
    ROWS.append((name, got, want, f"{tol:g}{'r' if rel else ''}", "ok" if ok else "FAIL"))


def check_range(name, got, lo, hi):
    global FAIL
    ok = lo <= got <= hi
    FAIL += not ok
    ROWS.append((name, got, (lo + hi) / 2, f"[{lo:g},{hi:g}]", "ok" if ok else "FAIL"))


def info(name, got, want=float("nan")):
    ROWS.append((name, got, want, "info", ""))


def hdr(t):
    ROWS.append((f"-- {t}", None, None, "", ""))


def split_steps(d, key):
    f = np.real(d["frequency"])
    idx = np.where(np.diff(f) < 0)[0] + 1
    return [(f[s], d[key][s]) for s in np.split(np.arange(len(f)), idx)]


def peak_db(f, v):
    g = 20 * np.log10(np.abs(v))
    i = int(np.argmax(g))
    if 0 < i < len(g) - 1:
        y0, y1, y2 = g[i - 1:i + 2]
        x0, x1, x2 = np.log(f[i - 1:i + 2])
        den = y0 - 2 * y1 + y2
        dx = 0.5 * (y0 - y2) / den * (x1 - x0) if den else 0
        fp, gp = math.exp(x1 + dx), y1 - 0.25 * (y0 - y2) * dx / (x1 - x0)
    else:
        fp, gp = f[i], g[i]
    above = f[i:][g[i:] < gp - 3]
    below = f[:i][g[:i] < gp - 3]
    q = fp / (above[0] - below[-1]) if len(above) and len(below) else float("nan")
    return fp, gp, q


def presets():
    hdr("presets: R(DC) and L vs the published LCR readings (PedalPCB thread 24076)")
    net = ["* dc", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 a{k} 1m", f"X{k} a{k} 0 {p['name']}"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dc")
    for k, p in enumerate(PRESETS):
        check(f"{p['name']} R(DC) ({p['src_R']})", float(d[f"v(a{k})"][0]) / 1e-3, p["R"], 1e-3, rel=True)
    net = ["* l", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 {p['name']}"]
    net.append(".ac list 1k")
    d, _ = run("\n".join(net) + "\n", "l")
    for k, p in enumerate(PRESETS):
        z = d[f"v(a{k})"][0]
        check(f"{p['name']} Im(Z)/w at 1 kHz (mH) ({p['src_L']})", np.imag(z) / (2 * math.pi * 1e3) * 1e3,
              p["L"] * 1e3, 0.005, rel=True)
        info(f"{p['name']}   other meter: {p['other']}; coil Q at 1 kHz = wL/R", np.imag(z) / np.real(z))


def options():
    hdr("options: core loss Qc and self-capacitance Cp (generic wah_inductor, 500 mH)")
    net = f"""* opt
.include "{SUB}"
I1 0 a AC 1
X1 a 0 wah_inductor L=500m R=17 Qc=0
I2 0 b AC 1
X2 b 0 wah_inductor L=500m R=17 Qc=50
I3 0 c AC 1
X3 c 0 wah_inductor L=500m R=17 Cp=100p
.ac list 1k {1 / (2 * math.pi * math.sqrt(0.5 * 100e-12)):g}
"""
    d, _ = run(net, "opt")
    za, zb, zc = d["v(a)"], d["v(b)"], d["v(c)"]
    wl = 2 * math.pi * 1e3 * 0.5
    check("Qc=0: coil Q at 1 kHz = wL/R", np.imag(za[0]) / np.real(za[0]), wl / 17, 1e-3, rel=True)
    check("Qc=50: coil Q at 1 kHz = 1/(R/wL + 1/Qc)", np.imag(zb[0]) / np.real(zb[0]),
          1 / (17 / wl + 1 / 50), 0.01, rel=True)
    check("Cp=100p: impedance phase at 1/(2 pi sqrt(L Cp)) ~ 0 (deg)", math.degrees(np.angle(zc[1])), 0, 2)


def wah():
    hdr("Cry Baby GCB-95 circuit, generic 500 mH / 17 ohm (ElectroSmash: '500mH typ.')")
    rl = [100, 1e3, 3e3, 5e3, 10e3, 25e3, 50e3, 75e3, 90e3, 100e3]
    d, _ = run(crybaby("wah_inductor L=500m R=17", rl), "cb")
    res = [peak_db(f, v) for f, v in split_steps(d, "v(out)")]
    for r, (fp, gp, q) in zip(rl, res):
        info(f"Rtone {r / 1e3:g}k: peak Hz / dB / Q(-3 dB):  peak (Hz)", fp)
        info("    gain (dB)", gp)
        info("    Q", q)
    fmin = min(r[0] for r in res)
    fmax = max(r[0] for r in res)
    gmax = max(r[1] for r in res)
    check("heel (pot end, Rtone 100k): peak (Hz) vs ElectroSmash 450 Hz", res[-1][0], 450, 0.15, rel=True)
    check_range("lowest peak <= 450 Hz: the published sweep bottom is reachable (Hz)", fmin, 0, 450)
    check_range("highest peak >= 1.6 kHz: the published sweep top is reachable (Hz)", fmax, 1600, 1e9)
    check_range("peak gain, max over the sweep (dB) vs ElectroSmash 'up to 18dB' (+-4 dB)", gmax, 14, 22)
    info("pot setting for 750 Hz (ElectroSmash, 'VR1 at mid position'): Rtone (k), interpolated",
         float(np.interp(math.log(750), np.log([r[0] for r in res])[::-1], np.array(rl)[::-1])) / 1e3)

    hdr("Cry Baby with each preset, Rtone 100k (heel) and 3k (near toe): the peak moves as 1/sqrt(L)")
    names = [p["name"] for p in PRESETS]
    base = None
    for p in PRESETS:
        # LTspice runs a .step list in ascending order: 3k (toe) first, then 100k (heel)
        d, _ = run(crybaby(p["name"], [3e3, 100e3]), "cbp")
        (ft, gt, qt), (fh, gh, qh) = [peak_db(f, v) for f, v in split_steps(d, "v(out)")]
        info(f"{p['name']} heel: peak (Hz)", fh)
        info(f"{p['name']} heel: gain (dB) / Q", gh, qh)
        info(f"{p['name']} toe:  peak (Hz)", ft)
        if base is None:
            base = (p, fh)
        else:
            check(f"{p['name']} heel peak / {base[0]['name']} = sqrt(L ratio)", fh / base[1],
                  math.sqrt(base[0]["L"] / p["L"]), 0.03, rel=True)
    _ = names


def tran_ac():
    hdr(".tran vs .ac: 1 V 2 kHz into 100 k + WAH_RED_FASEL || 10 nF")
    body = "R1 a t 100k\nX1 t 0 WAH_RED_FASEL\nC1 t 0 10n\n"
    d, _ = run(f'* ta\n.include "{SUB}"\nV1 a 0 SINE(0 1 2k)\n{body}'
               ".options plotwinsize=0\n.tran 0 40m 30m 0.5u\n", "ta")
    amp = (np.max(d["v(t)"]) - np.min(d["v(t)"])) / 2
    d2, _ = run(f'* ac1\n.include "{SUB}"\nV1 a 0 AC 1\n{body}.ac list 2k\n', "ac1")
    check("amplitude .tran = |V| .ac (V)", amp, abs(d2["v(t)"][0]), 0.01, rel=True)


def demo():
    hdr("demo_wah-inductor.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_wah-inductor.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n", "demo")
    hand = (f'* hand\n.include "{SUB}"\nV1 a 0 AC 1\nR1 a tank 100k\nX1 tank 0 WAH_RED_FASEL Qc=0 Cp=0\n'
            "C1 tank 0 10n\n.ac dec 200 100 20k\n")
    d2, _ = run(hand, "hand")
    f1 = np.real(d1["frequency"])
    for fx in (500, 2000, 8000):
        i = int(np.argmin(abs(f1 - fx)))
        check(f"demo |V(tank)| @{fx} Hz = hand netlist", abs(d1["v(tank)"][i]), abs(d2["v(tank)"][i]), 1e-4, rel=True)


def main():
    presets()
    options()
    wah()
    tran_ac()
    demo()
    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, st in ROWS:
        if got is None:
            print(name)
            continue
        print(f"{name:<{w}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<11} {st}")
    n = sum(1 for r in ROWS if r[4] in ("ok", "FAIL"))
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
