#!/usr/bin/env python3
"""Write the .asy symbol of vu.sub and the demo schematic.

Geometry: meter box with a dial arc, needle and "VU"; input P on top-left (0,16),
N bottom-left (0,112), deflection output DEFL on the right (128,64).
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "RECTANGLE Normal 16 16 112 112",
    "ARC Normal 24 40 104 120 100 72 28 72",
    "LINE Normal 64 96 88 56",
    "TEXT 64 100 Center 0 VU",
    "LINE Normal 0 16 16 16", "LINE Normal 0 112 16 112", "LINE Normal 112 64 128 64",
    "TEXT 20 24 Left 0 +",
]
PINS = [(0, 16, "P"), (0, 112, "N"), (128, 64, "DEFL")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 16 0 Left 2", "WINDOW 3 16 136 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile vu.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("vu_meter", "Vref=1.228 Rin=7.5k fn=2.1505 zeta=0.8127",
    "VU meter (IEC 60268-17 ballistics, full-wave rectifier). Pins P N DEFL (1 = 0 VU)")

# demo: a 1 kHz tone burst at 0 VU (1.228 V RMS) from 0.1 s to 1.1 s into the meter;
# DEFL rises to 99 % in 0.3 s with a 1.25 % overshoot and falls back.
# Meter at (400,96): P (400,112) N (400,208) DEFL (528,160).
DEMO = r"""Version 4
SHEET 1 800 400
FLAG 0 112 in
FLAG 0 192 0
FLAG 400 112 in
FLAG 400 208 0
FLAG 528 160 defl
SYMBOL bv 0 96 R0
SYMATTR InstName BIN
SYMATTR Value V=1.7367*sin(2*pi*1k*time)*(time > 0.1)*(time < 1.1)
SYMBOL vu_meter 400 96 R0
SYMATTR InstName XVU
TEXT 0 272 Left 2 !.tran 0 2 0 20u
TEXT 0 -40 Left 2 ;VU meter ballistics: 1 kHz burst at 0 VU; V(defl) = 1 at 0 VU, VU = 20 log10(V(defl))
"""
(HERE / "demo_vu.asc").write_text(DEMO)
print("symbols: vu_meter; demo_vu.asc")
