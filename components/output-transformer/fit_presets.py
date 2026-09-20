#!/usr/bin/env python3
"""Derive the winding capacitance Cw (and, where the datasheet leakage figure is not
usable, the leakage Llk) of each Hammond preset from Hammond's own frequency-response
graphs. Pure numpy, no LTspice: it evaluates the same linear equivalent circuit that
output-transformer.sub implements (bench_output-transformer.py then checks the .sub
against these numbers).

Equivalent circuit (whole primary; the test circuit on every Hammond sheet is a
source with Rs/2 in each leg and the nominal load on a secondary tap):

    Vs -- Rs -- A -- Rpri -- Llk -- B -- ideal n:1 -- Rsec -- RL
                |                   |
                Cw               Lp || Rc

Graph points are read off page 2/3 of each PDF (https://www.hammfg.com/files/parts/pdf/
<PART>.pdf) at 20 kHz and 30 kHz on the 8-ohm curve (or the only curve), amplitude in
dB re 1 kHz and phase in degrees; reading resolution about +-0.1 dB and +-2 deg.

Run: python3 fit_presets.py   (prints the table used in the .sub presets and README)
"""
from __future__ import annotations

import math

import numpy as np

# part: Za, Zload tap used by the graph, Rs of the graph, Lp, Llk_published (None = not
# usable), Rpri, Rsec(COM-tap of the graph), graph points [(f, dB, deg or None)],
# fit = "cw" (Cw only, datasheet Llk) or "both" (Llk and Cw)
PARTS = {
    # Fender replacements (1760 series); Lp, Llk at 1 kHz, 1 V, whole primary
    "1760E": dict(Za=8500, Zt=8, Rs=8500, Lp=21.6, Llk=None, Rpri=313.6, Rsec=0.540,
                  Lbounds=(1e-3, 323.9e-3),
                  pts=[(20e3, -0.25, -20), (30e3, -0.6, -31)], note="datasheet Llk 323.9 mH contradicts the graph"),
    "1760H": dict(Za=6600, Zt=8, Rs=6600, Lp=25.8, Llk=12.30e-3, Rpri=347.8, Rsec=0.803,
                  pts=[(20e3, -0.05, -10), (30e3, -0.15, -17)]),
    "1760J": dict(Za=4000, Zt=8, Rs=4000, Lp=19.5, Llk=35.93e-3, Rpri=185.0, Rsec=0.502,
                  pts=[(20e3, -1.3, -27), (30e3, -2.6, -40)]),
    "1760L": dict(Za=4200, Zt=8, Rs=4200, Lp=5.72, Llk=3.506e-3, Rpri=97.52, Rsec=0.405,
                  pts=[(20e3, 0.0, -7), (30e3, -0.05, -10)]),
    "1760W": dict(Za=2000, Zt=8, Rs=2000, Lp=4.55, Llk=1.280e-3, Rpri=27.68, Rsec=0.175,
                  pts=[(20e3, 0.0, -2), (30e3, 0.0, -3)]),
    # graph "RS = 5K": the 5 k tap (Brown-Red: Lp 16.2 H, DCR 272.08)
    "1760C": dict(Za=5000, Zt=8, Rs=5000, Lp=16.2, Llk=None, Rpri=272.08, Rsec=0.624,
                  Lbounds=(1e-3, 719.5e-3),
                  pts=[(20e3, -0.05, -13), (30e3, -0.2, -20)], note="datasheet Llk 719.5 mH contradicts the graph"),
    # Marshall / Vox replacements (1750 series)
    "1750N": dict(Za=3200, Zt=8, Rs=3200, Lp=18.3, Llk=13.41e-3, Rpri=84.88, Rsec=0.770,
                  pts=[(20e3, -0.1, -20), (30e3, -1.3, -30)]),
    "1750U": dict(Za=1700, Zt=8, Rs=1700, Lp=8.85, Llk=7.97e-3, Rpri=31.92, Rsec=0.320,
                  pts=[(20e3, -0.4, -15), (30e3, -0.7, -22)]),
    "1750Q": dict(Za=7371, Zt=8, Rs=7371, Lp=38.0, Llk=19.87e-3, Rpri=84.88, Rsec=0.580,
                  pts=[(20e3, -0.3, -22), (30e3, -2.1, -38)]),
    "1750Y": dict(Za=6200, Zt=8, Rs=6200, Lp=14.6, Llk=14.04e-3, Rpri=289.0, Rsec=0.480,
                  pts=[(20e3, -0.05, -14), (30e3, -0.15, -21)]),
    "1750V": dict(Za=4000, Zt=8, Rs=4000, Lp=6.30, Llk=5.14e-3, Rpri=140.67, Rsec=0.72 * 0.707,
                  pts=[(20e3, -0.05, -9), (30e3, -0.15, -14)]),
    # Hi-fi 1650 series: Lp and Llk published on one half-primary (Brown-Red) at 60 Hz,
    # 10 V; Lp of the whole primary = 4x (N^2); the leakage of the whole primary is fitted
    "1650F": dict(Za=7600, Zt=8, Rs=7600, Lp=4 * 285, Llk=None, Rpri=210.0, Rsec=0.25,
                  Lbounds=(10.40e-3, 4*10.40e-3),
                  pts=[(20e3, -0.35, -17), (30e3, -0.8, -26)], note="half-primary Llk 10.40 mH"),
    "1650H": dict(Za=6600, Zt=8, Rs=6600, Lp=4 * 245, Llk=None, Rpri=145.0, Rsec=0.22,
                  Lbounds=(10.60e-3, 4*10.60e-3),
                  pts=[(20e3, -0.3, -20), (30e3, -0.8, -28)], note="half-primary Llk 10.60 mH"),
    "1650N": dict(Za=4300, Zt=8, Rs=4300, Lp=4 * 134, Llk=None, Rpri=82.5, Rsec=0.30,
                  Lbounds=(7.72e-3, 4*7.72e-3),
                  pts=[(20e3, -0.1, -15), (30e3, -0.5, -24)], note="half-primary Llk 7.72 mH"),
    "1650R": dict(Za=5000, Zt=8, Rs=5000, Lp=4 * 320, Llk=None, Rpri=101.21, Rsec=0.36,
                  Lbounds=(10.84e-3, 4*10.84e-3),
                  pts=[(20e3, -0.3, -19), (30e3, -0.8, -28)], note="half-primary Llk 10.84 mH"),
    "1650T": dict(Za=1900, Zt=8, Rs=1900, Lp=4 * 124, Llk=None, Rpri=47.10, Rsec=0.30,
                  Lbounds=(4.30e-3, 4*4.30e-3),
                  pts=[(20e3, -0.1, -10), (30e3, -0.3, -18)], note="half-primary Llk 4.30 mH"),
    # Universal SE (125SE series): no leakage published, no phase graph; graph at the
    # 5 k connection (Rs = 5 k); Cw fixed at an estimate, Llk fitted to the amplitude
    # (the 5 k connection = 8 ohm on the 16-ohm lug; the primary is still the whole
    # Blue-Brown winding, so Lp and Rpri are the whole-winding figures)
    "125ESE": dict(Za=5000, Zt=8, Rs=5000, Lp=5.43, Llk=None, Rpri=103.0, Rsec=0.297,
                   pts=[(20e3, -0.1, None), (30e3, -0.2, None)], cw_fixed=200e-12,
                   note="no Llk published; Cw = 200 pF estimate"),
    "125CSE": dict(Za=5000, Zt=8, Rs=5000, Lp=9.28, Llk=None, Rpri=200.0, Rsec=0.428,
                   pts=[(20e3, -0.1, None), (30e3, -0.2, None)], cw_fixed=200e-12,
                   note="no Llk published; Cw = 200 pF estimate"),
}


