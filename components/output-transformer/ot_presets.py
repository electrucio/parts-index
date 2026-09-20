"""Preset table of output-transformer.sub: the one place where preset numbers live.

make_symbols.py writes the preset block of output-transformer.sub and the preset
symbols from it; bench_output-transformer.py checks the simulated transformer against
the *sheet* numbers kept here. Sources: README.md, "Provenance".

Keys
  base     subckt the preset wraps          amp     what it replaces (Hammond's list)
  Za, Z    primary impedance; tap impedances (3 taps) or Zs (one secondary)
  P        rated power (sheet)              fsat    full-power low frequency; src in fsat_src
  L_sheet  primary L on the sheet, measured at f_L; half=True if measured on a
           half-primary (whole primary = 4 x)
  Llk      leakage used by the model (whole primary); Llk_src "ds" (sheet),
           "fit" (fit_presets.py), "sc" (scaled); Llk_sheet = the sheet's figure
  Cw       fitted winding capacitance (fit_presets.py) or estimate (Cw_src)
  Rp       (DCR P1-CT, DCR CT-P2) when the sheet gives halves, else Rpri (P1-P2)
  Rt       COM->tap DCRs (3 taps) or Rsec; Rt_src per value: "ds" / "sc" / "est"
  Idc      rated DC current (SE sheets)
"""
from __future__ import annotations

import math

URL = "https://www.hammfg.com/files/parts/pdf/{}.pdf"

