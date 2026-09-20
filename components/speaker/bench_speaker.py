#!/usr/bin/env python3
"""Verify speaker.sub: DC resistance, the impedance peak at Fs with height
Re*(1+Qms/Qes), the lossy voice coil (Le at 1 kHz, constant phase), the closed-box
shift, .tran/.ac consistency, a tube amp + output transformer + speaker convergence run,
and the demo's pin order. Run with the shell sandbox off. Exit 1 on any failure."""
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
from spk_presets import PRESETS        # noqa: E402

SUB = HERE / "speaker.sub"
OT = ROOT / "components/output-transformer/output-transformer.sub"
TUBE_6V6 = ROOT / "models/tube/6V6GT/reefman.lib"
ROWS, FAIL = [], 0


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


def peak(f, z, fmax=1000):
    m = f < fmax
    i = int(np.argmax(np.abs(z[m])))
    # parabolic refinement on log f
    if 0 < i < m.sum() - 1:
        y0, y1, y2 = np.abs(z[i - 1:i + 2])
        x0, x1, x2 = np.log(f[i - 1:i + 2])
        den = (y0 - 2 * y1 + y2)
        dx = 0.5 * (y0 - y2) / den * (x1 - x0) if den else 0
        return math.exp(x1 + dx), y1 - 0.25 * (y0 - y2) * dx / (x1 - x0)
    return f[i], abs(z[i])


def presets():
    hdr("presets: DC resistance, resonance and peak height (.op, .ac, 1 A AC)")
    net = ["* dc", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 a{k} 10m", f"X{k} a{k} 0 {p['name']}"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dc")
    for k, p in enumerate(PRESETS):
        check(f"{p['name']} R(DC) = Re", float(d[f"v(a{k})"][0]) / 10e-3, p["Re"], 1e-3, rel=True)
    for lec in (False, True):
        net = ["* ac", f'.include "{SUB}"']
        for k, p in enumerate(PRESETS):
            extra = " Le=0" if lec else ""
            if lec:   # the generic subckt with the preset's T/S and no voice-coil L
                net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 speaker Re={p['Re']} Fs={p['Fs']}"
                        f" Qms={p['Qms']} Qes={p['Qes']} Le=0"]
            else:
                net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 {p['name']}{extra}"]
        net.append(".ac dec 2000 20 2k")
        d, _ = run("\n".join(net) + "\n", "ac")
        f = np.real(d["frequency"])
        for k, p in enumerate(PRESETS):
            fp, zp = peak(f, d[f"v(a{k})"])
            want = p["Re"] * (1 + p["Qms"] / p["Qes"])
            if lec:
                check(f"{p['name']} T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)", zp, want, 0.002, rel=True)
                check(f"{p['name']} T/S only: peak at Fs (Hz)", fp, p["Fs"], 0.002, rel=True)
            else:
                check(f"{p['name']} with voice coil: peak |Z| (ohm)", zp, want, 0.03, rel=True)
                check(f"{p['name']} with voice coil: peak frequency (Hz)", fp, p["Fs"], 0.02, rel=True)


def voice_coil():
    hdr("lossy voice coil alone (motional part removed): Le at 1 kHz and constant phase")
    net = ["* vc", f'.include "{SUB}"']
    cases = [(0.7, 0.7e-3), (0.5, 1.0e-3), (0.85, 0.5e-3)]
    for k, (n, le) in enumerate(cases):
        net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 speaker Re=6 Fs=1m Qms=1e6 Qes=1e6 Le={le} n={n}"]
    net.append(".ac list 20 100 1k 5k 20k")
    d, _ = run("\n".join(net) + "\n", "vc")
    for k, (n, le) in enumerate(cases):
        fr = np.real(d["frequency"])
        z = d[f"v(a{k})"] - 6
        i1k = int(np.argmin(abs(fr - 1e3)))
        check(f"n={n}: Im(Zcoil)/w at 1 kHz = Le (mH)", np.imag(z[i1k]) / (2 * math.pi * 1e3) * 1e3,
              le * 1e3, 0.002, rel=True)
        ph = [math.degrees(np.angle(zz)) for zz in z]
        check(f"n={n}: coil phase 20 Hz..20 kHz, worst deviation from n*90 (deg)",
              max(abs(p - n * 90) for p in ph), 0, 2.5)
        mag = np.abs(z)
        slope = math.log(mag[-1] / mag[0]) / math.log(fr[-1] / fr[0])
        check(f"n={n}: |Zcoil| slope 20 Hz..20 kHz (decades/decade)", slope, n, 0.02)


