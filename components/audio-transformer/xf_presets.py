"""Preset table of audio-transformer.sub: the one place where preset numbers live.

make_symbols.py writes the preset block of audio-transformer.sub and the preset symbols
from it; bench_audio-transformer.py checks the simulated transformers against the numbers
kept here. Source codes used in the notes: ds = datasheet value, der = derived from ds
values by the formula given, fit = fitted by this file to ds figures, est = estimate.

Datasheets (fetched 2026-09-14; sha256 of the fetched PDF in README.md):
  JT   Jensen JT-115K-E "Microphone Input Transformer 1:10",
       https://www.jensen-transformers.com/wp-content/uploads/2014/08/jt-115K-e1.pdf
       p.1 feature list: "-3 dB at 2.5 Hz and 90 kHz"; p.2 specification table and
       test circuit 1 (75 + 75 ohm generator, 150 k load).
  L60  Lundahl LL1660 "Tube Amplifier Interstage Transformer / Line Output Transformer",
       https://www.lundahltransformers.com/wp-content/uploads/datasheets/1660.pdf (R030211)
       p.1 section resistances and table of connections, p.2 connection drawings.
  L38  Lundahl LL1538 "Microphone Input Transformers LL1538 and LL1538XL",
       https://www.lundahltransformers.com/wp-content/uploads/datasheets/1538_8xl.pdf (R980616)
"""
from __future__ import annotations

import math

import numpy as np

PRESETS = []

# ----------------------------------------------------------------------------------
# linear small-signal model of atx_ct (sat = 0), referred to the whole primary
# ----------------------------------------------------------------------------------


def model(p, f, Rg, RL=None, CL=0.0):
    """Returns dict of complex arrays at frequencies f: H = V(sec)/Vg, Hp = V(sec)/V(pri),
    Zi (at the primary terminals, load on), Zo (at the secondary terminals, source Rg on,
    load RL in parallel). RL None = open secondary."""
    s = 2j * np.pi * np.asarray(f, dtype=float)
    n = p["n"]
    inf = 1e30
    ycp = s * p.get("Cp", 0.0)
    zcore = 1 / (1 / (s * p["Lp"]) + 1 / p["Rc"])
    yt = s * (p.get("Cs", 0.0) + CL) + (0 if RL is None else 1 / RL)
    zt = 1 / np.where(np.abs(yt) > 0, yt, 1 / inf)
    zaft = (p["Rs"] + zt) / n ** 2
    zright = 1 / (1 / zcore + 1 / zaft)
    zser = p["Rp"] + s * p["Llk"] + zright
    zin = 1 / (ycp + 1 / zser)
    vp = zin / (Rg + zin)
    vcore = vp * zright / zser
    vt = n * vcore * zt / (p["Rs"] + zt)
    zsrc = 1 / (1 / Rg + ycp) + p["Rp"] + s * p["Llk"]
    zo_int = (1 / (1 / zsrc + 1 / zcore)) * n ** 2 + p["Rs"]
    zo = 1 / (1 / zo_int + yt)
    return dict(H=vt, Hp=vt / vp, Zi=zin, Zo=zo)


def db(x):
    return 20 * np.log10(np.abs(x))


def bisect(fun, lo, hi, it=80):
    """Root of a monotonic fun on [lo, hi] in log space."""
    a, b = math.log(lo), math.log(hi)
    fa = fun(math.exp(a))
    for _ in range(it):
        m = 0.5 * (a + b)
        fm = fun(math.exp(m))
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return math.exp(0.5 * (a + b))


# ----------------------------------------------------------------------------------
# Jensen JT-115K-E
# ----------------------------------------------------------------------------------
JT_DS = dict(n=10.0, Rp=19.7, Rs=2465.0, Rg=150.0, RL=150e3,
             Zi_1k=1.40e3, gain_1k=19.75, Zo_1k=17.0e3,
             dB20=-0.26, dB20k=-0.13, f3lo=2.5, f3hi=90e3, Vsat=10 ** (-2.5 / 20) * 0.7746, fsat=20)


