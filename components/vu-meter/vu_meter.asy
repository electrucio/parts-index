Version 4
SymbolType CELL
RECTANGLE Normal 16 16 112 112
ARC Normal 24 40 104 120 100 72 28 72
LINE Normal 64 96 88 56
TEXT 64 100 Center 0 VU
LINE Normal 0 16 16 16
LINE Normal 0 112 16 112
LINE Normal 112 64 128 64
TEXT 20 24 Left 0 +
WINDOW 0 16 0 Left 2
WINDOW 3 16 136 Left 2
SYMATTR Value Vref=1.228 Rin=7.5k fn=2.1505 zeta=0.8127
SYMATTR Prefix X
SYMATTR SpiceModel vu_meter
SYMATTR ModelFile vu.sub
SYMATTR Description VU meter (IEC 60268-17 ballistics, full-wave rectifier). Pins P N DEFL (1 = 0 VU)
PIN 0 16 NONE 8
PINATTR PinName P
PINATTR SpiceOrder 1
PIN 0 112 NONE 8
PINATTR PinName N
PINATTR SpiceOrder 2
PIN 128 64 NONE 8
PINATTR PinName DEFL
PINATTR SpiceOrder 3
