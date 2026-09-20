#!/usr/bin/env python3
"""Verify mains-transformer.sub: every Hammond preset against its sheet (no-load
voltages, no-load current, DC resistances, rated-load voltages, regulation), the
generic parametrisation (ratios, regulation from reg, leakage from xlk), saturation
(50 Hz on a 60 Hz part, over-voltage, inrush) and rectifier convergence. Run with the
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
from bench.ltbatch import run          # noqa: E402

SUB = HERE / "mains-transformer.sub"
ROWS, FAIL = [], 0
DREC = ".model DREC D(Is=10n Rs=0.05 N=1.8 Cjo=20p Bv=1000 Ibv=5u)"


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


def rms(t, v, t0):
    m = t >= t0
    return math.sqrt(np.trapezoid(v[m] ** 2, t[m]) / (t[m][-1] - t[m][0]))


# Sheet data (Hammond part sheets, https://www.hammfg.com/files/parts/pdf/<PART>.pdf):
# windings: name -> (pins +, -, N.L.V., rated V under load, rated I, DCR or None)
PRESETS = {
    "PT_370AX": dict(pins="P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2", Vp=120, f=60, Iex=80e-3,
                     Rp=19.45 * 21.36 / (19.45 + 21.36),
                     w={"HV": ("hv1", "hv2", 520.1, 480, 58e-3, 333.2),
                        "HVhalf": ("hv1", "hvct", 260.1, None, None, None),
                        "BIAS": ("bias", "hvct", 50.06, None, None, None),
                        "H": ("h1", "h2", 7.013, 6.3, 2.5, 0.150)}),
    "PT_370CX": dict(pins="P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2 A1 A2", Vp=120, f=60, Iex=77e-3,
                     Rp=14.39 * 15.81 / (14.39 + 15.81),
                     w={"HV": ("hv1", "hv2", 608.8, 550, 75e-3, 361.3),
                        "HVhalf": ("hv1", "hvct", 304.4, None, None, None),
                        "BIAS": ("bias", "hvct", 50.00, None, None, None),
                        "H": ("h1", "h2", 6.977, 6.3, 2.5, 0.112),
                        "A": ("a1", "a2", 6.977, 6.3, 0.6, 0.435)}),
    "PT_370FX": dict(pins="P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2 A1 A2", Vp=120, f=60, Iex=132e-3,
                     Rp=4.541 * 4.902 / (4.541 + 4.902),
                     w={"HV": ("hv1", "hv2", 586.3, 550, 173e-3, 106.0),
                        "HVhalf": ("hv1", "hvct", 293.2, None, None, None),
                        "BIAS": ("bias", "hvct", 50.13, None, None, None),
                        "H": ("h1", "h2", 6.835, 6.3, 5.0, 0.053),
                        "A": ("a1", "a2", 5.316, 5.0, 3.0, 0.063)}),
    "PT_290AX": dict(pins="P1 P2 HV1 HVCT HV2 H1 HCT H2 A1 A2", Vp=120, f=60, Iex=184e-3, Rp=3.927,
                     w={"HV": ("hv1", "hv2", 702.3, 650, 100e-3, 277.1),
                        "HVhalf": ("hv1", "hvct", 351.2, None, None, None),
                        "H": ("h1", "h2", 6.841, 6.3, 2.25, 0.108),
                        "A": ("a1", "a2", 5.416, 5.0, 3.0, 0.091)}),
    "PT_290EX": dict(pins="P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2", Vp=120, f=60, Iex=700e-3, Rp=1.291,
                     w={"HV": ("hv1", "hv2", 686.2, 660, 275e-3, 35.64),
                        "HVhalf": ("hv1", "hvct", 343.1, None, None, None),
                        "BIAS": ("bias", "hvct", 55.21, None, None, None),
                        "H": ("h1", "h2", 6.761, 6.4, 4.0, 0.038)}),
    "PT_1182N18": dict(pins="P1 P2 SA1 SA2 SB1 SB2", Vp=117, f=60, Iex=None, Rp=2.55,
                       w={"SA": ("sa1", "sa2", 19.39, 18, 4.44, 0.140),
                          "SB": ("sb1", "sb2", 19.39, 18, 4.44, 0.140)}),
}


def source(node, Vp, f, soft=True):
    if soft:
        return f"B{node} {node} 0 V={Vp * math.sqrt(2)}*sin(2*pi*{f}*time)*min(time/50m,1)"
    return f"V{node} {node} 0 SINE(0 {Vp * math.sqrt(2)} {f})"


def inst(name, k, pins, extra=""):
    nodes = [f"k{k}_{p.lower()}" if p not in ("P2",) else "0" for p in pins.split()]
    return f"X{k} " + " ".join(nodes) + f" {name} {extra}", {p.lower(): n for p, n in zip(pins.split(), nodes)}


# ------------------------------------------------------------------ presets vs sheets
def presets():
    hdr("presets: no-load voltages and no-load current vs Hammond sheet (soft start, 1 s)")
    for load in (False, True):
        net = ["* presets", f'.include "{SUB}"']
        maps = {}
        for k, (name, p) in enumerate(PRESETS.items()):
            line, m = inst(name, k, p["pins"])
            maps[name] = m
            net += [source(m["p1"], p["Vp"], p["f"]), line]
            for wn, (a, b, nlv, vr, ir, dcr) in p["w"].items():
                if load and vr is not None:
                    net.append(f"RL{k}{wn} {m[a]} {m[b]} {vr / ir:.6g}")
            # ground a point of each floating winding group (the subckt holds them at 1G)
        net += [".options plotwinsize=0", ".tran 0 1 0.8 20u"]
        d, _ = run("\n".join(net) + "\n", "load" if load else "nl")
        t = d["time"]
        for k, (name, p) in enumerate(PRESETS.items()):
            m = maps[name]
            for wn, (a, b, nlv, vr, ir, dcr) in p["w"].items():
                v = rms(t, d[f"v({m[a]})"] - d[f"v({m[b]})"], 0.8)
                if not load:
                    check(f"{name} N.L.V. {wn} (V)", v, nlv, 0.01, rel=True)
                elif vr is not None:
                    check(f"{name} {wn} at rated {ir:g} A, resistive (V)", v, vr, 0.05, rel=True)
                    p.setdefault("vfl", {})[wn] = v
            if not load and p["Iex"]:
                i = rms(t, d[f"i(b{m['p1']})"], 0.8)
                check(f"{name} no-load current (A)", i, p["Iex"], 0.05, rel=True)
            if not load and not p["Iex"]:
                info(f"{name} no-load current [Iex estimate 46 mA] (A)", rms(t, d[f"i(b{m['p1']})"], 0.8))
    p = PRESETS["PT_1182N18"]
    reg = (p["w"]["SA"][2] - p["vfl"]["SA"]) / p["vfl"]["SA"] * 100
    info("PT_1182N18 regulation, NLV 19.39 V vs model at 4.44 A (%) [sheet table 7.7]", reg, 7.7)
    check_range("PT_1182N18 regulation within 2 points of the published 7.7 %", reg, 5.7, 9.7)

    hdr("presets: DC resistance vs sheet (.op, 10 mA through each winding)")
    net = ["* dcr", f'.include "{SUB}"']
    maps = {}
    for k, (name, p) in enumerate(PRESETS.items()):
        line, m = inst(name, k, p["pins"])
        maps[name] = m
        net += [line, f"Ip{k} 0 {m['p1']} 10m"]
        for wn, (a, b, nlv, vr, ir, dcr) in p["w"].items():
            if dcr is not None:
                net += [f"Vz{k}{wn} {m[b]} 0 0", f"Iw{k}{wn} 0 {m[a]} 10m"]
    net.append(".op")
    d, _ = run("\n".join(net) + "\n", "dcr")
    for k, (name, p) in enumerate(PRESETS.items()):
        m = maps[name]
        check(f"{name} Rp (primaries in parallel)", float(d[f"v({m['p1']})"][0]) / 10e-3, p["Rp"], 2e-3, rel=True)
        for wn, (a, b, nlv, vr, ir, dcr) in p["w"].items():
            if dcr is not None:
                check(f"{name} DCR {wn}", float(d[f"v({m[a]})"][0]) / 10e-3, dcr, 2e-3, rel=True)

    hdr("presets: dual primary in series (pri=2, 240 V): same secondary voltages")
    net = ["* pri2", f'.include "{SUB}"', source("p1", 240, 60),
           "X1 p1 0 hv1 b ct hv2 h1 hct h2 PT_370AX pri=2", ".options plotwinsize=0", ".tran 0 1 0.8 20u"]
    d, _ = run("\n".join(net) + "\n", "pri2")
    check("PT_370AX pri=2 at 240 V: N.L.V. HV (V)", rms(d["time"], d["v(hv1)"] - d["v(hv2)"], 0.8), 520.1, 0.01, rel=True)
    check("PT_370AX pri=2 at 240 V: no-load current = Iex/2 (A)", rms(d["time"], d["i(bp1)"], 0.8), 0.040, 0.05, rel=True)


# ------------------------------------------------------------------ generic
def generic():
    hdr("generic: regulation from reg, leakage from xlk (pt_ss, 230 V 50 Hz, 2 x 18 V 4.44 A)")
    for reg in (0.05, 0.10):
        net = ["* reg", f'.include "{SUB}"', source("p1", 230, 50),
               f"X1 p1 0 a1 0 b1 0 pt_ss Vp=230 fline=50 Vs=18 Is=4.44 reg={reg} xlk=1e-4 Iex=1m sat=0",
               f"RA a1 0 {18 / 4.44}", f"RB b1 0 {18 / 4.44}", ".options plotwinsize=0", ".tran 0 0.6 0.4 20u"]
        d, _ = run("\n".join(net) + "\n", "reg")
        v = rms(d["time"], d["v(a1)"], 0.4)
        # with R = reg/2*V/I in every winding (the primary carries both secondaries) the
        # series R referred to one secondary is reg*RL, so V_FL = 18/(1+reg) exactly
        r_meas = (18 - v) / v
        check(f"pt_ss reg={reg}: (V_NL - V_FL)/V_FL", r_meas, reg, 0.1 * reg + 0.003)
    # leakage: short one secondary, drive the primary at 1 kHz small signal
    net = ["* xlk", f'.include "{SUB}"', "V1 p1 0 AC 1",
           "X1 p1 0 a1 0 b1 0 pt_ss Vp=230 fline=50 Vs=18 Is=4.44 reg=1e-4 xlk=0.01 Iex=1m sat=0",
           "RS a1 0 1u", ".ac list 50"]
    d, _ = run("\n".join(net) + "\n", "xlk")
    z = 1 / (-d["i(v1)"][0])
    VA = 2 * 18 * 4.44
    # primary share (xlk/2 of the total rating) + the shorted winding's own (xlk/2 of its rating)
    want = 0.01 / 2 * 230 ** 2 / VA / (2 * math.pi * 50) + 0.01 / 2 * 18 / 4.44 / (2 * math.pi * 50) * (230 / 18) ** 2
    check("pt_ss xlk=0.01: leakage seen at the primary, one secondary shorted (mH)",
          np.imag(z) / (2 * math.pi * 50) * 1e3, want * 1e3, 0.02, rel=True)


# ------------------------------------------------------------------ saturation
def saturation():
    hdr("saturation: inrush, 50 Hz on a 60 Hz part, over-voltage")
    # inrush: 370FX switched on at a zero crossing (hard source), 120 V 60 Hz
    net = ["* inrush", f'.include "{SUB}"', source("p1", 120, 60, soft=False),
           "X1 p1 0 hv1 b ct hv2 h1 hct h2 a1 a2 PT_370FX", ".options plotwinsize=0", ".tran 0 0.2 0 5u"]
    d, _ = run("\n".join(net) + "\n", "inrush")
    ipk = float(np.max(np.abs(d["i(vp1)"])))
    iex_pk = 0.132 * math.sqrt(2)
    info("PT_370FX inrush peak, switch-on at a zero crossing (A)", ipk)
    check_range("PT_370FX inrush peak / no-load peak (>> 1; < Vpk/Rp limit)", ipk / iex_pk,
                20, 120 * math.sqrt(2) / (4.541 * 4.902 / 9.443) / iex_pk)
    net = ["* soft", f'.include "{SUB}"', source("p1", 120, 60),
           "X1 p1 0 hv1 b ct hv2 h1 hct h2 a1 a2 PT_370FX", ".options plotwinsize=0", ".tran 0 0.2 0 5u"]
    d, _ = run("\n".join(net) + "\n", "soft")
    check_range("PT_370FX soft start: peak current / no-load peak", float(np.max(np.abs(d["i(bp1)"]))) / iex_pk, 0.5, 2)
    # 290EX (60 Hz only) on 120 V 50 Hz, and 370FX at 132 V (+10 %)
    for name, pins, f, V, lab in (("PT_290EX", "hv1 b ct hv2 h1 hct h2", 50, 120, "290EX 120 V 50 Hz"),
                                  ("PT_290EX", "hv1 b ct hv2 h1 hct h2", 60, 120, "290EX 120 V 60 Hz"),
                                  ("PT_370FX", "hv1 b ct hv2 h1 hct h2 a1 a2", 60, 132, "370FX 132 V 60 Hz"),
                                  ("PT_370FX", "hv1 b ct hv2 h1 hct h2 a1 a2", 60, 150, "370FX 150 V 60 Hz")):
        net = ["* sat", f'.include "{SUB}"', source("p1", V, f), f"X1 p1 0 {pins} {name}",
               ".options plotwinsize=0", ".tran 0 1.2 1 10u"]
        d, _ = run("\n".join(net) + "\n", "sat")
        ROWS.append((f"no-load current {lab} (A)", rms(d["time"], d["i(bp1)"], 1.0), float("nan"), "info", ""))
    i50, i60 = ROWS[-4][1], ROWS[-3][1]
    check_range("290EX no-load current 50 Hz / 60 Hz (linear core would give 1.2)", i50 / i60, 1.2, 10)
    i132, i150 = ROWS[-2][1], ROWS[-1][1]
    check_range("370FX no-load current 150 V / 132 V (saturation: >> 150/132)", i150 / i132, 1.5, 100)


# ------------------------------------------------------------------ rectifiers
def rectifiers():
    hdr("rectifier convergence (.tran)")
    net = ["* fw ct", f'.include "{SUB}"', DREC, source("p1", 120, 60),
           "X1 p1 0 hv1 b 0 hv2 h1 hct h2 a1 a2 PT_370FX",
           "D1 hv1 bp DREC", "D2 hv2 bp DREC", "C1 bp 0 47u", "RL bp 0 2.2k", "RH h1 h2 1.26",
           "RB b 0 100k", ".options plotwinsize=0", ".tran 0 1 0.6 20u"]
    d, _ = run("\n".join(net) + "\n", "fw")
    t, v = d["time"], d["v(bp)"]
    m = t > 0.8
    vdc = float(np.mean(v[m]))
    info("370FX + FW CT + 47 uF + 2.2k: B+ (V)", vdc)
    info("  ripple p-p (V)", float(np.ptp(v[m])))
    # physics bounds: below the no-load peak of one half, above half of it
    check_range("370FX FW CT: B+ between 0.8 x and 1.0 x the no-load half-winding peak (V)",
                vdc, 0.8 * 293.2 * math.sqrt(2), 293.2 * math.sqrt(2))
    check_range("370FX FW CT: load current near the rated 173 mA (A)", vdc / 2.2e3, 0.13, 0.2)
    # solid state: bridge on the CT toroid, +-rails 4700 uF, 2 A each
    net = ["* ss", f'.include "{SUB}"', DREC, source("p1", 117, 60),
           "X1 p1 0 s1 0 s2 PT_1182N18_CT",
           "D1 s1 vp DREC", "D2 s2 vp DREC", "D3 vn s1 DREC", "D4 vn s2 DREC",
           "C1 vp 0 4700u", "C2 0 vn 4700u", "R1 vp 0 12.5", "R2 0 vn 12.5",
           ".options plotwinsize=0", ".tran 0 1.5 1 20u"]
    d, _ = run("\n".join(net) + "\n", "ss")
    m = d["time"] > 1.2
    vp, vn = float(np.mean(d["v(vp)"][m])), float(np.mean(d["v(vn)"][m]))
    info("1182N18 bridge +-rails, 2 A each: V+ (V)", vp)
    info("1182N18 bridge +-rails, 2 A each: V- (V)", vn)
    check_range("1182N18 +rail between 0.8 x and 1.0 x the no-load peak (V)", vp, 0.8 * 19.39 * math.sqrt(2), 19.39 * math.sqrt(2))
    check("1182N18 rails symmetric (V+ + V-)", vp + vn, 0, 0.2)


# ------------------------------------------------------------------ demo
def demo():
    hdr("demo_mains-transformer.asc netlisted by asc2net = hand netlist")
    asc = HERE / "demo_mains-transformer.asc"
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"), str(asc)],
                         capture_output=True, text=True, check=True).stdout
    body = [ln for ln in net.splitlines() if ln.strip() and not ln.lower().startswith((".lib", ".end"))]
    d1, _ = run("* demo\n" + f'.include "{SUB}"\n' + "\n".join(body) + "\n.options plotwinsize=0\n", "demo")
    hand = f"""* hand
.include "{SUB}"
{DREC}
B1 p1 0 V=120*sqrt(2)*sin(2*pi*60*time)*min(time/50m,1)
X1 p1 0 hv1 bias 0 hv2 h1 0 h2 a1 a2 PT_370FX pri=1
D1 hv1 bplus DREC
D2 hv2 bplus DREC
C1 bplus 0 47u
RL bplus 0 2.2k
RB bias 0 100k
RH h1 h2 1.26
.options plotwinsize=0
.tran 0 1 0.5 20u
"""
    d2, _ = run(hand, "hand")
    for node in ("v(bplus)", "v(bias)"):
        a = float(np.mean(d1[node][d1["time"] > 0.8]))
        b = float(np.mean(d2[node][d2["time"] > 0.8]))
        check(f"demo mean {node} = hand netlist", a, b, 1e-3, rel=True)


def main():
    presets()
    generic()
    saturation()
    rectifiers()
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
