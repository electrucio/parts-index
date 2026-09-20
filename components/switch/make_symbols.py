#!/usr/bin/env python3
"""Write the .asy symbols of switch.sub and the true-bypass demo schematic.

Changeover poles share one geometry (the relay's): throw 1 on top at (ox,16), throw 2
on top at (ox+64,16), common at the bottom (ox+32,112); poles every 96 units,
ox = 96*k. Blades are drawn in position 0 (on-off-on: centre). The CTRL pin of the
_vc variants is at (-32,64). Rotary: P1..PN on top every 32 units, COM at the bottom
middle. Jacks: plug side on the left (PT, PR, PS), jack lugs on the right.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pole(k, names, blade="t1"):
    """names = (throw1, common, throw2); blade: t1, ctr or open (spst)."""
    ox = 96 * k
    t1, com, t2 = names
    lines = [f"LINE Normal {ox + 32} 112 {ox + 32} 88",
             f"CIRCLE Normal {ox + 29} 85 {ox + 35} 91",
             f"LINE Normal {ox + 64} 16 {ox + 64} 40", f"LINE Normal {ox + 64} 40 {ox + 54} 40",
             f"TEXT {ox + 68} 24 Left 0 {t2}", f"TEXT {ox + 38} 104 Left 0 {com}"]
    pins = []
    if t1:
        lines += [f"LINE Normal {ox} 16 {ox} 40", f"LINE Normal {ox} 40 {ox + 10} 40",
                  f"TEXT {ox - 4} 24 Right 0 {t1}"]
    end = {"t1": (ox + 8, 44), "ctr": (ox + 32, 44), "open": (ox + 46, 46)}[blade]
    lines.append(f"LINE Normal {ox + 32} 88 {end[0]} {end[1]}")
    if t1:
        pins.append((ox, 16, t1))
    pins.append((ox + 32, 112, com))
    pins.append((ox + 64, 16, t2))
    return lines, pins, ox


def changeover(npoles, blade="t1", ctrl=False, foot=False):
    lines, pins = [], []
    labels = ["A", "B", "C"]
    for k in range(npoles):
        L = labels[k] if npoles > 1 else ""
        names = (f"{L}1", f"{L}C", f"{L}2") if npoles > 1 else ("T1", "COM", "T2")
        pl, pp, ox = pole(k, names, blade)
        lines += pl
        pins += pp
    right = 96 * (npoles - 1) + 64
    if npoles > 1 or ctrl or foot:
        lines.append(f"LINE Normal {-16 if ctrl else 20} 64 {96 * (npoles - 1) + 20} 64 1")
    if foot:   # push-button actuator on the link
        x = 96 * (npoles - 1) + 20
        lines += [f"LINE Normal {x} 64 {x + 28} 64 1", f"LINE Normal {x + 28} 48 {x + 28} 80",
                  f"LINE Normal {x + 28} 64 {x + 40} 64"]
        right += 16
    if blade == "ctr":
        lines.append(f"TEXT {right // 2} 136 Center 0 on-off-on")
    if ctrl:
        lines += ["LINE Normal -32 64 -16 64", "TEXT -28 56 Left 0 ctrl"]
        pins.append((-32, 64, "CTRL"))
    return lines, pins, right + 32


def spst():
    lines, pins, _ = pole(0, (None, "B", "A"), "open")
    # pin order A B
    return lines, [pins[1], pins[0]], 96


def rotary(n):
    lines, pins = [], []
    xc = 16 * (n - 1)
    for k in range(n):
        x = 32 * k
        lines += [f"LINE Normal {x} 16 {x} 36", f"CIRCLE Normal {x - 3} 36 {x + 3} 42",
                  f"TEXT {x} 8 Center 0 {k + 1}"]
    pins.append((xc, 112, "COM"))
    for k in range(n):
        pins.append((32 * k, 16, f"P{k + 1}"))
    lines += [f"LINE Normal {xc} 112 {xc} 88", f"CIRCLE Normal {xc - 3} 85 {xc + 3} 91",
              f"LINE Normal {xc} 88 2 44", f"LINE Normal 2 44 8 50", f"LINE Normal 2 44 10 44",
              f"TEXT {xc + 8} 104 Left 0 COM"]
    return lines, pins, 32 * (n - 1) + 32


def jack(trs):
    lines = ["RECTANGLE Normal 16 16 80 112",
             # sleeve: plug sleeve to jack sleeve
             "LINE Normal 0 96 16 96", "LINE Normal 80 96 96 96", "LINE Normal 16 96 80 96 2",
             # tip spring with its contact point
             "LINE Normal 0 32 16 32", "LINE Normal 80 32 96 32",
             "LINE Normal 16 32 40 32 2", "LINE Normal 40 32 48 40", "LINE Normal 48 40 56 32",
             "LINE Normal 56 32 80 32",
             "TEXT -4 24 Right 0 PT", "TEXT -4 104 Right 0 PS", "TEXT 100 24 Left 0 T",
             "TEXT 100 104 Left 0 S"]
    if trs:
        lines += ["LINE Normal 0 64 16 64", "LINE Normal 80 64 96 64", "LINE Normal 16 64 80 64 2",
                  "TEXT -4 56 Right 0 PR", "TEXT 100 56 Left 0 R"]
        pins = [(96, 32, "T"), (96, 64, "R"), (96, 96, "S"), (0, 32, "PT"), (0, 64, "PR"),
                (0, 96, "PS")]
    else:
        # tip normal: contact under the tip spring
        lines += ["LINE Normal 80 64 96 64", "LINE Normal 48 64 80 64", "LINE Normal 48 64 48 44",
                  "TEXT 100 56 Left 0 TN"]
        pins = [(96, 32, "T"), (96, 96, "S"), (96, 64, "TN"), (0, 32, "PT"), (0, 96, "PS")]
    return lines, pins, 128


def asy(name, geom, value, desc):
    lines, pins, right = geom
    out = ["Version 4", "SymbolType CELL"] + lines + [
        f"WINDOW 0 {right} 32 Left 2", f"WINDOW 3 {right} 96 Left 2"]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile switch.sub", f"SYMATTR Description {desc}"]
    for k, (px, py, pn) in enumerate(pins, 1):
        out += [f"PIN {px} {py} NONE 8", f"PINATTR PinName {pn}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


SYMS = {
    "sw_spst": (spst(), "pos=1", "Switch SPST, pos 0 open / 1 closed. Pins A B"),
    "sw_spdt": (changeover(1), "pos=0", "Switch SPDT (toggle), pos 0 COM-T1 / 1 COM-T2. Pins T1 COM T2"),
    "sw_dpdt": (changeover(2), "pos=0", "Switch DPDT, pos 0 x1 / 1 x2. Pins A1 AC A2 B1 BC B2"),
    "sw_3pdt": (changeover(3, foot=True), "pos=0",
                "3PDT latching footswitch, lugs 1..9 (2 5 8 common), pos 0 / 1"),
    "sw_spdt_ctr": (changeover(1, "ctr"), "pos=1", "Switch SPDT on-off-on, pos 0 T1 / 1 off / 2 T2"),
    "sw_dpdt_ctr": (changeover(2, "ctr"), "pos=1", "Switch DPDT on-off-on, pos 0 / 1 off / 2"),
    "sw_spdt_vc": (changeover(1, ctrl=True), "Ron=10m", "Switch SPDT, position = V(CTRL) 0..1"),
    "sw_dpdt_vc": (changeover(2, ctrl=True), "Ron=10m", "Switch DPDT, position = V(CTRL) 0..1"),
    "sw_3pdt_vc": (changeover(3, ctrl=True, foot=True), "Ron=30m",
                   "3PDT footswitch, position = V(CTRL) 0..1"),
    "jack_mono_sw": (jack(False), "plug=1", "Switched mono jack (tip normal TN), plug 0/1"),
    "jack_trs": (jack(True), "plug=1", "Stereo jack; plug 0 none, 1 mono (shorts R-S), 2 stereo"),
}
for n in (3, 4, 6, 12):
    SYMS[f"sw_rot1p{n}"] = (rotary(n), "pos=1", f"Rotary switch 1 pole {n} positions, pos 1..{n}")

for name, (geom, value, desc) in SYMS.items():
    asy(name, geom, value, desc)

# demo: 3PDT true bypass with LED. pos=0 bypass (2-1: IN straight to OUT through the
# link lugs 1 and 4), stomp at 20 ms -> pos=1: IN to the effect input, effect output
# to OUT, lug 9 grounds the LED cathode. The effect is a gain-of-2 stage biased at
# 4.5 V with a 100n output cap and a 1Meg pull-down (no pop on engage).
# 3PDT at (400,96): A1 (400,112) AC (432,208) A2 (464,112) B1 (496,112) BC (528,208)
# B2 (560,112) C1 (592,112) CC (624,208) C2 (656,112)
DEMO = r"""Version 4
SHEET 1 1300 480
FLAG 0 112 in
FLAG 0 192 0
FLAG 96 112 v9
FLAG 96 192 0
FLAG 192 112 v9
FLAG 192 192 led_a
FLAG 192 224 led_a
FLAG 192 288 led_k
FLAG 400 112 byp
FLAG 432 208 in
FLAG 464 112 fx_in
FLAG 496 112 byp
FLAG 528 208 out
FLAG 560 112 fx_out
FLAG 592 112 c1
FLAG 624 208 led_k
FLAG 656 112 0
FLAG 800 112 fxb
FLAG 800 192 0
FLAG 896 96 fxb
FLAG 896 160 fx_out
FLAG 976 112 fx_out
FLAG 976 192 0
FLAG 1056 112 fx_in
FLAG 1056 192 0
FLAG 1136 112 out
FLAG 1136 192 0
SYMBOL voltage 0 96 R0
SYMATTR InstName V1
SYMATTR Value SINE(0 0.2 440)
SYMBOL voltage 96 96 R0
SYMATTR InstName V9
SYMATTR Value 9
SYMBOL res 176 96 R0
SYMATTR InstName RLED
SYMATTR Value 4.7k
SYMBOL LED 176 224 R0
SYMATTR InstName D1
SYMATTR Value LEDR
SYMBOL sw_3pdt 400 96 R0
SYMATTR InstName XFS
SYMATTR Value pos=0 tsw=20m
SYMBOL bv 800 96 R0
SYMATTR InstName BFX
SYMATTR Value V=4.5+2*V(fx_in)
SYMBOL cap 880 96 R0
SYMATTR InstName COUT
SYMATTR Value 100n
SYMBOL res 960 96 R0
SYMATTR InstName RPD
SYMATTR Value 1Meg
SYMBOL res 1040 96 R0
SYMATTR InstName RIN
SYMATTR Value 1Meg
SYMBOL res 1120 96 R0
SYMATTR InstName RL
SYMATTR Value 1Meg
TEXT 0 344 Left 2 !.model LEDR D(Is=3e-20 N=1.8 Rs=5)\n.tran 0 60m 0 10u
TEXT 0 -40 Left 2 ;3PDT true bypass: bypassed until the stomp at 20 ms (lugs 2-1, 5-4 link IN to OUT), then IN -> effect -> OUT and lug 9 lights the LED
"""
(HERE / "demo_switch.asc").write_text(DEMO)
print("symbols:", ", ".join(sorted(SYMS)))
