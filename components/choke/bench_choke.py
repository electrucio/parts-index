#!/usr/bin/env python3
"""Verify choke.sub: DCR and inductance at rated DC current against the Hammond sheets,
the L(i) law at other currents, the 159ZJ self-resonance, a choke-input filter (DC
level and ripple against the textbook formulas) and convergence (overload, capacitor-
input start-up surge). Run with the shell sandbox off. Exit 1 on any failure."""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bench.ltbatch import run          # noqa: E402

SUB = HERE / "choke.sub"
ROWS, FAIL = [], 0
DREC = ".model DREC D(Is=10n Rs=0.05 N=1.8 Cjo=20p Bv=1000 Ibv=5u)"

# Hammond sheets (https://www.hammfg.com/files/parts/pdf/<PART>.pdf): L at rated DC, Idc, DCR
PRESETS = {
    "CH_159R": (6.0, 0.200, 150.0), "CH_159S": (4.0, 0.225, 60.60), "CH_159T": (2.5, 0.300, 40.17),
    "CH_159V": (1.5, 0.500, 27.0), "CH_159ZJ": (10e-3, 5.0, 0.160), "CH_193H": (5.0, 0.200, 65.0),
    "CH_193J": (10.0, 0.200, 79.0), "CH_193M": (10.0, 0.300, 63.0),
}
S = 1.3


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


def L_law(i, L, Idc, s=S):
    Ia = Idc / math.sqrt(s * s - 1)
    return s * L / math.sqrt(1 + (i / Ia) ** 2)


