#!/usr/bin/env python3
"""Write the .asy symbols of lamp.sub and the demo schematic.

Geometry: filament lamp (circle with a cross), A on top (16,16), B at the bottom
(16,112), like the LDR, so either can replace a resistor drawn vertically.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "LINE Normal 16 16 16 40", "LINE Normal 16 88 16 112",
    "CIRCLE Normal -8 40 40 88",
    "LINE Normal -1 47 33 81", "LINE Normal 33 47 -1 81",
]
PINS = [(16, 16, "A"), (16, 112, "B")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 48 40 Left 2", "WINDOW 3 48 88 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile lamp.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("lamp", "Vr=28 Ir=40m Rc=65 fc=0.0166 Ta=25 kC=1",
    "Incandescent lamp (tungsten filament, electro-thermal). Pins A B")
for p, d in (("LAMP_327", "#327 lamp, 28 V 40 mA (Wien-bridge stabiliser)"),
             ("LAMP_47", "#47 pilot lamp, 6.3 V 150 mA"),
             ("LAMP_12V40", "12 V 40 mA grain-of-wheat lamp"),
             ("LAMP_6V60", "6 V 60 mA lamp (sound-au project 179)")):
    asy(p, "T0=0", f"{d}. Pins A B")

# demo: lamp-stabilised Wien-bridge oscillator (R. Elliott's 375 ohm case).
# The op-amp is behavioural: BA = 1e5 (V(p)-V(n)), a 10 Hz pole (1k, 15.9u), BO a
# +-13 V buffer. Wien network 1.6k/100n (995 Hz). Lamp at (400,96): A (416,112) B (416,208).
DEMO = r"""Version 4
SHEET 1 1100 520
FLAG 0 112 x1
FLAG 0 192 0
FLAG 96 112 x1
FLAG 96 192 x
FLAG 192 112 x
FLAG 192 176 0
FLAG 288 112 out
FLAG 288 192 0
FLAG 416 112 n
FLAG 416 208 0
FLAG 512 112 out
FLAG 512 192 n
FLAG 608 112 out
FLAG 608 192 w
FLAG 704 112 w
FLAG 704 176 p
FLAG 800 112 p
FLAG 800 192 0
FLAG 896 112 p
FLAG 896 176 0
SYMBOL bv 0 96 R0
SYMATTR InstName BA
SYMATTR Value V=limit(1e5*(V(p)-V(n)), -1k, 1k)
SYMBOL res 80 96 R0
SYMATTR InstName RP
SYMATTR Value 1k
SYMBOL cap 176 112 R0
SYMATTR InstName CP
SYMATTR Value 15.9u
SYMBOL bv 288 96 R0
SYMATTR InstName BO
SYMATTR Value V=V(x)/(1 + (V(x)/13)**8)**0.125
SYMBOL LAMP_327 400 96 R0
SYMATTR InstName XL1
SYMATTR Value T0=700
SYMBOL res 496 96 R0
SYMATTR InstName RF
SYMATTR Value 375
SYMBOL res 592 96 R0
SYMATTR InstName R1
SYMATTR Value 1.6k
SYMBOL cap 688 112 R0
SYMATTR InstName C1
SYMATTR Value 470n
SYMBOL res 784 96 R0
SYMATTR InstName R2
SYMATTR Value 1.6k
SYMBOL cap 880 112 R0
SYMATTR InstName C2
SYMATTR Value 470n
TEXT 0 272 Left 2 !.tran 0 6 0 100u\n.ic V(p)=2\n.save V(out) V(n)
TEXT 0 -40 Left 2 ;Lamp-stabilised Wien-bridge oscillator, 212 Hz, started with a warm lamp (T0) and 2 V on the Wien network: the #327 settles where its resistance is RF/2 (sound-au sinewave 4.2: 1.39 V on the lamp, 4.16 V RMS out)
"""
(HERE / "demo_lamp.asc").write_text(DEMO)
print("symbols: lamp, LAMP_327, LAMP_47, LAMP_12V40, LAMP_6V60; demo_lamp.asc")
