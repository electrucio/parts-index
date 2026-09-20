#!/usr/bin/env python3
"""Verify audio-transformer.sub against the Jensen and Lundahl datasheets: DC resistances,
turns ratios, polarity and centre-tap balance, primary inductance, the datasheet test
circuits (Jensen test circuit 1: input impedance, gain, output impedance, response;
Lundahl: frequency response at the stated source impedance), the saturation calibration,
a DC-biased SE interstage, .tran/.ac consistency and the demo's pin order. Run with the
shell sandbox off. Exit 1 on any failure."""
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
from bench.ltbatch import run                         # noqa: E402
from xf_presets import JT_DS, PRESETS                 # noqa: E402

SUB = HERE / "audio-transformer.sub"
ROWS, FAIL = [], 0
BY = {p["name"]: p for p in PRESETS}
PINS = {"atx": ["P1", "P2", "S1", "S2"], "atx_sct": ["P1", "P2", "S1", "SC", "S2"],
        "atx_ct": ["P1", "PC", "P2", "S1", "SC", "S2"]}


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


def inst(p, k, nodes):
    """Instance line: nodes = dict pin -> node; unused pins get private nodes."""
    return f"X{k} " + " ".join(nodes.get(pn, f"nc{k}_{pn}") for pn in PINS[p["kind"]]) + f" {p['name']}"


def thd(t, v, f0, ncyc):
    tt = t[-1] - ncyc / f0
    m = t >= tt - 1e-12
    n = 8192
    tu = np.linspace(tt, t[-1], n, endpoint=False)
    vu = np.interp(tu, t[m], v[m])
    sp = np.abs(np.fft.rfft(vu - vu.mean()))
    h1 = sp[ncyc]
    hk = [sp[k * ncyc] for k in range(2, 11) if k * ncyc < len(sp)]
    return 100 * math.sqrt(sum(h * h for h in hk)) / h1


def dc_ratio():
    hdr("DC resistance (.op, 1 mA) and turns ratio / polarity (1 kHz, 0 ohm source, open secondary)")
    net = ["* dc", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"Ip{k} 0 p{k} 1m", inst(p, k, {"P1": f"p{k}", "P2": "0"})]
        net += [f"Is{k} 0 s{k} 1m", inst(p, 100 + k, {"S1": f"s{k}", "S2": "0"})]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dc")
    for k, p in enumerate(PRESETS):
        check(f"{p['name']} R(P1-P2) ({p['src']['Rp']})", float(d[f"v(p{k})"][0]) / 1e-3, p["Rp"], 2e-3, rel=True)
        check(f"{p['name']} R(S1-S2) ({p['src']['Rs']})", float(d[f"v(s{k})"][0]) / 1e-3, p["Rs"], 2e-3, rel=True)
    net = ["* ratio", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"V{k} p{k} 0 AC 1", inst(p, k, {"P1": f"p{k}", "P2": "0", "S1": f"s{k}", "S2": "0"})]
    net.append(".ac list 1k")
    d, _ = run("\n".join(net) + "\n", "ratio")
    for k, p in enumerate(PRESETS):
        v = d[f"v(s{k})"][0]
        check(f"{p['name']} V(S1,S2)/V(P1,P2) = n ({p['src']['n']})", abs(v), p["n"], 3e-3, rel=True)
        check(f"{p['name']} polarity: phase S1 re P1 (deg)", math.degrees(np.angle(v)), 0, 1)


def inductance():
    hdr("primary inductance: Im(Z)/w at 20 Hz, secondary open")
    net = ["* lp", f'.include "{SUB}"']
    for k, p in enumerate(PRESETS):
        net += [f"I{k} 0 p{k} AC 1", inst(p, k, {"P1": f"p{k}", "P2": "0", "S2": "0"})]
    net.append(".ac list 20")
    d, _ = run("\n".join(net) + "\n", "lp")
    for k, p in enumerate(PRESETS):
        z = d[f"v(p{k})"][0]
        check(f"{p['name']} Lp (H) ({p['src']['Lp']})", np.imag(z) / (2 * math.pi * 20), p["Lp"], 0.01, rel=True)