def fit_jt():
    """Rc to Zi(1 kHz) = 1.40 k; Lp to -0.26 dB at 20 Hz; Llk and Cs to -0.13 dB at
    20 kHz and -3 dB at 90 kHz (all in test circuit 1: Rg 150, RL 150 k, re 1 kHz)."""
    d = JT_DS
    p = dict(n=d["n"], Rp=d["Rp"], Rs=d["Rs"], Cp=0.0, Lp=5.0, Rc=15e3, Llk=50e-6, Cs=100e-12)

    def rel(f):
        m = model(p, [f, 1e3], d["Rg"], d["RL"])["H"]
        return db(m[0] / m[1])

    for _ in range(6):
        p["Rc"] = bisect(lambda rc: abs(model({**p, "Rc": rc}, [1e3], d["Rg"], d["RL"])["Zi"][0]) - d["Zi_1k"],
                         1e3, 1e8)
        p["Lp"] = bisect(lambda lp: (p.__setitem__("Lp", lp), rel(20))[1] - d["dB20"], 0.1, 1e3)

        def llk_for(cs):
            p["Cs"] = cs
            return bisect(lambda l: (p.__setitem__("Llk", l), -rel(d["f3hi"]))[1] - 3.0, 1e-7, 1e-1)

        def err20k(cs):
            p["Llk"] = llk_for(cs)
            return rel(20e3) - d["dB20k"]

        cs_grid = np.logspace(-12, -9.3, 120)
        e = [err20k(c) for c in cs_grid]
        k = next(i for i in range(len(e) - 1) if (e[i] > 0) != (e[i + 1] > 0))
        cs = bisect(err20k, cs_grid[k], cs_grid[k + 1], 60)
        p["Cs"] = cs
        p["Llk"] = llk_for(cs)
    return p


_jt = fit_jt()
PRESETS.append(dict(
    name="XF_JT115KE", kind="atx", desc="Jensen JT-115K-E mic input 1:10",
    n=10.0, Lp=float(f"{_jt['Lp']:.4g}"), Llk=float(f"{_jt['Llk']:.4g}"), Rp=19.7, Rs=2465.0,
    Cp=0.0, Cs=float(f"{_jt['Cs']:.4g}"), Rc=float(f"{_jt['Rc']:.4g}"), Idc=0.0,
    Vsat=float(f"{JT_DS['Vsat']:.4g}"), fsat=20.0,
    src=dict(n="ds 1:10.00 (1:9.95..1:10.05)", Rp="ds 19.7 (RED-BRN)", Rs="ds 2465 (YEL-ORG)",
             Lp="fit: -0.26 dB at 20 Hz (test circuit 1)", Llk="fit: -0.13 dB at 20 kHz and -3 dB at 90 kHz",
             Cs="fit: with Llk", Rc="fit: Zi 1.40 k at 1 kHz", Cp="0: the 475 pF primary-to-shield is common-mode",
             Vsat="ds: max 20 Hz input level -2.5 dBu at 1 % THD (typ)", Idc="-"),
    url="https://www.jensen-transformers.com/wp-content/uploads/2014/08/jt-115K-e1.pdf"))

# ----------------------------------------------------------------------------------
# Lundahl LL1660: sections A (2-5, 10-7) 315 ohm, B (3-4, 9-8) 240 ohm, C (13-16,
# 21-18) 625 ohm; turns 1+1+1+1 : 2.25+2.25 (A, B = 1 unit, C = 2.25 units).
# ----------------------------------------------------------------------------------
RA, RB, RC_ = 315.0, 240.0, 625.0
R_ALL4_SERIES = 2 * RA + 2 * RB                   # 1+1+1+1 in series (4 units)
R_ALL4_PAR = 1 / (2 / RA + 2 / RB)                # four 1-sections in parallel (1 unit)
R_PAIRS_PAR = (RA + RB) / 2                       # (A+B) || (A+B)            (2 units)
R_CC_SERIES = 2 * RC_                             # C + C                     (4.5 units)
R_CC_PAR = RC_ / 2                                # C || C                    (2.25 units)
R_2P2 = 2 * (RA + RB)                             # (A+B) + (A+B), CT between (2+2 units)

URL_L60 = "https://www.lundahltransformers.com/wp-content/uploads/datasheets/1660.pdf"


def l1660(name, kind, desc, conn, npri, nsec, rp, rs, lp, idc, flo, fhi, rsrc, vout):
    """npri, nsec in section units. Cp (effective, primary-referred, secondaries open)
    derived from the upper +-1 dB edge with the stated source: a first-order R-C,
    -1 dB where w*Rsrc*Cp = 0.5088."""
    cp = 0.50885 / (2 * math.pi * fhi * rsrc)
    n = nsec / npri
    PRESETS.append(dict(
        name=name, kind=kind, desc=desc, n=n, Lp=lp, Llk=0.0, Rp=rp, Rs=rs, Cp=float(f"{cp:.4g}"),
        Cs=0.0, Rc=0.0, Idc=idc, Vsat=float(f"{vout / n:.4g}"), fsat=30.0,
        conn=conn, flo=flo, fhi=fhi, rsrc=rsrc,
        src=dict(n=f"ds {conn}", Rp="der (sections, see drawing)", Rs="der (sections, see drawing)",
                 Lp="ds", Llk="not published (0)", Cp=f"der: +-1 dB at {fhi / 1e3:g} kHz, Rsrc {rsrc / 1e3:g}k",
                 Cs="0 (lumped into Cp)", Rc="default Qc = 10 (est)",
                 Vsat=f"ds max output {vout:g} V rms at 30 Hz / n", Idc="ds (0.9 T bias)" if idc else "-"),
        url=URL_L60))