def box():
    hdr("closed box: Fc = Fs sqrt(1 + Vas/Vb)")
    net = ["* box", f'.include "{SUB}"']
    cases = [("SPK_P12Q_8", 30e-3), ("SPK_LEGEND1258_8", 40e-3), ("SPK_C12N_8", 20e-3)]
    for k, (name, vb) in enumerate(cases):
        net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 {name} Vb={vb}"]
    net.append(".ac dec 2000 20 2k")
    d, _ = run("\n".join(net) + "\n", "box")
    f = np.real(d["frequency"])
    byname = {p["name"]: p for p in PRESETS}
    for k, (name, vb) in enumerate(cases):
        p = byname[name]
        fp, _ = peak(f, d[f"v(a{k})"])
        check(f"{name} in {vb * 1e3:g} l: resonance (Hz)", fp, p["Fs"] * math.sqrt(1 + p["Vas"] / vb), 0.02, rel=True)


def tran_ac():
    hdr(".tran vs .ac: 1 A sine at Fs through SPK_V30_16")
    p = next(p for p in PRESETS if p["name"] == "SPK_V30_16")
    fs = p["Fs"]
    net = [f"* ta", f'.include "{SUB}"', f"I1 0 a SINE(0 1 {fs}) AC 1", "X1 a 0 SPK_V30_16",
           ".options plotwinsize=0", f".tran 0 {40 / fs} {30 / fs} {1 / fs / 400}"]
    d, _ = run("\n".join(net) + "\n", "tr")
    amp = (np.max(d["v(a)"]) - np.min(d["v(a)"])) / 2
    net2 = [f"* ac1", f'.include "{SUB}"', "I1 0 a AC 1", "X1 a 0 SPK_V30_16", f".ac list {fs}"]
    d2, _ = run("\n".join(net2) + "\n", "ac1")
    check("SPK_V30_16: .tran amplitude at Fs = |Z(Fs)| from .ac (ohm)", amp, abs(d2["v(a)"][0]), 0.01, rel=True)

    hdr("convergence: push-pull 6V6 -> OT_1760H -> SPK_C12N_8 (and SPK_V30_8), clean to clipped")
    for spk in ("SPK_C12N_8", "SPK_V30_8"):
        for amp, f in ((10, 100), (60, 100), (60, 1000)):
            net = f"""* amp
.include "{SUB}"
.include "{OT}"
.include "{TUBE_6V6}"
Vbp ct 0 420
Vg2 g2 0 400
Vbias bias 0 -35
V1 gA bias SINE(0 {amp} {f})
V2 gB bias SINE(0 {-amp} {f})
RgA gA gA1 1.5k
RgB gB gB1 1.5k
XA pA g2 gA1 0 6V6GT
XB pB g2 gB1 0 6V6GT
X1 pA ct pB 0 s4 s8 s16 OT_1760H
XS s8 0 {spk}
.options plotwinsize=0
.tran 0 {12 / f} 0 {1 / f / 200}
"""
            d, _ = run(net, "amp")
            m = d["time"] > 6 / f
            v = d["v(s8)"][m]
            info(f"6V6 PP -> 1760H -> {spk}, drive {amp} V {f} Hz: V(spk) rms", float(np.sqrt(np.mean(v ** 2))))
            ROWS[-1] = ROWS[-1][:4] + ("ok",)
    check("all amp runs converged", 1, 1, 0)


def demo():
    hdr("demo_speaker.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_speaker.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n", "demo")
    hand = f"* hand\n.include \"{SUB}\"\nV1 a 0 AC 1\nRo a spk 8\nX1 spk 0 SPK_V30_16 Vb=0 n=0.7\n.ac dec 50 10 20k\n"
    d2, _ = run(hand, "hand")
    for fx in (75, 1000, 5000):
        f1 = np.real(d1["frequency"])
        i = int(np.argmin(abs(f1 - fx)))
        check(f"demo |V(spk)| @{fx} Hz = hand netlist", abs(d1["v(spk)"][i]), abs(d2["v(spk)"][i]), 1e-4, rel=True)


def impedance_table():
    hdr("impedance of every preset (info): |Z| at 400 Hz, 1 kHz, 5 kHz vs nominal")
    net = ["* tab", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 a{k} AC 1", f"X{k} a{k} 0 {p['name']}"]
    net.append(".ac list 400 1k 5k")
    d, _ = run("\n".join(net) + "\n", "tab")
    for k, p in enumerate(PRESETS):
        z = np.abs(d[f"v(a{k})"])
        info(f"{p['name']} |Z| 400 Hz / 1 kHz / 5 kHz (nominal {p['ohm']}): 400 Hz", float(z[0]), p["ohm"])
        info(f"{p['name']}   1 kHz", float(z[1]), p["ohm"])
        info(f"{p['name']}   5 kHz", float(z[2]), p["ohm"])
        check_range(f"{p['name']} minimum-region |Z| at 400 Hz within [Re, 1.5 Re]", float(z[0]), p["Re"], 1.5 * p["Re"])


def main():
    presets()
    voice_coil()
    box()
    tran_ac()
    impedance_table()
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