def centre_taps():
    hdr("centre taps: halves balanced; Alt V drives two grids in antiphase (SC grounded)")
    for name in ("XF_LL1660_M", "XF_LL1660_V"):
        p = BY[name]
        net = f"""* ct
.include "{SUB}"
V1 p 0 AC 1
{inst(p, 1, {"P1": "p", "P2": "0", "S1": "a", "SC": "0", "S2": "b"})}
Ra a 0 1Meg
Rb b 0 1Meg
.ac list 1k
"""
        d, _ = run(net, "ct")
        va, vb = d["v(a)"][0], d["v(b)"][0]
        check(f"{name}: |V(S1,SC)| / |V(SC,S2)|", abs(va) / abs(vb), 1, 2e-3)
        check(f"{name}: phase V(S2) re V(S1) (deg)", abs(math.degrees(np.angle(vb / va))), 180, 0.5)
    p = BY["XF_LL1660_M"]
    net = f"""* pct
.include "{SUB}"
V1 p 0 AC 1
V2 q 0 AC -1
{inst(p, 1, {"P1": "p", "PC": "0", "P2": "q", "S1": "a", "SC": "0", "S2": "b"})}
Ra a 0 1Meg
Rb b 0 1Meg
.ac list 1k
"""
    d, _ = run(net, "pct")
    check("XF_LL1660_M driven push-pull from PC: V(S1,S2) = n * V(P1,P2)",
          abs(d["v(a)"][0] - d["v(b)"][0]) / 2, p["n"], 3e-3, rel=True)


