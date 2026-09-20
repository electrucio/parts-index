#!/usr/bin/env python3
"""Verify switch.sub: every position of every switch closes the right lugs and
nothing else, contact and insulation resistance, rounding and end stops, the timed
move (break-before-make gap, shorting rotary overlap), the CTRL-driven footswitch,
the jacks (battery switch), .step of a position, .ac, and the true-bypass demo.
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

SUB = HERE / "switch.sub"
ROWS, FAIL = [], 0
# defaults in switch.sub (README: Provenance)
RON = {"toggle": 10e-3, "3pdt": 30e-3, "rotary": 20e-3, "jack": 30e-3}
ROFF = {"toggle": 1e9, "3pdt": 100e6, "rotary": 1e9, "jack": 10e9}


def check(name, got, want, tol):
    global FAIL
    ok = abs(got - want) <= tol
    FAIL += not ok
    ROWS.append((name, got, want, tol, ok))


def note(text):
    ROWS.append((text, None, None, None, True))


def cross(t, y, level, after=0.0, rising=True):
    i0 = np.searchsorted(t, after)
    a, b = y[i0:-1], y[i0 + 1:]
    idx = np.nonzero((a < level) & (b >= level) if rising else (a > level) & (b <= level))[0]
    if not len(idx):
        return math.nan
    k = i0 + idx[0]
    return float(t[k] + (level - y[k]) * (t[k + 1] - t[k]) / (y[k + 1] - y[k]))


def sim(body, name, analysis=".op"):
    return run(f"* {name}\n.include \"{SUB}\"\n{body}\n{analysis}\n", name, timeout=120)


def closed(ron):
    """V across a 1k load when a closed contact (ron) connects it to 1 V."""
    return 1000 / (1000 + ron)


def lugs_test(model, pins, commons, pos_list, expect, kind):
    """Drive every common at 1 V, load every other pin with 1k; expect[pos] = set of
    pins that must read ~1 V at that position."""
    body = []
    for j, pos in enumerate(pos_list):
        nodes = [f"n{j}_{p}" for p in pins]
        body.append(f"X{j} {' '.join(nodes)} {model} pos={pos}")
        for p in pins:
            body.append(f"V{j}_{p} n{j}_{p} 0 1" if p in commons else f"R{j}_{p} n{j}_{p} 0 1k")
    d, _ = sim("\n".join(body), model)
    for j, pos in enumerate(pos_list):
        bad = []
        for p in pins:
            if p in commons:
                continue
            v = float(d[f"v(n{j}_{p})".lower()][0])
            # open: leakage of 1 V through Roff into the 1k load
            want = closed(RON[kind]) if p in expect[pos] else 1000 / (1000 + ROFF[kind])
            if abs(v - want) > 1e-6 * max(want, 1e-3):
                bad.append(f"{p}={v:.4g}")
        FAIL_ = bool(bad)
        check(f"{model} pos={pos}: closed {sorted(expect[pos]) or 'none'}"
              + (f" [{', '.join(bad)}]" if bad else ""), float(FAIL_), 0, 0)


def main():
    # 1. every position of the toggles and the footswitch
    lugs_test("sw_spst", ["A", "B"], {"B"}, [0, 1], {0: set(), 1: {"A"}}, "toggle")
    lugs_test("sw_spdt", ["T1", "COM", "T2"], {"COM"}, [0, 1], {0: {"T1"}, 1: {"T2"}}, "toggle")
    lugs_test("sw_dpdt", ["A1", "AC", "A2", "B1", "BC", "B2"], {"AC", "BC"}, [0, 1],
              {0: {"A1", "B1"}, 1: {"A2", "B2"}}, "toggle")
    lugs_test("sw_spdt_ctr", ["T1", "COM", "T2"], {"COM"}, [0, 1, 2],
              {0: {"T1"}, 1: set(), 2: {"T2"}}, "toggle")
    lugs_test("sw_dpdt_ctr", ["A1", "AC", "A2", "B1", "BC", "B2"], {"AC", "BC"}, [0, 1, 2],
              {0: {"A1", "B1"}, 1: set(), 2: {"A2", "B2"}}, "toggle")
    # 3PDT: Aion FX datasheet p.1: pos 0 = 2-1, 5-4, 8-7; pos 1 = 2-3, 5-6, 8-9
    lug = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]
    lugs_test("sw_3pdt", lug, {"L2", "L5", "L8"}, [0, 1],
              {0: {"L1", "L4", "L7"}, 1: {"L3", "L6", "L9"}}, "3pdt")

    # 2. rotary 1P12: each position closes only its own contact; rounding and end stops
    pins = ["COM"] + [f"P{k}" for k in range(1, 13)]
    lugs_test("sw_rot1p12", pins, {"COM"}, list(range(1, 13)),
              {k: {f"P{k}"} for k in range(1, 13)}, "rotary")
    body = []
    cases = [("pos=2.4", 2), ("pos=0", 1), ("pos=15", 12), ("pos=8 npos=5", 5)]
    for j, (par, _) in enumerate(cases):
        body.append(f"X{j} c{j} " + " ".join(f"p{j}_{k}" for k in range(1, 13))
                    + f" sw_rot1p12 {par}")
        body.append(f"V{j} c{j} 0 1")
        body += [f"R{j}_{k} p{j}_{k} 0 1k" for k in range(1, 13)]
    for n in (3, 4, 6):
        body.append(f"Xr{n} cr{n} " + " ".join(f"r{n}_{k}" for k in range(1, n + 1))
                    + f" sw_rot1p{n} pos={n}")
        body.append(f"Vr{n} cr{n} 0 1")
        body += [f"Rr{n}_{k} r{n}_{k} 0 1k" for k in range(1, n + 1)]
    d, _ = sim("\n".join(body), "rotx")
    for j, (par, k) in enumerate(cases):
        on = [i for i in range(1, 13) if float(d[f"v(p{j}_{i})"][0]) > 0.5]
        check(f"sw_rot1p12 {par}: closed position", on[0] if len(on) == 1 else -1, k, 0)
    for n in (3, 4, 6):
        on = [i for i in range(1, n + 1) if float(d[f"v(r{n}_{i})"][0]) > 0.5]
        check(f"sw_rot1p{n} pos={n}: closed position", on[0] if len(on) == 1 else -1, n, 0)

    # 3. contact and insulation resistance (1 mA through closed, 1 uA into open)
    body = ("X1 a 0 sw_spst pos=1\nI1 0 a 1m\n"
            "X2 b 0 sw_spst pos=0\nI2 0 b 1u\n"
            "X3 t1 0 t2 sw_spdt pos=0\nI3 0 t1 1m\nI4 0 t2 1u\n"
            "X4 f1 0 f3 f4 f5 f6 f7 f8 f9 sw_3pdt pos=0\nI5 0 f1 1m\nI6 0 f3 1u\n"
            "Rf f5 0 1\nRg f8 0 1\nRh f4 0 1k\nRi f6 0 1k\nRj f7 0 1k\nRk f9 0 1k\n"
            "X5 0 q1 q2 q3 sw_rot1p3 pos=1\nI7 0 q1 1m\nI8 0 q2 1u\nRq3 q3 0 1k\n")
    d, _ = sim(body, "res")
    check("sw_spst Ron, mohm", float(d["v(a)"][0]) / 1e-3 * 1e3, RON["toggle"] * 1e3, 1e-6)
    check("sw_spst Roff, Gohm", float(d["v(b)"][0]) / 1e-6 / 1e9, ROFF["toggle"] / 1e9, 0.01)
    check("sw_spdt Ron (COM-T1), mohm", float(d["v(t1)"][0]) / 1e-3 * 1e3, 10, 1e-6)
    check("sw_spdt Roff (COM-T2), Gohm", float(d["v(t2)"][0]) / 1e-6 / 1e9, 1, 0.01)
    check("sw_3pdt Ron (2-1), mohm", float(d["v(f1)"][0]) / 1e-3 * 1e3, RON["3pdt"] * 1e3, 1e-6)
    check("sw_3pdt Roff (2-3), Mohm", float(d["v(f3)"][0]) / 1e-6 / 1e6, ROFF["3pdt"] / 1e6, 1)
    check("sw_rot1p3 Ron, mohm", float(d["v(q1)"][0]) / 1e-3 * 1e3, RON["rotary"] * 1e3, 1e-6)
    check("sw_rot1p3 Roff, Gohm", float(d["v(q2)"][0]) / 1e-6 / 1e9, 1, 0.01)

    # 4. timed stomp: 3PDT pos 0 -> 1 at tsw=10m, tmove=2m: throw 1 opens at p=0.25,
    #    throw 2 closes at p=0.75, all open for tmove/2 in between
    body = ("X1 a1 ac a2 b1 bc b2 c1 cc c2 sw_3pdt pos=0 tsw=10m tmove=2m\n"
            "Va ac 0 1\nVb bc 0 1\nVc cc 0 1\n"
            "Ra1 a1 0 1k\nRa2 a2 0 1k\nRb1 b1 0 1k\nRb2 b2 0 1k\nRc1 c1 0 1k\nRc2 c2 0 1k\n"
            # rotary 1 -> 2: non-shorting and shorting
            "X2 k k1 k2 k3 k4 sw_rot1p4 pos=1 pos2=2 tsw=10m tmove=2m\nVk k 0 1\n"
            "Rk1 k1 0 1k\nRk2 k2 0 1k\nRk3 k3 0 1k\nRk4 k4 0 1k\n"
            "X3 m m1 m2 m3 m4 sw_rot1p4 pos=1 pos2=2 tsw=10m tmove=2m mbb=1\nVm m 0 1\n"
            "Rm1 m1 0 1k\nRm2 m2 0 1k\nRm3 m3 0 1k\nRm4 m4 0 1k\n"
            # on-off-on flip passes the centre
            "X4 u1 u u2 sw_spdt_ctr pos=0 tsw=10m tmove=2m\nVu u 0 1\nRu1 u1 0 1k\nRu2 u2 0 1k\n")
    d, _ = sim(body, "move", ".tran 0 20m 0 5u")
    t = d["time"]
    t_open = cross(t, d["v(a1)"], 0.5, rising=False)
    t_close = cross(t, d["v(a2)"], 0.5)
    check("3PDT stomp: lug 1 opens, ms", t_open * 1e3, 10.5, 0.01)
    check("3PDT stomp: lug 3 makes, ms", t_close * 1e3, 11.5, 0.01)
    check("3PDT stomp: all-open gap (break-before-make), ms", (t_close - t_open) * 1e3, 1.0, 0.02)
    check("3PDT stomp: poles B and C switch with A, ms",
          max(abs(cross(t, d["v(b2)"], 0.5) - t_close), abs(cross(t, d["v(c2)"], 0.5) - t_close)) * 1e3,
          0, 0.01)
    g = cross(t, d["v(k2)"], 0.5) - cross(t, d["v(k1)"], 0.5, rising=False)
    check("rotary non-shorting 1->2: gap, ms", g * 1e3, 1.0, 0.02)
    o = cross(t, d["v(m1)"], 0.5, rising=False) - cross(t, d["v(m2)"], 0.5)
    check("rotary shorting (mbb=1) 1->2: overlap, ms", o * 1e3, 0.4, 0.02)
    check("rotary 1->2 does not touch position 3 (V)", float(np.max(d["v(k3)"])), 0, 1e-3)
    tc = cross(t, d["v(u2)"], 0.5) - cross(t, d["v(u1)"], 0.5, rising=False)
    check("on-off-on flip 0->2: centre-off interval, ms", tc * 1e3, 1.5, 0.02)

    # 5. CTRL-driven footswitch: two stomps with a PWL
    body = ("X1 a1 ac a2 b1 bc b2 c1 cc c2 k sw_3pdt_vc\n"
            "Vk k 0 PWL(0 0 10m 0 12m 1 30m 1 32m 0)\nVa ac 0 1\nRa1 a1 0 1k\nRa2 a2 0 1k\n"
            "Rb1 b1 0 1k\nRb2 b2 0 1k\nRc1 c1 0 1k\nRc2 c2 0 1k\nRbc bc 0 1k\nRcc cc 0 1k")
    d, _ = sim(body, "vc", ".tran 0 40m 0 10u")
    t = d["time"]
    check("sw_3pdt_vc: engaged between stomps (lug 3, V)", float(np.interp(20e-3, t, d["v(a2)"])),
          closed(30e-3), 1e-6)
    check("sw_3pdt_vc: back to bypass after 2nd stomp (lug 1, V)",
          float(np.interp(38e-3, t, d["v(a1)"])), closed(30e-3), 1e-6)

    # 6. jacks
    body = []
    for j, plug in enumerate((0, 1)):   # switched mono: drive T, watch TN and plug tip
        body += [f"Xm{j} t{j} 0 tn{j} pt{j} ps{j} jack_mono_sw plug={plug}", f"Vt{j} t{j} 0 1",
                 f"Rtn{j} tn{j} 0 1k", f"Rpt{j} pt{j} 0 1k", f"Rps{j} ps{j} 0 1k"]
    for j, plug in enumerate((0, 1, 2)):   # TRS: 9 V battery, - on R, load to S
        body += [f"Xs{j} st{j} sr{j} 0 spt{j} spr{j} sps{j} jack_trs plug={plug}",
                 f"Vbat{j} vp{j} sr{j} 9", f"Rload{j} vp{j} 0 10k",
                 f"Rpt{j}s spt{j} 0 1G", f"Rpr{j}s spr{j} 0 1G", f"Rps{j}s sps{j} 0 1G",
                 f"Rst{j} st{j} 0 1k"]
    d, _ = sim("\n".join(body), "jacks")
    check("jack_mono_sw no plug: T-TN closed (V)", float(d["v(tn0)"][0]), closed(RON["jack"]), 1e-6)
    check("jack_mono_sw no plug: plug tip open (V)", float(d["v(pt0)"][0]), 0, 1e-6)
    check("jack_mono_sw plug in: T-TN open (V)", float(d["v(tn1)"][0]), 0, 1e-6)
    check("jack_mono_sw plug in: plug tip on T (V)", float(d["v(pt1)"][0]), closed(RON["jack"]), 1e-6)
    i = [-float(d[f"i(vbat{j})"][0]) for j in range(3)]
    check("jack_trs no plug: battery current, mA", i[0] * 1e3, 0, 1e-3)
    check("jack_trs mono plug: battery on (R-S = 2 Ron), mA", i[1] * 1e3, 9 / (10e3 + 2 * RON["jack"]) * 1e3,
          1e-6)
    check("jack_trs stereo plug: battery off, mA", i[2] * 1e3, 0, 1e-3)

    # 7. .step param over a rotary position (how the webapp sweeps a selector)
    d, _ = sim(".param k=1\nX1 c p1 p2 p3 p4 p5 p6 sw_rot1p6 pos={k}\nVc c 0 1\n"
               + "\n".join(f"R{i} p{i} 0 1k" for i in range(1, 7))
               + "\n.step param k list 2 5", "step")
    check(".step pos=2: P2 (V)", float(d["v(p2)"][0]), closed(20e-3), 1e-6)
    check(".step pos=5: P5 (V)", float(d["v(p5)"][-1]), closed(20e-3), 1e-6)

    # 8. .ac through a closed toggle contact, 1k source into 1k
    d, _ = sim("V1 in 0 AC 1\nR1 in com 1k\nX1 t1 com t2 sw_spdt pos=1\nR2 t2 0 1k\nR3 t1 0 1k",
               "ac", ".ac dec 5 20 20k")
    check(".ac through COM-T2, max |gain| error", float(np.max(np.abs(np.abs(d["v(t2)"]) - 1000 / 2000.01))),
          0, 1e-6)

    # 9. demo: true bypass, stomp at 20 ms
    net = subprocess.run([sys.executable, str(ROOT / "tools/ltspice/asc2net.py"),
                          str(HERE / "demo_switch.asc")], capture_output=True, text=True,
                         check=True).stdout
    net = net.replace(".lib switch.sub", f'.lib "{SUB}"')
    d, _ = run(net, "demo", timeout=120)
    t = d["time"]
    w1, w2 = (t > 2e-3) & (t < 19e-3), (t > 30e-3) & (t < 59e-3)
    check("demo bypassed: OUT = IN, max |err| V",
          float(np.max(np.abs(d["v(out)"][w1] - d["v(in)"][w1]))), 0, 1e-4)
    check("demo bypassed: effect input only sees 100M insulation leakage, max |V|",
          float(np.max(np.abs(d["v(fx_in)"][w1]))), 0.2 * 1e6 / (100e6 + 1e6 + 0.03), 2e-5)
    check("demo engaged: OUT = effect output, max |err| V",
          float(np.max(np.abs(d["v(out)"][w2] - d["v(fx_out)"][w2]))), 0, 1e-4)
    w3 = (t > 49e-3) & (t < 59e-3)
    gain = float((np.max(d["v(out)"][w3]) - np.min(d["v(out)"][w3])) / 2 / 0.2)
    h = 1 / math.sqrt(1 + (1 / (2 * math.pi * 440 * 100e-9 * 500e3)) ** 2)
    check("demo engaged: gain (2 x, 100n into 1Meg || 1Meg at 440 Hz)", gain, 2 * h, 0.005)
    iled = [float(np.interp(tt, t, d["i(rled)"])) for tt in (10e-3, 40e-3)]
    check("demo: LED current bypassed, mA", iled[0] * 1e3, 0, 1e-3)
    check("demo: LED current engaged, mA (9 V - Vf)/4.7k", iled[1] * 1e3, 1.53, 0.1)

    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, ok in ROWS:
        if got is None:
            print(name)
        else:
            print(f"{name:<{w}}  got {got:11.5g}  want {want:11.5g}  tol {tol:<8.3g} "
                  f"{'ok' if ok else 'FAIL'}")
    n = sum(r[1] is not None for r in ROWS)
    print(f"\n{n - FAIL}/{n} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
