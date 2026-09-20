"""Preset table of speaker.sub: the one place where preset numbers live.

make_symbols.py writes the preset block of speaker.sub and the preset symbols from it;
bench_speaker.py checks the simulated speakers against the numbers kept here.

Sources (fetched 2026-09-14):
  Jensen   specification sheets, https://www.jensentone.com/specification-sheet/<id>
           (P10R = 36, C12N = 16, P12Q = 40): Re, Fs, Qms, Qes, Vas, Le @ 1 kHz.
  Eminence https://eminence.com/products/legend_1258: Re, Fs, Qms, Qes, Vas, Le.
  Celestion https://celestion.com/productpdf.php?id=<id> (Vintage 30 = 888, G12M
           Greenback = 899, G12T-75 = 898, G12H Anniversary = 900): Re and Fs only;
           Celestion publishes no Q, Vas or Le for its guitar speakers (see
           https://celestion.com/blog/thinking-of-using-thiele-small-parameters-to-design-a-guitar-speaker-cab-think/).
           Qms and Qes are derived here from Duncan Munro's measured impedance networks
           (1997) of the same speakers, sources/ltwiki/extracted/lib/lib/sub/speaker.lib
           (subckts VINT30, G12M, G12T75, G12H100): a parallel R-L-C (RD1, LD1, CD1)
           behind RL. Le for Celestion: estimate (see LE_EST).
"""
from __future__ import annotations

import math

# Munro networks: RL (series R), RD1 (parallel R), LD1 (H), CD1 (F)
MUNRO = {
    "VINT30": (7.5, 12.5, 20e-3, 250e-6),
    "G12M": (7.5, 12.0, 20e-3, 225e-6),
    "G12T75": (7.5, 15.0, 20e-3, 190e-6),
    "G12H100": (6.5, 13.0, 20e-3, 190e-6),
}


def munro_q(name):
    """Qms, Qes and Fs of a parallel-RLC motional network behind Re:
    Qms = Res*sqrt(C/L), Qes = Re*sqrt(C/L), Fs = 1/(2 pi sqrt(L C))."""
    re, res, l, c = MUNRO[name]
    k = math.sqrt(c / l)
    return res * k, re * k, 1 / (2 * math.pi * math.sqrt(l * c))


# Le estimate for Celestion 8-ohm 12" (1.75" coil) guitar speakers: median of the
# maker-published 8-ohm Le of comparable 12" guitar drivers used below (Eminence Legend
# 1258 0.7 mH, Jensen P12Q 0.67 mH, Jensen C12N 0.9 mH) = 0.7 mH; 16-ohm versions
# scaled by the Re ratio (more turns of thinner wire in the same space: L ~ N^2 ~ Re).
LE_EST = 0.7e-3
N_EST = 0.7          # Leach exponent, typical value (estimate) for all presets

URL_J = "https://www.jensentone.com/specification-sheet/{}"
URL_C = "https://celestion.com/productpdf.php?id={}"
URL_E = "https://eminence.com/products/legend_1258"

PRESETS = []


def jensen(name, sheet, ohm, re, fs, qms, qes, vas, le, note=""):
    PRESETS.append(dict(name=name, maker="Jensen", ohm=ohm, Re=re, Fs=fs, Qms=qms, Qes=qes,
                        Vas=vas, Le=le, n=N_EST, url=URL_J.format(sheet),
                        src=dict(Re="ds", Fs="ds", Qms="ds", Qes="ds", Vas="ds", Le="ds"), note=note))


def celestion(name, pid, ohm, re, fs, re8, munro, model):
    qms, qes, fm = munro_q(munro)
    le = LE_EST * (re / re8)
    PRESETS.append(dict(name=name, maker="Celestion", ohm=ohm, Re=re, Fs=fs, Qms=qms, Qes=qes,
                        Vas=0, Le=le, n=N_EST, url=URL_C.format(pid),
                        src=dict(Re="ds", Fs="ds", Qms=f"Munro {munro}", Qes=f"Munro {munro}",
                                 Vas="-", Le="est"),
                        note=f"{model}; Munro's {munro} network resonates at {fm:.1f} Hz"))


