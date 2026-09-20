#!/usr/bin/env python3
"""Verify output-transformer.sub: DC resistances, turns ratios, taps, polarity,
reflected impedance, -3 dB corners against the equivalent-circuit formulas, every
Hammond preset against its sheet (DCR, L, leakage, response graph), flux saturation,
and convergence with real tubes. Run with the shell sandbox off. Exit 1 on failure."""
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
from fit_presets import PARTS          # noqa: E402  (Hammond graph readings)
from ot_presets import PRESETS, model_params, pins   # noqa: E402

SUB = HERE / "output-transformer.sub"
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


def hdr(title):
    ROWS.append((f"-- {title}", None, None, "", ""))


def thd(t, v, f, ncyc=4):
    T = 1 / f
    tt = np.linspace(t[-1] - ncyc * T, t[-1], ncyc * 256, endpoint=False)
    vv = np.interp(tt, t, v)
    vv = vv - vv.mean()
    X = np.abs(np.fft.rfft(vv))
    return 100 * math.sqrt(sum(X[ncyc * k] ** 2 for k in range(2, 11))) / X[ncyc], 2 * X[ncyc] / len(tt)


def acval(d, node, f):
    fr = np.real(d["frequency"])
    i = int(np.argmin(abs(fr - f)))
    return d[node][i]


# ------------------------------------------------------------------ generic physics
def generic():
    hdr("generic: ratios, UL tap, polarity, impedance (ot_pp_ul_tap, sat=0)")
    Za, Z = 6600, (4, 8, 16)
    net = [f"* ratios", f'.include "{SUB}"',
           # low-impedance drive, open secondary: V(tap)/V(P1,P2) = sqrt(Z/Za)
           "V1 p1 0 AC 1", "X1 p1 g1 ct g2 0 0 s1 s2 s3 ot_pp_ul_tap Za=6600 Z1=4 Z2=8 Z3=16 ul=0.4"
           " Rpri=1m R1=1m R2=2m R3=3m Llk=1u Cw=1p sat=0",
           # reflected impedance: 16 ohm on S3, current drive -> Zin
           "I2 0 q1 AC 1", "X2 q1 h1 qct h2 0 0 t1 t2 t3 ot_pp_ul_tap Za=6600 Z1=4 Z2=8 Z3=16 ul=0.4"
           " Rpri=1m R1=1m R2=2m R3=3m Llk=1u Cw=1p Qc=1e6 Lp=1e4 sat=0", "RL t3 0 16",
           ".ac list 1k"]
    d, _ = run("\n".join(net) + "\n", "ratio")
    for k, z in enumerate(Z, 1):
        r = acval(d, f"v(s{k})", 1e3)
        check(f"tap S{k} ratio sqrt({z}/{Za})", abs(r), math.sqrt(z / Za), 1e-3, rel=True)
    check("S3 in phase with P1 (deg)", math.degrees(np.angle(acval(d, "v(s3)", 1e3))), 0, 0.5)
    ul = acval(d, "v(g1)", 1e3) - acval(d, "v(ct)", 1e3)
    pl = 1 - acval(d, "v(ct)", 1e3)
    check("UL tap V(G1,CT)/V(P1,CT) = ul", abs(ul / pl), 0.4, 1e-3, rel=True)
    check("CT at half the primary voltage", abs(acval(d, "v(ct)", 1e3)), 0.5, 1e-3, rel=True)
    check("Zin with Zs on S3 = Za", abs(acval(d, "v(q1)", 1e3)), 6600, 2e-3, rel=True)

    hdr("generic: -3 dB corners vs formula (Rs = Za, RL = Zs, no Cw, no loss)")
    net = [f"* corners", f'.include "{SUB}"',
           "V1 a 0 AC 1", "Rs a p1 6600",
           "X1 p1 ct p2 sp 0 ot_pp Za=6600 Zs=8 Lp=25 Llk=12m Cw=1f Rpri=1m Rsec=1m Qc=1e9 sat=0",
           "RL sp 0 8", "Vp2 p2 0 0", "Rct ct 0 1G",
           "V2 b 0 AC 1", "Rs2 b q1 6600",
           "X2 q1 qct q2 tp 0 ot_pp Za=6600 Zs=8 flow=25 fhigh=40k Cw=1f Rpri=1m Rsec=1m Qc=1e9 sat=0",
           "RL2 tp 0 8", "Vq2 q2 0 0", "Rqct qct 0 1G",
           ".ac dec 400 1 1Meg"]
    d, _ = run("\n".join(net) + "\n", "corners")
    f = np.real(d["frequency"])
    for node, lo_want, hi_want, lab in (("v(sp)", 3300 / (2 * math.pi * 25), 13200 / (2 * math.pi * 12e-3), "Lp=25 Llk=12m"),
                                        ("v(tp)", 25, 40e3, "flow=25 fhigh=40k")):
        v = np.abs(d[node])
        db = 20 * np.log10(v / v[np.argmin(abs(f - 1e3))]) + 3.0103
        s = np.sign(db)
        cross = np.nonzero(s[:-1] != s[1:])[0]          # the two -3 dB crossings
        fx = [math.exp(np.interp(0, sorted(db[i:i + 2]), np.log(f[i:i + 2])[np.argsort(db[i:i + 2])]))
              for i in cross]
        check(f"f-3dB low  {lab} (Hz)", fx[0], lo_want, 0.01, rel=True)
        check(f"f-3dB high {lab} (Hz)", fx[-1], hi_want, 0.01, rel=True)


