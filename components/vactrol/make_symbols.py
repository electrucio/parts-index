#!/usr/bin/env python3
"""Write the .asy symbols of vactrol.sub and the demo schematic, and copy the
ldr_cell core from ../ldr/ldr.sub into vactrol.sub (the maths lives in ldr.sub; the
copy keeps vactrol.sub self-contained for LTspice's ModelFile).

Geometry: LED on the left (A on top (0,16), K at the bottom (0,112)), cell on the
right (C1 (96,16), C2 (96,112)), light arrows between them, dashed package outline.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEGIN, END = "* >>> ldr_cell", "* <<< ldr_cell"


def sync_core():
    src = (HERE.parent / "ldr" / "ldr.sub").read_text()
    dst_p = HERE / "vactrol.sub"
    dst = dst_p.read_text()
    block = src[src.index(BEGIN):src.index(END) + len(END)]
    new = dst[:dst.index(BEGIN)] + block + dst[dst.index(END) + len(END):]
    if new != dst:
        dst_p.write_text(new)
        return "updated"
    return "already identical"


BODY = [
    # LED
    "LINE Normal 0 16 0 48", "LINE Normal 0 72 0 112",
    "LINE Normal -16 48 16 48", "LINE Normal -16 48 0 72", "LINE Normal 16 48 0 72",
    "LINE Normal -16 72 16 72",
    # light
    "LINE Normal 24 52 60 52", "LINE Normal 60 52 52 48", "LINE Normal 60 52 52 56",
    "LINE Normal 24 68 60 68", "LINE Normal 60 68 52 64", "LINE Normal 60 68 52 72",
    # cell
    "LINE Normal 96 16 96 32", "LINE Normal 96 96 96 112",
    "RECTANGLE Normal 84 32 108 96",
    # package
    "RECTANGLE Normal -32 24 124 104 1",
    "TEXT -4 24 Right 0 A", "TEXT -4 108 Right 0 K",
]
PINS = [(0, 16, "A"), (0, 112, "K"), (96, 16, "C1"), (96, 112, "C2")]


def asy(name, value, desc):
    out = ["Version 4", "SymbolType CELL"] + BODY + [
        "WINDOW 0 136 32 Left 2", "WINDOW 3 136 96 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile vactrol.sub", f"SYMATTR Description {desc}"]
    for k, (x, y, n) in enumerate(PINS, 1):
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {n}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


print("ldr_cell core:", sync_core())
asy("vactrol", "Rref=19.85k gamma=0.8299 m=1.987 Rs=154.7 tau=3.896m ka=0.1394 hist=0",
    "LED/LDR optocoupler (vactrol). Pins A K C1 C2")
for p, d in (("VTL5C1", "PerkinElmer VTL5C1 (type 1: fast, large memory)"),
             ("VTL5C3", "PerkinElmer VTL5C3 (type 3: slow decay, small memory)"),
             ("VTL5C4", "PerkinElmer VTL5C4 (type 4: low on-resistance, long decay)"),
             ("VTL5C6", "Xvive VTL5C6"),
             ("NSL32SR2", "Silonex NSL-32SR2 (lowest on-resistance)")):
    asy(p, "hist=0", f"{d} vactrol. Pins A K C1 C2")

# demo: optical tremolo. 5 Hz LFO (0..5 V) through 220 ohm into the LED of a VTL5C3;
# its cell shunts a 440 Hz signal after 22k. VTL5C3 at (400,96): A (400,112) K (400,208)
# C1 (496,112) C2 (496,208)
DEMO = r"""Version 4
SHEET 1 900 400
FLAG 0 112 lfo
FLAG 0 192 0
FLAG 96 112 lfo
FLAG 96 192 led
FLAG 400 112 led
FLAG 400 208 0
FLAG 496 112 out
FLAG 496 208 0
FLAG 592 112 in
FLAG 592 192 0
FLAG 688 112 in
FLAG 688 192 out
FLAG 784 112 out
FLAG 784 192 0
SYMBOL voltage 0 96 R0
SYMATTR InstName VLFO
SYMATTR Value SINE(2.5 2.5 5)
SYMBOL res 80 96 R0
SYMATTR InstName RLED
SYMATTR Value 220
SYMBOL VTL5C3 400 96 R0
SYMATTR InstName XOPTO
SYMBOL voltage 592 96 R0
SYMATTR InstName VIN
SYMATTR Value SINE(0 0.5 440)
SYMBOL res 672 96 R0
SYMATTR InstName R1
SYMATTR Value 22k
SYMBOL res 768 96 R0
SYMATTR InstName RL
SYMATTR Value 1Meg
TEXT 0 272 Left 2 !.tran 0 1 0 20u
TEXT 0 -40 Left 2 ;Optical tremolo: a 5 Hz LFO lights the LED; the cell shunts the 440 Hz signal after 22k
"""
(HERE / "demo_vactrol.asc").write_text(DEMO)
print("symbols: vactrol, VTL5C1, VTL5C3, VTL5C4, VTL5C6, NSL32SR2")
