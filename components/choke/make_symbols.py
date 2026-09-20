#!/usr/bin/env python3
"""Write the .asy symbols of choke.sub (the generic choke and every preset) and the
demo schematic. One geometry: A on top (16,16), B at the bottom (16,112), the coil
between them bulging right, two core bars on the right."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

SYMS = {
    "choke": ("L=5 Idc=0.2 S=1.3 Rdc=65", "Filter choke, inductance falling with DC current. Pins A B"),
    "CH_159R": ("S=1.3", "Hammond 159R choke 6 H @ 200 mA, 150 ohm"),
    "CH_159S": ("S=1.3", "Hammond 159S choke 4 H @ 225 mA, 60.6 ohm"),
    "CH_159T": ("S=1.3", "Hammond 159T choke 2.5 H @ 300 mA, 40.17 ohm"),
    "CH_159V": ("S=1.3", "Hammond 159V choke 1.5 H @ 500 mA, 27 ohm"),
    "CH_159ZJ": ("S=1.3", "Hammond 159ZJ choke 10 mH @ 5 A, 0.16 ohm"),
    "CH_193H": ("S=1.3", "Hammond 193H choke 5 H @ 200 mA, 65 ohm"),
    "CH_193J": ("S=1.3", "Hammond 193J choke 10 H @ 200 mA, 79 ohm"),
    "CH_193M": ("S=1.3", "Hammond 193M choke 10 H @ 300 mA, 63 ohm"),
}


def write_asy(name, value, desc):
    L = []
    for y in range(16, 112, 16):       # bumps bulging right (counter-clockwise bottom->top)
        L.append(f"ARC Normal 8 {y} 24 {y + 16} 16 {y + 16} 16 {y}")
    L += ["LINE Normal 36 16 36 112", "LINE Normal 42 16 42 112"]
    out = ["Version 4", "SymbolType CELL"] + L + [
        "WINDOW 0 52 40 Left 2",
        "WINDOW 3 52 88 Left 2",
        f"SYMATTR Value {value}",
        "SYMATTR Prefix X",
        f"SYMATTR SpiceModel {name}",
        "SYMATTR ModelFile choke.sub",
        f"SYMATTR Description {desc}",
        "PIN 16 16 NONE 8", "PINATTR PinName A", "PINATTR SpiceOrder 1",
        "PIN 16 112 NONE 8", "PINATTR PinName B", "PINATTR SpiceOrder 2",
    ]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


# Demo: choke-input filter. Ideal 350-0-350 V 60 Hz (two sources), full-wave CT
# rectifier (generic diode DREC), CH_193H, 40 uF, 1.5k load (~200 mA).
# CH_193H at (432,96) rotated R270 is awkward; keep it vertical: A (448,112), B (448,208)?
# Simpler: horizontal via R270: pins (x,y)->(y,-x): A (16,16)->(16,-16), B (16,112)->(112,-16)
# placed at (400,128): A at (416,112), B at (512,112).
DEMO = """Version 4
SHEET 1 1000 460
WIRE 96 112 176 112
WIRE 240 112 336 112
WIRE 96 288 176 288
WIRE 240 288 336 288
WIRE 336 112 336 288
WIRE 336 112 416 112
WIRE 512 112 592 112
WIRE 592 112 592 144
WIRE 592 112 688 112
FLAG 96 192 0
FLAG 96 208 0
FLAG 592 208 0
FLAG 688 192 0
FLAG 592 112 out
SYMBOL voltage 96 96 R0
SYMATTR InstName V1
SYMATTR Value SINE(0 495 60)
SYMBOL voltage 96 304 R180
SYMATTR InstName V2
SYMATTR Value SINE(0 -495 60)
SYMBOL diode 176 128 R270
SYMATTR InstName D1
SYMATTR Value DREC
SYMBOL diode 176 304 R270
SYMATTR InstName D2
SYMATTR Value DREC
SYMBOL CH_193H 400 128 R270
SYMATTR InstName XL1
SYMATTR Value S=1.3
SYMBOL cap 576 144 R0
SYMATTR InstName C1
SYMATTR Value 40u
SYMBOL res 672 96 R0
SYMATTR InstName RL
SYMATTR Value 1.5k
TEXT 64 376 Left 2 !.model DREC D(Is=10n Rs=0.05 N=1.8 Cjo=20p Bv=1000 Ibv=5u)
TEXT 64 408 Left 2 !.tran 0 2 1.5 20u
TEXT 64 440 Left 2 ;choke-input filter: 350-0-350 V 60 Hz, full-wave, Hammond 193H (5 H @ 200 mA), 40 uF, 1.5k
"""


def main():
    for name, (value, desc) in SYMS.items():
        write_asy(name, value, desc)
    (HERE / "demo_choke.asc").write_text(DEMO)
    print("symbols:", ", ".join(SYMS))


if __name__ == "__main__":
    main()