PRESETS = [
    # --- Fender replacements (Hammond 1760), 4/8/16-ohm taps ---------------------------
    dict(name="OT_1760E", part="1760E", base="ot_pp_tap", amp="Fender 5E3 Deluxe, Princeton (Fender 50246)",
         Za=8500, Z=(4, 8, 16), P=15, L_sheet=21.6, f_L=1e3, Llk=42.1e-3, Llk_src="fit", Llk_sheet=323.9e-3,
         Cw=99e-12, Rp=(154.40, 159.20), Rt=(0.410, 0.540, 0.830), fsat=70),
    dict(name="OT_1760H", part="1760H", base="ot_pp_tap", amp="Fender Deluxe / Deluxe Reverb (125A1A, 022640, 041318)",
         Za=6600, Z=(4, 8, 16), P=20, L_sheet=25.8, f_L=1e3, Llk=12.30e-3, Llk_src="ds",
         Cw=118e-12, Rpri=347.8, Rt=(0.686, 0.803, 1.157), fsat=70),
    dict(name="OT_1760J", part="1760J", base="ot_pp_tap", amp="Fender Pro / Bandmaster / Tremolux (125A6A, 022848, 125A7A)",
         Za=4000, Z=(4, 8, 16), P=40, L_sheet=19.5, f_L=1e3, Llk=35.93e-3, Llk_src="ds",
         Cw=20e-12, Rpri=185.0, Rt=(0.356, 0.502, 0.910), fsat=70),
    dict(name="OT_1760L", part="1760L", base="ot_pp_tap", amp="Fender Bassman 5F6A / AA864 / AB165 (022871, 125A13A)",
         Za=4200, Z=(4, 8, 16), P=50, L_sheet=5.72, f_L=1e3, Llk=3.506e-3, Llk_src="ds",
         Cw=66e-12, Rp=(46.48, 51.04), Rt=(0.238, 0.405, 0.578), fsat=70),
    dict(name="OT_1760W", part="1760W", base="ot_pp_tap", amp="Fender Twin Reverb / Showman / Bassman 100 (125A29A, 022689)",
         Za=2000, Z=(4, 8, 16), P=100, L_sheet=4.55, f_L=1e3, Llk=1.280e-3, Llk_src="ds",
         Cw=20e-12, Rp=(13.24, 14.44), Rt=(0.110, 0.175, 0.279), fsat=70),
    # --- Marshall replacements (Hammond 1750), 4/8/16 -----------------------------------
    dict(name="OT_1750N", part="1750N", base="ot_pp_tap", amp="Marshall JMP / JCM800 50 W (P-TM050)",
         Za=3200, Z=(4, 8, 16), P=50, L_sheet=18.3, f_L=1e3, Llk=13.41e-3, Llk_src="ds",
         Cw=477e-12, Rp=(41.74, 43.14), Rt=(0.770, None, None), fsat=70),
    dict(name="OT_1750U", part="1750U", base="ot_pp_tap", amp="Marshall JMP / JCM800 100 W (P-TM0100)",
         Za=1700, Z=(4, 8, 16), P=100, L_sheet=8.85, f_L=1e3, Llk=7.97e-3, Llk_src="ds",
         Cw=20e-12, Rp=(15.36, 16.56), Rt=(None, None, 0.320), fsat=70),
    dict(name="OT_1750Q", part="1750Q", base="ot_pp_tap", amp="Marshall JTM45 (P-TM450)",
         Za=7371, Z=(4, 8, 16), P=50, L_sheet=38.0, f_L=1e3, Llk=19.87e-3, Llk_src="ds",
         Cw=453e-12, Rp=(41.74, 43.14), Rt=(None, None, 0.580), fsat=70),
    # --- Vox replacements (Hammond 1750) ------------------------------------------------
    dict(name="OT_1750Y", part="1750Y", base="ot_pp", amp="Vox AC15 vintage (P-TVO15)",
         Za=6200, Zs=8, P=15, L_sheet=14.6, f_L=1e3, Llk=14.04e-3, Llk_src="ds",
         Cw=207e-12, Rpri=289.0, Rt=(0.480,), fsat=70),
    dict(name="OT_1750V", part="1750V", base="ot_pp", amp="Vox AC30 vintage (P-TVO30V), 16-ohm tap",
         Za=4000, Zs=16, P=30, L_sheet=6.30, f_L=1e3, Llk=5.14e-3, Llk_src="ds",
         Cw=135e-12, Rp=(70.37, 70.30), Rt=(0.720,), fsat=70),
    dict(name="OT_1750V_8", part="1750V", base="ot_pp", amp="Vox AC30 vintage (P-TVO30V), 8-ohm tap",
         Za=4000, Zs=8, P=30, L_sheet=6.30, f_L=1e3, Llk=5.14e-3, Llk_src="ds",
         Cw=135e-12, Rp=(70.37, 70.30), Rt=(None,), Rt_from=(0.720, 16), fsat=70),
    # --- Hi-fi ultra-linear (Hammond 1650), 40 % taps, 8-ohm hook-up --------------------
    dict(name="OT_1650F", part="1650F", base="ot_pp_ul", amp="hi-fi UL 25 W (6V6, 6L6GC, EL34)",
         Za=7600, Zs=8, P=25, ul=0.4, L_sheet=285, f_L=60, half=True, Llk=38.8e-3, Llk_src="fit",
         Llk_sheet=10.40e-3, Cw=32e-12, Rpri=210.0, Rt=(None,), Rsec_pair=(0.220, 0.270), fsat=30, fsat_src="ds"),
    dict(name="OT_1650H", part="1650H", base="ot_pp_ul", amp="hi-fi UL 40 W (6L6GC, EL34)",
         Za=6600, Zs=8, P=40, ul=0.4, L_sheet=245, f_L=60, half=True, Llk=35.2e-3, Llk_src="fit",
         Llk_sheet=10.60e-3, Cw=80e-12, Rp=(77.0, 68.0), Rt=(None,), Rsec_pair=(0.160, 0.272), fsat=30, fsat_src="ds"),
    dict(name="OT_1650N", part="1650N", base="ot_pp_ul", amp="hi-fi UL 60 W (EL34, 6550, KT88)",
         Za=4300, Zs=8, P=60, ul=0.4, L_sheet=134, f_L=60, half=True, Llk=17.9e-3, Llk_src="fit",
         Llk_sheet=7.72e-3, Cw=133e-12, Rpri=82.5, Rt=(None,), Rsec_pair=(0.230, 0.370), fsat=30, fsat_src="ds"),
    dict(name="OT_1650R", part="1650R", base="ot_pp_ul", amp="hi-fi UL 100 W (6550, KT88)",
         Za=5000, Zs=8, P=100, ul=0.4, L_sheet=320, f_L=60, half=True, Llk=26.6e-3, Llk_src="fit",
         Llk_sheet=10.84e-3, Cw=99e-12, Rp=(54.59, 46.62), Rt=(None,), Rsec_pair=(0.300, 0.420), fsat=30, fsat_src="ds"),
    dict(name="OT_1650T", part="1650T", base="ot_pp_ul", amp="hi-fi UL 120 W (4 x 6550 / KT88)",
         Za=1900, Zs=8, P=120, ul=0.4, L_sheet=124, f_L=60, half=True, Llk=5.96e-3, Llk_src="fit",
         Llk_sheet=4.30e-3, Cw=151e-12, Rpri=47.10, Rt=(None,), Rsec_pair=(0.230, 0.360), fsat=30, fsat_src="ds"),
    # --- Single-ended --------------------------------------------------------------------
    dict(name="OT_1760C", part="1760C", base="ot_se_tap", amp="Fender Champ 5F1 / AA764, Princeton, Vibro Champ (125A35A, 022905), 8 k tap",
         Za=8000, Z=(3.2, 8, 16), P=5, L_sheet=23.0, f_L=1e3, Llk=6.03e-3, Llk_src="sc", Llk_sheet=719.5e-3,
         Cw=334e-12, Cw_src="sc", Rpri=359.9, Rt=(0.278, 0.624, 1.491), Idc=40e-3, fsat=70),
    dict(name="OT_1760C_5K", part="1760C", base="ot_se_tap", amp="as OT_1760C, 5 k tap",
         Za=5000, Z=(3.2, 8, 16), P=5, L_sheet=16.2, f_L=1e3, Llk=3.77e-3, Llk_src="fit", Llk_sheet=583.0e-3,
         Cw=534e-12, Rpri=272.08, Rt=(0.278, 0.624, 1.491), Idc=40e-3, fsat=70),
    dict(name="OT_125ESE", part="125ESE", base="ot_se_tap", amp="universal SE 15 W; lugs GRN/YEL/WHT = 8/16/32 ohm at 10 k",
         Za=10000, Z=(8, 16, 32), P=15, L_sheet=5.43, f_L=1e3, Llk=16.8e-3, Llk_src="fit",
         Cw=200e-12, Cw_src="est", Rpri=103.0, Rt=(0.225, 0.297, 0.412), Idc=80e-3, fsat=100, fsat_src="ds"),
    dict(name="OT_125CSE", part="125CSE", base="ot_se_tap", amp="universal SE 8 W; lugs GRN/YEL/WHT = 8/16/32 ohm at 10 k",
         Za=10000, Z=(8, 16, 32), P=8, L_sheet=9.28, f_L=1e3, Llk=16.5e-3, Llk_src="fit",
         Cw=200e-12, Cw_src="est", Rpri=200.0, Rt=(0.312, 0.428, 0.595), Idc=60e-3, fsat=100, fsat_src="ds"),
]