def response(f, Za, Zt, Rs, Lp, Llk, Cw, Rpri, Rsec, Qc=3.0):
    """Complex V(RL) of the equivalent circuit, any scale."""
    w = 2 * np.pi * np.asarray(f, dtype=float)
    Rc = Qc * 2 * np.pi * 1e3 * Lp
    n2 = Za / Zt                                  # impedance ratio
    Zload = (Rsec + Zt) * n2                      # secondary branch referred to primary
    Zm = 1 / (1 / (1j * w * Lp) + 1 / Rc + 1 / Zload)
    Zser = Rpri + 1j * w * Llk + Zm
    Za_node = 1 / (1j * w * Cw + 1 / Zser)
    vA = Za_node / (Rs + Za_node)
    vB = vA * Zm / Zser
    return vB * Zt * n2 / Zload                   # voltage across the load, referred


def db_ph(p, f, Llk, Cw):
    h = response([1e3, f], p["Za"], p["Zt"], p["Rs"], p["Lp"], Llk, Cw, p["Rpri"], p["Rsec"])
    r = h[1] / h[0]
    return 20 * math.log10(abs(r)), math.degrees(np.angle(r))


def phase_at(p, f, Llk, Cw):
    return db_ph(p, f, Llk, Cw)[1]


def cw_from_phase(p, Llk, f=20e3, lo=20e-12, hi=5e-9):
    """Cw that gives the graph's phase at f (bisection on log Cw); Cw grows the lag."""
    target = next(deg for ff, _, deg in p["pts"] if ff == f)
    if phase_at(p, f, Llk, lo) <= target:
        return lo                                  # leakage alone already lags enough
    if phase_at(p, f, Llk, hi) >= target:
        return hi
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if phase_at(p, f, Llk, mid) > target:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def cost(p, Llk, Cw):
    c = 0.0
    for f, dB, deg in p["pts"]:
        m_db, m_ph = db_ph(p, f, Llk, Cw)
        c += ((m_db - dB) / 0.1) ** 2
        if deg is not None:
            c += ((m_ph - deg) / 2.0) ** 2
    return c


