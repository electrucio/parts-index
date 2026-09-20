#!/usr/bin/env python3
"""Verify guitar-pickup.sub against published measurements: DC resistance, inductance,
resonance with Lemme's seven load capacitors, peak height, the peak vanishing at 47 k
(Lemme), Zollner's measured iron-free coil, .tran/.ac consistency and the demo's pin
order. Run with the shell sandbox off. Exit 1 on any failure."""
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
from bench.ltbatch import run                          # noqa: E402
from pu_presets import CAPS, PRESETS, RLOAD_Q          # noqa: E402

SUB = HERE / "guitar-pickup.sub"
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


def split_steps(d, key):
    """.step runs in one ASCII raw: split where frequency restarts."""
    f = np.real(d["frequency"])
    idx = np.where(np.diff(f) < 0)[0] + 1
    return [(f[s], d[key][s]) for s in np.split(np.arange(len(f)), idx)]


def peak(f, h):
    """Peak frequency (parabolic on log f) and value of |h|."""
    a = np.abs(h)
    i = int(np.argmax(a))
    if 0 < i < len(a) - 1:
        y0, y1, y2 = a[i - 1:i + 2]
        x0, x1, x2 = np.log(f[i - 1:i + 2])
        den = y0 - 2 * y1 + y2
        dx = 0.5 * (y0 - y2) / den * (x1 - x0) if den else 0
        return math.exp(x1 + dx), y1 - 0.25 * (y0 - y2) * dx / (x1 - x0)
    return f[i], a[i]