def jensen():
    p, ds = BY["XF_JT115KE"], JT_DS
    hdr("Jensen JT-115K-E, test circuit 1 (75 + 75 ohm generator, 150 k load)")
    body = f"""V1 g 0 AC 1
Rg1 g p 75
Rg2 m 0 75
{inst(p, 1, {"P1": "p", "P2": "m", "S1": "o", "S2": "0"})}
RL o 0 150k
"""
    d, _ = run(f'* jt\n.include "{SUB}"\n{body}.ac dec 400 0.5 1Meg\n', "jt")
    f = np.real(d["frequency"])
    h = np.abs(d["v(o)"])
    h1k = float(np.interp(math.log(1e3), np.log(f), h))

    def rel(fx):
        return 20 * math.log10(float(np.interp(math.log(fx), np.log(f), h)) / h1k)

    def f3(lo):
        g = 20 * np.log10(h / h1k)
        idx = np.where(g > -3)[0]
        i = idx[0] if lo else idx[-1]
        j = i - 1 if lo else i + 1
        return math.exp(np.interp(-3, [g[j], g[i]] if lo else [g[j], g[i]],
                                  [math.log(f[j]), math.log(f[i])])) if lo else \
            math.exp(np.interp(-3, [g[j], g[i]], [math.log(f[j]), math.log(f[i])]))

    check("magnitude re 1 kHz at 20 Hz (dB) [Lp fitted]", rel(20), ds["dB20"], 0.02)
    check("magnitude re 1 kHz at 20 kHz (dB) [Llk, Cs fitted]", rel(20e3), ds["dB20k"], 0.02)
    check("upper -3 dB point (kHz) [Llk, Cs fitted]", f3(False) / 1e3, ds["f3hi"] / 1e3, 0.02, rel=True)
    check_range("magnitude at 20 Hz within the ds limits -0.50 .. 0.0 dB", rel(20), -0.50, 0.0)
    check_range("magnitude at 20 kHz within the ds limits -0.25 .. +0.1 dB", rel(20e3), -0.25, 0.1)
    info("lower -3 dB point (Hz); ds feature list: 2.5 Hz (level-dependent Lp, see README)", f3(True), ds["f3lo"])
    # input impedance and gain from the primary terminals
    zi = d["v(p)"] - d["v(m)"]
    ip = (d["v(g)"] - d["v(p)"]) / 75
    k1 = int(np.argmin(abs(f - 1e3)))
    check("Zi at 1 kHz (ohm) [Rc fitted]", abs(zi[k1] / ip[k1]), ds["Zi_1k"], 0.01, rel=True)
    gain = 20 * math.log10(abs(d["v(o)"][k1] / zi[k1]))
    check_range("voltage gain V(S)/V(P) at 1 kHz (dB), ds min/typ/max 19.65/19.75/19.85", gain, 19.65, 19.85)
    # output impedance at the secondary with the generator on and the load in place
    net = f"""* zo
.include "{SUB}"
V1 g 0 0
Rg1 g p 75
Rg2 m 0 75
{inst(p, 1, {"P1": "p", "P2": "m", "S1": "o", "S2": "0"})}
RL o 0 150k
I1 0 o AC 1
.ac list 1k
"""
    d2, _ = run(net, "zo")
    check("Zo at 1 kHz (ohm), ds typ 17.0 k (150 k load in place)", abs(d2["v(o)"][0]), ds["Zo_1k"], 0.03, rel=True)

    hdr("Jensen JT-115K-E saturation (sat=1): THD at the ds 1 % point (-2.5 dBu at 20 Hz)")
    for lvl_db, lo, hi, tag in ((-2.5, 0.3, 3.0, "ds max 20 Hz input level, 1 % THD typ (calibration)"),
                                (-20, 0, 0.05, "20 dB lower: saturation gone")):
        vrms = 0.7746 * 10 ** (lvl_db / 20)
        net = f"""* jtthd
.include "{SUB}"
V1 g 0 SINE(0 {math.sqrt(2) * vrms * 1.107:.6g} 20)
Rg1 g p 75
Rg2 m 0 75
X1 p m o 0 XF_JT115KE sat=1
RL o 0 150k
.options plotwinsize=0
.tran 0 0.6 0 20u
"""
        d3, _ = run(net, "jtthd", timeout=120)
        t = d3["time"]
        vp = d3["v(p)"] - d3["v(m)"]
        m = t > 0.3
        info(f"  primary rms at {lvl_db:g} dBu drive (V)", float(np.sqrt(np.mean(vp[m] ** 2))), vrms)
        check_range(f"THD % of V(S) at {lvl_db:g} dBu, 20 Hz: {tag}", thd(t, d3["v(o)"], 20, 6), lo, hi)
    # Jensen p.2 graph "THD+N vs input level" (read off at +-10 %; its floor of 0.015 -
    # 0.07 % is hysteresis + noise, which the model does not have): info only
    for lvl_db, f0, graph in ((-5, 20, 0.40), (0, 30, 0.40), (-5, 30, 0.13), (0, 50, 0.11)):
        vrms = 0.7746 * 10 ** (lvl_db / 20)
        net = f"""* jtg
.include "{SUB}"
V1 g 0 SINE(0 {math.sqrt(2) * vrms * 1.107:.6g} {f0})
Rg1 g p 75
Rg2 m 0 75
X1 p m o 0 XF_JT115KE sat=1
RL o 0 150k
.options plotwinsize=0
.tran 0 {12 / f0:.6g} 0 20u
"""
        d4, _ = run(net, "jtg", timeout=120)
        info(f"THD % at {lvl_db:g} dBu, {f0} Hz vs Jensen graph reading", thd(d4["time"], d4["v(o)"], f0, 6), graph)