l1660("XF_LL1660_M", "atx_ct", "Lundahl LL1660PP Alt M'' PP-PP interstage 2.25+2.25:2+2",
      "Alt M'' 2.25+2.25 : 2+2", 4.5, 4.0, R_CC_SERIES, R_2P2, 290.0, 0.0, 20, 25e3, 15e3, 520)
l1660("XF_LL1660_N", "atx_ct", "Lundahl LL1660PP Alt N PP line output 2.25+2.25:1",
      "Alt N 2.25+2.25 : 1", 4.5, 1.0, R_CC_SERIES, R_ALL4_PAR, 290.0, 0.0, 16, 30e3, 15e3, 130)
l1660("XF_LL1660_Q", "atx", "Lundahl LL1660/18mA Alt Q SE line output 4.5:1",
      "Alt Q 4.5 : 1", 4.5, 1.0, R_CC_SERIES, R_ALL4_PAR, 100.0, 16e-3, 11, 35e3, 3e3, 57)
l1660("XF_LL1660_S", "atx", "Lundahl LL1660/10mA Alt S SE-SE interstage 4:4.5",
      "Alt S 4 : 4.5", 4.0, 4.5, R_ALL4_SERIES, R_CC_SERIES, 130.0, 10e-3, 25, 40e3, 14e3, 250)
l1660("XF_LL1660_T", "atx", "Lundahl LL1660/10mA Alt T SE-SE interstage 2:4.5",
      "Alt T 2 : 4.5", 2.0, 4.5, R_PAIRS_PAR, R_CC_SERIES, 33.0, 20e-3, 25, 30e3, 3.5e3, 250)
l1660("XF_LL1660_V", "atx_sct", "Lundahl LL1660/10mA Alt V SE-PP phase splitter 2.25:2+2",
      "Alt V 2.25 : 2+2", 2.25, 4.0, R_CC_PAR, R_2P2, 42.0, 18e-3, 25, 30e3, 3.5e3, 220)

# ----------------------------------------------------------------------------------
# Lundahl LL1538: primaries 44 ohm each (1 unit each), secondary 880 ohm (5 units)
# ----------------------------------------------------------------------------------
URL_L38 = "https://www.lundahltransformers.com/wp-content/uploads/datasheets/1538_8xl.pdf"
L38_RSRC, L38_FLO, L38_FHI, L38_DB = 200.0, 10.0, 100e3, 0.3
L38_FR, L38_Q = 200e3, 1 / math.sqrt(2)     # est: resonance and damping of the HF end


def l1538():
    """1:5 (primaries parallel). Lp: the smallest value that keeps the 10 Hz point within
    -0.3 dB (200 ohm source, no termination) -- der. Llk, Cs: est, a maximally flat
    (Q = 0.707) second-order HF end at 200 kHz, the lowest resonance that keeps 100 kHz
    within -0.3 dB; the datasheet only says 'self resonance > 120 kHz'."""
    rp1, rs, n = 22.0, 880.0, 5.0
    x = math.sqrt(10 ** (L38_DB / 10) - 1)
    lp1 = (L38_RSRC + rp1) / (2 * math.pi * L38_FLO * x)
    rsec = (L38_RSRC + rp1) * n ** 2 + rs              # series R seen by the secondary
    z0 = L38_Q * rsec
    lls = z0 / (2 * math.pi * L38_FR)                  # secondary-referred leakage
    cs = 1 / (2 * math.pi * L38_FR * z0)
    llk1 = lls / n ** 2
    common = dict(kind="atx", Cp=0.0, Cs=float(f"{cs:.4g}"), Rc=0.0, Idc=0.0, fsat=50.0, url=URL_L38)
    src = dict(Rs="ds 880 (secondary 5-6)", Llk="est (Q 0.707 at 200 kHz)", Cs="est (with Llk)",
               Rc="default Qc = 10 (est)", Cp="0", Idc="-",
               Vsat="ds 1 % THD at +10 dBu (2.5 V), 50 Hz, primaries parallel")
    PRESETS.append(dict(name="XF_LL1538_5", desc="Lundahl LL1538 mic input 1:5 (primaries parallel)",
                        n=5.0, Lp=float(f"{lp1:.4g}"), Llk=float(f"{llk1:.4g}"), Rp=rp1, Rs=rs, Vsat=2.5,
                        src=dict(src, n="ds 1:5", Rp="der 44 || 44",
                                 Lp="der: -0.3 dB at 10 Hz, 200 ohm, no termination"),
                        **common))
    # series primaries: twice the turns -> Lp and Llk x4, same core; knee voltage x2
    PRESETS.append(dict(name="XF_LL1538_25", desc="Lundahl LL1538 mic input 1:2.5 (primaries series)",
                        n=2.5, Lp=float(f"{4 * lp1:.4g}"), Llk=float(f"{4 * llk1:.4g}"), Rp=88.0, Rs=rs,
                        Vsat=5.0,
                        src=dict(src, n="ds 1:2.5", Rp="der 44 + 44", Lp="der: 4 x the 1:5 value (N^2)",
                                 Llk="est: 4 x the 1:5 value (N^2)",
                                 Vsat="der: 2 x the 1:5 value (twice the turns)"),
                        **common))


