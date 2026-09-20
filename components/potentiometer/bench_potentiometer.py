#!/usr/bin/env python3
"""Verify potentiometer.sub: tapers, clamping, ganging, the tapped pot and the
voltage-controlled pots. Run with the shell sandbox off. Exit 1 on any failure."""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from bench.ltbatch import run        # noqa: E402

SUB = HERE / "potentiometer.sub"
ROWS, FAIL = [], 0


def check(name, got, want, tol):
    global FAIL
    ok = abs(got - want) <= tol
    FAIL += not ok
    ROWS.append((name, got, want, tol, ok))


def f_log(r, L):
    a = (1 / L - 1) ** 2
    return (a ** r - 1) / (a - 1)


def divider(sub, params, rots):
    """V(W) with 1 V across CCW(0 V)..CW(1 V), for several rotations, one .op."""
    lines = [f"* pot divider {sub}", f'.include "{SUB}"']
    for k, r in enumerate(rots):
        lines += [f"V{k} cw{k} 0 1", f"X{k} 0 w{k} cw{k} {sub} R=100k rot={r:g} Rend=1 {params}"]
    lines.append(".op")
    d, _ = run("\n".join(lines) + "\n", "div")
    return [float(d[f"v(w{k})"][0]) for k in range(len(rots))]