def fit(p):
    """Return (Llk, Cw, how).
    ds:   datasheet Llk (whole primary); Cw from the graph phase at 20 kHz
    both: Llk and Cw least-squares on amplitude+phase at 20 and 30 kHz, Llk bounded
    amp:  no phase graph: Cw fixed at the estimate, Llk from the 30 kHz amplitude"""
    if p["Llk"] is not None:
        return p["Llk"], cw_from_phase(p, p["Llk"]), "ds"
    if p.get("cw_fixed"):
        C = p["cw_fixed"]
        f, dB, _ = p["pts"][-1]
        llks = np.geomspace(0.5e-3, 200e-3, 400)
        L = min(llks, key=lambda L: abs(db_ph(p, f, L, C)[0] - dB))
        return L, C, "amp"
    lo, hi = p["Lbounds"]
    best = min((cost(p, L, C), L, C)
               for L in np.geomspace(lo, hi, 120) for C in np.geomspace(20e-12, 3e-9, 120))
    return best[1], best[2], "both"


def main():
    print(f"{'part':7} {'Llk(mH)':>8} {'Cw(pF)':>7} {'src':>5}  "
          "graph -> model at 20k / 30k (dB, deg)")
    out = {}
    for name, p in PARTS.items():
        L, C, how = fit(p)
        out[name] = (L, C)
        pts = "  ".join(
            f"{dB:+.2f}{'' if deg is None else f'/{deg:+.0f}'}->"
            f"{db_ph(p, f, L, C)[0]:+.2f}/{db_ph(p, f, L, C)[1]:+.0f}"
            for f, dB, deg in p["pts"])
        print(f"{name:7} {L * 1e3:8.3g} {C * 1e12:7.3g} {how:>5}  {pts}  {p.get('note', '')}")
    return out


if __name__ == "__main__":
    main()