# Jensen (maker T/S)
jensen("SPK_P10R_4", 36, 4, 3.6, 99, 23.8, 1.45, 29e-3, 0.35e-3)
jensen("SPK_P10R_8", 36, 8, 6.68, 97, 14.83, 1.82, 27.4e-3, 0.54e-3)
jensen("SPK_P10R_16", 36, 16, 12.3, 99, 23.4, 1.94, 29.5e-3, 0.75e-3)
jensen("SPK_P12Q_8", 40, 8, 5.6, 90.5, 11.57, 2.46, 39.5e-3, 0.67e-3,
       note="Qes 2.46 from the spec sheet (consistent with its Qts 2.03); the product page's 3.33 is not")
jensen("SPK_P12Q_16", 40, 16, 12.45, 90, 12.68, 2.81, 41.2e-3, 0.60e-3)
jensen("SPK_P12Q_32", 40, 32, 25.2, 85.6, 10.94, 3.33, 46.6e-3, 1.59e-3)
jensen("SPK_C12N_8", 16, 8, 6.05, 113, 7.52, 1.18, 22.6e-3, 0.90e-3)
jensen("SPK_C12N_16", 16, 16, 12.5, 110, 6.84, 1.25, 28e-3, 1.55e-3,
       note="the sheet's 4-ohm column (Re 6.5) is inconsistent and not used")
# Eminence (maker T/S)
PRESETS.append(dict(name="SPK_LEGEND1258_8", maker="Eminence", ohm=8, Re=7.44, Fs=94, Qms=6.15,
                    Qes=1.18, Vas=32.5e-3, Le=0.7e-3, n=N_EST, url=URL_E,
                    src=dict(Re="ds", Fs="ds", Qms="ds", Qes="ds", Vas="ds", Le="ds"), note=""))
# Celestion (Re, Fs from Celestion; Qms, Qes from Munro's measured network; Le estimate)
celestion("SPK_V30_8", 888, 8, 7.3, 75, 7.3, "VINT30", "Vintage 30")
celestion("SPK_V30_16", 888, 16, 12.9, 75, 7.3, "VINT30", "Vintage 30")
celestion("SPK_G12M_8", 899, 8, 6.7, 75, 6.7, "G12M", "G12M Greenback")
celestion("SPK_G12M_16", 899, 16, 13.1, 75, 6.7, "G12M", "G12M Greenback")
celestion("SPK_G12H_8", 900, 8, 6.7, 85, 6.7, "G12H100",
          "G12H Anniversary (Q from Munro's G12H-100, the closest measured G12H)")
celestion("SPK_G12H_16", 900, 16, 13.1, 85, 6.7, "G12H100",
          "G12H Anniversary (Q from Munro's G12H-100, the closest measured G12H)")
celestion("SPK_G12T75_8", 898, 8, 6.77, 85, 6.77, "G12T75", "G12T-75")
celestion("SPK_G12T75_16", 898, 16, 12.9, 85, 6.77, "G12T75", "G12T-75")


def fmt(x):
    for unit, k in (("m", 1e-3), ("u", 1e-6)):
        if abs(x) < 1 and abs(x) >= k:
            return f"{x / k:.4g}{unit}"
    return f"{x:.5g}"


def subckt_text(p):
    vas = fmt(p["Vas"]) if p["Vas"] else "30m"
    head = f"* {p['maker']} {p['name'][4:]}: {p['url']}" + (f"  ({p['note']})" if p["note"] else "")
    return "\n".join([
        head,
        f".subckt {p['name']} P N params: Vb=0 n={p['n']:g}" + ("" if p["Vas"] else " Vas=30m"),
        f"X1 P N speaker Re={fmt(p['Re'])} Fs={fmt(p['Fs'])} Qms={p['Qms']:.4g} Qes={p['Qes']:.4g}"
        f" Le={fmt(p['Le'])} n={{n}} Vb={{Vb}} Vas={{Vas}}" if not p["Vas"] else
        f"X1 P N speaker Re={fmt(p['Re'])} Fs={fmt(p['Fs'])} Qms={p['Qms']:.4g} Qes={p['Qes']:.4g}"
        f" Le={fmt(p['Le'])} n={{n}} Vb={{Vb}} Vas={vas}",
        f".ends {p['name']}",
    ])