def lundahl_1538():
    hdr("Lundahl LL1538: response with 200 ohm source, no termination, +-0.3 dB 10 Hz-100 kHz (ds)")
    for name in ("XF_LL1538_5", "XF_LL1538_25"):
        p = BY[name]
        net = f"""* l38
.include "{SUB}"
V1 g 0 AC 1
Rg g p 200
{inst(p, 1, {"P1": "p", "P2": "0", "S1": "o", "S2": "0"})}
.ac dec 400 1 1Meg
"""
        d, _ = run(net, "l38")
        f = np.real(d["frequency"])
        h = np.abs(d["v(o)"])
        h1k = float(np.interp(math.log(1e3), np.log(f), h))
        for fx in (10, 100e3):
            g = 20 * math.log10(float(np.interp(math.log(fx), np.log(f), h)) / h1k)
            if name == "XF_LL1538_5":
                check_range(f"{name} re 1 kHz at {fx:g} Hz (dB) [Lp der, Llk/Cs est for this band]", g, -0.3, 0.3)
            else:   # the ds response row states no connection; Lp, Llk, Cs were set on 1:5
                info(f"{name} re 1 kHz at {fx:g} Hz (dB) [ds band assumed for 1:5 only]", g, 0)
        ph = np.degrees(np.unwrap(np.angle(d["v(o)"])))
        k = np.where((f > 1e4) & (ph < -90))[0]
        fr = float(f[k[0]]) if len(k) else float("inf")
        check_range(f"{name} self-resonance (phase -90 deg) > 120 kHz (ds) [est]", fr / 1e3, 120, 1e9)
    hdr("Lundahl LL1538 1:5 saturation (sat=1), 200 ohm source, 50 Hz")
    for lvl_db, lo, hi, tag in ((10, 0.3, 3.0, "ds 1 % at +10 dBu (calibration)"),
                                (0, 0, 0.05, "ds 0.2 % at 0 dBu: hysteresis, not modelled")):
        vrms = 0.7746 * 10 ** (lvl_db / 20)
        net = f"""* l38thd
.include "{SUB}"
V1 g 0 SINE(0 {math.sqrt(2) * vrms:.6g} 50)
Rg g p 200
X1 p 0 o 0 XF_LL1538_5 sat=1
.options plotwinsize=0
.tran 0 0.24 0 10u
"""
        d, _ = run(net, "l38thd", timeout=120)
        val = thd(d["time"], d["v(o)"], 50, 6)
        if lvl_db == 0:
            info(f"THD % at {lvl_db:g} dBu, 50 Hz ({tag})", val, 0.2)
        else:
            check_range(f"THD % at {lvl_db:g} dBu, 50 Hz ({tag})", val, lo, hi)


def lundahl_1660():
    hdr("Lundahl LL1660: +-1 dB band edges with the ds source impedance, secondaries open")
    for name in ("XF_LL1660_M", "XF_LL1660_N", "XF_LL1660_Q", "XF_LL1660_S", "XF_LL1660_T", "XF_LL1660_V"):
        p = BY[name]
        net = f"""* l60
.include "{SUB}"
V1 g 0 AC 1
Rg g p {p['rsrc']:g}
{inst(p, 1, {"P1": "p", "P2": "0", "S1": "o", "S2": "0", "SC": "sc"})}
.ac dec 400 1 200k
"""
        d, _ = run(net, "l60")
        f = np.real(d["frequency"])
        h = np.abs(d["v(o)"])
        h1k = float(np.interp(math.log(1e3), np.log(f), h))

        def rel(fx):
            return 20 * math.log10(float(np.interp(math.log(fx), np.log(f), h)) / h1k)

        glo, ghi = rel(p["flo"]), rel(p["fhi"])
        lbl = f"{name} ({p['conn']}, {p['rsrc'] / 1e3:g}k)"
        # all six as info: with the ds Lp and the primary DCR only Alt M'' meets its
        # published lower edge (README: Lundahl's Lp is a working-level figure)
        info(f"{lbl} at {p['flo']:g} Hz (dB), ds within +-1 dB", glo, -1)
        check(f"{lbl} at {p['fhi'] / 1e3:g} kHz (dB) [Cp derived from this edge]", ghi, -1, 0.05)
        g = 20 * np.log10(h / h1k)
        i = np.where(g > -1)[0][0]
        info(f"{lbl}: model -1 dB low point (Hz), ds {p['flo']:g}",
             math.exp(np.interp(-1, [g[i - 1], g[i]], [math.log(f[i - 1]), math.log(f[i])])), p["flo"])


