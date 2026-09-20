#!/usr/bin/env python3
"""Write the .asy symbols of relay.sub and the demo schematic.

One geometry for every relay so the webapp can place any of them the same way:
coil on the left (COIL+ on top at (0,16), COIL- at the bottom (0,112)), then one
changeover pole every 128 units to the right: NC on top at (ox,16), NO on top at
(ox+64,16), COM at the bottom (ox+32,112), with ox = 64 + 128*k. The dual-coil
latching relay has its reset coil 64 units left of the set coil. Contacts are drawn
in the de-energised (reset) position, blade on NC, dashed link to the coil.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def coil(x0, pin_p, pin_n, label=""):
    lines = [f"LINE Normal {x0} 16 {x0} 40", f"LINE Normal {x0} 88 {x0} 112",
             f"RECTANGLE Normal {x0 - 16} 40 {x0 + 16} 88",
             f"TEXT {x0 - 4} 28 Right 0 +"]
    if label:
        lines.append(f"TEXT {x0} 64 Center 0 {label}")
    return lines, [(x0, 16, pin_p), (x0, 112, pin_n)]


def pole(k, suffix, nc=True):
    ox = 64 + 128 * k
    lines = [f"LINE Normal {ox + 32} 112 {ox + 32} 88",
             f"CIRCLE Normal {ox + 29} 85 {ox + 35} 91",
             f"LINE Normal {ox + 64} 16 {ox + 64} 40", f"LINE Normal {ox + 64} 40 {ox + 54} 40",
             f"TEXT {ox + 68} 24 Left 0 NO{suffix}", f"TEXT {ox + 38} 104 Left 0 COM{suffix}"]
    pins = [(ox + 32, 112, f"COM{suffix}")]
    if nc:
        lines += [f"LINE Normal {ox + 32} 88 {ox + 8} 44",
                  f"LINE Normal {ox} 16 {ox} 40", f"LINE Normal {ox} 40 {ox + 10} 40",
                  f"TEXT {ox - 4} 24 Right 0 NC{suffix}"]
        pins.append((ox, 16, f"NC{suffix}"))
    else:
        lines.append(f"LINE Normal {ox + 32} 88 {ox + 46} 46")
    pins.append((ox + 64, 16, f"NO{suffix}"))
    return lines, pins, ox


def relay(npoles, nc=True, latch=0):
    """latch: 0 monostable, 1 single-coil latching, 2 dual-coil latching."""
    if latch == 2:
        l1, p1 = coil(-64, "RST+", "RST-", "R")
        l2, p2 = coil(0, "SET+", "SET-", "S")
        lines = l1 + l2 + ["LINE Normal -48 64 -16 64 1"]
        pins = p2 + p1                                  # subckt order: SP SN RP RN
    else:
        lines, pins = coil(0, "COIL+", "COIL-", "L" if latch else "")
    ox = 64
    for k in range(npoles):
        suf = str(k + 1) if npoles > 1 else ""
        pl, pp, ox = pole(k, suf, nc)
        lines += pl
        pins += pp
    lines.append(f"LINE Normal 16 64 {ox + 19} 64 1")
    return lines, pins, ox + 96


def asy(name, geom, value, desc):
    lines, pins, right = geom
    left = -80 if any(p[0] < 0 for p in pins) else -16
    out = ["Version 4", "SymbolType CELL"] + lines + [
        f"WINDOW 0 {right} 32 Left 2",
        f"WINDOW 3 {left} 144 Left 2",
    ]
    if value:
        out.append(f"SYMATTR Value {value}")
    out += ["SYMATTR Prefix X", f"SYMATTR SpiceModel {name}",
            "SYMATTR ModelFile relay.sub", f"SYMATTR Description {desc}"]
    for k, (px, py, pn) in enumerate(pins, 1):
        out += [f"PIN {px} {py} NONE 8", f"PINATTR PinName {pn}", f"PINATTR SpiceOrder {k}"]
    (HERE / f"{name}.asy").write_text("\n".join(out) + "\n")


MONO = "Vnom=12 R=288 pu=0.65 do=0.2 Top=4m Trel=2m Ron=50m pol=0"
GENERIC = {
    "relay_spst": (relay(1, nc=False), MONO, "Relay, SPST-NO (1 Form A). Pins COIL+ COIL- COM NO"),
    "relay_spdt": (relay(1), MONO, "Relay, SPDT (1 Form C). Pins COIL+ COIL- COM NC NO"),
    "relay_dpdt": (relay(2), MONO, "Relay, DPDT (2 Form C). Pins COIL+ COIL- COM1 NC1 NO1 COM2 NC2 NO2"),
    "relay_latch_dpdt": (relay(2, latch=1),
                         "Vnom=5 R=250 pset=0.6 prst=0.6 Top=3m Trel=3m state0=0",
                         "Latching relay, single coil, DPDT: COIL+ > COIL- sets, reversed resets"),
    "relay_latch2_dpdt": (relay(2, latch=2),
                          "Vnom=5 R=125 pset=0.6 prst=0.6 Top=3m Trel=3m state0=0",
                          "Latching relay, dual coil (SET, RST), DPDT"),
}
PRESETS = {
    "TQ2_5V": "Panasonic TQ2-5V signal relay, polarised, 2 Form C, 178 ohm",
    "TQ2_12V": "Panasonic TQ2-12V signal relay, polarised, 2 Form C, 1028 ohm",
    "G5V_2_DC5": "Omron G5V-2 5 VDC signal relay, 2 Form C, 50 ohm",
    "G5V_2_DC12": "Omron G5V-2 12 VDC signal relay, 2 Form C, 288 ohm",
    "G5V_2_DC24": "Omron G5V-2 24 VDC signal relay, 2 Form C, 1152 ohm",
    "G6K_2_DC5": "Omron G6K-2 5 VDC SMD signal relay, polarised, 2 Form C, 237 ohm",
    "G6K_2_DC12": "Omron G6K-2 12 VDC SMD signal relay, polarised, 2 Form C, 1315 ohm",
    "F40_52_12V": "Finder 40.52 12 VDC power relay, 2 CO 8 A, 220 ohm",
    "F40_52_24V": "Finder 40.52 24 VDC power relay, 2 CO 8 A, 900 ohm",
}

for name, (geom, value, desc) in GENERIC.items():
    asy(name, geom, value, desc)
for name, desc in PRESETS.items():
    asy(name, relay(2), "", desc + ". Pins COIL+ COIL- COM1 NC1 NO1 COM2 NC2 NO2")
asy("TQ2_L2_5V", relay(2, latch=2), "state0=0",
    "Panasonic TQ2-L2-5V dual-coil latching relay, 2 Form C, 125 ohm per coil")

# demo: amp channel switch. A footswitch (V2) turns on Q1, which energises a G5V-2
# 12 V relay (flyback diode D1); pole 1 moves the output from the clean to the lead
# signal. Every pin carries a net flag, so the netlist does not depend on wire routing.
# Relay at (400,96): COIL+ (400,112) COIL- (400,208) NC1 (464,112) NO1 (528,112)
# COM1 (496,208) NC2 (592,112) NO2 (656,112) COM2 (624,208).
DEMO = r"""Version 4
SHEET 1 1000 520
FLAG 0 112 vcc
FLAG 0 192 0
FLAG 400 112 vcc
FLAG 400 208 drv
FLAG 464 112 clean
FLAG 528 112 lead
FLAG 496 208 out
FLAG 592 112 nc2
FLAG 656 112 no2
FLAG 624 208 0
FLAG 496 288 0
FLAG 320 208 drv
FLAG 320 144 vcc
FLAG 400 272 drv
FLAG 336 320 base
FLAG 400 368 0
FLAG 240 320 base
FLAG 240 400 fs
FLAG 96 320 fs
FLAG 96 400 0
FLAG 720 112 clean
FLAG 720 192 0
FLAG 816 112 lead
FLAG 816 192 0
SYMBOL voltage 0 96 R0
SYMATTR InstName V1
SYMATTR Value 12
SYMBOL G5V_2_DC12 400 96 R0
SYMATTR InstName XK1
SYMBOL res 480 192 R0
SYMATTR InstName RL
SYMATTR Value 100k
SYMBOL diode 336 208 R180
SYMATTR InstName D1
SYMATTR Value 1N4148
SYMBOL npn 336 272 R0
SYMATTR InstName Q1
SYMATTR Value 2N3904
SYMBOL res 224 304 R0
SYMATTR InstName RB
SYMATTR Value 4.7k
SYMBOL voltage 96 304 R0
SYMATTR InstName V2
SYMATTR Value PULSE(0 5 10m 1u 1u 30m 100m)
SYMBOL voltage 720 96 R0
SYMATTR InstName V3
SYMATTR Value SINE(0 0.5 1k)
SYMBOL voltage 816 96 R0
SYMATTR InstName V4
SYMATTR Value SINE(0 0.5 3k)
TEXT 0 456 Left 2 !.model 1N4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n)\n.model 2N3904 NPN(IS=1E-14 VAF=100 BF=300 IKF=0.4 XTB=1.5 BR=4 CJC=4E-12 CJE=8E-12 RB=20 RC=0.1 RE=0.1 TR=250E-9 TF=350E-12 ITF=1 VTF=2 XTF=3)\n.tran 0 60m 0 5u
TEXT 0 -40 Left 2 ;Channel switch: V2 (footswitch) at 10 ms energises K1, OUT moves from CLEAN (1 kHz) to LEAD (3 kHz);\nat 40 ms it releases, later than it operated because D1 keeps the coil current up
"""
(HERE / "demo_relay.asc").write_text(DEMO)
print("symbols:", ", ".join(sorted(list(GENERIC) + list(PRESETS) + ["TQ2_L2_5V"])))
