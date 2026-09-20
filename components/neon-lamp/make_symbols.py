#!/usr/bin/env python3
"""Write the .asy symbols of neon.sub and the demo schematic.

Geometry: glow lamp (circle, two electrode plates, gas dot), A on top (16,16), K at
the bottom (16,112), like the lamp and the LDR.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "LINE Normal 16 16 16 52", "LINE Normal 16 76 16 112",
    "CIRCLE Normal -8 40 40 88",
    "LINE Normal 2 52 30 52", "LINE Normal 2 76 30 76",
    "CIRCLE Normal 26 60 34 68",
]
PINS = [(16, 16, "A"), (16, 112, "K")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 48 40 Left 2", "WINDOW 3 48 88 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile neon.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("neon", "Vb=75 Ve=55 Ri=5.5k Imin=100u tion=5u toff=20u",
    "Neon glow lamp (breakdown, glow, extinction hysteresis). Pins A K")
for p, d in (("NE2", "NE-2 (A1A) neon lamp"), ("NE2E", "NE-2E (A9A) neon lamp"),
             ("NE2H", "NE-2H (C2A) high-brightness neon lamp")):
    asy(p, "", f"{d}. Pins A K")

# demo: neon relaxation oscillator, the LFO of old neon/LDR tremolos. 150 V through
# 2.2 Meg charges 0.47 uF; the NE-2 fires at Vb and discharges it to the extinguishing
# voltage: a ~4 Hz sawtooth on SAW. NE2 at (400,96): A (416,112) K (416,208).
DEMO = r"""Version 4
SHEET 1 700 400
FLAG 0 112 hv
FLAG 0 192 0
FLAG 176 112 hv
FLAG 176 192 saw
FLAG 288 112 saw
FLAG 288 176 0
FLAG 416 112 saw
FLAG 416 208 0
SYMBOL voltage 0 96 R0
SYMATTR InstName VB
SYMATTR Value PWL(0 0 10m 150)
SYMBOL res 160 96 R0
SYMATTR InstName R1
SYMATTR Value 2.2Meg
SYMBOL cap 272 112 R0
SYMATTR InstName C1
SYMATTR Value 470n
SYMBOL NE2 400 96 R0
SYMATTR InstName XN1
TEXT 0 272 Left 2 !.tran 0 3 0 50u
TEXT 0 -40 Left 2 ;Neon relaxation oscillator (tremolo LFO): period = R1 C1 ln((150 - Vx)/(150 - Vb)), GE Glow Lamp Manual Fig. 2.4
"""
(HERE / "demo_neon.asc").write_text(DEMO)
print("symbols: neon, NE2, NE2E, NE2H; demo_neon.asc")
