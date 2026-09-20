#!/usr/bin/env python3
"""Calibrate the saturation knee (ksat) of the presets that have a published 1 % THD
point, in the datasheet's own test conditions, by bisection on LTspice .tran runs.
Paste the printed values into KSAT in xf_presets.py, then run make_symbols.py.
Run with the shell sandbox off.

  XF_JT115KE   Jensen: "Maximum 20 Hz input level, 1% THD, test circuit 1: -2.5 dBu typ"
               (75 + 75 ohm generator, 150 k load; level at the primary)
  XF_LL1538_5  Lundahl: "1 % @ +10 dBU (2.5 V rms) primary level, 50 Hz" (primaries
               in parallel, source impedance 200 ohm, no termination); driven at
               +10 dBu = 2.449 V from the generator, as the bench does
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bench.ltbatch import run          # noqa: E402

SUB = HERE / "audio-transformer.sub"


def thd(t, v, f0, ncyc):
    tt = t[-1] - ncyc / f0
    m = t >= tt - 1e-12
    tu = np.linspace(tt, t[-1], 8192, endpoint=False)
    vu = np.interp(tu, t[m], v[m])
    sp = np.abs(np.fft.rfft(vu - vu.mean()))
    return 100 * math.sqrt(sum(sp[k * ncyc] ** 2 for k in range(2, 11))) / sp[ncyc]


def jt_net(ksat):
    # generator amplitude set so that the primary sees the rated level (Zi ~ 1.4 k)
    vp = 0.7746 * 10 ** (-2.5 / 20)
    return f"""* jt
.include "{SUB}"
V1 g 0 SINE(0 {math.sqrt(2) * vp * 1.107:.6g} 20)
Rg1 g p 75
Rg2 m 0 75
X1 p m o 0 XF_JT115KE sat=1 ksat={ksat:.6g}
RL o 0 150k
.options plotwinsize=0
.tran 0 0.6 0 20u
""", 20


def ll38_net(ksat):
    return f"""* l38
.include "{SUB}"
V1 g 0 SINE(0 {math.sqrt(2) * 0.7746 * 10 ** (10 / 20):.6g} 50)
Rg g p 200
X1 p 0 o 0 XF_LL1538_5 sat=1 ksat={ksat:.6g}
.options plotwinsize=0
.tran 0 0.24 0 10u
""", 50


def calib(netf, target=1.0):
    lo, hi = 0.6, 2.0          # THD falls as ksat rises
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        net, f0 = netf(mid)
        d, _ = run(net, "cal", timeout=120)
        val = thd(d["time"], d["v(o)"], f0, 6)
        if val > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


if __name__ == "__main__":
    print(f'    "XF_JT115KE": {calib(jt_net):.4g},')
    print(f'    "XF_LL1538_5": {calib(ll38_net):.4g},')