def main():
    rots = [-0.2, 0, 0.1, 0.25, 0.5, 0.75, 0.9, 1, 1.3]
    # lin
    for r, v in zip(rots, divider("pot_lin", "", rots)):
        rc = min(max(r, 0), 1)
        check(f"lin rot={r:g}", v, (1e5 * rc + 1) / (1e5 + 2), 1e-6)
    # log, smooth and segmented, L=0.1 and 0.15
    for L in (0.1, 0.15):
        for r, v in zip(rots, divider("pot_log", f"L={L}", rots)):
            rc = min(max(r, 0), 1)
            check(f"log L={L} rot={r:g}", v, (1e5 * f_log(rc, L) + 1) / (1e5 + 2), 1e-6)
    for r, v in zip(rots, divider("pot_log", "L=0.1 seg=1", rots)):
        rc = min(max(r, 0), 1)
        f = 0.2 * rc if rc < 0.5 else 0.1 + 1.8 * (rc - 0.5)
        check(f"log seg rot={r:g}", v, (1e5 * f + 1) / (1e5 + 2), 1e-6)
    # revlog is the mirror of log
    for r, v in zip(rots, divider("pot_revlog", "L=0.1", rots)):
        rc = min(max(r, 0), 1)
        check(f"revlog rot={r:g}", v, (1e5 * (1 - f_log(1 - rc, 0.1)) + 1) / (1e5 + 2), 1e-6)

    # taper given as points: linear between (0,0),(.1,f10),(.5,f50),(.9,f90),(1,1)
    pts = dict(f10=0.02, f50=0.15, f90=0.6)
    table = [(0, 0), (0.1, 0.02), (0.5, 0.15), (0.9, 0.6), (1, 1)]
    import numpy as np
    xs, ys = zip(*table)
    for r, v in zip(rots, divider("pot_pts", "f10=0.02 f50=0.15 f90=0.6", rots)):
        rc = min(max(r, 0), 1)
        check(f"pts rot={r:g}", v, (1e5 * float(np.interp(rc, xs, ys)) + 1) / (1e5 + 2), 1e-6)
    # symmetric taper: f(0.25)=Lq, f(0.5)=0.5, f(0.75)=1-Lq, for S (Lq<.25) and W-like (Lq>.25)
    for lq in (0.1, 0.4):
        vs = divider("pot_sym", f"Lq={lq}", [0.25, 0.5, 0.75])
        for r, v, want in zip((0.25, 0.5, 0.75), vs, (lq, 0.5, 1 - lq)):
            check(f"sym Lq={lq} rot={r}", v, (1e5 * want + 1) / (1e5 + 2), 1e-6)

    # wiper contact resistance appears between the track and W
    net = (f'* wiper R\n.include "{SUB}"\nV1 cw 0 1\n'
           "X1 0 w cw pot_lin R=100k rot=0.5 Rend=1 Rw=1k\nRL w 0 1k\n.op\n")
    d, _ = run(net, "rw")
    # Thevenin at the track midpoint: 0.5 V behind (50001 || 50001) + 1k wiper, into 1k
    rth = 50001 / 2 + 1000
    check("wiper R=1k into 1k load", float(d["v(w)"][0]), 0.5 * 1000 / (rth + 1000), 1e-6)

    # gang tracking error: section 2 off by drot=0.02 and dR=+10 %
    net = (f'* track\n.include "{SUB}"\nV1 a 0 1\nV2 b 0 1\n'
           "X1 0 w1 a 0 w2 b pot_dual_log R=50k rot=0.2 L=0.1 drot=0.02 dR=0.1\n"
           "I1 0 b 0\n.op\n")
    d, _ = run(net, "track")
    v1, v2 = float(d["v(w1)"][0]), float(d["v(w2)"][0])
    check("dual track: section 1 at rot", v1, (5e4 * f_log(0.2, 0.1) + 1) / (5e4 + 2), 1e-6)
    check("dual track: section 2 at rot+drot", v2,
          (5.5e4 * f_log(0.22, 0.1) + 1) / (5.5e4 + 2), 1e-6)
    ROWS.append((f"  (tracking error at rot=0.2: {20 * math.log10(v2 / v1):+.2f} dB)", 0, 0, 0, True))

    # total resistance CCW-CW is R + 2 Rend at any rotation (log pot, W open)
    net = (f'* total R\n.include "{SUB}"\nI1 0 cw 1m\nX1 0 w cw pot_log R=250k rot=0.3\n'
           "Rw w 0 1T\n.op\n")
    d, _ = run(net, "rt")
    check("log R(CCW-CW) 250k", float(d["v(cw)"][0]) / 1e-3, 250e3 + 2, 1e-3)

    # ganged: both sections identical
    net = (f'* dual\n.include "{SUB}"\nV1 a 0 1\nV2 b 0 1\n'
           "X1 0 w1 a 0 w2 b pot_dual_log R=50k rot=0.3 L=0.15\n.op\n")
    d, _ = run(net, "dual")
    check("dual sections track", float(d["v(w1)"][0]) - float(d["v(w2)"][0]), 0, 1e-9)

    # tapped pot: tap at 0.5 of travel; wiper below and above the tap
    for r in (0.2, 0.5, 0.8):
        net = (f'* tap\n.include "{SUB}"\nV1 cw 0 1\n'
               f"X1 0 w cw t pot_log_tap R=1Meg rot={r} L=0.1 tap=0.5 Rend=1\n"
               "Rt t 0 1T\nRw w 0 1T\n.op\n")
        d, _ = run(net, "tap")
        fw, ft = f_log(r, 0.1), f_log(0.5, 0.1)
        check(f"tap rot={r} V(W)", float(d["v(w)"][0]), fw, 2e-5)
        check(f"tap rot={r} V(TAP)", float(d["v(t)"][0]), ft, 2e-5)

    # voltage-controlled: a ramp on CTRL reproduces the static taper
    net = (f'* vc\n.include "{SUB}"\nV1 cw 0 1\nVc c 0 PWL(0 0 1 1)\n'
           "X1 0 w cw c pot_log_vc R=100k L=0.1 Rend=1\n"
           "X2 0 w2 cw c pot_lin_vc R=100k Rend=1\n"
           "X3 0 w3 cw c pot_revlog_vc R=100k L=0.1 Rend=1\n"
           ".tran 0 1 0 1m\n")
    d, _ = run(net, "vc")
    import numpy as np
    t = d["time"]
    for x in (0.1, 0.5, 0.9):
        v = float(np.interp(x, t, d["v(w)"]))
        check(f"log_vc ctrl={x}", v, (1e5 * f_log(x, 0.1) + 1) / (1e5 + 2), 1e-4)
        v = float(np.interp(x, t, d["v(w2)"]))
        check(f"lin_vc ctrl={x}", v, (1e5 * x + 1) / (1e5 + 2), 1e-4)
        v = float(np.interp(x, t, d["v(w3)"]))
        check(f"revlog_vc ctrl={x}", v, (1e5 * (1 - f_log(1 - x, 0.1)) + 1) / (1e5 + 2), 1e-4)

    # .step param works (the webapp will sweep knobs this way)
    net = (f'* step\n.include "{SUB}"\n.param vol=0.5\nV1 cw 0 1\n'
           "X1 0 w cw pot_log R=100k rot={vol}\n.step param vol list 0.25 0.75\n.op\n")
    d, _ = run(net, "step")
    vs = list(d["v(w)"])
    check(".step rot=0.25", float(vs[0]), (1e5 * f_log(0.25, 0.1) + 1) / (1e5 + 2), 1e-6)
    check(".step rot=0.75", float(vs[-1]), (1e5 * f_log(0.75, 0.1) + 1) / (1e5 + 2), 1e-6)

    w = max(len(r[0]) for r in ROWS)
    for name, got, want, tol, ok in ROWS:
        print(f"{name:<{w}}  got {got:12.6g}  want {want:12.6g}  tol {tol:g}  {'ok' if ok else 'FAIL'}")
    print(f"\n{len(ROWS) - FAIL}/{len(ROWS)} checks passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