l1538()

# Saturation knee calibration (ksat = knee flux / design peak flux). The default 1.25 is
# the output-transformer calibration (est). For the parts with a published 1 % THD point,
# ksat is FITTED by fit_sat.py (LTspice, bisection) so that THD = 1 % at that point in
# the datasheet's own conditions; paste its output here.
KSAT_DEFAULT = 1.25
KSAT = {
    "XF_JT115KE": 1.193,      # fit_sat.py: -2.5 dBu at 20 Hz, test circuit 1
    "XF_LL1538_5": 1.108,     # fit_sat.py: +10 dBu (2.449 V) at 50 Hz, 200 ohm source
}
KSAT["XF_LL1538_25"] = KSAT["XF_LL1538_5"]     # same core and flux: same knee ratio

for _p in PRESETS:
    _p["ksat"] = KSAT.get(_p["name"], KSAT_DEFAULT)
    _p["src"]["ksat"] = ("fit_sat.py: 1 % THD at the ds point" if _p["name"] in KSAT
                         else f"{KSAT_DEFAULT} est (output-transformer calibration)")
    if not _p["Rc"]:
        _p["Rc_eff"] = 10 * 2 * math.pi * 1e3 * _p["Lp"]      # atx_ct default Qc = 10
    else:
        _p["Rc_eff"] = _p["Rc"]


def fmt(x):
    if x == 0:
        return "0"
    for unit, k in (("Meg", 1e6), ("k", 1e3)):
        if abs(x) >= k:
            return f"{x / k:.5g}{unit}"
    for unit, k in (("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(x) < 1 and abs(x) >= k:
            return f"{x / k:.5g}{unit}"
    return f"{x:.5g}"


PINS = {"atx": "P1 P2 S1 S2", "atx_sct": "P1 P2 S1 SC S2", "atx_ct": "P1 PC P2 S1 SC S2"}


def subckt_text(p):
    pins = PINS[p["kind"]]
    lines = [f"* {p['desc']}  [{p['url']}]"]
    lines += [f"*   {k}: {v}" for k, v in p["src"].items()]
    args = (f"n={p['n']:.6g} Lp={fmt(p['Lp'])} Llk={fmt(p['Llk'])} Rp={fmt(p['Rp'])}"
            f" Rs={fmt(p['Rs'])} Cp={fmt(p['Cp'])} Cs={fmt(p['Cs'])} Rc={fmt(p['Rc'])}"
            f" Idc={fmt(p['Idc'])} Vsat={fmt(p['Vsat'])} fsat={fmt(p['fsat'])}")
    lines += [f".subckt {p['name']} {pins} params: sat=0 ksat={p['ksat']:.4g}",
              f"X1 {pins} {p['kind']} {args} sat={{sat}} ksat={{ksat}}",
              f".ends {p['name']}"]
    # LTspice line length is not limited, but keep the X line readable: wrap with '+'
    out = []
    for ln in lines:
        if ln.startswith("X1 ") and len(ln) > 88:
            words, cur = ln.split(" "), ""
            for w in words:
                if len(cur) + len(w) + 1 > 88:
                    out.append(cur)
                    cur = "+ " + w
                else:
                    cur = (cur + " " + w) if cur else w
            out.append(cur)
        else:
            out.append(ln)
    return "\n".join(out)


if __name__ == "__main__":
    for p in PRESETS:
        print(p["name"], {k: p[k] for k in ("n", "Lp", "Llk", "Rp", "Rs", "Cp", "Cs", "Rc", "Idc", "Vsat")})
    d = JT_DS
    m = model(_jt, [2.5, 20, 1e3, 20e3, 90e3], d["Rg"], d["RL"])
    print("JT rel dB:", db(m["H"] / m["H"][2]), "Zi", abs(m["Zi"][2]), "Zo", abs(m["Zo"][2]),
          "gain", db(m["Hp"][2]))
