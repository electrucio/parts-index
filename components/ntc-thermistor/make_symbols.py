#!/usr/bin/env python3
"""Write the .asy symbols of ntc.sub and the demo schematic.

Geometry: resistor box crossed by the thermistor's bent line, "-t" mark; A on top
(16,16), B at the bottom (16,112), the same footprint as the lamp and the LDR.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "LINE Normal 16 16 16 32", "LINE Normal 16 96 16 112",
    "RECTANGLE Normal 4 32 28 96",
    "LINE Normal -8 100 0 100", "LINE Normal 0 100 40 28",
    "TEXT 34 92 Left 0 -t",
]
PINS = [(16, 16, "A"), (16, 112, "B")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 48 40 Left 2", "WINDOW 3 48 72 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile ntc.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("ntc", "R25=10 B=3058 D=0 dth=11m Cth=0.33 Ta=25",
    "NTC thermistor with self-heating (beta model). Pins A B")
for p, d in (("SL10_10003", "Ametherm SL10 10003 inrush limiter, 10 ohm 3 A"),
             ("B57236S0100", "TDK/EPCOS S236 inrush limiter, 10 ohm 3.5 A"),
             ("B57164K0103", "TDK/EPCOS K164 NTC, 10 kohm B25/100 4300 K")):
    asy(p, "Ta=25", f"{d}. Pins A B")

# demo: inrush limiting in a capacitor-input rectifier. 120 V RMS switched on at the
# crest at 1 ms (behavioural source: a DC source would pre-charge C1 in the .op), SL10 in
# series with the line, a half-wave rectifier (generic silicon), 470 uF and a 1k load.
# Ground-referenced on purpose: a floating source feeding a bridge makes LTspice crawl.
# NTC at (96,96): A (112,112) B (112,208).
DEMO = r"""Version 4
SHEET 1 700 400
FLAG 0 112 l
FLAG 0 192 0
FLAG 112 112 l
FLAG 112 208 ln
FLAG 224 96 ln
FLAG 224 160 p
FLAG 320 112 p
FLAG 320 176 0
FLAG 416 112 p
FLAG 416 192 0
SYMBOL bv 0 96 R0
SYMATTR InstName BAC
SYMATTR Value V=if(time < 1m, 0, 169.7*cos(2*pi*60*(time - 1m)))
SYMBOL SL10_10003 96 96 R0
SYMATTR InstName XNTC
SYMBOL diode 208 96 R0
SYMATTR InstName D1
SYMATTR Value DR
SYMBOL cap 304 112 R0
SYMATTR InstName C1
SYMATTR Value 470u
SYMBOL res 400 96 R0
SYMATTR InstName RL
SYMATTR Value 1k
TEXT 0 256 Left 2 !.model DR D(Is=10n N=1.8 Rs=30m Cjo=30p BV=1k IBV=5u)\n.tran 0 0.3 0 20u\n.save V(l) V(ln) V(p) I(BAC)
TEXT 0 -40 Left 2 ;Inrush limiting: 120 V RMS switched on at the crest (1 ms) into a rectifier and 470 uF; the SL10 (10 ohm cold) holds the first peak near 170 V / 10 ohm
"""
(HERE / "demo_ntc.asc").write_text(DEMO)
print("symbols: ntc, SL10_10003, B57236S0100, B57164K0103; demo_ntc.asc")
