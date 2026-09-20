#!/usr/bin/env python3
"""Verify relay.sub: pick-up/drop-out thresholds and hysteresis, polarity,
operate/release timing, break-before-make, flyback with and without a diode (the
diode lengthens the release), contact resistance, latching relays, the presets
against their datasheets, .ac, and the demo schematic.
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

SUB = HERE / "relay.sub"
ROWS, FAIL = [], 0
D4148 = ".model 1N4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n)"


def check(name, got, want, tol):
    global FAIL
    ok = abs(got - want) <= tol
    FAIL += not ok
    ROWS.append((name, got, want, tol, ok))


def note(text):
    ROWS.append((text, None, None, None, True))


def cross(t, y, level, after=0.0, rising=True):
    """First time > after at which y crosses level (linear interpolation)."""
    i0 = np.searchsorted(t, after)
    a, b = y[i0:-1], y[i0 + 1:]
    idx = np.nonzero((a < level) & (b >= level) if rising else (a > level) & (b <= level))[0]
    if not len(idx):
        return math.nan
    k = i0 + idx[0]
    return float(t[k] + (level - y[k]) * (t[k + 1] - t[k]) / (y[k + 1] - y[k]))


def sim(body, name, analysis):
    return run(f"* {name}\n.include \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=120)


# contact sensing: COM at 1 V, NC and NO loaded with 1k: 1 V when closed, ~0 when open
def poles(inst, cp, cn, model, params="", n=1, tag=""):
    nodes = " ".join(f"com{tag}{k} nc{tag}{k} no{tag}{k}" for k in range(1, n + 1))
    lines = [f"X{inst} {cp} {cn} {nodes} {model} {params}"]
    for k in range(1, n + 1):
        lines += [f"Vc{tag}{k} com{tag}{k} 0 1", f"Rnc{tag}{k} nc{tag}{k} 0 1k",
                  f"Rno{tag}{k} no{tag}{k} 0 1k"]
    return "\n".join(lines)


def decay_time(L, R, i0, i1, diode):
    """Time for a coil current to fall from i0 to i1, freewheeling in a 1N4148:
    L di/dt = -(R i + Vd(i)), Vd = N Vt ln(1 + i/Is) + Rs i (RK4)."""
    Is, N, Rs, Vt = 2.52e-9, 1.752, 0.568, 0.025865
    f = (lambda i: -(R * i + N * Vt * math.log1p(max(i, 0) / Is) + Rs * i) / L) if diode \
        else (lambda i: -(R * i) / L)
    i, t, dt = i0, 0.0, 1e-7
    while i > i1:
        k1 = f(i); k2 = f(i + dt / 2 * k1); k3 = f(i + dt / 2 * k2); k4 = f(i + dt * k3)
        i += dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
    return t


def main():
    # defaults of relay_spdt: Vnom=12 R=288 L=1.6m*R Lc=1.4 L pu=0.65 do=0.2 Top=4m Trel=2m
    Vn, R = 12.0, 288.0
    Lo, Lc = 1.6e-3 * R, 1.4 * 1.6e-3 * R

    # 1. thresholds: coil voltage ramped 0 -> 14 V -> 0 over 20 s (quasi-static)
    d, _ = sim(f"Vs cp 0 PWL(0 0 10 14 20 0)\n{poles(1, 'cp', 0, 'relay_spdt')}",
               "thr", ".tran 0 20 0 1m")
    t = d["time"]
    tu = cross(t, d["v(no1)"], 0.5)
    td = cross(t, d["v(nc1)"], 0.5, after=10)
    check("pick-up voltage (NO makes), V", 1.4 * tu, 0.65 * Vn, 0.03)
    check("drop-out voltage (NC makes), V", 14 - 1.4 * (td - 10), 0.2 * Vn, 0.03)
    note("  hysteresis: between 2.4 V and 7.8 V the relay keeps its last state")

    # 2. polarity: -12 V on the coil
    body = (f"Vs cp 0 -12\n{poles(1, 'cp', 0, 'relay_spdt', 'pol=0', tag='a')}\n"
            f"{poles(2, 'cp', 0, 'relay_spdt', 'pol=1', tag='b')}\n"
            f"Vt cq 0 -5\n{poles(3, 'cq', 0, 'TQ2_5V', n=2, tag='c')}")
    d, _ = sim(body, "pol", ".op")
    check("non-polarised, -12 V: NO closed (V)", float(d["v(noa1)"][0]), 1000 / 1000.05, 1e-3)
    check("polarised pol=1, -12 V: NO open (V)", float(d["v(nob1)"][0]), 0, 1e-3)
    check("TQ2_5V (polarised), -5 V: NO open (V)", float(d["v(noc1)"][0]), 0, 1e-3)

    # 3. timing: low-side switch on at 1 ms, off at 31 ms; 60 V clamp (transistor
    #    avalanche, "no diode") or a 1N4148 across the coil
    t_on, t_off = 1.0005e-3, 31.0015e-3
    base = ("Vs vcc 0 12\nSd cn 0 g 0 SWD\n.model SWD SW(Ron=1m Roff=100Meg Vt=0.5)\n"
            "Vg g 0 PULSE(0 1 1m 1u 1u 30m 100m)\n" + poles(1, "vcc", "cn", "relay_spdt"))
    res = {}
    for tag, supp in (("nodiode", "Dz 0 cn DZ\n.model DZ D(Is=1e-14 BV=60 IBV=1m)"),
                      ("diode", f"Df cn vcc 1N4148\n{D4148}")):
        d, _ = sim(base + "\n" + supp, tag, ".tran 0 60m 0 2u")
        t = d["time"]
        res[tag] = dict(
            nc_break=cross(t, d["v(nc1)"], 0.5, rising=False) - t_on,
            no_make=cross(t, d["v(no1)"], 0.5) - t_on,
            no_break=cross(t, d["v(no1)"], 0.5, after=t_off, rising=False) - t_off,
            nc_make=cross(t, d["v(nc1)"], 0.5, after=t_off) - t_off,
            vpk=float(np.max(d["v(cn)"])))
    r = res["nodiode"]
    Tmon = (4e-3 - Lo / R * math.log(1 / (1 - 0.65))) / 0.85
    check("operate time (on -> NO makes), ms", r["no_make"] * 1e3, 4.0, 0.08)
    check("break-before-make gap on operate, ms", (r["no_make"] - r["nc_break"]) * 1e3,
          (0.85 - 0.15 - 0.02) * Tmon * 1e3, 0.05)
    check("break-before-make gap on release (NO breaks .. NC makes), ms",
          (r["nc_make"] - r["no_break"]) * 1e3, (0.85 - 0.02 - 0.15) * 2e-3 / 0.85 * 1e3, 0.05)
    # no diode: the clamp takes the current down at 60 V, then the armature travels Trel
    i0 = Vn / R
    tdec = Lc / R * math.log((i0 + 48 / R) / (0.2 * i0 + 48 / R))
    check("release, 60 V clamp (off -> NC makes), ms", r["nc_make"] * 1e3,
          (tdec + 2e-3) * 1e3, 0.08)
    check("  flyback peak, 60 V clamp, V", r["vpk"], 60, 1.5)
    r2 = res["diode"]
    tdec_d = decay_time(Lc, R, i0, 0.2 * i0, diode=True)
    check("release with 1N4148 flyback (off -> NC makes), ms", r2["nc_make"] * 1e3,
          (tdec_d + 2e-3) * 1e3, 0.12)
    check("  flyback peak with diode, V", r2["vpk"], 12.75, 0.3)
    note(f"  the diode lengthens the release {r2['nc_make'] / r['nc_make']:.2f}x: "
         f"coil current decays with Lc/R = {Lc / R * 1e3:.2f} ms to the drop-out level first")

    # 4. contact resistance: 10 mA through a closed NO, 1 uA into the open NC
    d, _ = sim("Vs cp 0 12\nX1 cp 0 0 nc no relay_spdt Ron=50m\nI1 0 no 10m\nI2 0 nc 1u",
               "ron", ".op")
    check("Ron (NO closed), ohm", float(d["v(no)"][0]) / 10e-3, 0.05, 1e-6)
    check("Roff (NC open), Gohm", float(d["v(nc)"][0]) / 1e-6 / 1e9, 1.0, 0.01)

    # 5. single-coil latching (defaults Vnom=5 R=250 pset=prst=0.6 Top=Trel=3m):
    #    +5 V pulse sets, -5 V resets, a 2.5 V (50 %) pulse does nothing
    pwl = ("PWL(0 0 5m 0 5.001m 5 15m 5 15.001m 0 50m 0 50.001m -5 60m -5 60.001m 0 "
           "100m 0 100.001m 2.5 110m 2.5 110.001m 0)")
    d, _ = sim(f"Vs cp 0 {pwl}\n{poles(1, 'cp', 0, 'relay_latch_dpdt', n=2)}",
               "latch", ".tran 0 140m 0 5u")
    t = d["time"]
    check("latch: set time (+pulse -> NO makes), ms",
          (cross(t, d["v(no1)"], 0.5) - 5.0005e-3) * 1e3, 3.0, 0.08)
    check("latch: holds set with no coil current (NO, V)",
          float(np.interp(45e-3, t, d["v(no1)"])), 1, 1e-3)
    check("latch: reset time (-pulse -> NC makes), ms",
          (cross(t, d["v(nc1)"], 0.5, after=50e-3) - 50.0005e-3) * 1e3, 3.0, 0.08)
    check("latch: 50 % pulse does not set (NC, V)", float(np.interp(135e-3, t, d["v(nc1)"])),
          1, 1e-3)
    d, _ = sim(f"Vs cp 0 0\n{poles(1, 'cp', 0, 'relay_latch_dpdt', 'state0=1', n=2)}",
               "latch0", ".op")
    check("latch: state0=1 at the operating point (NO, V)", float(d["v(no1)"][0]), 1, 1e-3)

    # 6. dual-coil latching preset TQ2-L2-5V: set coil pulse, then reset coil pulse
    body = ("Vs sp 0 PWL(0 0 5m 0 5.001m 5 15m 5 15.001m 0)\n"
            "Vr rp 0 PWL(0 0 50m 0 50.001m 5 60m 5 60.001m 0)\n"
            "X1 sp 0 rp 0 com1 nc1 no1 com2 nc2 no2 TQ2_L2_5V\nVc1 com1 0 1\n"
            "Rnc1 nc1 0 1k\nRno1 no1 0 1k\nVc2 com2 0 1\nRnc2 nc2 0 1k\nRno2 no2 0 1k")
    d, _ = sim(body, "latch2", ".tran 0 100m 0 5u")
    t = d["time"]
    check("TQ2-L2-5V: set coil current, mA (datasheet 40)",
          -float(np.interp(14e-3, t, d["i(vs)"])) * 1e3, 40, 0.5)
    check("TQ2-L2-5V: set time, ms (datasheet approx. 2, max 3)",
          (cross(t, d["v(no1)"], 0.5) - 5.0005e-3) * 1e3, 2.0, 0.1)
    check("TQ2-L2-5V: holds set (NO2, V)", float(np.interp(45e-3, t, d["v(no2)"])), 1, 1e-3)
    check("TQ2-L2-5V: reset time, ms (datasheet approx. 2, max 3)",
          (cross(t, d["v(nc1)"], 0.5, after=50e-3) - 50.0005e-3) * 1e3, 2.0, 0.1)

    # 7. presets: rated coil current (.op) and operate time (step at 1 ms)
    presets = {  # name: (Vnom, datasheet rated current A, Top s)
        "TQ2_5V": (5, 28.1e-3, 2.2e-3), "TQ2_12V": (12, 11.7e-3, 2.2e-3),
        "G5V_2_DC5": (5, 100e-3, 3.5e-3), "G5V_2_DC12": (12, 41.7e-3, 3.5e-3),
        "G5V_2_DC24": (24, 20.8e-3, 3.5e-3), "G6K_2_DC5": (5, 21.1e-3, 1.5e-3),
        "G6K_2_DC12": (12, 9.1e-3, 1.5e-3), "F40_52_12V": (12, 55e-3, 7e-3),
        "F40_52_24V": (24, 27e-3, 7e-3)}
    body = []
    for k, (p, (v, _, _)) in enumerate(presets.items()):
        body += [f"V{k} c{k} 0 PWL(0 0 1m 0 1.001m {v})",
                 poles(k, f"c{k}", 0, p, n=2, tag=f"p{k}_")]
    d, _ = sim("\n".join(body), "presets", ".tran 0 40m 0 5u")
    t = d["time"]
    for k, (p, (v, irated, top)) in enumerate(presets.items()):
        i = -float(np.interp(39.9e-3, t, d[f"i(v{k})"]))
        check(f"{p}: coil current at {v} V, mA", i * 1e3, irated * 1e3, 0.015 * irated * 1e3)
        check(f"{p}: operate time, ms", (cross(t, d[f"v(nop{k}_1)"], 0.5) - 1.0005e-3) * 1e3,
              top * 1e3, 0.04 * top * 1e3)

    # 8. TQ2-12V operate time vs coil voltage, against Panasonic ASCTB14E p.9 fig. 6
    #    (TQ2SA-12V, 6 pcs): band read off the graph at 80/100/120 %V
    graph = {0.8: (2.8, 3.1), 1.0: (2.1, 2.45), 1.2: (1.7, 1.85)}
    body = []
    for k, f in enumerate(graph):
        body += [f"V{k} c{k} 0 PWL(0 0 1m 0 1.001m {12 * f})",
                 poles(k, f"c{k}", 0, "TQ2_12V", n=2, tag=f"q{k}_")]
    d, _ = sim("\n".join(body), "tqv", ".tran 0 15m 0 2u")
    t = d["time"]
    for k, (f, (lo, hi)) in enumerate(graph.items()):
        top = (cross(t, d[f"v(noq{k}_1)"], 0.5) - 1.0005e-3) * 1e3
        check(f"TQ2-12V operate time at {f * 100:.0f} %V, ms (graph {lo}..{hi})", top,
              (lo + hi) / 2, (hi - lo) / 2 + 0.05)

    # 9. .ac: signal through the NC contact of an unpowered relay into 1k
    d, _ = sim("V1 in 0 AC 1\nR1 in com 1k\nX1 cp 0 com nc no relay_spdt Ron=50m\n"
               "Vc cp 0 0\nR2 nc 0 1k\nR3 no 0 1k", "ac", ".ac dec 5 20 20k")
    g = np.abs(d["v(nc)"])
    check(".ac through NC, max |gain| error", float(np.max(np.abs(g - 1000 / 2000.05))), 0, 1e-6)

    # 10. the demo schematic netlists (asc2net) and switches channels
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_relay.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib relay.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=120)
    t = d["time"]
    w1 = (t > 2e-3) & (t < 9e-3)
    w2 = (t > 20e-3) & (t < 39e-3)
    check("demo: OUT = CLEAN before the footswitch, max |err| V",
          float(np.max(np.abs(d["v(out)"][w1] - d["v(clean)"][w1]))), 0, 1e-3)
    check("demo: OUT = LEAD after it, max |err| V",
          float(np.max(np.abs(d["v(out)"][w2] - d["v(lead)"][w2]))), 0, 1e-3)

    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, ok in ROWS:
        if got is None:
            print(name)
        else:
            print(f"{name:<{w}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<8.3g} "
                  f"{'ok' if ok else 'FAIL'}")
    print(f"\n{sum(r[1] is not None for r in ROWS) - FAIL}/"
          f"{sum(r[1] is not None for r in ROWS)} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
