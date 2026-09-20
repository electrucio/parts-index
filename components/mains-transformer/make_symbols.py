#!/usr/bin/env python3
"""Write the .asy symbols of mains-transformer.sub and the demo schematic.

Geometry: primary on the left (P1 top (0,16), P2 (0,112)); secondaries stacked on the
right at x=160, top to bottom in pin order; dots on the in-phase ends (P1, HV1, H1,
A1, SA1, SB1, S1). Every winding has its own coil; the tube symbols draw the HV, heater
and auxiliary windings as separate coils.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

# pin -> (y, shown name); primary pins at x=0, others at x=160
LAYOUTS = {
    "tube": [("P1", 16), ("P2", 112), ("HV1", 16), ("BIAS", 48), ("HVCT", 80), ("HV2", 144),
             ("H1", 176), ("HCT", 208), ("H2", 240)],
    "tube_nobias": [("P1", 16), ("P2", 112), ("HV1", 16), ("HVCT", 80), ("HV2", 144),
                    ("H1", 176), ("HCT", 208), ("H2", 240), ("A1", 272), ("A2", 304)],
    "tube_aux": [("P1", 16), ("P2", 112), ("HV1", 16), ("BIAS", 48), ("HVCT", 80), ("HV2", 144),
                 ("H1", 176), ("HCT", 208), ("H2", 240), ("A1", 272), ("A2", 304)],
    "ss": [("P1", 16), ("P2", 112), ("SA1", 16), ("SA2", 64), ("SB1", 96), ("SB2", 144)],
    "ss_ct": [("P1", 16), ("P2", 112), ("S1", 16), ("SCT", 80), ("S2", 144)],
}
# coils on the secondary side: (y0, y1, dotted)
SEC_COILS = {
    "tube": [(16, 144), (176, 240)], "tube_nobias": [(16, 144), (176, 240), (272, 304)],
    "tube_aux": [(16, 144), (176, 240), (272, 304)], "ss": [(16, 64), (96, 144)],
    "ss_ct": [(16, 144)],
}

SYMS = {
    # name: (layout, value, description)
    "pt_tube": ("tube", "Vp=120 Vhv=600 Ihv=0.1 Vb=50 Vh=6.8 Ih=3 Iex=0.1 reg=0.08",
                "Tube amp power transformer: HV CT + bias tap + heater CT. Pins P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2"),
    "pt_tube_aux": ("tube_aux", "Vp=120 Vhv=600 Ihv=0.1 Vb=50 Vh=6.8 Ih=3 Va=5.3 Ia=3 Iex=0.1 reg=0.08",
                    "Tube amp power transformer + auxiliary winding. Pins P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2 A1 A2"),
    "pt_ss": ("ss", "Vp=230 fline=50 Vs=19.4 Is=4.44 Iex=20m reg=0.08",
              "Solid-state power transformer, two secondaries. Pins P1 P2 SA1 SA2 SB1 SB2"),
    "pt_ss_ct": ("ss_ct", "Vp=230 fline=50 Vs=19.4 Is=4.44 Iex=20m reg=0.08",
                 "Solid-state power transformer, centre-tapped secondary. Pins P1 P2 S1 SCT S2"),
    "PT_370AX": ("tube", "pri=1", "Hammond 370AX 480VCT 58mA, 50V bias, 6.3VCT 2.5A (pri=2: 240 V)"),
    "PT_370CX": ("tube_aux", "pri=1", "Hammond 370CX 550VCT 75mA, 50V bias, 6.3VCT 2.5A, aux 6.3VCT 0.6A"),
    "PT_370FX": ("tube_aux", "pri=1", "Hammond 370FX 550VCT 173mA, 50V bias, 6.3VCT 5A, aux 5VCT 3A"),
    "PT_290AX": ("tube_nobias", "sat=1", "Hammond 290AX (Fender Champ/Princeton) 650VCT 100mA, 6.3VCT 2.25A, 5V 3A; 120 V 60 Hz"),
    "PT_290EX": ("tube", "sat=1", "Hammond 290EX (Fender Bassman AB165/Bandmaster) 660VCT 275mA, 53V bias, 6.4VCT 4A; 120 V 60 Hz"),
    "PT_1182N18": ("ss", "pri=1", "Hammond 1182N18 toroid 2x18V 4.44A 160VA (pri=2: 234 V)"),
    "PT_1182N18_CT": ("ss_ct", "pri=1", "Hammond 1182N18 toroid, secondaries in series (18-0-18 V)"),
}


def coil(x, y0, y1, right):
    out = []
    for y in range(y0, y1, 16):
        if right:
            out.append(f"ARC Normal {x - 8} {y} {x + 8} {y + 16} {x} {y + 16} {x} {y}")
        else:
            out.append(f"ARC Normal {x - 8} {y} {x + 8} {y + 16} {x} {y} {x} {y + 16}")
    return out


def write_asy(name, layout, value, desc):
    pins = LAYOUTS[layout]
    ymax = max(y for _, y in pins)
    L = coil(48, 16, 112, right=True)
    for y0, y1 in SEC_COILS[layout]:
        L += coil(112, y0, y1, right=False)
        L.append(f"CIRCLE Normal 100 {y0 + 2} 106 {y0 + 8}")
    L += [f"LINE Normal 76 8 76 {ymax + 8}", f"LINE Normal 84 8 84 {ymax + 8}",
          "CIRCLE Normal 54 18 60 24"]
    for pn, y in pins:
        if pn in ("P1", "P2"):
            L += [f"LINE Normal 0 {y} 48 {y}", f"TEXT 4 {y - 8} Left 0 {pn}"]
        else:
            L += [f"LINE Normal 112 {y} 160 {y}", f"TEXT 156 {y - 8} Right 0 {pn}"]
    out = ["Version 4", "SymbolType CELL"] + L + [
        "WINDOW 0 80 -8 Center 2",
        f"WINDOW 3 80 {ymax + 40} Center 2",
        f"SYMATTR Value {value}",
        "SYMATTR Prefix X",
        f"SYMATTR SpiceModel {name}",
        "SYMATTR ModelFile mains-transformer.sub",
        f"SYMATTR Description {desc}",
    ]
    for k, (pn, y) in enumerate(pins, 1):
        x = 0 if pn in ("P1", "P2") else 160
        out += [f"PIN {x} {y} NONE 8", f"PINATTR PinName {pn}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


# Demo: 370FX on 120 V 60 Hz (soft start), full-wave CT rectifier into 47 uF and a
# 2.2 k load (~170 mA), heater loaded with 1.26 ohm (5 A), bias tap into 100k.
# PT_370FX at (320,96): P1 (320,112) P2 (320,208) HV1 (480,112) BIAS (480,144)
# HVCT (480,176) HV2 (480,240) H1 (480,272) HCT (480,304) H2 (480,336) A1 (480,368) A2 (480,400)
DEMO = """Version 4
SHEET 1 1200 560
WIRE 208 112 320 112
WIRE 208 208 320 208
WIRE 480 112 576 112
WIRE 480 240 576 240
WIRE 640 112 704 112
WIRE 640 240 704 240
WIRE 704 112 704 240
WIRE 704 112 800 112
WIRE 800 112 800 144
WIRE 800 112 896 112
WIRE 480 272 544 272
WIRE 480 336 480 352
WIRE 480 352 544 352
WIRE 480 144 544 144
WIRE 208 192 208 208
FLAG 208 208 0
FLAG 480 176 0
FLAG 800 208 0
FLAG 896 192 0
FLAG 480 304 0
FLAG 544 224 0
FLAG 800 112 bplus
FLAG 544 144 bias
SYMBOL bv 208 96 R0
SYMATTR InstName B1
SYMATTR Value V=120*sqrt(2)*sin(2*pi*60*time)*min(time/50m,1)
SYMBOL PT_370FX 320 96 R0
SYMATTR InstName XPT
SYMATTR Value pri=1
SYMBOL diode 576 128 R270
SYMATTR InstName D1
SYMATTR Value DREC
SYMBOL diode 576 256 R270
SYMATTR InstName D2
SYMATTR Value DREC
SYMBOL cap 784 144 R0
SYMATTR InstName C1
SYMATTR Value 47u
SYMBOL res 880 96 R0
SYMATTR InstName RL
SYMATTR Value 2.2k
SYMBOL res 528 128 R0
SYMATTR InstName RB
SYMATTR Value 100k
SYMBOL res 528 256 R0
SYMATTR InstName RH
SYMATTR Value 1.26
TEXT 176 456 Left 2 !.model DREC D(Is=10n Rs=0.05 N=1.8 Cjo=20p Bv=1000 Ibv=5u)
TEXT 176 488 Left 2 !.tran 0 1 0.5 20u
TEXT 176 520 Left 2 ;Hammond 370FX: full-wave CT rectifier, 47 uF, ~170 mA load; heater 5 A; bias tap into 100k
"""


def main():
    for name, (layout, value, desc) in SYMS.items():
        write_asy(name, layout, value, desc)
    (HERE / "demo_mains-transformer.asc").write_text(DEMO)
    print("symbols:", ", ".join(SYMS))


if __name__ == "__main__":
    main()