def presets():
    hdr("presets: DCR (.op, 10 mA) and L at rated DC current (60 Hz small signal) vs sheet")
    net = ["* dcr", f'.include "{SUB}"']
    for k, name in enumerate(PRESETS):
        net += [f"I{k} 0 a{k} 10m", f"X{k} a{k} 0 {name}"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dcr")
    for k, (name, (L, Idc, R)) in enumerate(PRESETS.items()):
        check(f"{name} DCR (ohm)", float(d[f"v(a{k})"][0]) / 10e-3, R, 1e-3, rel=True)
    # L at bias: DC Idc + 1 A AC through the choke, L = Im(Z)/w at 60 Hz
    for frac, lab in ((1.0, "rated Idc"), (0.0, "zero DC"), (0.5, "Idc/2"), (2.0, "2 x Idc")):
        net = ["* L", f'.include "{SUB}"']
        for k, name in enumerate(PRESETS):
            L, Idc, R = PRESETS[name]
            net += [f"I{k} 0 a{k} {frac * Idc} AC 1", f"X{k} a{k} 0 {name}"]
        net.append(".ac list 60")
        d, _ = run("\n".join(net) + "\n", "lbias")
        for k, (name, (L, Idc, R)) in enumerate(PRESETS.items()):
            z = d[f"v(a{k})"][0]
            Lm = np.imag(z) / (2 * math.pi * 60)
            if frac == 1.0:
                check(f"{name} L at {lab} (H) [sheet]", Lm, L, 0.01, rel=True)
            else:
                check(f"{name} L at {lab} (H) [law, S={S}]", Lm, L_law(frac * Idc, L, Idc), 0.01, rel=True)


def srf():
    hdr("159ZJ self-resonance at rated current (sheet: 302.90 kHz)")
    net = ["* srf", f'.include "{SUB}"', "I1 0 a 5 AC 1", "X1 a 0 CH_159ZJ", ".ac dec 2000 50k 1Meg"]
    d, _ = run("\n".join(net) + "\n", "srf")
    f = np.real(d["frequency"])
    z = np.abs(d["v(a)"])
    check("CH_159ZJ |Z| peak frequency at 5 A (kHz)", f[np.argmax(z)] / 1e3, 302.9, 0.01, rel=True)


def filters():
    hdr("choke-input filter: 350 V rms full-wave (ideal), CH_193H, 40 uF, 1.5k")
    Vpk = 350 * math.sqrt(2)
    net = ["* lc", f'.include "{SUB}"', f"B1 r 0 V=abs({Vpk}*sin(2*pi*60*time))",
           "X1 r out CH_193H", "C1 out 0 40u", "RL out 0 1.5k",
           ".options plotwinsize=0", ".tran 0 3 2.5 10u"]
    d, _ = run("\n".join(net) + "\n", "lc")
    t, v = d["time"], d["v(out)"]
    m = t >= 2.5
    vdc = float(np.mean(v[m]))
    idc = vdc / 1.5e3
    # DC: mean of the rectified sine (2/pi Vpk) minus the DCR drop
    check("V_DC = 2 Vpk/pi - Idc*Rdc (V)", vdc, 2 * Vpk / math.pi - idc * 65.0, 0.005, rel=True)
    # ripple: the 120 Hz term of a full-wave rectified sine is (4/(3 pi)) Vpk; the LC
    # divider (with L(Idc) from the law, Rc and Cp negligible) passes 1/|1 - w^2 L C|
    tt = np.linspace(2.5, 3.0, 60 * 512, endpoint=False)
    vv = np.interp(tt, t, v)
    X = np.fft.rfft(vv - vv.mean()) * 2 / len(tt)
    r120 = abs(X[60])                      # 0.5 s window: bin k = k*2 Hz -> 120 Hz = bin 60
    w = 2 * math.pi * 120
    L = L_law(idc, 5.0, 0.2)
    zc = 1 / (1j * w * 40e-6)
    zp = 1 / (1 / zc + 1 / 1.5e3)
    want = 4 / (3 * math.pi) * Vpk * abs(zp / (zp + 65.0 + 1j * w * L))
    check("120 Hz ripple at the output (V pk)", r120, want, 0.05, rel=True)
    info("  L(Idc) used by the formula (H)", L, 5.0)
    # the same filter with a linear 5 H (no saturation law) would give:
    info("  ripple if L stayed at L(0) = 6.5 H (V pk)",
         4 / (3 * math.pi) * Vpk * abs(zp / (zp + 65.0 + 1j * w * 6.5)))

    hdr("convergence: overload and capacitor-input start-up surge")
    # 5 x rated DC through a 193H from a stiff source: must converge; L falls by the law
    net = ["* over", f'.include "{SUB}"', "V1 a 0 PWL(0 0 10m 65 1 65)", "X1 a 0 CH_193H",
           ".options plotwinsize=0", ".tran 0 1 0 100u"]
    d, _ = run("\n".join(net) + "\n", "over")
    check("CH_193H at 65 V DC: I = V/Rdc (A)", float(-d["i(v1)"][-1]), 1.0, 0.01, rel=True)
    # CLC with real diodes, switch-on surge into 22 uF - choke - 22 uF
    net = ["* clc", f'.include "{SUB}"', DREC, "V1 a 0 SINE(0 495 60)", "V2 0 b SINE(0 495 60)",
           "D1 a r DREC", "D2 b r DREC", "C1 r 0 22u", "X1 r out CH_193H", "C2 out 0 22u",
           "RL out 0 2.2k", ".options plotwinsize=0", ".tran 0 2 0 20u"]
    d, _ = run("\n".join(net) + "\n", "clc")
    m = d["time"] > 1.5
    v = float(np.mean(d["v(out)"][m]))
    info("CLC 22u-193H-22u, 2.2k: B+ (V)", v)
    check_range("CLC B+ between the choke-input level and the peak (V)", v, 2 * 495 / math.pi, 495)
    info("CLC peak choke current at switch-on (A)", float(np.max(np.abs(d["i(c2)"]))))


def demo():
    hdr("demo_choke.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_choke.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n.options plotwinsize=0\n", "demo")
    hand = f"""* hand
.include "{SUB}"
{DREC}
V1 a 0 SINE(0 495 60)
V2 0 b SINE(0 495 60)
D1 a r DREC
D2 b r DREC
X1 r out CH_193H S=1.3
C1 out 0 40u
RL out 0 1.5k
.options plotwinsize=0
.tran 0 2 1.5 20u
"""
    d2, _ = run(hand, "hand")
    a = float(np.mean(d1["v(out)"][d1["time"] > 1.8]))
    b = float(np.mean(d2["v(out)"][d2["time"] > 1.8]))
    check("demo mean V(out) = hand netlist", a, b, 1e-3, rel=True)


def main():
    presets()
    srf()
    filters()
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