def presets_dc_l():
    hdr("presets: R(DC) vs source, low-frequency inductance vs Lemme (EMF grounded)")
    net = ["* dc", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 o{k} 1m", f"X{k} o{k} 0 0 {p['name']}"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dc")
    for k, p in enumerate(PRESETS):
        check(f"{p['name']} R(DC) ({p['rsrc']})", float(d[f"v(o{k})"][0]) / 1e-3, p["R"], 1e-3, rel=True)
    net = ["* l", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 o{k} AC 1", f"X{k} o{k} 0 0 {p['name']}"]
    net.append(".ac list 100")
    d, _ = run("\n".join(net) + "\n", "l")
    for k, p in enumerate(PRESETS):
        z = d[f"v(o{k})"][0]
        check(f"{p['name']} Im(Z)/w at 100 Hz = Lemme L (H)", np.imag(z) / (2 * math.pi * 100), p["L"], 0.02, rel=True)


def presets_resonance():
    hdr(f"presets: resonance with Lemme's load capacitors (|| {RLOAD_Q / 1e6:g} Meg), kHz; "
        "tol = Lemme's +-10 % sample spread")
    caps = " ".join(f"{c:g}" for c in CAPS)
    all_dev = []
    for p in PRESETS:
        net = f"""* res
.include "{SUB}"
.param Cx=470p
V1 e 0 AC 1
X1 o 0 e {p['name']}
Cx o 0 {{Cx}}
Rl o 0 {RLOAD_Q:g}
.step param Cx list {caps}
.ac dec 1000 100 30k
"""
        d, _ = run(net, "res")
        for (f, v), cx, fl in zip(split_steps(d, "v(o)"), CAPS, p["f"]):
            fp, hp = peak(f, v)
            dev = fp / 1e3 / fl - 1
            all_dev.append(dev)
            check(f"{p['name']} + {cx * 1e12:g}p: peak (kHz)", fp / 1e3, fl, 0.10, rel=True)
            if cx == CAPS[0]:
                h0 = RLOAD_Q / (RLOAD_Q + p["R"])
                check(f"{p['name']} + 470p: peak height (Rx fitted to Lemme Q)", hp / h0, p["Q"], 0.02, rel=True)
    rms = math.sqrt(sum(x * x for x in all_dev) / len(all_dev))
    check_range(f"all {len(all_dev)} Lemme resonances: rms deviation (fraction)", rms, 0, 0.05)
    info("  worst single deviation (fraction)", max(all_dev, key=abs))


def lemme_47k():
    hdr("Lemme, article Fig. 14: 1972 Strat with 470 pF, 'with 47 kOhms or less the peak vanishes'")
    for rl, lo, hi in ((47e3, 0, 1.05), (10e6, 5.5, 7.5)):
        net = f"""* l47
.include "{SUB}"
V1 e 0 AC 1
X1 o 0 e PU_STRAT72
Cx o 0 470p
Rl o 0 {rl:g}
.ac dec 1000 100 30k
"""
        d, _ = run(net, "l47")
        f = np.real(d["frequency"])
        h = np.abs(d["v(o)"])
        h0 = h[0]
        check_range(f"PU_STRAT72, 470p || {rl / 1e3:g}k: max |H| / |H(100 Hz)|", float(h.max() / h0), lo, hi)


def zollner_coil():
    hdr("Zollner PotEG Fig. 5.9.26: Gibson screw-coil without iron (R 4420, L 1125 mH, C 43 pF),"
        " |Z| maximum vs load")
    cases = ((330e-12, 7.7), (700e-12, 5.5), (1030e-12, 4.6))
    net = ["* zc", f'.include "{SUB}"']
    for k, (cx, _) in enumerate(cases):
        net += [f"I{k} 0 o{k} AC 1", f"X{k} o{k} 0 0 pickup L=1.125 R=4420 C=43p Rx=0 kx=0",
                f"C{k} o{k} 0 {cx:g}"]
    net += ["I9 0 o9 AC 1", "X9 o9 0 0 pickup L=1.125 R=4420 C=43p Rx=0 kx=0"]
    net.append(".ac dec 2000 1k 50k")
    d, _ = run("\n".join(net) + "\n", "zc")
    f = np.real(d["frequency"])
    for k, (cx, fz) in enumerate(cases):
        fp, _ = peak(f, d[f"v(o{k})"])
        check(f"screw-coil + {cx * 1e12:g}p: |Z| max (kHz, measured)", fp / 1e3, fz, 0.03, rel=True)
    fp, _ = peak(f, d["v(o9)"])
    info("screw-coil unloaded: |Z| max (kHz); Zollner: 21 (Fig. 5.9.26) and 23 (Fig. 5.9.18)", fp / 1e3, 21)


def eddy_slope():
    hdr("eddy loss (info): Lemme's split coil vs a plain resistor across the terminals, same peak"
        " height (P-90 + 470p)")
    from pu_presets import peak as npeak
    p = next(q for q in PRESETS if q["name"] == "PU_P90")
    # the "unsuccessful" alternative: no eddy branch, a resistor Rp across OUT giving the
    # same peak height (bisection with the numpy model of pu_presets)
    lo, hi = math.log(1e3), math.log(1e9)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if npeak(p, 0, 470e-12, math.exp(mid))[1] > p["Q"]:
            hi = mid
        else:
            lo = mid
    rp = math.exp(0.5 * (lo + hi))
    f0 = next(fk for cx, fk in zip(CAPS, p["f"]) if cx == 470e-12) * 1e3
    fl = [f0 / 2, f0, 2 * f0, 4 * f0, 8 * f0]
    res = {}
    for tag, xline, rl in (("split coil", f"pickup L={p['L']} R={p['R']} C={p['C']} Rx={p['Rx']} kx=0.5", 10e6),
                           (f"Rp {rp / 1e3:.0f}k", f"pickup L={p['L']} R={p['R']} C={p['C']} Rx=0 kx=0", rp)):
        net = f"""* sl
.include "{SUB}"
V1 e 0 AC 1
X1 o 0 e {xline}
Cx o 0 470p
Rl o 0 {rl:g}
.ac list 20 {' '.join(f'{x:g}' for x in fl)}
"""
        d, _ = run(net, "sl")
        h = np.abs(d["v(o)"])
        res[tag] = 20 * np.log10(h[1:] / h[0])
    for tag, db in res.items():
        info(f"PU_P90 {tag}: level at f0/2 re 20 Hz (dB) (Lemme: eddy currents lower it)", db[0])
        info(f"PU_P90 {tag}: slope 2 f0 -> 4 f0 (dB/oct)", db[3] - db[2])
        info(f"PU_P90 {tag}: slope 4 f0 -> 8 f0 (dB/oct) (Lemme: up to -18)", db[4] - db[3])


def tran_ac():
    hdr(".tran vs .ac: PU_STRAT72, 100 mV 3 kHz EMF, 470p || 1 Meg")
    body = """X1 o 0 e PU_STRAT72
Cx o 0 470p
Rl o 0 1Meg
"""
    d, _ = run(f'* ta\n.include "{SUB}"\nV1 e 0 SINE(0 0.1 3k)\n{body}'
               ".options plotwinsize=0\n.tran 0 12m 8m 0.5u\n", "ta")
    amp = (np.max(d["v(o)"]) - np.min(d["v(o)"])) / 2
    d2, _ = run(f'* ac1\n.include "{SUB}"\nV1 e 0 AC 0.1\n{body}.ac list 3k\n', "ac1")
    check("amplitude .tran = |V| .ac at 3 kHz (V)", amp, abs(d2["v(o)"][0]), 0.01, rel=True)
    d3, _ = run(f'* ph\n.include "{SUB}"\nV1 e 0 AC 1\n{body}.ac list 100\n', "ph")
    check("polarity: phase V(OUT)/V(EMF) at 100 Hz (deg)", math.degrees(np.angle(d3["v(o)"][0])), 0, 1)


def demo():
    hdr("demo_guitar-pickup.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_guitar-pickup.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n", "demo")
    hand = (f'* hand\n.include "{SUB}"\nV1 e 0 AC 0.1\nX1 out 0 e PU_STRAT72 kx=0.5\n'
            "R1 out 0 250k\nC1 out 0 330p\nR2 out 0 1Meg\n.ac dec 50 20 20k\n")
    d2, _ = run(hand, "hand")
    f1 = np.real(d1["frequency"])
    for fx in (100, 3000, 10000):
        i = int(np.argmin(abs(f1 - fx)))
        check(f"demo |V(out)| @{fx} Hz = hand netlist", abs(d1["v(out)"][i]), abs(d2["v(out)"][i]), 1e-4, rel=True)


def main():
    presets_dc_l()
    presets_resonance()
    lemme_47k()
    zollner_coil()
    eddy_slope()
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
