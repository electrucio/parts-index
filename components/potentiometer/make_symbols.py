#!/usr/bin/env python3
"""Write the .asy symbols of potentiometer.sub and a demo schematic.

One geometry for every variant so the webapp can place any pot the same way:
CW end on top (16,16), CCW end at the bottom (16,112), wiper on the right (64,64).
Extra pins: TAP on the left (-16,64) for the tapped pot, CTRL on the left for the
voltage-controlled pots. Dual pots repeat the section 96 units to the right.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

VARIANTS = {
    # name: (taper letter, default value, extra pin)
    "pot_lin": ("B", "R=100k rot=0.5", None),
    "pot_log": ("A", "R=100k rot=0.5 L=0.1", None),
    "pot_revlog": ("C", "R=100k rot=0.5 L=0.1", None),
    "pot_pts": ("P", "R=100k rot=0.5 f10=0.02 f50=0.15 f90=0.6", None),
    "pot_sym": ("S", "R=100k rot=0.5 Lq=0.1", None),
    "pot_log_tap": ("A", "R=1Meg rot=0.5 L=0.1 tap=0.5", "TAP"),
    "pot_lin_vc": ("B", "R=100k", "CTRL"),
    "pot_log_vc": ("A", "R=100k L=0.1", "CTRL"),
    "pot_revlog_vc": ("C", "R=100k L=0.1", "CTRL"),
}
DUALS = {"pot_dual_lin": "B", "pot_dual_log": "A", "pot_dual_revlog": "C"}
DESC = {"B": "linear (B)", "A": "logarithmic (A, audio)", "C": "reverse log (C)",
        "P": "taper from points at 10/50/90 %", "S": "symmetric (S/W family), Lq = f(25 %)"}


def section(dx, letter, suffix=""):
    """Lines of one track + wiper, offset dx; returns (lines, pins)."""
    x = lambda v: v + dx                      # noqa: E731
    lines = [
        f"LINE Normal {x(16)} 16 {x(16)} 24",
        f"LINE Normal {x(16)} 104 {x(16)} 112",
        f"RECTANGLE Normal {x(4)} 24 {x(28)} 104",
        f"LINE Normal {x(64)} 64 {x(30)} 64",
        f"LINE Normal {x(30)} 64 {x(40)} 58",
        f"LINE Normal {x(30)} 64 {x(40)} 70",
        f"TEXT {x(16)} 64 Center 0 {letter}",
        f"TEXT {x(-4)} 20 Right 0 CW",
    ]
    pins = [(x(16), 112, f"CCW{suffix}"), (x(64), 64, f"W{suffix}"), (x(16), 16, f"CW{suffix}")]
    return lines, pins


def asy(name, lines, pins, value, desc, win_x=72):
    out = ["Version 4", "SymbolType CELL"] + lines + [
        f"WINDOW 0 {win_x} 16 Left 2",
        f"WINDOW 3 {win_x} 104 Left 2",
        f"SYMATTR Value {value}",
        "SYMATTR Prefix X",
        f"SYMATTR SpiceModel {name}",
        "SYMATTR ModelFile potentiometer.sub",
        f"SYMATTR Description {desc}",
    ]
    for k, (px, py, pn) in enumerate(pins, 1):
        side = "LEFT" if px < 16 else ("RIGHT" if px > 16 + (px // 96) * 96 else "NONE")
        out += [f"PIN {px} {py} NONE 8", f"PINATTR PinName {pn}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


for name, (letter, value, extra) in VARIANTS.items():
    lines, pins = section(0, letter)
    if extra:
        lines += ["LINE Normal -16 64 4 64", f"TEXT -12 56 Left 0 {extra.lower()}"]
        pins.append((-16, 64, extra))
    kind = DESC[letter] + (", tapped" if extra == "TAP" else "") + \
        (", rotation = V(CTRL) 0..1" if extra == "CTRL" else "")
    asy(name, lines, pins, value, f"Potentiometer, {kind}. Pins CCW W CW"
        + (f" {extra}" if extra else ""))

for name, letter in DUALS.items():
    l1, p1 = section(0, letter, "1")
    l2, p2 = section(96, letter, "2")
    link = ["LINE Normal 48 64 48 136 1", "LINE Normal 48 136 144 136 1",
            "LINE Normal 144 136 144 64 1"]
    value = "R=100k rot=0.5" + ("" if letter == "B" else " L=0.1")
    asy(name, l1 + l2 + link, p1 + p2, value,
        f"Dual-gang potentiometer, {DESC[letter]}, one rotation", win_x=168)

# demo: volume pot after a 1 V source, tone-style dual pot, and a tapped pot
# pot_log placed at (80,48): CW (96,64), W (144,112), CCW (96,160)
DEMO = """Version 4
SHEET 1 1200 500
WIRE 96 64 32 64
WIRE 32 64 32 96
WIRE 96 160 96 208
WIRE 144 112 208 112
FLAG 32 176 0
FLAG 96 208 0
FLAG 208 192 0
FLAG 208 112 vol_out
SYMBOL voltage 32 80 R0
SYMATTR InstName V1
SYMATTR Value 1
SYMBOL pot_log 80 48 R0
SYMATTR InstName XVOL
SYMATTR Value R=500k rot={vol} L=0.1
SYMBOL res 192 96 R0
SYMATTR InstName RL
SYMATTR Value 1Meg
TEXT 32 280 Left 2 !.param vol=0.3\\n.step param vol list 0 0.3 0.5 1\\n.op
"""
(HERE / "demo_potentiometer.asc").write_text(DEMO)
print("symbols:", ", ".join(sorted(list(VARIANTS) + list(DUALS))))