# ------------------------------------------------------------------ presets vs sheets
def presets_dc():
    hdr("presets: DC resistance vs Hammond sheet (.op)")
    net = [f"* dcr", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        pl = pins(p["base"])
        nodes = {q: f"n{k}_{q.lower()}" for q in pl}
        if p["base"].startswith("ot_se"):
            net += [f"Vb{k} {nodes['BP']} 0 0", f"Ip{k} 0 {nodes['P']} 10m"]
        else:
            net += [f"Vb{k} {nodes['CT']} 0 0", f"Ia{k} 0 {nodes['P1']} 10m", f"Ib{k} 0 {nodes['P2']} 10m"]
        net.append(f"X{k} " + " ".join(nodes[q] for q in pl) + f" {p['name']}")
        # secondary DCR on a second instance with the primary open (a secondary DC current
        # would otherwise bias the core and add n*lambda/1k volts to the primary reading)
        nb = {q: f"m{k}_{q.lower()}" for q in pl}
        net += [f"Rf{k} {nb[pl[0]]} 0 1G",
                f"Vs{k} {nb.get('COM', nb.get('SN'))} 0 0",
                f"Is{k} 0 {nb.get('S3', nb.get('SP'))} 100m",
                f"XB{k} " + " ".join(nb[q] for q in pl) + f" {p['name']}"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dcr")
    for k, p in enumerate(PRESETS):
        pl = pins(p["base"])
        nodes = {q: f"n{k}_{q.lower()}" for q in pl}
        sec = {q: f"m{k}_{q.lower()}" for q in pl}
        m = model_params(p)
        if p["base"].startswith("ot_se"):
            check(f"{p['name']} Rpri", float(d[f"v({nodes['P']})"][0]) / 10e-3, m["Rpri"], 1e-3, rel=True)
        else:
            if "Rp" in p:
                check(f"{p['name']} R(P1-CT)", float(d[f"v({nodes['P1']})"][0]) / 10e-3, p["Rp"][0], 1e-3, rel=True)
                check(f"{p['name']} R(CT-P2)", float(d[f"v({nodes['P2']})"][0]) / 10e-3, p["Rp"][1], 1e-3, rel=True)
            else:
                r = (float(d[f"v({nodes['P1']})"][0]) + float(d[f"v({nodes['P2']})"][0])) / 10e-3
                check(f"{p['name']} Rpri", r, m["Rpri"], 1e-3, rel=True)
        if "S3" in nodes:
            for j, q in enumerate(("S1", "S2", "S3")):
                r = float(d[f"v({sec[q]})"][0]) / 0.1
                want = p["Rt"][j]
                if want is None:
                    info(f"{p['name']} R(COM-{q}) [scaled]", r, m[f"R{j + 1}"])
                else:
                    check(f"{p['name']} R(COM-{q})", r, want, 2e-3, rel=True)
        else:
            r = float(d[f"v({sec['SP']})"][0]) / 0.1
            if p["Rt"][0] is not None:
                check(f"{p['name']} Rsec", r, p["Rt"][0], 2e-3, rel=True)
            else:
                info(f"{p['name']} Rsec [estimate]", r, m["Rsec"])


def presets_lp_llk():
    hdr("presets: primary L (secondary open) and leakage (secondary shorted) vs sheet")
    for mode in ("open", "short"):
        net = [f"* L {mode}", f'.include "{SUB}"']
        for k, p in enumerate(PRESETS):
            pl = pins(p["base"])
            nodes = {q: f"n{k}_{q.lower()}" for q in pl}
            se = p["base"].startswith("ot_se")
            a = nodes["P"] if se else nodes["P1"]
            # 1650 sheets measure one half-primary (plate to CT, other half open)
            if mode == "open" and p.get("half"):
                b = nodes["CT"]
            else:
                b = nodes["BP"] if se else nodes["P2"]
            net += [f"V{k} {a} 0 AC 1", f"Vg{k} {b} 0 0"]
            lo = nodes.get("COM", nodes.get("SN"))
            hi = nodes.get("S3", nodes.get("SP"))
            if mode == "short":
                net += [f"Rsh{k} {hi} {lo} 1u"]
            net.append(f"X{k} " + " ".join(nodes[q] for q in pl) + f" {p['name']} sat=0")
        net.append(".ac list 60 1k")
        d, _ = run("\n".join(net) + "\n", f"l{mode}")
        for k, p in enumerate(PRESETS):
            f = p["f_L"] if mode == "open" else 1e3
            y = -acval(d, f"i(v{k})", f)          # current into the transformer
            w = 2 * math.pi * f
            if mode == "open":
                L = -1 / (w * np.imag(y))          # parallel-model L, as an LCR meter reads it
                want = p["L_sheet"]
                check(f"{p['name']} L_app @{f:g} Hz{' (half)' if p.get('half') else ''} (H)", L, want, 0.02, rel=True)
            else:
                z = 1 / y
                L = np.imag(z) / w
                if p["Llk_src"] == "ds":
                    # the apparent value also holds (n^2 Rsec || Lp) and Cw, as on the meter
                    check(f"{p['name']} Llk @1 kHz (mH)", L * 1e3, p["Llk"] * 1e3, 0.05, rel=True)
                else:
                    info(f"{p['name']} Llk @1 kHz [{p['Llk_src']}; sheet {p.get('Llk_sheet', float('nan')) * 1e3:.4g}] (mH)",
                         L * 1e3, p["Llk"] * 1e3)


def presets_graph():
    hdr("presets: response re 1 kHz vs Hammond graph (Rs = graph Rs, 8 ohm load)")
    which = {"1760E": "OT_1760E", "1760H": "OT_1760H", "1760J": "OT_1760J", "1760L": "OT_1760L",
             "1760W": "OT_1760W", "1760C": "OT_1760C_5K", "1750N": "OT_1750N", "1750U": "OT_1750U",
             "1750Q": "OT_1750Q", "1750Y": "OT_1750Y", "1750V": "OT_1750V_8", "1650F": "OT_1650F",
             "1650H": "OT_1650H", "1650N": "OT_1650N", "1650R": "OT_1650R", "1650T": "OT_1650T",
             "125ESE": "OT_125ESE", "125CSE": "OT_125CSE"}
    byname = {p["name"]: p for p in PRESETS}
    net = [f"* graphs", f'.include "{SUB}"']
    for k, (part, name) in enumerate(which.items()):
        p, g = byname[name], PARTS[part]
        pl = pins(p["base"])
        nodes = {q: f"n{k}_{q.lower()}" for q in pl}
        se = p["base"].startswith("ot_se")
        a, b = (nodes["P"], nodes["BP"]) if se else (nodes["P1"], nodes["P2"])
        net += [f"V{k} s{k} 0 AC 1", f"Ra{k} s{k} {a} {g['Rs'] / 2}", f"Rb{k} 0 {b} {g['Rs'] / 2}"]
        lo = nodes.get("COM", nodes.get("SN"))
        if "S3" in nodes:     # the 8-ohm lug (16-ohm lug for the 125SE 5 k connection)
            out = nodes["S2"] if p["Z"][1] in (8, 16) and p["Z"] != (8, 16, 32) else nodes["S2"]
        else:
            out = nodes["SP"]
        net += [f"RL{k} {out} {lo} 8", f"Rgl{k} {lo} 0 1m"]
        if not se:
            net += [f"Rct{k} {nodes['CT']} 0 1G"]
        net.append(f"X{k} " + " ".join(nodes[q] for q in pl) + f" {name} sat=0")
        g["_out"] = (out, lo)
    net.append(".ac list 1k 20k 30k")
    d, _ = run("\n".join(net) + "\n", "graphs")
    for k, (part, name) in enumerate(which.items()):
        g = PARTS[part]
        out, lo = g["_out"]
        v = {f: acval(d, f"v({out})", f) - acval(d, f"v({lo})", f) for f in (1e3, 20e3, 30e3)}
        for f, dB, deg in g["pts"]:
            r = v[f] / v[1e3]
            mdb, mph = 20 * math.log10(abs(r)), math.degrees(np.angle(r))
            if f == 20e3:
                check(f"{name} {f / 1e3:g} kHz dB (graph)", mdb, dB, 0.5)
                if deg is not None:
                    check(f"{name} {f / 1e3:g} kHz deg (graph)", mph, deg, 5)
            else:
                info(f"{name} {f / 1e3:g} kHz dB (graph)", mdb, dB)
                if deg is not None:
                    info(f"{name} {f / 1e3:g} kHz deg (graph)", mph, deg)


# ------------------------------------------------------------------ saturation
def saturation():
    hdr("saturation: THD of V(S+) at rated power, Rs = Za (calibration target ~1 % at fsat)")
    rows = {}
    for base, extra, drive in (
            ("ot_se", "Za=5000 Zs=8 P=5 Lp=15 Llk=20m Rpri=250 Rsec=0.5 Idc=50m fsat=70",
             "Vb bp 0 300\nI1 p 0 SINE(50m {Iac} {f})\nRs p rc 5000\nCb rc bp 1m\nX1 p bp sp 0 ot_se {extra}"),
            ("ot_pp", "Za=6600 Zs=8 P=20 Lp=25 Llk=12m Rpri=300 Rsec=0.5 fsat=70",
             "I1 p1 p2 SINE(0 {Iac} {f})\nRs p1 p2 6600\nVb ct 0 0\nX1 p1 ct p2 sp 0 ot_pp {extra}")):
        Za = 5000 if base == "ot_se" else 6600
        P = 5 if base == "ot_se" else 20
        Iac = 2 * math.sqrt(2 * P * Za) / Za
        for f, sat in ((35, 1), (70, 1), (140, 1), (1000, 1), (35, 0)):
            T = 1 / f
            ex = extra + f" sat={sat}"
            net = (f"* sat\n.include \"{SUB}\"\n" + drive.format(Iac=Iac, f=f, extra=ex)
                   + f"\nRL sp 0 8\n.options plotwinsize=0\n.tran 0 {12 * T} 0 {T / 400}\n")
            d, _ = run(net, "sat")
            rows[(base, f, sat)] = thd(d["time"], d["v(sp)"], f)[0]
    for base in ("ot_se", "ot_pp"):
        check_range(f"{base} THD % at P, fsat=70 Hz", rows[(base, 70, 1)], 0.3, 3.0)
        check_range(f"{base} THD % at P, fsat/2 (2x flux)", rows[(base, 35, 1)], 8, 100)
        check_range(f"{base} THD % at P, 2 fsat", rows[(base, 140, 1)], 0, 0.5)
        check_range(f"{base} THD % at P, 1 kHz", rows[(base, 1000, 1)], 0, 0.1)
        check_range(f"{base} THD % at P, fsat/2, sat=0", rows[(base, 35, 0)], 0, 0.05)


# ------------------------------------------------------------------ real tubes
def tubes():
    hdr("convergence with real tubes (.tran), 6V6GT Reefman model")
    res = {}
    # push-pull fixed bias into the Deluxe Reverb OT, clean to hard clipping
    for amp in (10, 60):
        for f in (82, 1000):
            net = f"""* pp 6v6
.include "{SUB}"
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
RL s8 0 8
.options plotwinsize=0
.tran 0 {12 / f} 0 {1 / f / 200}
"""
            d, _ = run(net, "pp6v6")
            t, v = d["time"], d["v(s8)"]
            m = t > 6 / f
            res[("pp", amp, f)] = float(np.mean(v[m] ** 2) / 8)
    # ideal (stiff) supplies: class-B ceiling 2*(0.9*B+)^2/Za = 2*378^2/6600 = 43 W
    pmax = 2 * (0.9 * 420) ** 2 / 6600
    info("PP 6V6 -> 1760H, 10 V drive, 1 kHz: Pout (W)", res[("pp", 10, 1000)])
    check_range("PP 6V6 -> 1760H, 60 V drive (clipped), 1 kHz: Pout (W)", res[("pp", 60, 1000)], 10, 1.05 * pmax)
    check_range("PP 6V6 -> 1760H, clipped, 82 Hz: Pout (W)", res[("pp", 60, 82)], 10, 1.05 * pmax)
    # ultra-linear: screens on the 40 % taps of the 1650F
    net = f"""* ul 6v6
.include "{SUB}"
.include "{TUBE_6V6}"
Vbp ct 0 400
Vbias bias 0 -30
V1 gA bias SINE(0 25 1k)
V2 gB bias SINE(0 -25 1k)
XA pA sA gA 0 6V6GT
XB pB sB gB 0 6V6GT
Rsa sA ga1 470
Rsb sB gb1 470
X1 pA ga1 ct gb1 pB sp 0 OT_1650F
RL sp 0 8
.options plotwinsize=0
.tran 0 12m 0 5u
"""
    d, _ = run(net, "ul6v6")
    m = d["time"] > 6e-3
    check_range("UL 6V6 -> 1650F, 1 kHz: Pout (W)", float(np.mean(d["v(sp)"][m] ** 2) / 8), 3, 30)
    # single-ended class A: 6V6 on the Champ OT, bass drive -> saturation distortion
    for sat in (1, 0):
        net = f"""* se 6v6
.include "{SUB}"
.include "{TUBE_6V6}"
Vbp bp 0 350
Vbias bias 0 -14
V1 g bias SINE(0 12 40)
XA p bp g 0 6V6GT
X1 p bp 0 s3 s8 s16 OT_1760C sat={sat}
RL s8 0 8
.options plotwinsize=0
.tran 0 400m 0 20u
"""
        d, _ = run(net, "se6v6")
        res[("se", sat)] = thd(d["time"], d["v(s8)"], 40)[0]
    info("SE 6V6 -> 1760C, 40 Hz: THD % linear core", res[("se", 0)])
    check_range("SE 6V6 -> 1760C, 40 Hz: THD % saturating / linear", res[("se", 1)] / res[("se", 0)], 1.5, 1e3)


# ------------------------------------------------------------------ demo pin order
def demo():
    hdr("demo_output-transformer.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_output-transformer.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n", "demo")
    hand = f"""* hand
.include "{SUB}"
V1 a b SINE(0 200 100) AC 1
R1 a p1 3300
R2 b p2 3300
X1 p1 0 p2 0 s1 out s3 OT_1760H sat=1
RL out 0 8
.ac dec 20 10 100k
"""
    d2, _ = run(hand, "hand")
    for f in (100, 1e3, 10e3):
        check(f"demo |V(out)| @{f:g} Hz = hand netlist", abs(acval(d1, "v(out)", f)),
              abs(acval(d2, "v(out)", f)), 1e-4, rel=True)


def main():
    generic()
    presets_dc()
    presets_lp_llk()
    presets_graph()
    saturation()
    tubes()
    demo()
    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, st in ROWS:
        if got is None:
            print(name)
            continue
        print(f"{name:<{w}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<9} {st}")
    n = sum(1 for r in ROWS if r[4] in ("ok", "FAIL"))
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
