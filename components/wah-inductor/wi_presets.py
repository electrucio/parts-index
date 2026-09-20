"""Preset table of wah-inductor.sub: the one place where preset numbers live.

make_symbols.py writes the preset block of wah-inductor.sub and the preset symbols from
it; bench_wah-inductor.py checks the simulated inductors against the numbers kept here.

Source of every preset (fetched 2026-09-14):
  PCB  "Wah Inductors. No hype. Just measurements.", PedalPCB Community Forum, thread
       24076, first post by Stickman393 (Nov 9, 2024),
       https://forum.pedalpcb.com/threads/wah-inductors-no-hype-just-measurements.24076/
       Older readings list, format "R ohms/L mH (R ohms/L mH)"; the author: "The numbers
       in parenthesis are from my Fluke 87+ and my honeytek LC meter." The numbers
       outside the parentheses are from a cheaper component tester (the thread calls
       these the TC-1 readings); for several cup-core parts it reads 14-77 mH, which is
       not credible for a 0.5 H wah inductor, so the preset L is the Honeytek LC-meter
       value and the preset R the Fluke 87+ ohmmeter value. Where that pair is missing or
       garbled the substitute is stated per preset (src_L / src_R).
       The thread's later Hantek 1832C sweeps (100 Hz..10 kHz, 648 mV) sit in a linked
       spreadsheet that could not be read, so no frequency dependence of L or Q is used.
  ES   ElectroSmash, "Dunlop CryBaby GCB-95 Circuit Analysis",
       https://www.electrosmash.com/crybaby-gcb-95 (read via the mirror
       https://electrosmash.mas-effects.com/crybaby-gcb-95.html): "between 200mH to 1H
       (500mH typ.)" -- the generic 500 mH default.

Not published for any of these parts: core loss (Q vs frequency), self-capacitance,
saturation current. The subckt has parameters for the first two, defaulting to "not
modelled" (Qc = 0, Cp = 0); see README.md.
"""
from __future__ import annotations

URL_PCB = "https://forum.pedalpcb.com/threads/wah-inductors-no-hype-just-measurements.24076/"

PRESETS = []


def add(name, desc, L, R, src_L, src_R, other, note=""):
    """other: the other meter's reading 'R ohms/L mH' as printed, for the record."""
    PRESETS.append(dict(name=name, desc=desc, L=L, R=R, src_L=src_L, src_R=src_R,
                        other=other, note=note))


add("WAH_RED_FASEL", "Dunlop red Fasel (toroid)", 583e-3, 17.0,
    "Honeytek", "Fluke 87+", "17.5 ohms/565.2mH")
add("WAH_YELLOW_FASEL", "Dunlop yellow Fasel (cup core)", 620e-3, 13.9,
    "Honeytek", "Fluke 87+", "14.7 ohms/24.26mH",
    note="the tester's 24.26 mH is not credible")
add("WAH_GCB95", "Dunlop Cry Baby GCB-95 stock (modern)", 645e-3, 17.4,
    "Honeytek", "Fluke 87+", "17.8 ohms/599.4mH")
add("WAH_GCB95_90S", "Dunlop Cry Baby GCB-95 (late 90s-early 00s, black cylinder)", 690e-3, 14.6,
    "Honeytek", "Fluke 87+", "15.1 ohms/24.85mH",
    note="the tester's 24.85 mH is not credible")
add("WAH_GCB95_80S", "Dunlop Cry Baby GCB-95 (80s, Mexico)", 343e-3, 11.8,
    "Honeytek", "Fluke 87+", "12 ohms/76.78mH")
add("WAH_HENDRIX", "Dunlop Hendrix Cry Baby (late 90s-early 00s)", 564e-3, 13.7,
    "Honeytek", "Fluke 87+", "14.1 ohms/14.03mH",
    note="the tester's 14.03 mH is not credible")
add("WAH_535Q", "Dunlop Cry Baby 535Q (metal can)", 593.3e-3, 18.3,
    "tester", "tester", "-",
    note="only the tester reading is given for this part")
add("WAH_HALO", "Whipple Halo", 580.7e-3, 27.8,
    "tester", "Fluke 87+", "Honeytek '522uH'",
    note="the Honeytek value is printed as 522uH (unit typo); the tester's 580.7 mH is used")
add("WAH_SOUL_HALO", "Sabbadius Soul Halo", 510e-3, 29.5,
    "Honeytek", "Fluke 87+", "30.3 ohms/597.8mH")
add("WAH_MAMMOTH", "Mammoth / SBP ME-6", 622e-3, 29.4,
    "Honeytek", "Fluke 87+", "30.7 ohms/730.3mH")


def fmt(x):
    for unit, k in (("m", 1e-3), ("u", 1e-6)):
        if abs(x) < 1 and abs(x) >= k:
            return f"{x / k:.4g}{unit}"
    return f"{x:.5g}"


def subckt_text(p):
    head = (f"* {p['desc']}: L {p['src_L']}, R {p['src_R']}, PedalPCB thread 24076 {URL_PCB}"
            + (f"  ({p['note']})" if p["note"] else ""))
    return "\n".join([
        head,
        f".subckt {p['name']} A B params: Qc=0 Cp=0",
        f"X1 A B wah_inductor L={fmt(p['L'])} R={fmt(p['R'])} Qc={{Qc}} Cp={{Cp}}",
        f".ends {p['name']}",
    ])