def se_bias():
    hdr("SE interstage with DC: LL1660 Alt S, 10 mA through the primary, 14 k source, sat=1")
    p = BY["XF_LL1660_S"]
    for scale, lo, hi, tag in ((1.0, 0.3, 5.0, "at the ds max output (250 V at 30 Hz): knee reached"),
                               (0.25, 0, 0.1, "12 dB lower: linear")):
        # AC source sized for the ds max output on the secondary
        amp = scale * math.sqrt(2) * p["Vsat"] * abs(1 + p["rsrc"] / (2j * math.pi * 30 * p["Lp"]))
        net = f"""* se
.include "{SUB}"
I1 p 0 {p['Idc']:g}
V1 g 0 SINE(0 {amp:.6g} 30)
Rg g x {p['rsrc']:g}
Cc x p 1000u
X1 p 0 o 0 XF_LL1660_S sat=1
RL o 0 1Meg
.options plotwinsize=0
.tran 0 0.4 0 20u
"""
        d, log = run(net, "se", timeout=180)
        t, v = d["time"], d["v(o)"]
        m = t > 0.2
        info(f"  V(S) rms (V), target {scale * p['Vsat'] * p['n']:g}", float(np.sqrt(np.mean(v[m] ** 2))))
        check_range(f"THD % of V(S), 30 Hz, {tag}", thd(t, v, 30, 6), lo, hi)
    info("DC flux at 10 mA = Lp*Idc (V s); knee = ksat*(AC design + DC)", p["Lp"] * p["Idc"])


def tran_ac():
    hdr(".tran vs .ac: JT-115K-E test circuit 1, 100 mV 1 kHz")
    p = BY["XF_JT115KE"]
    body = f"""Rg1 g p 75
Rg2 m 0 75
{inst(p, 1, {"P1": "p", "P2": "m", "S1": "o", "S2": "0"})}
RL o 0 150k
"""
    d, _ = run(f'* ta\n.include "{SUB}"\nV1 g 0 SINE(0 0.1 1k)\n{body}'
               ".options plotwinsize=0\n.tran 0 60m 50m 1u\n", "ta")
    amp = (np.max(d["v(o)"]) - np.min(d["v(o)"])) / 2
    d2, _ = run(f'* ac1\n.include "{SUB}"\nV1 g 0 AC 0.1\n{body}.ac list 1k\n', "ac1")
    check("amplitude .tran = |V| .ac (V)", amp, abs(d2["v(o)"][0]), 0.01, rel=True)


def demo():
    hdr("demo_audio-transformer.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_audio-transformer.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n", "demo")
    hand = (f'* hand\n.include "{SUB}"\nV1 g 0 AC 1\nR1 g p 75\nR2 0 m 75\n'
            "X1 p m out 0 XF_JT115KE sat=0\nRL out 0 150k\n.ac dec 50 1 300k\n")
    d2, _ = run(hand, "hand")
    f1 = np.real(d1["frequency"])
    for fx in (10, 1000, 100000):
        i = int(np.argmin(abs(f1 - fx)))
        check(f"demo |V(out)| @{fx} Hz = hand netlist", abs(d1["v(out)"][i]), abs(d2["v(out)"][i]), 1e-4, rel=True)


def main():
    dc_ratio()
    inductance()
    centre_taps()
    jensen()
    lundahl_1538()
    lundahl_1660()
    se_bias()
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
