#!/usr/bin/env python3
"""Write the .asy symbols of ecap.sub and the demo schematic.

Geometry: polarised capacitor (straight + plate, curved - plate), P on top (16,16),
N at the bottom (16,112), + sign next to P.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BODY = [
    "LINE Normal 16 16 16 56", "LINE Normal 16 72 16 112",
    "LINE Normal -8 56 40 56",
    "ARC Normal -16 68 48 132 40 76 -8 76",
    "LINE Normal -4 36 4 36", "LINE Normal 0 32 0 40",
]
PINS = [(16, 16, "P"), (16, 112, "N")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 48 40 Left 2", "WINDOW 3 48 80 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile ecap.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


asy("ecap", "C=47u Vr=450 tand=0.25 Rs=2.47 ESL=20n Ilk=946u kDA=0.03 Temp=20",
    "Aluminium electrolytic capacitor (ESR(f), ESL, leakage, DA). Pins P N")
for p, d in (("UPW1V102MHD", "Nichicon UPW 1000 uF 35 V low-impedance"),
             ("UPW1H471MHD", "Nichicon UPW 470 uF 50 V low-impedance"),
             ("UVR2W470MHD", "Nichicon UVR 47 uF 450 V general purpose"),
             ("381LX101M450H022", "Cornell Dubilier 381LX 100 uF 450 V snap-in"),
             ("381LX471M450A052", "Cornell Dubilier 381LX 470 uF 450 V snap-in")):
    asy(p, "Temp=20", f"{d}. Pins P N")

# demo: valve-amp HT supply, full-wave with a centre-tapped secondary (the two-diode
# circuit of a valve rectifier): 300-0-300 V RMS 60 Hz (50 ohm per half), generic silicon
# diodes, 381LX 100 uF 450 V reservoir, 100 mA load (current sink). Ground-referenced
# sources on purpose (a floating source feeding a bridge makes LTspice crawl).
# Reservoir at (480,96): P (496,112) N (496,208).
DEMO = r"""Version 4
SHEET 1 800 480
FLAG 0 112 s1
FLAG 0 192 0
FLAG 96 112 s1
FLAG 96 192 a1
FLAG 0 272 s2
FLAG 0 352 0
FLAG 96 272 s2
FLAG 96 352 a2
FLAG 224 96 a1
FLAG 224 160 ht
FLAG 224 256 a2
FLAG 224 320 ht
FLAG 496 112 ht
FLAG 496 208 0
FLAG 608 112 ht
FLAG 608 192 0
SYMBOL bv 0 96 R0
SYMATTR InstName B1
SYMATTR Value V=424.3*sin(2*pi*60*time)*min(time/5m, 1)
SYMBOL bv 0 256 R0
SYMATTR InstName B2
SYMATTR Value V=-424.3*sin(2*pi*60*time)*min(time/5m, 1)
SYMBOL res 80 96 R0
SYMATTR InstName R1
SYMATTR Value 50
SYMBOL res 80 256 R0
SYMATTR InstName R2
SYMATTR Value 50
SYMBOL diode 208 96 R0
SYMATTR InstName D1
SYMATTR Value DR
SYMBOL diode 208 256 R0
SYMATTR InstName D2
SYMATTR Value DR
SYMBOL 381LX101M450H022 480 96 R0
SYMATTR InstName XC1
SYMBOL current 608 112 R0
SYMATTR InstName ILOAD
SYMATTR Value 100m
TEXT 0 400 Left 2 !.model DR D(Is=10n N=1.8 Rs=30m Cjo=30p BV=1k IBV=5u)\n.tran 0 0.4 0 20u\n.save V(ht) I(R1) I(R2)
TEXT 0 -40 Left 2 ;Valve-amp HT supply (300-0-300 V, full wave): 381LX 100 uF 450 V reservoir, 100 mA load; ripple below I/(2 f C) = 8.3 V p-p
"""
(HERE / "demo_ecap.asc").write_text(DEMO)
print("symbols: ecap, UPW1V102MHD, UPW1H471MHD, UVR2W470MHD, 381LX101M450H022, "
      "381LX471M450A052; demo_ecap.asc")
