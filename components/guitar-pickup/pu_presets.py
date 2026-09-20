"""Preset table of guitar-pickup.sub: the one place where preset numbers live.

make_symbols.py writes the preset block of guitar-pickup.sub and the preset symbols from
it; bench_guitar-pickup.py checks the simulated pickups against the numbers kept here.

Sources (fetched 2026-09-14):
  LEMME  H. Lemme, "Resonant frequencies of some well-know pickups for various parallel
         capacitors", https://buildyourguitar.com/resources/lemme/table.htm (companion
         table of "The Secrets of Electric Guitar Pickups",
         https://buildyourguitar.com/resources/lemme/). All values measured by Lemme.
         Columns used: inductance L (H), winding capacitance C (pF), resonant frequency
         (kHz, rounded to 0.1 kHz) with 470p/680p/1n/1.5n/2.2n/3.3n/4.7n added in
         parallel, and "Max. peak height Q". Lemme: "figures may show sample variations
         by +-10 % or more". The site's TLS certificate had expired; the page was read
         with curl -k (sha256 of the HTML: see README.md).
  SD     Seymour Duncan, "What is the dc resistance of popular pickups?" (last updated
         2019-10-17), https://www.seymourduncan.com/blog/swd/what-is-the-dc-resistance-of-popular-pickups
         -- DC resistance of the Fender/Gibson originals.
  SD59   Seymour Duncan '59 Model product page, https://www.seymourduncan.com/single-product/59-model
         -- DCR 7.60k (neck), 8.2k (bridge).
Lemme's table has no DC resistance, so R comes from SD/SD59 for the same model family
(same pickup type, not the same specimen). Zollner (PotEG 5.5.4, gitec-forum-eng.de)
shows that R changes the resonance emphasis only very little, so this mix is acceptable.

Eddy-current loss (Rx, kx): Lemme's split-coil circuit (article, Fig. 6), kx = 0.5 as he
suggests ("identical sizes can be used as a point of departure"). Rx is FITTED (fit_rx
below) so that the peak height with 470 pF and a 10 Mohm resistive load equals Lemme's
"Max. peak height Q". The 10 Mohm load is an assumption: it is the ohmic load of Lemme's
high-impedance reference curves (article, Fig. 15), and "max." means the least-damped
condition. If no Rx can lower the peak enough... it cannot happen: Rx -> 0 always damps
more; if the eddy-free coil is already below Lemme's Q, Rx is set to 0 (= no eddy loss,
open) and the bench reports the difference.
"""
from __future__ import annotations

import math

import numpy as np

URL_LEMME = "https://buildyourguitar.com/resources/lemme/table.htm"
URL_SD = "https://www.seymourduncan.com/blog/swd/what-is-the-dc-resistance-of-popular-pickups"
URL_SD59 = "https://www.seymourduncan.com/single-product/59-model"

CAPS = (470e-12, 680e-12, 1e-9, 1.5e-9, 2.2e-9, 3.3e-9, 4.7e-9)   # Lemme's columns
RLOAD_Q = 10e6          # assumed resistive load of Lemme's peak-height column
KX = 0.5                # Lemme: equal split of the coil as the point of departure

PRESETS = []


def add(name, desc, lemme_row, L, C, fk, q, R, rsrc, note=""):
    PRESETS.append(dict(name=name, desc=desc, lemme_row=lemme_row, L=L, C=C, f=fk, Q=q,
                        R=R, rsrc=rsrc, kx=KX, note=note))


# name, description, Lemme row, L (H), C (F), f at CAPS (kHz), Q, R (ohm), R source
add("PU_STRAT72", "Fender Stratocaster (1972)", "Fender US-Strat. (1972)", 2.2, 110e-12,
    (4.4, 3.8, 3.2, 2.7, 2.2, 1.8, 1.5), 6.3, 6050, "SD 5.8k-6.3k (midpoint)")
add("PU_STRAT_MEX", "Fender Mexico Stratocaster", "Fender Mexico Strat.", 2.8, 60e-12,
    (4.2, 3.3, 2.9, 2.3, 1.9, 1.6, 1.3), 3.1, 6050, "SD 5.8k-6.3k (midpoint, Fender Strat)")
add("PU_TELE_BRIDGE", "Fender Telecaster bridge", "Fender Telecaster Bridge", 2.9, 160e-12,
    (3.7, 3.2, 2.7, 2.3, 1.9, 1.6, 1.3), 3.7, 6400, "SD Telecaster lead 6.2k-6.6k (midpoint)")
