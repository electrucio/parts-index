#!/usr/bin/env python3
"""Write the .asy symbols of ldr.sub and the demo schematic.

Geometry (all variants): resistor body between A on top (16,16) and B at the bottom
(16,112); light input L on the left (-32,64), with two arrows pointing at the body.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "LINE Normal 16 16 16 24", "LINE Normal 16 104 16 112",
    "RECTANGLE Normal 4 24 28 104",
    "CIRCLE Normal -8 36 40 92",
    # light arrows from the L pin towards the body
    "LINE Normal -32 64 -24 64",
    "LINE Normal -24 48 -4 58", "LINE Normal -4 58 -12 58", "LINE Normal -4 58 -9 51",
    "LINE Normal -24 72 -4 82", "LINE Normal -4 82 -12 82", "LINE Normal -4 82 -9 75",
    "LINE Normal -24 48 -24 72",
    "TEXT -28 40 Right 0 lux",
]
PINS = [(16, 16, "A"), (16, 112, "B"), (-32, 64, "L")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 48 24 Left 2", "WINDOW 3 48 104 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}", "SYMATTR ModelFile ldr.sub",
            f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("ldr", "R10=14.14k gamma=0.6 Rdark=10Meg tau=21.09m ka=0.8336 kLH=1.2 hist=1",
    "CdS LDR, R = R10 (E/10 lux)^-gamma with attack/decay and light history. "
    "Pins A B L (V(L) = lux)")
for p, r in (("GL5516", "5-10k"), ("GL5528", "10-20k"), ("GL5537_1", "20-30k"),
             ("GL5539", "50-100k")):
    asy(p, "hist=1", f"{p.replace('_', '-')} CdS photoresistor, {r} at 10 lux. Pins A B L (lux)")

# demo: light-controlled attenuator. 1 kHz into 10k, GL5528 to ground; a lamp gives
# 100 lux from 50 ms to 300 ms. GL5528 at (320,96): A (336,112) B (336,208) L (288,160)
DEMO = r"""Version 4
SHEET 1 900 400
FLAG 0 112 in
FLAG 0 192 0
FLAG 96 112 in
FLAG 96 192 out
FLAG 336 112 out
FLAG 336 208 0
FLAG 288 160 lux
FLAG 192 112 lux
FLAG 192 192 0
FLAG 448 112 out
FLAG 448 192 0
SYMBOL voltage 0 96 R0
SYMATTR InstName VIN
SYMATTR Value SINE(0 1 1k)
SYMBOL res 80 96 R0
SYMATTR InstName R1
SYMATTR Value 10k
SYMBOL voltage 192 96 R0
SYMATTR InstName VLUX
SYMATTR Value PWL(0 0 50m 0 50.1m 100 300m 100 300.1m 0)
SYMBOL GL5528 320 96 R0
SYMATTR InstName XLDR
SYMBOL res 432 96 R0
SYMATTR InstName RL
SYMATTR Value 1Meg
TEXT 0 272 Left 2 !.tran 0 800m 0 20u
TEXT 0 -40 Left 2 ;Light-controlled attenuator: V(lux) is the illuminance on the GL5528. Fast attack at 50 ms, slow decay after 300 ms
"""
(HERE / "demo_ldr.asc").write_text(DEMO)
print("symbols: ldr, GL5516, GL5528, GL5537_1, GL5539")