def model_params(p: dict) -> dict:
    """Numbers the model uses (derived from the sheet numbers above)."""
    w = 2 * math.pi * p["f_L"]
    L_app = p["L_sheet"] * (4 if p.get("half") else 1)      # whole-primary apparent L
    # the meter sees Lp in parallel with the winding capacitance: L_app = Lp/(1 - w^2 Lp Cw)
    Lp = L_app / (1 + w * w * L_app * p["Cw"])
    if "Rp" in p:
        Rpri = p["Rp"][0] + p["Rp"][1]
        rbal = p["Rp"][0] / Rpri
    else:
        Rpri, rbal = p["Rpri"], 0.5
    out = dict(Za=p["Za"], P=p["P"], Lp=Lp, Llk=p["Llk"], Cw=p["Cw"], Rpri=Rpri, rbal=rbal)
    if "Z" in p:
        Z = p["Z"]
        known = [(z, r) for z, r in zip(Z, p["Rt"]) if r is not None]
        z0, r0 = known[0]
        Rt = [r if r is not None else r0 * math.sqrt(z / z0) for z, r in zip(Z, p["Rt"])]
        out.update(Z1=Z[0], Z2=Z[1], Z3=Z[2], R1=Rt[0], R2=Rt[1], R3=Rt[2])
    else:
        if p["Rt"][0] is not None:
            Rsec = p["Rt"][0]
        elif "Rt_from" in p:
            r0, z0 = p["Rt_from"]
            Rsec = r0 * math.sqrt(p["Zs"] / z0)
        else:
            Rsec = sum(p["Rsec_pair"]) / 2
        out.update(Zs=p["Zs"], Rsec=Rsec)
    if "ul" in p:
        out["ul"] = p["ul"]
    if "Idc" in p:
        out["Idc"] = p["Idc"]
    out["fsat"] = p["fsat"]
    return out


def pins(base: str) -> list[str]:
    return {"ot_pp": ["P1", "CT", "P2", "SP", "SN"],
            "ot_pp_ul": ["P1", "G1", "CT", "G2", "P2", "SP", "SN"],
            "ot_pp_tap": ["P1", "CT", "P2", "COM", "S1", "S2", "S3"],
            "ot_pp_ul_tap": ["P1", "G1", "CT", "G2", "P2", "COM", "S1", "S2", "S3"],
            "ot_se": ["P", "BP", "SP", "SN"],
            "ot_se_tap": ["P", "BP", "COM", "S1", "S2", "S3"]}[base]


def fmt(x: float) -> str:
    for unit, k in (("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(x) < 1 and abs(x) >= k:
            return f"{x / k:.4g}{unit}"
    return f"{x:.5g}"


def subckt_text(p: dict) -> str:
    m = model_params(p)
    order = ["Za", "Z1", "Z2", "Z3", "Zs", "P", "ul", "Lp", "Llk", "Cw", "Rpri", "rbal",
             "R1", "R2", "R3", "Rsec", "Idc"]
    kv = " ".join(f"{k}={fmt(m[k])}" for k in order if k in m)
    pl = " ".join(pins(p["base"]))
    body = (f"X1 {pl} {p['base']} {kv} fsat={{fsat}} sat={{sat}} ksat={{ksat}} Qc={{Qc}}")
    # wrap at ~88 columns with + continuation lines
    words, lines, cur = body.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > 86:
            lines.append(cur)
            cur = "+ " + wd
        else:
            cur = (cur + " " + wd).strip() if cur else wd
    lines.append(cur)
    return "\n".join([f"* {p['amp']}  [Hammond {p['part']}]",
                      f".subckt {p['name']} {pl} params: sat=1 fsat={m['fsat']:g} ksat=1.25 Qc=3"]
                     + lines + [f".ends {p['name']}"])