add("PU_P90", "Gibson P-90", "Gibson P90", 6.6, 95e-12,
    (2.6, 2.2, 1.9, 1.5, 1.3, 1.1, 0.9), 2.9, 8600, "SD Gibson P-90 8.6k")
add("PU_SD59", "Seymour Duncan '59 humbucker (PAF type)", "Seymour Duncan 59", 5.0, 120e-12,
    (2.9, 2.6, 2.2, 1.8, 1.5, 1.3, 1.0), 2.6, 7600, "SD59 neck 7.60k (bridge 8.2k)",
    note="Lemme does not say neck or bridge; the neck DCR is used")
add("PU_JAZZBASS", "Fender Jazz Bass", "Fender Jazz Bass", 3.6, 150e-12,
    (3.4, 2.9, 2.5, 2.1, 1.7, 1.4, 1.2), 3.9, 8500, "SD Fender Jazz Bass 8.5k")
add("PU_PBASS", "Fender Precision Bass", "Fender Precision Bass", 6.0, 15e-12,
    (2.9, 2.5, 2.1, 1.7, 1.4, 1.1, 0.9), 5.4, 10600, "SD Fender Precision Bass 10.6k",
    note="Lemme's 15 pF winding capacitance is unusually low but used as published")


def response(p, rx, cx, rl, f):
    """|V(OUT)/EMF| of the subckt with cx and rl across OUT-GND (numpy, same circuit as
    the .sub: EMF - L(1-k) - (L k || Rx) - R - OUT, C from OUT to GND)."""
    w = 2 * np.pi * np.asarray(f)
    jw = 1j * w
    k = p["kx"]
    z2 = jw * p["L"] * k if rx <= 0 else (jw * p["L"] * k * rx) / (jw * p["L"] * k + rx)
    zs = jw * p["L"] * (1 - k) + z2 + p["R"]
    yl = jw * (p["C"] + cx) + 1 / rl
    return np.abs(1 / (1 + zs * yl))


def peak(p, rx, cx, rl):
    """(peak frequency Hz, peak height re low-frequency gain) on a fine log grid."""
    f = np.logspace(2, 5, 6001)
    h = response(p, rx, cx, rl, f)
    i = int(np.argmax(h))
    return f[i], h[i] / (rl / (rl + p["R"]))


def fit_rx(p):
    """Rx giving Lemme's peak height at 470 pF, RLOAD_Q (bisection on log Rx)."""
    q_open = peak(p, 0, CAPS[0], RLOAD_Q)[1]
    if q_open <= p["Q"]:
        return 0.0
    lo, hi = math.log(1e3), math.log(1e9)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if peak(p, math.exp(mid), CAPS[0], RLOAD_Q)[1] > p["Q"]:
            hi = mid
        else:
            lo = mid
    return float(f"{math.exp(0.5 * (lo + hi)):.4g}")


for _p in PRESETS:
    _p["Rx"] = fit_rx(_p)


def fmt(x):
    for unit, k in (("Meg", 1e6), ("k", 1e3)):
        if abs(x) >= k:
            return f"{x / k:.4g}{unit}"
    for unit, k in (("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(x) < 1 and abs(x) >= k:
            return f"{x / k:.4g}{unit}"
    return f"{x:.5g}"


def subckt_text(p):
    head = (f"* {p['desc']}: Lemme \"{p['lemme_row']}\" {URL_LEMME}; R: {p['rsrc']};"
            f" Rx fitted to Lemme's peak height Q = {p['Q']:g}")
    return "\n".join([
        head + (f"  ({p['note']})" if p["note"] else ""),
        f".subckt {p['name']} OUT GND EMF params: kx={p['kx']:g}",
        f"X1 OUT GND EMF pickup L={fmt(p['L'])} R={fmt(p['R'])} C={fmt(p['C'])}"
        f" Rx={fmt(p['Rx'])} kx={{kx}}",
        f".ends {p['name']}",
    ])


if __name__ == "__main__":
    for p in PRESETS:
        print(f"{p['name']:<15} Rx={p['Rx']:>10.4g}", end="  f model/Lemme:")
        for cx, fl in zip(CAPS, p["f"]):
            fm = peak(p, p["Rx"], cx, RLOAD_Q)[0] / 1e3
            print(f" {fm:.2f}/{fl:.1f}", end="")
        print(f"   Q {peak(p, p['Rx'], CAPS[0], RLOAD_Q)[1]:.2f}/{p['Q']}")
